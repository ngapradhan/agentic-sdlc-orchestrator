"""Build exact command and requirement/evidence indices; verify every referenced path."""

import json
from pathlib import Path


def main() -> None:
    evidence = Path("runs/evidence")
    commands = {}
    for name in [
        "final-checks",
        "final-security",
        "final-contract",
        "final-http",
        "final-greenfield",
        "final-brownfield",
        "final-ambiguous",
        "final-collect",
        "final-acceptance",
        "final-clean-quickstart",
        "final-clean-checks",
        "final-clean-acceptance",
        "final-packaging-lint",
        "final-dependencies",
    ]:
        records = sorted(evidence.glob(name + "-*.json"))
        if records:
            path = records[-1]
            data = json.loads(path.read_text())
            if data["exit_code"] != 0:
                raise ValueError(f"Latest {name} command failed")
            commands[name] = {
                "record": str(path),
                "command": data["command"],
                "exit_code": data["exit_code"],
                "output": data["output_path"],
            }
    scenarios = json.loads((evidence / "submission-index.json").read_text())["scenarios"]
    green = scenarios["greenfield"]["path"]
    brown = scenarios["brownfield"]["path"]
    ambiguous = scenarios["ambiguous"]["path"]
    checks = commands["final-checks"]["record"]
    rows = [
        (
            "Core 1 Requirement understanding",
            "prototype-template",
            [
                ambiguous + "/workspace/requirements.json",
                ambiguous + "/workspace/approved-scope.json",
            ],
        ),
        (
            "Core 2 Task decomposition",
            "prototype-template-real-DAG",
            [green + "/dag.json", green + "/state.json"],
        ),
        (
            "Core 3 Brownfield codebase reasoning",
            "verified-AST-analysis",
            [brown + "/workspace/impact-analysis.json", brown + "/workspace/change.diff"],
        ),
        (
            "Core 4 SDLC coordination",
            "verified",
            [green + "/events.jsonl", green + "/artifacts/summary.json"],
        ),
        (
            "Core 4 Explicit graph and gates",
            "verified",
            [green + "/dag.json", green + "/commands", checks],
        ),
        (
            "Core 4 Sequential parallel synchronization",
            "verified",
            [
                "tests/test_workflow.py",
                green + "/artifacts/implementation.json",
                green + "/artifacts/test_preparation.json",
                checks,
            ],
        ),
        (
            "Core 4 Context state decision lineage",
            "verified",
            [
                "orchestrator/store.py",
                green + "/events.jsonl",
                green + "/artifacts/validation.json",
            ],
        ),
        (
            "Core 4 Approval checkpoints",
            "verified-mechanism-demo-decisions",
            [green + "/approvals.json", "tests/test_workflow.py", checks],
        ),
        (
            "Core 4 Retry fallback",
            "verified",
            ["tests/test_workflow.py", brown + "/events.jsonl", checks],
        ),
        (
            "Core 4 Rollback safe-stop recovery",
            "verified",
            ["tests/test_workflow.py", brown + "/events.jsonl", checks],
        ),
        (
            "Core 4 Security compliance change control",
            "partial-trusted-local-policy",
            ["policy.yaml", "orchestrator/policy.py", "docs/limitations.md", checks],
        ),
        (
            "Core 4 Audit observability traceability",
            "verified-local",
            [green + "/events.jsonl", green + "/commands", green + "/state.json"],
        ),
        (
            "Core 4 Reliability metrics",
            "verified",
            [brown + "/metrics.json", "tests/test_workflow.py", checks],
        ),
        (
            "Core 4 Dynamic replanning",
            "verified",
            [ambiguous + "/events.jsonl", "tests/test_workflow.py", checks],
        ),
        (
            "Core 5 Engineering output generation",
            "verified-template-tools",
            [
                "shortener/app.py",
                "alembic/versions/0001_links.py",
                "tests/test_contract.py",
                checks,
            ],
        ),
        (
            "Core 6 Validation risk control",
            "verified-prototype",
            ["docs/threat-model.md", "docs/decision-log.md", commands["final-security"]["record"]],
        ),
        (
            "Core 7 Controlled autonomy",
            "verified-local-mechanism",
            ["orchestrator/policy.py", green + "/approvals.json", "docs/limitations.md"],
        ),
        (
            "Core 8 Engineering summary",
            "provided",
            ["docs/engineering-summary.md", "docs/limitations.md"],
        ),
        (
            "Deliverable Runnable prototype",
            "verified",
            [commands["final-http"]["record"], commands["final-greenfield"]["record"], "Makefile"],
        ),
        (
            "Deliverable Architecture overview",
            "provided",
            ["docs/architecture.md", "docs/decision-log.md"],
        ),
        (
            "Deliverable Three scenarios",
            "verified",
            [
                commands["final-greenfield"]["record"],
                commands["final-brownfield"]["record"],
                commands["final-ambiguous"]["record"],
                "docs/scenarios.md",
            ],
        ),
        ("Deliverable Setup", "provided-and-smoke-verified", ["README.md", "uv.lock", "Makefile"]),
        (
            "Deliverable Testing limitations tradeoffs",
            "provided",
            ["docs/testing.md", "docs/limitations.md", "docs/decision-log.md", checks],
        ),
    ]
    evaluations = {
        "Orchestration effectiveness": ["tests/test_workflow.py", checks],
        "Architecture system design quality": ["docs/architecture.md", "docs/decision-log.md"],
        "Decomposition execution depth": [green + "/dag.json", brown + "/workspace/change.diff"],
        "Output realism quality": ["shortener/app.py", checks, commands["final-http"]["record"]],
        "Validation risk rigor": ["docs/threat-model.md", checks],
        "Decision clarity defensibility": ["docs/decision-log.md", "docs/demo.md"],
        "Core engineering principles": ["docs/architecture.md", "docs/limitations.md", checks],
        "Engineering judgment": ["docs/ai-usage-and-judgment.md", "docs/limitations.md"],
    }
    rows.extend(
        ("Evaluation " + name, "reviewer-assessment-supported", paths)
        for name, paths in evaluations.items()
    )
    coverage = []
    for criterion, status, paths in rows:
        for path in paths:
            if not Path(path).exists():
                raise ValueError(f"Missing criterion evidence: {path}")
        coverage.append({"criterion": criterion, "status": status, "evidence": paths})
    (evidence / "requirement-coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
    manifest = {
        "commands": commands,
        "scenarios": scenarios,
        "requirement_mapping": "runs/evidence/requirement-coverage.json",
        "coverage_percent": json.loads((evidence / "coverage.json").read_text())["totals"][
            "percent_covered"
        ],
        "scope": (
            "Verified local prototype; deterministic reasoning, "
            "simulated demo approvals; see limitations"
        ),
    }
    (evidence / "final-validation.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "indexed_commands": len(commands),
                "mapped_requirements": len(coverage),
                "all_evidence_paths_exist": True,
            }
        )
    )


if __name__ == "__main__":
    main()
