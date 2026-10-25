"""Persisted general DAG executor; S0 remains available through its original Engine."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from orchestrator.engine import append_event as base_append_event
from orchestrator.policy import Tools, load_policy
from orchestrator.store import Base, Run, Store
from orchestrator.validation import Json, digest, validate


def append_event(session: Session, run_id: str, action: str, payload: Json, reason: str) -> None:
    base_append_event(session, run_id, action, payload, reason, actor="workflow-engine")


ARTIFACT_SCHEMA: Json = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["role", "data", "reasoning_mode"],
    "additionalProperties": False,
    "properties": {
        "role": {"type": "string"},
        "data": {"type": "object"},
        "reasoning_mode": {"enum": ["deterministic-template", "real-tool-output"]},
    },
}


class Task(Base):
    __tablename__ = "workflow_tasks"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    spec: Mapped[Json] = mapped_column(JSON)
    output: Mapped[Json | None] = mapped_column(JSON, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    input_hashes: Mapped[Json] = mapped_column(JSON, default=dict)
    failure: Mapped[str | None] = mapped_column(String, nullable=True)
    snapshot: Mapped[Json] = mapped_column(JSON, default=dict)


class Approval(Base):
    __tablename__ = "workflow_approvals"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    reviewer: Mapped[str] = mapped_column(String, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String, primary_key=True)
    decision: Mapped[str] = mapped_column(String)
    simulated: Mapped[bool] = mapped_column(default=False)
    note: Mapped[str] = mapped_column(String)


@dataclass
class TaskSpec:
    id: str
    role: str
    deps: list[str] = field(default_factory=list)
    risk: str = "low"
    max_attempts: int = 2
    writes: list[str] = field(default_factory=list)
    config: Json = field(default_factory=dict)
    entry: str = "dependencies_passed_and_approval_bound_to_inputs"
    exit: str = "json_schema_and_tool_validation"
    fallback: str = "human_escalation"


Action = Callable[[TaskSpec, Tools, Json], Json]


def validate_graph(specs: list[TaskSpec]) -> None:
    indexed = {s.id: s for s in specs}
    if len(indexed) != len(specs) or not specs:
        raise ValueError("Task IDs must be unique; graph must not be empty")
    for s in specs:
        if (
            not s.id.replace("_", "").isalnum()
            or s.risk not in {"low", "medium", "high", "release"}
            or s.max_attempts < 1
            or s.max_attempts > 3
            or any(d not in indexed for d in s.deps)
        ):
            raise ValueError("Invalid task specification")
    done: set[str] = set()
    while len(done) < len(specs):
        ready = {s.id for s in specs if s.id not in done and set(s.deps) <= done}
        if not ready:
            raise ValueError("Dependency cycle")
        done |= ready


class Workflow:
    def __init__(self, store: Store, actions: dict[str, Action], policy_path: Path) -> None:
        self.store = store
        Base.metadata.create_all(store.engine)
        self.actions = actions
        self.policy = load_policy(policy_path)
        self.stop_requested = False

    def record(self, run_id: str, action: str, payload: Json, reason: str) -> None:
        with self.store.session() as session, session.begin():
            append_event(session, run_id, action, payload, reason)

    def create(self, requirement: str, specs: list[TaskSpec], scenario: str = "custom") -> str:
        validate_graph(specs)
        if any(s.max_attempts > self.policy["budgets"]["max_attempts"] for s in specs):
            raise ValueError("Task retry budget exceeds policy")
        if not requirement.strip() or len(requirement) > 10000:
            raise ValueError("Invalid requirement")
        run_id = uuid.uuid4().hex
        with self.store.exclusive(), self.store.session() as session, session.begin():
            session.add(
                Run(
                    id=run_id,
                    requirement_hash=digest(requirement),
                    dag={
                        "version": 2,
                        "scenario": scenario,
                        "nodes": [asdict(s) for s in specs],
                        "edges": [[d, s.id] for s in specs for d in s.deps],
                    },
                )
            )
            session.flush()
            for spec in specs:
                session.add(Task(run_id=run_id, id=spec.id, spec=asdict(spec)))
            append_event(
                session,
                run_id,
                "RUN_CREATED",
                {"requirement_hash": digest(requirement), "scenario": scenario},
                "New v3 workflow; requirement is user data, no shell interpolation",
            )
        self.sync(run_id)
        return run_id

    def inspect(self, run_id: str) -> Json:
        result = self.store.get_run(run_id)
        with self.store.session() as session:
            result["nodes"] = [
                {
                    "id": t.id,
                    "status": t.status,
                    "attempts": t.attempts,
                    "spec": t.spec,
                    "input_hashes": t.input_hashes,
                    "output_hash": t.output_hash,
                    "failure": t.failure,
                }
                for t in session.scalars(select(Task).where(Task.run_id == run_id))
            ]
            result["approvals"] = [
                {
                    "task_id": a.task_id,
                    "reviewer": a.reviewer,
                    "decision": a.decision,
                    "simulated": a.simulated,
                    "fingerprint": a.fingerprint,
                    "note": a.note,
                }
                for a in session.scalars(select(Approval).where(Approval.run_id == run_id))
            ]
        return result

    def tools(self, run_id: str) -> Tools:
        directory = self.store.run_dir(run_id)
        return Tools(directory / "workspace", self.policy, directory / "commands")

    def _inputs(self, run_id: str, spec: TaskSpec) -> tuple[Json, Json]:
        hashes: Json = {}
        context: Json = {}
        with self.store.session() as session:
            run = session.get(Run, run_id)
            assert run is not None
            for dependency in spec.deps:
                node = session.get(Task, (run_id, dependency))
                if node is None or node.status != "PASSED" or node.output is None:
                    raise ValueError("Dependency entry gate is closed")
                validate(node.output, ARTIFACT_SCHEMA)
                if digest(node.output) != node.output_hash:
                    raise ValueError("Artifact integrity violation")
                hashes[dependency] = node.output_hash
                context[dependency] = node.output["data"]
            if not hashes:
                hashes["requirement"] = run.requirement_hash
        return hashes, context

    def _fingerprint(self, run_id: str, spec: TaskSpec) -> str:
        inputs, _ = self._inputs(run_id, spec)
        return digest({"spec": asdict(spec), "inputs": inputs})

    def decide(
        self,
        run_id: str,
        task_id: str,
        reviewer: str,
        decision: str,
        note: str,
        simulated: bool = False,
    ) -> None:
        if decision not in {"approve", "reject"} or not reviewer.strip() or not note.strip():
            raise ValueError("Decision, reviewer and rationale required")
        with self.store.exclusive():
            with self.store.session() as session:
                node = session.get(Task, (run_id, task_id))
                if node is None or node.status != "AWAITING_APPROVAL":
                    raise ValueError("Task is not awaiting approval")
                spec = TaskSpec(**node.spec)
            fingerprint = self._fingerprint(run_id, spec)
            with self.store.session() as session, session.begin():
                key = (run_id, task_id, reviewer, fingerprint)
                if session.get(Approval, key) is not None:
                    raise ValueError("Reviewer already decided on these inputs")
                session.add(
                    Approval(
                        run_id=run_id,
                        task_id=task_id,
                        reviewer=reviewer,
                        fingerprint=fingerprint,
                        decision=decision,
                        note=note[:2000],
                        simulated=simulated,
                    )
                )
                append_event(
                    session,
                    run_id,
                    "APPROVAL_DECIDED",
                    {
                        "node": task_id,
                        "reviewer": reviewer,
                        "decision": decision,
                        "simulated": simulated,
                        "fingerprint": fingerprint,
                    },
                    note[:2000],
                )
            self.sync(run_id)

    def _approved(self, run_id: str, spec: TaskSpec) -> bool:
        count = self.policy["approvals"].get(spec.risk, 0)
        if not count:
            return True
        fingerprint = self._fingerprint(run_id, spec)
        with self.store.session() as session:
            decisions = session.scalars(
                select(Approval).where(
                    Approval.run_id == run_id,
                    Approval.task_id == spec.id,
                    Approval.fingerprint == fingerprint,
                )
            ).all()
        if any(a.decision == "reject" for a in decisions):
            return False
        return len({a.reviewer for a in decisions if a.decision == "approve"}) >= int(count)

    def request_halt(self, run_id: str) -> None:
        self.record(run_id, "HALT_REQUESTED", {}, "User requested stop after current atomic wave")

    def _set_run(self, run_id: str, status: str, reason: str) -> Json:
        with self.store.session() as session, session.begin():
            run = session.get(Run, run_id)
            assert run is not None
            run.status = status
            append_event(session, run_id, "RUN_" + status, {}, reason)
        self.sync(run_id)
        return self.inspect(run_id)

    def execute(self, run_id: str, stop_after: int | None = None) -> Json:
        started = time.monotonic()
        completed = 0
        with self.store.exclusive():
            self.sync(run_id)
            with self.store.session() as session:
                for committed in session.scalars(select(Task).where(Task.run_id == run_id)):
                    if committed.status == "PASSED":
                        validate(committed.output, ARTIFACT_SCHEMA)
                        if digest(committed.output) != committed.output_hash:
                            raise ValueError("Committed artifact hash mismatch")
                        expected, _ = self._inputs(run_id, TaskSpec(**committed.spec))
                        if expected != committed.input_hashes:
                            raise ValueError(
                                "Stale committed input hashes; explicit replan required"
                            )
            # Interrupted tool work is restored from persisted pre-attempt snapshots.
            for item in self.inspect(run_id)["nodes"]:
                if item["status"] == "RUNNING":
                    with self.store.session() as session, session.begin():
                        task = session.get(Task, (run_id, item["id"]))
                        assert task is not None
                        snapshot = {
                            p: bytes.fromhex(v) if v is not None else None
                            for p, v in task.snapshot.items()
                        }
                        self.tools(run_id).restore(snapshot)
                        task.status = (
                            "PENDING" if task.attempts < task.spec["max_attempts"] else "BLOCKED"
                        )
                        append_event(
                            session,
                            run_id,
                            "ROLLBACK_VERIFIED",
                            {"node": task.id},
                            "Interrupted task snapshot restored and byte-verified",
                        )
                        append_event(
                            session,
                            run_id,
                            "TASK_RECOVERED",
                            {"node": task.id},
                            "Resume retries only uncommitted work",
                        )
            self._set_run(
                run_id, "RUNNING", "Execute eligible tasks, preserving valid passed tasks"
            )
            start_index = len(self.store.events(run_id))
            while True:
                state = self.inspect(run_id)
                if all(n["status"] == "PASSED" for n in state["nodes"]):
                    return self._set_run(run_id, "PASSED", "Every task and required gate passed")
                halt = any(
                    e["event_type"] == "HALT_REQUESTED"
                    for e in self.store.events(run_id)[start_index:]
                )
                if (
                    self.stop_requested
                    or halt
                    or (stop_after is not None and completed >= stop_after)
                ):
                    return self._set_run(run_id, "HALTED", "Atomic wave completed; safe to resume")
                if time.monotonic() - started > self.policy["budgets"]["run_seconds"]:
                    return self._set_run(run_id, "HALTED", "Run time budget exhausted")
                indexed = {n["id"]: n for n in state["nodes"]}
                ready: list[TaskSpec] = []
                for item in state["nodes"]:
                    if item["status"] not in {"PENDING", "STALE", "AWAITING_APPROVAL"}:
                        continue
                    spec = TaskSpec(**item["spec"])
                    if not all(indexed[d]["status"] == "PASSED" for d in spec.deps):
                        continue
                    if not self._approved(run_id, spec):
                        if item["status"] != "AWAITING_APPROVAL":
                            with self.store.session() as session, session.begin():
                                task = session.get(Task, (run_id, spec.id))
                                assert task is not None
                                task.status = "AWAITING_APPROVAL"
                                append_event(
                                    session,
                                    run_id,
                                    "APPROVAL_REQUESTED",
                                    {
                                        "node": spec.id,
                                        "risk": spec.risk,
                                        "fingerprint": self._fingerprint(run_id, spec),
                                    },
                                    "Input-bound human decision required before execution",
                                )
                        continue
                    if item["attempts"] >= spec.max_attempts:
                        with self.store.session() as session, session.begin():
                            task = session.get(Task, (run_id, spec.id))
                            assert task is not None
                            task.status = "BLOCKED"
                            append_event(
                                session,
                                run_id,
                                "FALLBACK",
                                {"node": spec.id},
                                "Attempts exhausted; human escalation; no unsafe bypass",
                            )
                        continue
                    ready.append(spec)
                if not ready:
                    return self._set_run(
                        run_id, "BLOCKED", "Waiting on approvals or human fallback"
                    )
                ready = ready[: self.policy["budgets"]["max_workers"]]
                # Concurrent writers must declare disjoint file effects.
                paths = [p for spec in ready for p in spec.writes]
                if len(paths) != len(set(paths)):
                    raise ValueError("Concurrent write sets overlap")
                for spec in ready:
                    inputs, _ = self._inputs(run_id, spec)
                    snapshot = self.tools(run_id).snapshot(spec.writes)
                    with self.store.session() as session, session.begin():
                        task = session.get(Task, (run_id, spec.id))
                        assert task is not None
                        task.snapshot = {
                            p: value.hex() if value is not None else None
                            for p, value in snapshot.items()
                        }
                        task.input_hashes = inputs
                        task.attempts += 1
                        task.status = "RUNNING"
                        append_event(
                            session,
                            run_id,
                            "TASK_STARTED",
                            {
                                "node": spec.id,
                                "attempt": task.attempts,
                                "inputs": inputs,
                                "role": spec.role,
                            },
                            "Dependency and approval entry gates passed",
                        )
                self.sync(run_id)
                with ThreadPoolExecutor(max_workers=self.policy["budgets"]["max_workers"]) as pool:
                    futures = {pool.submit(self._perform, run_id, spec): spec for spec in ready}
                    for future in as_completed(futures):
                        spec = futures[future]
                        ok, artifact, error = future.result()
                        with self.store.session() as session, session.begin():
                            task = session.get(Task, (run_id, spec.id))
                            assert task is not None
                            if ok:
                                task.status = "PASSED"
                                task.output = artifact
                                task.output_hash = digest(artifact)
                                append_event(
                                    session,
                                    run_id,
                                    "GATE_PASSED",
                                    {
                                        "node": spec.id,
                                        "gate": spec.id + ".exit",
                                        "artifact_hash": task.output_hash,
                                        "input_hashes": task.input_hashes,
                                        "evidence": f"artifacts/{spec.id}.json",
                                    },
                                    "Artifact schema and real tool exit validation passed",
                                )
                            else:
                                task.status = "ROLLED_BACK"
                                task.failure = error
                                append_event(
                                    session,
                                    run_id,
                                    "TASK_FAILED",
                                    {"node": spec.id, "error": error, "attempt": task.attempts},
                                    "Action or gate failed; failure context retained",
                                )
                                append_event(
                                    session,
                                    run_id,
                                    "ROLLBACK_VERIFIED",
                                    {"node": spec.id},
                                    "Declared files restored and byte-verified",
                                )
                                if task.attempts < spec.max_attempts:
                                    task.status = "PENDING"
                                    append_event(
                                        session,
                                        run_id,
                                        "RETRY_QUEUED",
                                        {"node": spec.id, "previous_failure": error},
                                        "Retry within declared bounded attempt policy",
                                    )
                                else:
                                    task.status = "BLOCKED"
                                    append_event(
                                        session,
                                        run_id,
                                        "FALLBACK",
                                        {"node": spec.id, "mode": spec.fallback},
                                        "Retry exhausted; escalate to human, stop dependent work",
                                    )
                        completed += 1
                self.sync(run_id)
                if any(n["failure"] for n in self.inspect(run_id)["nodes"]):
                    time.sleep(0.02)  # Small bounded retry backoff for local prototype.

    def _perform(self, run_id: str, spec: TaskSpec) -> tuple[bool, Json, str]:
        tools = self.tools(run_id)
        tools.allowed_writes = set(spec.writes)
        with self.store.session() as session:
            task = session.get(Task, (run_id, spec.id))
            assert task is not None
            snapshot = {
                p: bytes.fromhex(v) if v is not None else None for p, v in task.snapshot.items()
            }
            attempt, previous = task.attempts, task.failure
        _, context = self._inputs(run_id, spec)
        context.update({"attempt": attempt, "previous_failure": previous})
        try:
            data = self.actions[spec.role](spec, tools, context)
            artifact = {
                "role": spec.role,
                "data": data,
                "reasoning_mode": "deterministic-template"
                if spec.role in {"intake", "planner", "design"}
                else "real-tool-output",
            }
            validate(artifact, ARTIFACT_SCHEMA)
            return True, artifact, ""
        except Exception as exc:
            tools.restore(snapshot)
            return False, {}, type(exc).__name__

    def replan(self, run_id: str, task_id: str, data: Json) -> list[str]:
        """Revise a passed upstream artifact and invalidate only its descendants."""
        with self.store.exclusive():
            state = self.inspect(run_id)
            indexed = {n["id"]: n for n in state["nodes"]}
            if task_id not in indexed or indexed[task_id]["status"] != "PASSED":
                raise ValueError("Replan requires a passed upstream task")
            with self.store.session() as session, session.begin():
                task = session.get(Task, (run_id, task_id))
                assert task is not None and task.output is not None
                updated = {**task.output, "data": data}
                validate(updated, ARTIFACT_SCHEMA)
                if digest(updated) == task.output_hash:
                    return []
                previous = task.output_hash
                task.output = updated
                task.output_hash = digest(updated)
                affected = {task_id}
                while True:
                    new = {
                        n["id"] for n in state["nodes"] if set(n["spec"]["deps"]) & affected
                    } | affected
                    if new == affected:
                        break
                    affected = new
                affected.remove(task_id)
                for identifier in affected:
                    stale = session.get(Task, (run_id, identifier))
                    assert stale is not None
                    stale.status = "STALE"
                    stale.attempts = 0
                    stale.output = None
                    stale.output_hash = None
                    stale.failure = None
                run = session.get(Run, run_id)
                assert run is not None
                run.status = "PENDING"
                append_event(
                    session,
                    run_id,
                    "REPLAN",
                    {
                        "node": task_id,
                        "old_hash": previous,
                        "new_hash": task.output_hash,
                        "invalidated": sorted(affected),
                    },
                    "Upstream content changed; downstream approvals bind to old inputs",
                )
            self.sync(run_id)
            return sorted(affected)

    def metrics(self, run_id: str) -> Json:
        events = self.store.events(run_id)
        times: dict[str, datetime] = {}
        failed: dict[str, datetime] = {}
        waiting: dict[str, datetime] = {}
        latencies: dict[str, list[float]] = {}
        repairs: list[float] = []
        waits: list[float] = []
        failures: dict[str, int] = {}
        for item in events:
            now = datetime.fromisoformat(item["timestamp"])
            node = item["payload"].get("node", "")
            kind = item["event_type"]
            if kind == "TASK_STARTED":
                times[node] = now
                if node in waiting:
                    waits.append((now - waiting.pop(node)).total_seconds())
            if kind == "APPROVAL_REQUESTED":
                waiting.setdefault(node, now)
            if kind == "TASK_FAILED":
                failed.setdefault(node, now)
                failures[node + ".exit"] = failures.get(node + ".exit", 0) + 1
            if kind in {"GATE_PASSED", "TASK_FAILED"} and node in times:
                latencies.setdefault(node, []).append((now - times.pop(node)).total_seconds())
            if kind == "GATE_PASSED" and node in failed:
                repairs.append((now - failed.pop(node)).total_seconds())
        state = self.inspect(run_id)

        def count(kind: str) -> int:
            return sum(e["event_type"] == kind for e in events)

        attempted = count("TASK_STARTED")
        successful = count("GATE_PASSED")
        first = datetime.fromisoformat(events[0]["timestamp"])
        last = datetime.fromisoformat(events[-1]["timestamp"])
        with self.store.session() as session:
            runs = [r for r in session.scalars(select(Run)) if r.dag.get("version") == 2]
        return {
            "run_id": run_id,
            "status": state["status"],
            "run_success": state["status"] == "PASSED",
            "run_success_rate_across_observed_runs": sum(r.status == "PASSED" for r in runs)
            / len(runs),
            "observed_runs": len(runs),
            "task_attempts": attempted,
            "task_attempt_success_rate": successful / attempted if attempted else None,
            "retry_count": count("RETRY_QUEUED"),
            "retry_frequency": count("RETRY_QUEUED") / attempted if attempted else None,
            "rollback_count": count("ROLLBACK_VERIFIED"),
            "rollback_frequency": count("ROLLBACK_VERIFIED") / attempted if attempted else None,
            "gate_failures": failures,
            "per_task_latency_seconds": latencies,
            "end_to_end_seconds": (last - first).total_seconds(),
            "mttr_seconds": sum(repairs) / len(repairs) if repairs else None,
            "repair_observations": len(repairs),
            "approval_wait_seconds": sum(waits),
            "approval_wait_observations": len(waits),
            "limitations": (
                "MTTR null without repairs. Demo decisions labeled; waits are actual elapsed time. "
                "Latency includes pauses."
            ),
        }

    def sync(self, run_id: str) -> None:
        self.store.sync_files(run_id)
        directory = self.store.run_dir(run_id)
        artifact_dir = directory / "artifacts"
        artifact_dir.mkdir(exist_ok=True)
        with self.store.session() as session:
            for task in session.scalars(select(Task).where(Task.run_id == run_id)):
                if task.output is not None:
                    validate(task.output, ARTIFACT_SCHEMA)
                    self.store.write_json(artifact_dir / f"{task.id}.json", task.output)
        state = self.inspect(run_id)
        self.store.write_json(directory / "state.json", state)
        self.store.write_json(directory / "approvals.json", state["approvals"])
        self.store.write_json(directory / "metrics.json", self.metrics(run_id))
        mermaid = "flowchart TD\n" + "".join(f"  {a} --> {b}\n" for a, b in state["dag"]["edges"])
        (directory / "dag.mmd").write_text(mermaid)
