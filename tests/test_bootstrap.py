"""S0 unit/integration/CLI tests; not URL-shortener acceptance tests."""

import json
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from jsonschema import ValidationError

from orchestrator.cli import main
from orchestrator.engine import Engine
from orchestrator.llm import LiveHTTPClient, MockLLM
from orchestrator.store import Node, Run, Store
from orchestrator.validation import Json, digest, schema_for, validate


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "runs")


def test_fixture_contract_and_determinism() -> None:
    client = MockLLM()
    for name in ["intake", "plan", "summary"]:
        first = client.complete("system", [{"content": "one"}], schema_for(name))
        second = client.complete("system", [{"content": "two"}], schema_for(name))
        assert first == second  # Explicitly fixture-backed, independent of requirement text.
        validate(first, schema_for(name))
        assert first["mode"] == "mock-fixture"


def test_default_engine_runs_without_network(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline bootstrap attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    engine = Engine(store)
    run_id = engine.create("Untrusted input is data; never run commands")
    assert engine.execute(run_id)["status"] == "PASSED"


def test_schema_rejects_bad_artifacts() -> None:
    with pytest.raises(ValidationError):
        validate({"unexpected": True}, schema_for("intake"))
    with pytest.raises(ValueError, match="Unknown schema"):
        schema_for("../../private")
    with pytest.raises(ValueError, match="Remote"):
        validate({}, {"$ref": "https://example.invalid/private"})
    with pytest.raises(ValueError, match="Remote"):
        validate({}, {"anyOf": [{"$dynamicRef": "https://example.invalid/private"}]})
    with pytest.raises(ValueError):
        MockLLM().complete("system", [{}], {"title": "unknown"})
    with pytest.raises(ValueError):
        MockLLM().complete("", [], schema_for("intake"))
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_live_gateway_contract_without_network() -> None:
    schema = schema_for("intake")
    artifact = MockLLM().complete("system", [{}], schema)

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert set(body) == {"system", "messages", "schema"}
        assert body["schema"] == schema
        return httpx.Response(200, json=artifact)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        adapter = LiveHTTPClient("https://gateway.invalid/complete", client)
        assert adapter.complete("system", [{}], schema) == artifact
        with pytest.raises(ValueError, match="HTTPS"):
            LiveHTTPClient("http://gateway.invalid/complete", client)


@pytest.mark.parametrize(
    "status,body,error",
    [
        (200, [], ValueError),
        (200, {}, ValidationError),
        (503, {}, httpx.HTTPStatusError),
    ],
)
def test_live_gateway_failures(status: int, body: object, error: type[Exception]) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    ) as client:
        with pytest.raises(error):
            LiveHTTPClient("https://gateway.invalid/complete", client).complete(
                "system", [{}], schema_for("intake")
            )


def test_transactional_run_and_lineage(store: Store) -> None:
    engine = Engine(store)
    run_id = engine.create("Create a short link")
    state = engine.execute(run_id)
    assert state["status"] == "PASSED"
    assert [n["status"] for n in state["nodes"]] == ["PASSED"] * 3
    events = store.events(run_id)
    assert events[0]["parent_event_id"] is None
    for previous, current in zip(events, events[1:], strict=False):
        assert current["parent_event_id"] == previous["event_id"]
        validate(current, schema_for("event"))
    gates = [e for e in events if e["event_type"] == "GATE_PASSED"]
    assert len(gates) == 3
    assert gates[1]["payload"]["input_hashes"] == {"intake": gates[0]["payload"]["artifact_hash"]}
    directory = store.run_dir(run_id)
    lines = (directory / "events.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == events
    for name in ["intake", "plan", "summary"]:
        validate(json.loads((directory / f"{name}.json").read_text()), schema_for(name))
    engine.execute(run_id)
    assert store.events(run_id) == events  # Completed resume is idempotent.


def test_pause_resume_from_new_store(store: Store) -> None:
    engine = Engine(store)
    run_id = engine.create("Requirement")
    assert engine.execute(run_id, stop_after=1)["status"] == "HALTED"
    prefix = (store.run_dir(run_id) / "events.jsonl").read_bytes()
    replacement = Store(store.root)
    result = Engine(replacement).execute(run_id)
    assert result["status"] == "PASSED"
    assert all(n["attempts"] == 1 for n in result["nodes"])
    assert (store.run_dir(run_id) / "events.jsonl").read_bytes().startswith(prefix)


def test_resume_in_separate_processes(tmp_path: Path) -> None:
    command = [sys.executable, "-m", "orchestrator.cli", "--root", str(tmp_path / "runs")]
    created = subprocess.run(
        [*command, "run", "--requirement", "URL shortener", "--stop-after", "1"],
        check=True,
        capture_output=True,
        text=True,
    )
    run_id = json.loads(created.stdout.splitlines()[0])["created_run_id"]
    resumed = subprocess.run(
        [*command, "resume", run_id], check=True, capture_output=True, text=True
    )
    result = json.loads(resumed.stdout)
    assert result["status"] == "PASSED"
    assert all(n["attempts"] == 1 for n in result["nodes"])


class BadClient:
    def complete(self, system: str, messages: list[Json], schema: Json) -> Json:
        return {"private-input": "MUST_NOT_APPEAR_IN_AUDIT"}


def test_engine_gate_independent_of_client(store: Store) -> None:
    engine = Engine(store, BadClient())
    run_id = engine.create("Requirement")
    with pytest.raises(ValueError, match="intake failed"):
        engine.execute(run_id)
    result = store.get_run(run_id)
    assert result["status"] == "FAILED"
    assert result["nodes"][0]["artifact_hash"] is None
    assert "MUST_NOT_APPEAR_IN_AUDIT" not in json.dumps(store.events(run_id))
    assert not (store.run_dir(run_id) / "intake.json").exists()
    with pytest.raises(ValueError, match="S1 rework"):
        engine.execute(run_id)


def test_commit_before_projection_is_recoverable(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = Engine(store)
    run_id = engine.create("Requirement")
    real_sync = store.sync_files
    calls = 0

    def interrupted_sync(identifier: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:  # Intake artifact + exit event committed; projection not written.
            raise OSError("injected power-loss boundary")
        real_sync(identifier)

    monkeypatch.setattr(store, "sync_files", interrupted_sync)
    with pytest.raises(OSError):
        engine.execute(run_id)
    assert store.get_run(run_id)["nodes"][0]["status"] == "PASSED"
    monkeypatch.setattr(store, "sync_files", real_sync)
    assert engine.execute(run_id)["status"] == "PASSED"
    assert store.get_run(run_id)["nodes"][0]["attempts"] == 1
    lines = (store.run_dir(run_id) / "events.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == store.events(run_id)


def test_interrupted_running_computation_requeues(store: Store) -> None:
    run_id = Engine(store).create("Requirement")
    with store.session() as session, session.begin():
        node = session.get(Node, (run_id, "intake"))
        assert node is not None
        node.status = "RUNNING"
        node.attempts = 1
    result = Engine(store).execute(run_id)
    assert result["status"] == "PASSED"
    assert result["nodes"][0]["attempts"] == 2
    assert any(e["event_type"] == "NODE_RECOVERED" for e in store.events(run_id))


@pytest.mark.parametrize("tail", ['{"torn":', "{}\n"])
def test_corrupt_audit_fails_closed(store: Store, tail: str) -> None:
    run_id = Engine(store).create("Requirement")
    store.sync_files(run_id)
    path = store.run_dir(run_id) / "events.jsonl"
    with path.open("a") as stream:
        stream.write(tail)
    original = path.read_bytes()
    with pytest.raises(ValueError):
        Engine(store).execute(run_id)
    assert path.read_bytes() == original


@pytest.mark.parametrize("tamper", ["artifact", "inputs", "dag", "missing", "dependency"])
def test_corrupt_state_fails_closed(store: Store, tamper: str) -> None:
    engine = Engine(store)
    run_id = engine.create("Requirement")
    engine.execute(run_id, stop_after=2)
    with store.session() as session, session.begin():
        node = session.get(Node, (run_id, "intake"))
        run = session.get(Run, run_id)
        assert node is not None and run is not None
        if tamper == "artifact":
            node.artifact_hash = "0" * 64
        elif tamper == "inputs":
            node.input_hashes = {"requirement": "0" * 64}
        elif tamper == "dag":
            run.dag = {}
        elif tamper == "missing":
            session.delete(node)
        else:
            node.status = "PENDING"
    with pytest.raises(ValueError):
        engine.execute(run_id)


def test_lock_and_identifiers(store: Store) -> None:
    with store.exclusive(), pytest.raises(ValueError, match="Another executor"):
        with Store(store.root).exclusive():
            pass
    with pytest.raises(ValueError):
        store.run_dir("../../outside")
    with pytest.raises(ValueError, match="Unknown run"):
        store.get_run("f" * 32)
    with pytest.raises(ValueError):
        Engine(store).create(" ")
    with pytest.raises(ValueError):
        Engine(store).create("x" * 10001)
    with pytest.raises(ValueError):
        Engine(store).execute("f" * 32, stop_after=0)


def test_cli_views(store: Store, capsys: pytest.CaptureFixture[str]) -> None:
    run_id = Engine(store).create("Requirement")
    Engine(store).execute(run_id)
    prefix = ["--root", str(store.root)]
    assert main([*prefix, "inspect", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASSED"
    assert main([*prefix, "trace", run_id, "--format", "mermaid"]) == 0
    assert "intake --> plan" in capsys.readouterr().out
    assert main([*prefix, "trace", run_id]) == 0
    assert "GATE_PASSED" in capsys.readouterr().out
    assert main([*prefix, "lineage", run_id]) == 0
    chain = json.loads(capsys.readouterr().out)["lineage"]
    assert chain[0]["event_type"] == "RUN_CREATED"
    assert chain[-1]["payload"]["node"] == "summary"
    assert main([*prefix, "inspect", "bad-id"]) == 1
    capsys.readouterr()
    assert main([*prefix, "run", "--requirement", "x", "--stop-after", "0"]) == 1
    capsys.readouterr()
    new_run = Engine(store).create("Not executed")
    assert main([*prefix, "lineage", new_run]) == 1


@pytest.mark.parametrize("command", ["metrics", "halt", "approve", "reject", "list-pending"])
def test_future_commands_never_report_success(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = [command] if command == "list-pending" else [command, "f" * 32]
    assert main(arguments) == 2
    assert "Unavailable in S0" in capsys.readouterr().out


def test_live_environment_adapter(monkeypatch) -> None:
    import secrets

    monkeypatch.delenv("SDLC_LLM_ENDPOINT", raising=False)
    monkeypatch.delenv("SDLC_LLM_TOKEN", raising=False)
    with pytest.raises(ValueError):
        LiveHTTPClient.from_environment()
    monkeypatch.setenv("SDLC_LLM_ENDPOINT", "https://gateway.invalid/complete")
    monkeypatch.setenv("SDLC_LLM_TOKEN", secrets.token_urlsafe(32))
    adapter = LiveHTTPClient.from_environment()
    assert adapter.client.headers["Authorization"].startswith("Bearer ")
    adapter.client.close()
