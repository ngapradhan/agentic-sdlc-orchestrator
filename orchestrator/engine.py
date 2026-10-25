"""Three-node bootstrap executor. Full SDLC scheduling is deferred to S1+."""

import uuid
from datetime import UTC, datetime
from importlib.resources import files

from sqlalchemy import select
from sqlalchemy.orm import Session

from orchestrator.llm import LLMClient, MockLLM
from orchestrator.store import AuditEvent, Node, Run, Store
from orchestrator.validation import Json, digest, schema_for, validate

DAG: Json = {
    "version": 1,
    "scope": "S0 bootstrap only",
    "nodes": ["intake", "plan", "summary"],
    "edges": [["intake", "plan"], ["plan", "summary"]],
}


def append_event(
    session: Session,
    run_id: str,
    event_type: str,
    payload: Json,
    rationale: str,
    actor: str = "bootstrap-engine",
) -> None:
    previous = session.scalar(
        select(AuditEvent).where(AuditEvent.run_id == run_id).order_by(AuditEvent.seq.desc())
    )
    item: Json = {
        "event_id": uuid.uuid4().hex,
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "actor": actor,
        "event_type": event_type,
        "payload": payload,
        "rationale": rationale,
        "parent_event_id": previous.event_id if previous else None,
    }
    validate(item, schema_for("event"))
    session.add(AuditEvent(event_id=item["event_id"], run_id=run_id, body=item))
    session.flush()


class Engine:
    def __init__(self, store: Store, client: LLMClient | None = None) -> None:
        self.store = store
        self.client = client if client is not None else MockLLM()

    def create(self, requirement: str) -> str:
        if not requirement.strip() or len(requirement) > 10000:
            raise ValueError("Requirement must contain 1–10000 characters")
        validate(DAG, schema_for("dag"))
        run_id = uuid.uuid4().hex
        with self.store.exclusive(), self.store.session() as session, session.begin():
            run = Run(id=run_id, requirement_hash=digest(requirement), dag=DAG)
            session.add(run)
            session.flush()
            for name in DAG["nodes"]:
                session.add(Node(run_id=run_id, id=name))
            append_event(
                session,
                run_id,
                "RUN_CREATED",
                {"requirement_hash": digest(requirement)},
                "User requested bootstrap; raw input is deliberately not persisted",
            )
        return run_id

    def execute(self, run_id: str, stop_after: int | None = None) -> Json:
        if stop_after is not None and stop_after < 1:
            raise ValueError("stop-after must be positive")
        with self.store.exclusive():
            state = self.store.get_run(run_id)
            self.store.sync_files(run_id)
            self._verify_committed(run_id)
            if state["status"] == "PASSED":
                return state
            if state["status"] == "FAILED":
                raise ValueError("Failed runs require S1 rework support; inspect evidence")
            with self.store.session() as session, session.begin():
                run = session.get(Run, run_id)
                assert run is not None
                run.status = "RUNNING"
                for interrupted in session.scalars(select(Node).where(Node.run_id == run_id)):
                    if interrupted.status == "RUNNING":
                        interrupted.status = "PENDING"
                        append_event(
                            session,
                            run_id,
                            "NODE_RECOVERED",
                            {"node": interrupted.id},
                            "Previous process left an uncommitted bootstrap computation",
                        )
                append_event(session, run_id, "RUN_STARTED", {}, "Execute pending bootstrap nodes")
            completed = 0
            for name in DAG["nodes"]:
                with self.store.session() as session, session.begin():
                    node = session.get(Node, (run_id, name))
                    run = session.get(Run, run_id)
                    assert node is not None and run is not None
                    if node.status == "PASSED":
                        continue
                    dependencies = [source for source, target in DAG["edges"] if target == name]
                    inputs: Json = {}
                    context: Json = {}
                    for dependency in dependencies:
                        parent = session.get(Node, (run_id, dependency))
                        if parent is None or parent.status != "PASSED":
                            raise ValueError("Entry gate: dependency not PASSED")
                        inputs[dependency] = parent.artifact_hash
                        context[dependency] = parent.artifact
                    if not dependencies:
                        inputs["requirement"] = run.requirement_hash
                    node.status = "RUNNING"
                    node.attempts += 1
                    node.input_hashes = inputs
                    append_event(
                        session,
                        run_id,
                        "NODE_STARTED",
                        {"node": name, "inputs": inputs},
                        "Entry gate passed: all dependencies committed and validated",
                    )
                self.store.sync_files(run_id)
                try:
                    schema = schema_for(name)
                    prompt = files("orchestrator").joinpath(f"prompts/{name}.txt").read_text()
                    artifact = self.client.complete(
                        prompt,
                        [{"role": "user", "content": context, "input_hashes": inputs}],
                        schema,
                    )
                    validate(artifact, schema)  # Independent engine exit gate.
                    with self.store.session() as session, session.begin():
                        node = session.get(Node, (run_id, name))
                        assert node is not None
                        node.artifact = artifact
                        node.artifact_hash = digest(artifact)
                        node.status = "PASSED"
                        append_event(
                            session,
                            run_id,
                            "GATE_PASSED",
                            {
                                "node": name,
                                "gate": f"{name}.exit",
                                "artifact_hash": digest(artifact),
                                "input_hashes": inputs,
                                "evidence": f"{name}.json",
                            },
                            "Draft 2020-12 JSON Schema validated; fixture content only",
                        )
                except Exception as exc:
                    # Store only error type: provider/validator messages may echo private inputs.
                    with self.store.session() as session, session.begin():
                        node = session.get(Node, (run_id, name))
                        run = session.get(Run, run_id)
                        assert node is not None and run is not None
                        node.status = "FAILED"
                        run.status = "FAILED"
                        append_event(
                            session,
                            run_id,
                            "GATE_FAILED",
                            {"node": name, "error_type": type(exc).__name__},
                            "Exit gate failed; no artifact committed; S0 stops safely",
                        )
                    self.store.sync_files(run_id)
                    raise ValueError(
                        f"{name} failed ({type(exc).__name__}); see audit log"
                    ) from None
                self.store.sync_files(run_id)
                completed += 1
                if stop_after is not None and completed >= stop_after and name != DAG["nodes"][-1]:
                    return self._finish(run_id, "HALTED", "RUN_PAUSED", "Requested S0 pause point")
            return self._finish(run_id, "PASSED", "RUN_PASSED", "All three bootstrap gates passed")

    def _verify_committed(self, run_id: str) -> None:
        with self.store.session() as session:
            run = session.get(Run, run_id)
            assert run is not None
            if run.dag != DAG:
                raise ValueError("Stored DAG differs from supported S0 graph")
            for name in DAG["nodes"]:
                node = session.get(Node, (run_id, name))
                if node is None:
                    raise ValueError("Stored DAG node is missing")
                if node.status == "PASSED":
                    validate(node.artifact, schema_for(name))
                    if digest(node.artifact) != node.artifact_hash:
                        raise ValueError("Committed artifact hash mismatch")
                    expected: Json = {}
                    for source, target in DAG["edges"]:
                        if target == name:
                            parent = session.get(Node, (run_id, source))
                            if parent is None or parent.status != "PASSED":
                                raise ValueError("Committed node has unpassed dependency")
                            expected[source] = parent.artifact_hash
                    if not expected:
                        expected["requirement"] = run.requirement_hash
                    if node.input_hashes != expected:
                        raise ValueError("Committed artifact input hash mismatch")

    def _finish(self, run_id: str, status: str, event_type: str, rationale: str) -> Json:
        with self.store.session() as session, session.begin():
            run = session.get(Run, run_id)
            assert run is not None
            run.status = status
            append_event(session, run_id, event_type, {}, rationale)
        self.store.sync_files(run_id)
        return self.store.get_run(run_id)
