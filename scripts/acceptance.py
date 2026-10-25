"""Fail if submission claims point to missing evidence or failed scenario gates."""

import hashlib
import json
from pathlib import Path


def main() -> None:
    index = json.loads(Path("runs/evidence/submission-index.json").read_text())
    for relative, expected in index["files"].items():
        path = Path(relative)
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative
    for scenario, record in index["scenarios"].items():
        directory = Path(record["path"])
        state = json.loads((directory / "state.json").read_text())
        assert state["status"] == "PASSED"
        assert all(n["status"] == "PASSED" for n in state["nodes"])
        assert all(a["simulated"] for a in state["approvals"])
        commands = [json.loads(p.read_text()) for p in (directory / "commands").glob("*.json")]
        assert len(commands) >= 2
        assert all(c["exit_code"] == 0 for c in commands)
        assert all((directory / "commands" / Path(c["output"]).name).is_file() for c in commands)
        if scenario == "brownfield":
            metrics = json.loads((directory / "metrics.json").read_text())
            assert metrics["rollback_count"] >= 1 and metrics["retry_count"] >= 1
            assert (directory / "workspace/change.diff").is_file()
        if scenario == "ambiguous":
            events = [
                json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()
            ]
            assert any(e["event_type"] == "REPLAN" for e in events)
            assert any(e["event_type"] == "APPROVAL_REQUESTED" for e in events)
    for path in [
        "README.md",
        "PROGRESS.md",
        "docs/architecture.md",
        "docs/scenarios.md",
        "docs/testing.md",
        "docs/limitations.md",
        "docs/engineering-summary.md",
        "docs/demo.md",
        "docs/threat-model.md",
    ]:
        assert Path(path).is_file(), path
    coverage = json.loads(Path("runs/evidence/coverage.json").read_text())
    assert coverage["totals"]["percent_covered"] >= 80
    print(
        json.dumps(
            {
                "acceptance_evidence": "PASSED",
                "scenarios": 3,
                "file_hashes_verified": len(index["files"]),
                "coverage": round(coverage["totals"]["percent_covered"], 2),
                "scope": "Local prototype; see limitations, no human release sign-off claimed",
            }
        )
    )


if __name__ == "__main__":
    main()
