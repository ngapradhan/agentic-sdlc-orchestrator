import json
from pathlib import Path

import pytest

from orchestrator.cli import main
from orchestrator.scenarios import REPO, action_registry, demo, new_scenario
from orchestrator.store import Store
from orchestrator.workflow import Workflow


@pytest.mark.parametrize("scenario", ["greenfield", "brownfield", "ambiguous"])
def test_scenario_end_to_end(tmp_path: Path, scenario: str) -> None:
    result = demo(scenario, tmp_path / "runs")
    assert result["status"] == "PASSED"
    assert result["initially_blocked_without_approval"]
    directory = Path(result["evidence"])
    state = json.loads((directory / "state.json").read_text())
    assert all(n["status"] == "PASSED" for n in state["nodes"])
    assert all(a["simulated"] for a in state["approvals"])
    assert len({a["reviewer"] for a in state["approvals"] if a["task_id"] == "design"}) == 2
    for name in ["dag.json", "dag.mmd", "events.jsonl", "metrics.json", "scenario-summary.json"]:
        assert (directory / name).is_file()
    impl = json.loads((directory / "artifacts/implementation.json").read_text())["data"]
    prep = json.loads((directory / "artifacts/test_preparation.json").read_text())["data"]
    if scenario != "brownfield":
        # Brownfield's successful retry follows the initial concurrent failed attempt.
        assert max(impl["execution_started"], prep["execution_started"]) < min(
            impl["execution_finished"], prep["execution_finished"]
        )
    validation = json.loads((directory / "artifacts/validation.json").read_text())["data"]
    assert validation["validation"]["exit_code"] == 0
    if scenario == "brownfield":
        assert result["metrics"]["retry_count"] == 1
        assert result["metrics"]["rollback_count"] == 1
        assert (directory / "workspace/change.diff").read_text()
        impact = json.loads((directory / "workspace/impact-analysis.json").read_text())
        assert any("Link" in m["classes"] for m in impact["modules"])
        assert "def report(" not in (REPO / "shortener/app.py").read_text()
        assert "def report(" in (directory / "workspace/shortener/app.py").read_text()
    if scenario == "ambiguous":
        events = [
            json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()
        ]
        assert any(e["event_type"] == "REPLAN" for e in events)
        assert (directory / "workspace/approved-scope.json").exists()


def test_ambiguous_cli_blocks_and_resumes_with_recorded_decisions(tmp_path, capsys) -> None:
    root = tmp_path / "runs"
    engine = Workflow(Store(root), action_registry(), REPO / "policy.yaml")
    run_id = new_scenario(engine, "ambiguous")
    assert engine.execute(run_id)["status"] == "BLOCKED"
    prefix = ["--root", str(root)]
    assert main([*prefix, "list-pending", "--run-id", run_id]) == 0
    capsys.readouterr()
    for reviewer in ["human-test-1", "human-test-2"]:
        assert (
            main(
                [
                    *prefix,
                    "approve",
                    run_id,
                    "clarification",
                    "--reviewer",
                    reviewer,
                    "--reason",
                    "test approval, not an actual submission review",
                    "--demo",
                ]
            )
            == 0
        )
        capsys.readouterr()
    assert main([*prefix, "resume", run_id]) == 0
    state = json.loads(capsys.readouterr().out)
    assert next(n for n in state["nodes"] if n["id"] == "clarification")["status"] == "PASSED"
    assert main([*prefix, "metrics", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["approval_wait_observations"] >= 1
    assert main([*prefix, "inspect", run_id]) == 0
    capsys.readouterr()
    assert main([*prefix, "trace", run_id, "--format", "mermaid"]) == 0
    assert "implementation --> validation" in capsys.readouterr().out
    assert main([*prefix, "lineage", run_id, "--node", "plan"]) == 0
    assert json.loads(capsys.readouterr().out)["lineage"][0]["event_type"] == "RUN_CREATED"
