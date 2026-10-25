"""Three workflows with deterministic reasoning and real sandboxed engineering tools."""

from __future__ import annotations

import ast
import difflib
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from orchestrator.llm import LLMClient
from orchestrator.policy import Tools
from orchestrator.reasoning import OfflineReasoner
from orchestrator.store import Store
from orchestrator.validation import Json, digest
from orchestrator.workflow import Action, TaskSpec, Workflow

REPO = Path(__file__).resolve().parents[1]
SOURCE_FILES = [
    "shortener/__init__.py",
    "shortener/app.py",
    "shortener/models.py",
    "shortener/database.py",
    "shortener/__main__.py",
    "alembic.ini",
    "alembic/env.py",
    "alembic/versions/0001_links.py",
]
TEST_FILES = ["tests/test_service.py", "tests/security/test_regressions.py"]
REQUIREMENTS = {
    "greenfield": "Build a URL shortener with REST APIs, persistence, redirection, and analytics.",
    "brownfield": "Add owner-protected daily click reporting to the existing URL shortener.",
    "ambiguous": "Make the URL shortener enterprise-ready and secure.",
}
REPORT_MODULE = '''"""Brownfield enhancement: owner-scoped daily click aggregation."""
from collections import Counter
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from shortener.models import Click

def daily_report(session: Session, code: str) -> dict[str, object]:
    timestamps = session.scalars(select(Click.timestamp).where(Click.code == code)).all()
    counts = Counter(datetime.fromtimestamp(t, UTC).date().isoformat() for t in timestamps)
    return {"code": code, "total": len(timestamps), "daily": dict(sorted(counts.items()))}
'''
REPORT_ROUTE = """
    @app.get("/api/v1/urls/{short_code}/report")
    def report(short_code: str, session: Session = Depends(db),
               owner: str = Depends(principal)) -> dict[str, object]:
        from shortener.reporting import daily_report
        owned(session, short_code, owner)
        return daily_report(session, short_code)

"""
REPORT_TEST = """import secrets
from fastapi.testclient import TestClient
from shortener.app import Settings, create_app

def test_daily_reporting_and_owner_isolation(tmp_path):
    keys = (secrets.token_urlsafe(32), secrets.token_urlsafe(32))
    app = create_app(Settings(f"sqlite:///{tmp_path / 'report.sqlite'}", keys))
    with TestClient(app) as client:
        h = {"X-API-Key": keys[0]}
        created = client.post('/api/v1/urls', headers=h, json={"url":"https://example.com"})
        assert created.status_code == 201
        code = created.json()['code']
        path = f'/api/v1/urls/{code}/report'
        assert client.get(path, headers=h).json()['total'] == 0
        for _ in range(2):
            assert client.get('/'+code, follow_redirects=False).status_code == 302
        response = client.get(path, headers=h)
        assert response.status_code == 200
        assert response.json()['total'] == 2
        assert sum(response.json()['daily'].values()) == 2
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-API-Key":keys[1]}).status_code == 404
    app.state.engine.dispose()
"""
SCOPE_TEST = """import secrets
from fastapi.testclient import TestClient
from shortener.app import Settings, create_app

def test_approved_security_scope(tmp_path):
    settings = Settings(f"sqlite:///{tmp_path / 'scope.sqlite'}", (secrets.token_urlsafe(32),))
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get('/health')
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['referrer-policy'] == 'no-referrer'
    app.state.engine.dispose()
"""
MIDDLEWARE = """
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

"""


def action_registry(source: Path = REPO, reasoner: LLMClient | None = None) -> dict[str, Action]:
    reasoning = reasoner or OfflineReasoner()

    def think(spec: TaskSpec, tools: Tools, context: Json) -> Json:
        output = reasoning.complete(
            spec.role,
            [{"requirement": spec.config.get("requirement"), "dependencies": context}],
            {"type": "object"},
        )
        if spec.role == "intake":
            output["ambiguous"] = spec.config.get("ambiguous", False)
        if spec.role == "planner":
            output["approved_scope"] = spec.config.get("scope", "core API and validation")
            output["upstream_context"] = context
        tools.write(spec.writes[0], json.dumps(output, indent=2))
        return output

    def inspect_code(spec: TaskSpec, tools: Tools, context: Json) -> Json:
        modules = []
        for path in sorted(tools.workspace.glob("shortener/*.py")):
            tree = ast.parse(path.read_text())
            modules.append(
                {
                    "path": str(path.relative_to(tools.workspace)),
                    "sha256": digest(path.read_text()),
                    "imports": [
                        ast.unparse(n)
                        for n in ast.walk(tree)
                        if isinstance(n, (ast.Import, ast.ImportFrom))
                    ],
                    "functions": [
                        n.name
                        for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ],
                    "classes": [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)],
                    "routes": [
                        ast.unparse(d)
                        for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        for d in n.decorator_list
                        if isinstance(d, ast.Call)
                    ],
                }
            )
        result = {
            "modules": modules,
            "tests": [
                str(p.relative_to(tools.workspace)) for p in tools.workspace.glob("tests/**/*.py")
            ],
            "impact": ["shortener/app.py", "shortener/reporting.py", "tests/test_reporting.py"],
            "database": "Existing links and clicks tables; no schema change required",
            "change_plan": "Add authenticated owner-scoped daily reporting; preserve old tests",
        }
        tools.write("impact-analysis.json", json.dumps(result, indent=2))
        return result

    def implement(spec: TaskSpec, tools: Tools, context: Json) -> Json:
        started = time.time()
        scenario = spec.config["scenario"]
        if scenario == "greenfield":
            files = tools.copy_files(source, SOURCE_FILES)
        elif scenario == "brownfield":
            before = tools.path("shortener/app.py").read_text()
            if context["attempt"] == 1:
                tools.write("shortener/app.py", "# injected failed change\n")
                raise RuntimeError("Documented failure injection: rollback must restore baseline")
            if "def report(" in before:
                raise ValueError("Enhancement already present; genuine before/after required")
            after = before.replace("    return app\n", REPORT_ROUTE + "    return app\n")
            files = [
                tools.write("shortener/app.py", after),
                tools.write("shortener/reporting.py", REPORT_MODULE),
            ]
            tools.write(
                "change.diff",
                "".join(
                    difflib.unified_diff(
                        before.splitlines(True),
                        after.splitlines(True),
                        fromfile="baseline/shortener/app.py",
                        tofile="enhanced/shortener/app.py",
                    )
                ),
            )
        else:
            before = tools.path("shortener/app.py").read_text()
            if "def security_headers(" not in before:
                after = before.replace("    return app\n", MIDDLEWARE + "    return app\n")
            else:
                after = before
            files = [tools.write("shortener/app.py", after)]
            tools.write(
                "approved-scope.json",
                json.dumps(
                    {
                        "scope": "nosniff and no-referrer response headers plus regression tests",
                        "assumptions": ["local single-tenant demonstration"],
                        "excluded": [
                            "SSO",
                            "compliance certification",
                            "HA deployment",
                            "enterprise SLA",
                        ],
                    }
                ),
            )
        time.sleep(0.04)
        return {
            "files": files,
            "execution_started": started,
            "execution_finished": time.time(),
            "generation": "Versioned source templates copied/patched through scoped file tool",
            "retry_context_received": context.get("previous_failure"),
        }

    def prepare_tests(spec: TaskSpec, tools: Tools, context: Json) -> Json:
        started = time.time()
        files = tools.copy_files(source, TEST_FILES)
        if spec.config["scenario"] == "brownfield":
            files.append(tools.write("tests/test_reporting.py", REPORT_TEST))
        if spec.config["scenario"] == "ambiguous":
            files.append(tools.write("tests/test_scope.py", SCOPE_TEST))
        time.sleep(0.04)
        return {"files": files, "execution_started": started, "execution_finished": time.time()}

    def validate_code(spec: TaskSpec, tools: Tools, context: Json) -> Json:
        arguments = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "tests"]
        result = tools.command(arguments, f"validation-attempt-{context['attempt']}")
        return {
            "validation": result,
            "barrier_inputs": sorted(
                k for k in context if k not in {"attempt", "previous_failure"}
            ),
        }

    def security(spec: TaskSpec, tools: Tools, context: Json) -> Json:
        result = tools.command(
            [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "tests/security"],
            "security-regression",
        )
        return {
            "validation": result,
            "scope": "Executable security regressions; not a full pentest",
            "findings": "See actual test output; no invented findings",
        }

    def review(spec: TaskSpec, tools: Tools, context: Json) -> Json:
        result = {
            "release": "Ready for local prototype review only",
            "dependencies": sorted(k for k in context if k not in {"attempt", "previous_failure"}),
            "mocked": "Reasoning templates; approval records explicitly label demo decisions",
            "real": "File writes, commands, tests, database state and gates",
        }
        tools.write(spec.writes[0], json.dumps(result, indent=2))
        return result

    return {
        "intake": think,
        "planner": think,
        "design": think,
        "codebase_reasoner": inspect_code,
        "implementer": implement,
        "test_author": prepare_tests,
        "validator": validate_code,
        "security": security,
        "release": review,
        "documenter": review,
    }


def specs_for(scenario: str, requirement: str | None = None) -> list[TaskSpec]:
    if scenario not in REQUIREMENTS:
        raise ValueError("Unknown scenario")
    requirement = requirement or REQUIREMENTS[scenario]
    specs = [
        TaskSpec(
            "intake",
            "intake",
            writes=["requirements.json"],
            config={"requirement": requirement, "ambiguous": scenario == "ambiguous"},
        )
    ]
    if scenario == "ambiguous":
        specs.append(
            TaskSpec(
                "clarification",
                "design",
                ["intake"],
                risk="high",
                writes=["clarification.json"],
                config={"requirement": requirement},
            )
        )
    prior = "clarification" if scenario == "ambiguous" else "intake"
    if scenario == "brownfield":
        specs.append(
            TaskSpec(
                "codebase_reasoning", "codebase_reasoner", [prior], writes=["impact-analysis.json"]
            )
        )
        prior = "codebase_reasoning"
    specs += [
        TaskSpec(
            "plan",
            "planner",
            [prior],
            writes=["plan.json"],
            config={
                "scope": "security response headers" if scenario == "ambiguous" else requirement
            },
        ),
        TaskSpec("design", "design", ["plan"], risk="high", writes=["design.json"]),
    ]
    changes = (
        SOURCE_FILES
        if scenario == "greenfield"
        else ["shortener/app.py", "shortener/reporting.py", "change.diff"]
        if scenario == "brownfield"
        else ["shortener/app.py", "approved-scope.json"]
    )
    tests = TEST_FILES + (
        ["tests/test_reporting.py"]
        if scenario == "brownfield"
        else ["tests/test_scope.py"]
        if scenario == "ambiguous"
        else []
    )
    specs += [
        TaskSpec(
            "implementation",
            "implementer",
            ["design"],
            writes=changes,
            config={"scenario": scenario},
        ),
        TaskSpec(
            "test_preparation",
            "test_author",
            ["design"],
            writes=tests,
            config={"scenario": scenario},
        ),
        TaskSpec("validation", "validator", ["implementation", "test_preparation"]),
        TaskSpec("security", "security", ["validation"]),
        TaskSpec(
            "release", "release", ["security"], risk="release", writes=["release-review.json"]
        ),
        TaskSpec("summary", "documenter", ["release"], writes=["engineering-summary.json"]),
    ]
    return specs


def new_scenario(engine: Workflow, scenario: str, requirement: str | None = None) -> str:
    run_id = engine.create(
        requirement or REQUIREMENTS[scenario], specs_for(scenario, requirement), scenario
    )
    if scenario != "greenfield":
        engine.tools(run_id).copy_files(REPO, SOURCE_FILES + TEST_FILES)
        engine.record(
            run_id,
            "BASELINE_CAPTURED",
            {"files": SOURCE_FILES},
            "Copied actual existing application into isolated scenario workspace",
        )
    return run_id


def demo(scenario: str, root: Path = Path("runs")) -> Json:
    engine = Workflow(Store(root), action_registry(), REPO / "policy.yaml")
    run_id = new_scenario(engine, scenario)
    state = engine.execute(run_id)
    initial_blocked = state["status"] == "BLOCKED"
    clarification_replan = False
    for _ in range(12):
        if state["status"] == "PASSED":
            break
        pending = [n for n in state["nodes"] if n["status"] == "AWAITING_APPROVAL"]
        if not pending:
            raise ValueError(f"Workflow blocked without approval task; inspect {run_id}")
        for task in pending:
            required = engine.policy["approvals"][task["spec"]["risk"]]
            for index in range(required):
                engine.decide(
                    run_id,
                    task["id"],
                    f"demo-reviewer-{index + 1}",
                    "approve",
                    "SIMULATED DEMO DECISION: approve isolated prototype scope only",
                    True,
                )
        state = engine.execute(run_id)
        if (
            scenario == "ambiguous"
            and not clarification_replan
            and any(n["id"] == "plan" and n["status"] == "PASSED" for n in state["nodes"])
        ):
            engine.replan(
                run_id,
                "plan",
                {
                    "approved_scope": "nosniff and no-referrer headers",
                    "decision": "SIMULATED explicit scope; SSO/HA/compliance excluded",
                    "questions_resolved_by_demo_defaults": True,
                },
            )
            clarification_replan = True
            state = engine.execute(run_id)
    if state["status"] != "PASSED":
        raise ValueError("Scenario did not reach release")
    engine.sync(run_id)
    directory = engine.store.run_dir(run_id)
    summary = {
        "run_id": run_id,
        "scenario": scenario,
        "status": state["status"],
        "initially_blocked_without_approval": initial_blocked,
        "reasoning": "deterministic templates",
        "approvals": "SIMULATED DEMO ONLY",
        "workspace": str(directory / "workspace"),
        "metrics": engine.metrics(run_id),
        "evidence": str(directory),
        "tasks": [asdict(s) for s in specs_for(scenario)],
    }
    engine.store.write_json(directory / "scenario-summary.json", summary)
    index_path = root / "evidence" / f"latest-{scenario}.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    engine.store.write_json(index_path, summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "tasks"}, indent=2))
    return summary
