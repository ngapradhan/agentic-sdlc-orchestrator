# Three executable scenarios

All scenarios use the same real persisted engine, versioned reasoning templates,
scoped file tools, schema gates and real subprocess validation. Approval records
in demos are simulated and labeled. `run --scenario ...` instead stops for human
CLI decisions. Stable portable evidence locations are indexed by
`runs/evidence/submission-index.json`; each entry names its sample directory.

## Greenfield

Requirement: build REST creation, persistence, redirects and analytics.
Tasks: intake → plan → approved design → implementation || test preparation →
joined validation → security → release approval → summary.
The implementation copies real service/migration templates into an initially
empty run workspace. The separate test role writes tests concurrently. Validation
executes those tests against the sandbox's service code and real isolated SQLite
migrations. The engine unit test uses a thread barrier, and the scenario records
actual execution spans proving overlap. Status: see the passed sample and command
evidence, not a simulated console assertion.

## Brownfield

Requirement: add owner-protected daily click reporting. Expiration already exists,
so daily reporting is a genuine enhancement absent from baseline.
The codebase reasoner parses actual Python imports, functions, route decorators,
models and test paths, emitting impact analysis and a change plan. The implementer
adds `shortener/reporting.py` and `GET /api/v1/urls/{code}/report` in the sandbox.
The first attempt deliberately damages a declared file and raises; its original
bytes are restored and checked, then the retry applies the real change. Existing
API/security tests plus a new owner-isolation/reporting test run against the
modified sandbox. Inspect `workspace/change.diff`, `impact-analysis.json`,
`tests/test_reporting.py`, retry/rollback events and metrics. Baseline source is
preserved, allowing repeated demos without secretly changing their starting point.

## Ambiguous

Requirement: “Make the URL shortener enterprise-ready and secure.”
Intake emits questions about measurable SLOs, identity/retention and security scope.
A two-reviewer clarification checkpoint blocks before design. In offline demo
mode the recorded decision chooses only nosniff/no-referrer response headers and
regression coverage. SSO, availability architecture and compliance are excluded.
After the clarification, the driver revises the plan artifact; transitive
invalidation and a REPLAN event require a new design decision bound to the revised
inputs. The tool writes middleware and a new test, then actual validation runs.
`approved-scope.json` records assumptions and exclusions. This is an explicit
demo decision, not evidence that an LLM inferred an enterprise specification.

## Trace and gate review

In each sample, inspect `dag.json`, `dag.mmd`, `events.jsonl`, `state.json`,
`approvals.json`, `metrics.json`, `artifacts/`, `commands/` and
`scenario-summary.json`. Commands include timestamp/cwd/argv/exit/output path.
Historical absolute paths describe the machine that executed the command; copied
logs in the sample's `commands/` directory remain usable after cloning elsewhere.

The gate sequence is entry dependencies/approval → role execution → JSON Schema
artifact gate; validation/security roles additionally require real command exit 0.
Release cannot run before validation/security pass and its own recorded approval.
No failed/blocked workflow is silently reported as complete by the demo driver.
