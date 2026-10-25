# Limitations and scope boundaries

## Implemented and verified

Real local service/API/migrations; persisted general DAG; concurrent tool branches
and joins; schema/command gates; input-bound approvals and rejection; bounded
retry/fallback; declared-file compensation with byte verification; atomic-wave
stop/resume; actual SIGKILL recovery test; transitive stale invalidation; event
lineage and reliability metrics; all three real engineering scenarios. S0 remains
regression-tested. Commands and results are in `runs/evidence/`.

## Mocked or deliberately injected

- Requirement interpretation, decomposition, architectural suggestions and code
  edits use deterministic fixtures/templates. No live autonomous coding claim.
- Scenario drivers record simulated approvals. CLI reviewer identities are
  self-asserted local labels, not authenticated organizational reviewers.
- Brownfield's first change failure is deliberate and labeled. It demonstrates
  real rollback/retry; it is not an organic security finding.
- The ambiguous demo resolves questions with explicit documented defaults; it
  does not infer enterprise business requirements.

## Partial controls / production gaps

- Scope and command policy protects trusted tool invocations, not malicious Python
  code. Network default-deny means no exposed network tool/live adapter in demo;
  it is not kernel-enforced egress filtering. Deploy in a container/OS sandbox
  before running untrusted agents or tests.
- Whole-run time budgets are checked between waves; subprocess timeouts are
  enforced. Arbitrary in-process extension code is trusted and cannot be forcibly
  stopped safely by this thread scheduler.
- Single executor per workspace, POSIX flock; no distributed leases/Windows support.
- SQLite workflow tables bootstrap with SQLAlchemy; product tables use versioned
  Alembic. Future orchestrator schema evolution needs migrations.
- JSONL torn records fail closed for manual repair; the kill-9 test covers a real
  interrupted tool step, not every possible filesystem/power-loss boundary.
- Events are append-only through the application but not tamper-proof against a
  local operator who controls SQLite and files. No external immutable audit sink.
- Artifact validation checks shapes/hashes and executed tests, not full semantic
  correctness. Replanning is explicit via API/CLI, not a filesystem watcher.
- Fallback escalates to a human and blocks; it does not autonomously invent a
  smaller safe product scope. Failure context is an exception type plus retained
  command evidence, not live-model remediation.
- Local API keys only; no corporate identity, rotation service, TLS termination,
  multi-process deployment validation or organizational RBAC.
- Public redirect path has no distributed abuse limiter. Management limits are
  per authenticated key and persist; redirect enumeration/abuse remains a risk.
- Destination validation rejects unsafe schemes, credentials, control characters,
  private literal IPs and obvious local names. No server-side destination fetch
  occurs, so this is not a server-side URL-fetch SSRF feature. DNS rebinding,
  phishing and malicious public domains need operational allowlists/moderation.
- Click events have no PII but grow without retention/pagination. SQLite serialized
  writes limit throughput. No measured production SLO or load certification.
- Explicitly permanent links use 301, so browser caching can undercount clicks and
  retain destinations after deletion; use the default 302 for managed lifecycles.
- Brownfield reporting and ambiguous headers are generated in their run workspaces;
  the baseline remains unchanged for repeatability. Review the diff and promote
  it through a real change-control process if desired.
- Tests use current locked FastAPI/Starlette with a TestClient/httpx deprecation
  warning. Tests pass; migration to the replacement client is deferred.

## Excluded under v3 priorities

Redis, Kubernetes/cloud deployment, frontend/dashboard, advanced SAST/DAST,
comprehensive independent pentest, load/chaos pipeline and compliance certification.
No vulnerabilities or external scans are fabricated. CI configuration exists but
remote GitHub CI was not run in this environment. The live gateway adapter is
implemented and transport-tested; no real provider or paid service was used.

V3 supplies sufficient product/security/docs requirements and supersedes the old
v2 references to missing sections. No extra input is needed for this scoped
submission. Human review notes remain blank in `ai-usage-and-judgment.md`.
