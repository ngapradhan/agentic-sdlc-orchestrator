# Controlled Agentic SDLC — URL Shortener

A locally runnable URL shortener and an offline SDLC orchestration prototype.
The orchestrator is the main deliverable: actual dependencies, parallel tasks,
entry/exit gates, persisted state, approvals, retry/rollback, safe-stop, replanning,
lineage and event-derived reliability metrics. S0 is preserved as a bootstrap demo.

## Setup and run

Prerequisites: **Python 3.11+, uv, make, Git, macOS or Linux**. Verified in this
session with Python 3.12. First setup downloads pinned dependencies; workflows
and tests use no cloud resources or model API keys.

```sh
make quickstart                 # install, real HTTP smoke test, greenfield workflow
make serve                      # persistent local service at http://127.0.0.1:8000
```

Quickstart exits after verification. `make serve` runs until Ctrl-C and generates
`work/local-api-key` with mode 0600; it never prints the credential. Alternatively
provide your own 24+ character `SHORTENER_API_KEY` through the environment.
Database defaults to `work/service.sqlite`; override with `SHORTENER_DB`.
`SHORTENER_PORT` changes the loopback port. API docs: `/docs`; schema: `/openapi.json`.
Swagger assets use their usual external CDN; direct API calls and workflows are offline.

```sh
# In a second terminal after make serve; do not commit the generated key.
export API_KEY="$(cat work/local-api-key)"
curl -s http://127.0.0.1:8000/health
curl -s -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","alias":"interview-link"}' \
  http://127.0.0.1:8000/api/v1/urls
curl -i http://127.0.0.1:8000/interview-link
curl -s -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/v1/urls/interview-link/stats
curl -X DELETE -H "X-API-Key: $API_KEY" http://127.0.0.1:8000/api/v1/urls/interview-link
unset API_KEY
```

Management requires an API key and checks link ownership. Redirects are public.
Creation accepts optional `alias`, timezone-aware `expires_at` and `permanent`.
Default redirect: 302; explicitly permanent links: 301. Errors: 400 invalid input,
401 authentication, 404 missing/not-owned, 409 alias collision, 410 inactive,
429 per-key limit, 503 storage/allocation unavailable. Limits persist in SQLite
and ignore X-Forwarded-For. Click count and event timestamp commit with redirect.
No IP addresses, user-agent data, raw keys or destination URLs are written to logs.

## Execute scenarios

```sh
make demo-greenfield
make demo-brownfield
make demo-ambiguous
```

These run through the actual engine and real file/test tools. Each begins blocked
at an approval checkpoint; the demo driver records **SIMULATED DEMO ONLY**
decisions, then resumes. High-risk design needs two distinct reviewer labels.
No human review or production release is asserted.

- Greenfield copies versioned service and test templates into an empty workspace,
  concurrently, then executes API/security tests and release gates.
- Brownfield analyzes the real baseline with Python ASTs, adds owner-protected
  daily-click reporting, intentionally fails a sandbox change, verifies rollback,
  retries, then runs old tests and the new reporting tests.
- Ambiguous starts with “enterprise-ready and secure,” lists unanswered questions,
  blocks, records a demo scope decision, replans to two security response headers,
  requires fresh approval of revised inputs, implements and validates that slice.

Run outputs: `runs/<run_id>/` includes DAG JSON/Mermaid, events, state, approvals,
artifacts, command outputs, metrics and scenario summary. Submission samples and
hash manifest are under `runs/evidence/scenarios/` and `submission-index.json`.
See [scenario details](docs/scenarios.md).

## Human-controlled CLI

```sh
.venv/bin/python -m orchestrator.cli run --scenario ambiguous
# Output includes run ID; workflow stays BLOCKED until explicit decisions.
.venv/bin/python -m orchestrator.cli inspect RUN_ID
.venv/bin/python -m orchestrator.cli list-pending --run-id RUN_ID
.venv/bin/python -m orchestrator.cli approve RUN_ID clarification --reviewer alice --reason 'Approved scoped prototype'
.venv/bin/python -m orchestrator.cli approve RUN_ID clarification --reviewer bob --reason 'Second scoped review'
.venv/bin/python -m orchestrator.cli resume RUN_ID
.venv/bin/python -m orchestrator.cli trace RUN_ID --format mermaid
.venv/bin/python -m orchestrator.cli lineage RUN_ID --node plan
.venv/bin/python -m orchestrator.cli metrics RUN_ID
.venv/bin/python -m orchestrator.cli halt RUN_ID
.venv/bin/python -m orchestrator.cli replan RUN_ID plan --artifact revised-plan.json
```

Approve the later design/release tasks in the same manner. `reject` uses the same
arguments and keeps execution blocked. Reviewer names are local operator assertions,
not authenticated corporate identities. Run/inspect/resume/trace also support S0:
`make demo-bootstrap` or `run --requirement 'Build a URL shortener' --stop-after 1`.
Successful commands exit 0 even when returning BLOCKED/HALTED state; inspect status.
Invalid operations exit 1; controls unavailable to legacy S0 return 2.

## What is real and what is mocked

**Real:** scheduler, concurrent tools, file writes, migrations, HTTP API, tests,
transactions, approval blocking, rollback verification, kill-9 recovery, artifact
validation/hashes, downstream invalidation, audit and metrics.

**Deterministic reasoning:** `MockLLM` preserves S0; `OfflineReasoner` implements
`LLMClient` using versioned role fixtures. Scenario decomposition and scope options
are templates. These do not independently understand arbitrary new requirements.
Implementation tools copy or patch versioned code; they do not claim live model
code generation. Test preparation is a separate role but also uses fixed tests.

`LiveHTTPClient.from_environment()` implements an optional HTTPS JSON-gateway
adapter using `SDLC_LLM_ENDPOINT`/`SDLC_LLM_TOKEN`. Its request/response behavior is
tested with MockTransport; **no live provider was exercised**. The demo CLI cannot
select it or perform network tools. A trusted Python integrator can pass an
LLMClient to `action_registry`; output still goes through the same real gates.
Keep credentials out of requirements and command arguments.

## Validate and review

```sh
make check                      # lint, strict types, full tests + coverage
make security
make contract
make smoke                      # actual HTTP process
make evidence                   # captures checks and all 3 scenarios
.venv/bin/python scripts/collect_submission.py
.venv/bin/python scripts/acceptance.py
```

[Architecture](docs/architecture.md) · [Testing](docs/testing.md) ·
[Engineering summary and coverage table](docs/engineering-summary.md) ·
[Threat model](docs/threat-model.md) · [Limitations](docs/limitations.md) ·
[5–10 minute demo](docs/demo.md) · [Progress](PROGRESS.md).

This is a defensible local prototype, not a production deployment or security
certification. The policy constrains trusted tool calls; it is not an OS sandbox.
