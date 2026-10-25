import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from orchestrator.policy import PolicyError, Tools
from orchestrator.store import Store
from orchestrator.validation import Json
from orchestrator.workflow import TaskSpec, Workflow, validate_graph

POLICY = Path(__file__).resolve().parents[1] / "policy.yaml"


def noop(spec: TaskSpec, tools: Tools, context: Json) -> Json:
    return {"task": spec.id, "context": context}


def build(tmp_path: Path, actions=None) -> Workflow:
    return Workflow(Store(tmp_path / "runs"), actions or {"noop": noop}, POLICY)


def test_real_parallel_barrier(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    spans = {}

    def parallel(spec, tools, context):
        start = time.monotonic()
        barrier.wait(timeout=3)
        time.sleep(0.03)
        spans[spec.id] = (start, time.monotonic())
        tools.write(spec.id + ".txt", "real side effect")
        return {"finished": True}

    engine = build(tmp_path, {"noop": noop, "parallel": parallel})
    run_id = engine.create(
        "parallel branches",
        [
            TaskSpec("root", "noop"),
            TaskSpec("a", "parallel", ["root"], writes=["a.txt"]),
            TaskSpec("b", "parallel", ["root"], writes=["b.txt"]),
            TaskSpec("join", "noop", ["a", "b"]),
        ],
    )
    assert engine.execute(run_id)["status"] == "PASSED"
    assert max(spans["a"][0], spans["b"][0]) < min(spans["a"][1], spans["b"][1])
    events = engine.store.events(run_id)
    join = next(
        i
        for i, e in enumerate(events)
        if e["event_type"] == "TASK_STARTED" and e["payload"]["node"] == "join"
    )
    assert all(
        any(e["event_type"] == "GATE_PASSED" and e["payload"]["node"] == n for e in events[:join])
        for n in ["a", "b"]
    )


def test_approval_distinct_reviewers_rejection_and_resume(tmp_path: Path) -> None:
    engine = build(tmp_path)
    run_id = engine.create("sensitive change", [TaskSpec("design", "noop", risk="high")])
    assert engine.execute(run_id)["status"] == "BLOCKED"
    assert engine.inspect(run_id)["nodes"][0]["attempts"] == 0
    engine.decide(run_id, "design", "alice", "approve", "reviewed isolated design")
    assert engine.execute(run_id)["status"] == "BLOCKED"
    with pytest.raises(ValueError):
        engine.decide(run_id, "design", "alice", "approve", "duplicate")
    engine.decide(run_id, "design", "bob", "approve", "second review")
    assert engine.execute(run_id)["status"] == "PASSED"
    assert all(not a["simulated"] for a in engine.inspect(run_id)["approvals"])
    other = engine.create("reject", [TaskSpec("design", "noop", risk="medium")])
    engine.execute(other)
    engine.decide(other, "design", "alice", "reject", "insufficient scope")
    assert engine.execute(other)["status"] == "BLOCKED"
    assert engine.inspect(other)["nodes"][0]["attempts"] == 0


def test_retry_rollback_context_and_metrics(tmp_path: Path) -> None:
    contexts = []

    def flaky(spec, tools, context):
        contexts.append(context)
        if context["attempt"] == 1:
            tools.write("effect.txt", "broken")
            raise RuntimeError("injected")
        assert tools.path("effect.txt").read_text() == "before"
        assert context["previous_failure"] == "RuntimeError"
        tools.write("effect.txt", "fixed")
        return {"fixed": True}

    engine = build(tmp_path, {"flaky": flaky})
    run_id = engine.create(
        "retry real writes", [TaskSpec("change", "flaky", writes=["effect.txt"])]
    )
    engine.tools(run_id).write("effect.txt", "before")
    assert engine.execute(run_id)["status"] == "PASSED"
    assert engine.tools(run_id).path("effect.txt").read_text() == "fixed"
    metrics = engine.metrics(run_id)
    assert metrics["retry_count"] == 1
    assert metrics["rollback_count"] == 1
    assert metrics["gate_failures"] == {"change.exit": 1}
    assert metrics["task_attempt_success_rate"] == 0.5
    assert metrics["mttr_seconds"] > 0
    assert len(contexts) == 2


def test_exhaustion_fallback_stops_dependents(tmp_path: Path) -> None:
    def fail(spec, tools, context):
        tools.write("new.txt", "must be removed")
        raise ValueError("always fails")

    engine = build(tmp_path, {"fail": fail, "noop": noop})
    run_id = engine.create(
        "fallback",
        [TaskSpec("bad", "fail", writes=["new.txt"]), TaskSpec("downstream", "noop", ["bad"])],
    )
    assert engine.execute(run_id)["status"] == "BLOCKED"
    assert not engine.tools(run_id).path("new.txt").exists()
    nodes = {n["id"]: n for n in engine.inspect(run_id)["nodes"]}
    assert nodes["bad"]["attempts"] == 2
    assert nodes["downstream"]["attempts"] == 0
    assert any(e["event_type"] == "FALLBACK" for e in engine.store.events(run_id))
    engine.execute(run_id)
    assert engine.inspect(run_id)["nodes"][0]["attempts"] == 2


def test_replan_only_descendants_and_reapproval(tmp_path: Path) -> None:
    engine = build(tmp_path)
    run_id = engine.create(
        "change contract",
        [
            TaskSpec("contract", "noop"),
            TaskSpec("independent", "noop"),
            TaskSpec("design", "noop", ["contract"], risk="medium"),
            TaskSpec("release", "noop", ["design"]),
        ],
    )
    engine.execute(run_id)
    engine.decide(run_id, "design", "demo-reviewer", "approve", "DEMO ONLY", simulated=True)
    assert engine.execute(run_id)["status"] == "PASSED"
    assert engine.replan(run_id, "contract", {"version": 2}) == ["design", "release"]
    assert engine.execute(run_id)["status"] == "BLOCKED"
    nodes = {n["id"]: n for n in engine.inspect(run_id)["nodes"]}
    assert nodes["independent"]["attempts"] == 1
    assert nodes["design"]["status"] == "AWAITING_APPROVAL"
    engine.decide(
        run_id, "design", "demo-reviewer", "approve", "DEMO revised inputs", simulated=True
    )
    assert engine.execute(run_id)["status"] == "PASSED"
    assert engine.replan(run_id, "contract", {"version": 2}) == []


def test_safe_stop_resume_without_repeating_passed(tmp_path: Path) -> None:
    engine = build(tmp_path)
    run_id = engine.create("pause", [TaskSpec("a", "noop"), TaskSpec("b", "noop", ["a"])])
    assert engine.execute(run_id, stop_after=1)["status"] == "HALTED"
    replacement = Workflow(Store(engine.store.root), {"noop": noop}, POLICY)
    assert replacement.execute(run_id)["status"] == "PASSED"
    assert all(n["attempts"] == 1 for n in replacement.inspect(run_id)["nodes"])
    assert replacement.metrics(run_id)["mttr_seconds"] is None


def test_kill9_resume_restores_interrupted_tool(tmp_path: Path) -> None:
    source = """
import sys,time
from pathlib import Path
from orchestrator.workflow import Workflow,TaskSpec
from orchestrator.store import Store
policy=Path(sys.argv[2])
def action(spec,tools,context):
    tools.write('effect.txt','uncommitted')
    tools.write('ready.txt','ready')
    time.sleep(60)
    return {}
e=Workflow(Store(Path(sys.argv[1])),{'wait':action},policy)
r=e.create('kill9',[TaskSpec('task','wait',writes=['effect.txt','ready.txt'])])
e.tools(r).write('effect.txt','original')
print(r,flush=True)
e.execute(r)
"""
    root = tmp_path / "killed"
    process = subprocess.Popen(
        [sys.executable, "-c", source, str(root), str(POLICY)], stdout=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    run_id = process.stdout.readline().strip()
    try:
        marker = root / run_id / "workspace" / "ready.txt"
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
    finally:
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL

    def recovered(spec, tools, context):
        assert tools.path("effect.txt").read_text() == "original"
        assert not tools.path("ready.txt").exists()
        tools.write("effect.txt", "completed")
        return {"recovered": True}

    engine = Workflow(Store(root), {"wait": recovered}, POLICY)
    assert engine.execute(run_id)["status"] == "PASSED"
    assert engine.tools(run_id).path("effect.txt").read_text() == "completed"
    assert engine.metrics(run_id)["rollback_count"] == 1
    assert engine.inspect(run_id)["nodes"][0]["attempts"] == 2


@pytest.mark.parametrize(
    "specs",
    [
        [],
        [TaskSpec("a", "noop", ["missing"])],
        [TaskSpec("a", "noop", ["b"]), TaskSpec("b", "noop", ["a"])],
        [TaskSpec("a", "noop"), TaskSpec("a", "noop")],
        [TaskSpec("../escape", "noop")],
    ],
)
def test_invalid_graph(specs) -> None:
    with pytest.raises(ValueError):
        validate_graph(specs)


def test_policy_denies_escape_command_and_secret(tmp_path: Path) -> None:
    engine = build(tmp_path)
    run_id = engine.create("policy", [TaskSpec("a", "noop")])
    tools = engine.tools(run_id)
    for path in ["../escape", "/tmp/escape", ".git/config", ".env"]:
        with pytest.raises(PolicyError):
            tools.write(path, "denied")
    outside = tmp_path / "outside"
    outside.mkdir()
    (tools.workspace / "symlink").symlink_to(outside)
    with pytest.raises(PolicyError):
        tools.write("symlink/escape", "denied")
    with pytest.raises(PolicyError):
        tools.write("secret.txt", "-----BEGIN RSA PRIVATE KEY-----")
    with pytest.raises(PolicyError):
        tools.command(["rm", "-rf", "/"], "denied")
    with pytest.raises(PolicyError):
        tools.command([sys.executable, "-m", "pytest", "../outside"], "denied")


def test_committed_artifact_and_input_tampering_refused(tmp_path: Path) -> None:
    from orchestrator.workflow import Task

    engine = build(tmp_path)
    run_id = engine.create("integrity", [TaskSpec("a", "noop")])
    engine.execute(run_id)
    with engine.store.session() as session, session.begin():
        task = session.get(Task, (run_id, "a"))
        task.output_hash = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        engine.execute(run_id)


def test_signal_style_safe_stop_and_cli_halt_request(tmp_path: Path) -> None:
    engine = None

    def stop(spec, tools, context):
        engine.stop_requested = True
        return {"finished_atomic_step": True}

    engine = build(tmp_path, {"stop": stop, "noop": noop})
    run_id = engine.create("stop", [TaskSpec("a", "stop"), TaskSpec("b", "noop", ["a"])])
    assert engine.execute(run_id)["status"] == "HALTED"
    engine.stop_requested = False
    assert engine.execute(run_id)["status"] == "PASSED"
    engine.request_halt(run_id)
    assert engine.store.events(run_id)[-1]["event_type"] == "HALT_REQUESTED"


def test_task_write_scope_enforced(tmp_path: Path) -> None:
    def escape(spec, tools, context):
        tools.write("undeclared.txt", "denied")
        return {}

    engine = build(tmp_path, {"escape": escape})
    run_id = engine.create("role scope", [TaskSpec("a", "escape", max_attempts=1)])
    assert engine.execute(run_id)["status"] == "BLOCKED"
    assert not engine.tools(run_id).path("undeclared.txt").exists()
