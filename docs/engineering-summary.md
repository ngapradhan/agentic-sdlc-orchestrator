# Final engineering summary

## Objective and scope

Deliver a reviewable, locally runnable prototype that turns configured requirements
into actual engineering artifacts and validation evidence under explicit controls.
The reference assignment's core workflow requirements are implemented at practical
prototype depth. V3 prioritizes these capabilities and three scenarios over Redis,
cloud, dashboards and comprehensive penetration testing.

The supplied noon-IST cutoff on 25 October had already passed when continuation
was requested; no on-time submission claim is made. This repository is prepared
for local review. No external deployment, message or submission was performed.

## Implementation and decisions

- Preserve S0 and reuse SQLAlchemy runs/events, JSONL projection and hashing; new
  general task/approval tables and one CLI avoid discarding verified work.
- Use actual bounded concurrent role tools with declared file effects and a join.
  Templates keep the demonstration reproducible while test/command gates remain real.
- Bind approval records to input hashes and task specs. Sensitive design requires
  two reviewer labels; demos explicitly mark decisions simulated.
- Recover failed effects by restoring declared file snapshots, verifying bytes,
  and applying bounded retries; exhausted work blocks for human escalation.
- Explicit transitive replanning invalidates dependent outcomes and approvals,
  while preserving independent work. Metrics derive from recorded observations.
- Keep the service local and small: FastAPI, SQLite/Alembic, owner-scoped API keys,
  CSPRNG identifiers, expiry, default 302, persistent quotas and click timestamps.

The baseline service is committed source; greenfield writes it through file tools.
Brownfield adds a reporting endpoint in its workspace; ambiguity implements only
approved security headers. These are actual before/after files, not narrative-only
outputs. Scope choices, generated tests and architectural suggestions are templated,
not live LLM reasoning. Human judgment notes remain for the user to fill in.

## Requirement and deliverable coverage

The portable sample root for each scenario is in `runs/evidence/submission-index.json`.
Command records are indexed by `runs/evidence/final-validation.json`. All listed
source/test/docs paths exist; acceptance verifies the packaged sample paths and
hashes. Evaluation is supported by evidence, not a production-readiness assertion.

| Original assignment requirement / deliverable | Capability and real evidence path |
| --- | --- |
| Core 1 — understand intent, ambiguity, normalization | Deterministic role templates and explicit question/scope gate; `orchestrator/reasoning.py`, `tests/test_scenarios.py`, ambiguous sample `workspace/requirements.json`, `approved-scope.json` |
| Core 2 — actionable tasks, dependencies, sequencing | Persisted TaskSpec DAG with entry/exit rules; `orchestrator/workflow.py`, each sample `dag.json`/`dag.mmd` |
| Core 3 — brownfield modules/APIs/data flows | Real AST analysis, models/routes/imports/tests and change plan; brownfield sample `workspace/impact-analysis.json`, `workspace/change.diff`, `tests/test_scenarios.py` |
| Core 4 — full SDLC coordination | Intake/planner/design/implementation/test/security/release/docs roles through one engine; all samples `state.json`, `events.jsonl`, `artifacts/` |
| Core 4 — explicit dependency graph and entry/exit gates | `TaskSpec`, `_inputs`, approvals and JSON Schema/command exit validation; `tests/test_workflow.py`, sample gate events |
| Core 4 — sequential/parallel/synchronization | Two actual threads and dependency join; `test_real_parallel_barrier`, `tests/test_scenarios.py`, branch execution-span artifacts |
| Core 4 — state, cross-stage context and decision lineage | SQLite plus artifact/input hashes and parent events; `orchestrator/store.py`, workflow tables, CLI `lineage`, sample events/artifacts |
| Core 4 — human approval checkpoints | Input-bound two-reviewer high-risk design and release decisions; `test_approval_distinct_reviewers_rejection_and_resume`, sample `approvals.json` (simulated in demo) |
| Core 4 — bounded retry and fallback | Failure context, max attempts, retry queue and blocked human escalation; `test_retry_rollback_context_and_metrics`, `test_exhaustion_fallback_stops_dependents` |
| Core 4 — rollback and safe-stop | Persisted snapshots/verified restore, interrupted recovery and HALTED waves; `test_kill9_resume_restores_interrupted_tool`, `test_safe_stop_resume_without_repeating_passed`, brownfield retry log |
| Core 4 — security/compliance/change-control policy | Enforced trusted-tool paths/commands/budgets and approval checks; `policy.yaml`, `orchestrator/policy.py`, policy-denial tests; limitations describe missing OS/organizational controls |
| Core 4 — audit, traceability and observability | Actual events with rationale, command output and artifact hashes; each sample `events.jsonl`, `commands/`, `state.json` |
| Core 4 — success/retry/rollback/MTTR/latency metrics | Event-derived `metrics()`, each sample `metrics.json`, `test_retry_rollback_context_and_metrics`; null MTTR when unobserved |
| Core 4 — dynamic upstream replanning/governance | Descendant invalidation and reapproval; `test_replan_only_descendants_and_reapproval`, ambiguous sample REPLAN event |
| Core 5 — code/API/schema/tests/documentation | Real service, Alembic, OpenAPI 3.1, contracts and API tests; `shortener/`, `alembic/`, `tests/test_service.py`, `tests/test_contract.py`, docs |
| Core 6 — risks/trade-offs/failure scenarios/guardrails | `docs/threat-model.md`, `docs/decision-log.md`, `docs/limitations.md`, negative tests and injected brownfield failure |
| Core 7 — controlled agent autonomy and human oversight | Real scoped tool execution, blocked approval, explicit demo labels; `orchestrator/policy.py`, approval tests; reviewer authentication remains a prototype limitation |
| Core 8 — final plan/rationale/artifacts/risks/assumptions/limitations | This summary, architecture, decisions, limitations and actual command/sample indices |
| Deliverable — working end-to-end prototype | `make quickstart`, HTTP smoke, three scenario commands; final command records and fresh-clone evidence |
| Deliverable — architecture overview/model/control flow/decisions | `docs/architecture.md`, `docs/decision-log.md`, sample DAGs |
| Deliverable — greenfield scenario | `make demo-greenfield`; greenfield sample + validation/security logs |
| Deliverable — brownfield scenario | `make demo-brownfield`; brownfield sample + real code diff/new tests/rollback |
| Deliverable — ambiguous scenario | `make demo-ambiguous`; ambiguous sample + approval loop/revised scope |
| Deliverable — setup instructions | `README.md`, `Makefile`, `uv.lock`, fresh-clone quickstart evidence |
| Deliverable — testing approach, limitations and trade-offs | `docs/testing.md`, `docs/limitations.md`, `docs/decision-log.md`, final evidence |
| Evaluation — orchestration effectiveness | Non-linear retry/approval/replan/recovery tests and actual scenario traces |
| Evaluation — architecture/system design | Modular service/store/scheduler/tools/reasoning interfaces; architecture and decision log |
| Evaluation — decomposition/execution depth | Persisted specs, actual tool files, gates and scenario evidence; deterministic decomposition limitation explicit |
| Evaluation — output realism/quality | Working service/migrations/tests, real source diffs and command outputs; no fake model provenance |
| Evaluation — validation/risk rigor | API/contract/security/engine/scenario tests, HTTP smoke, STRIDE and negative paths |
| Evaluation — clear/defensible decisions | `docs/decision-log.md`, `docs/demo.md`, explicit assumptions/limitations |
| Evaluation — modular/testable/reliable/secure/scalable/safe change principles | Tests, transactional updates, owner checks, compensation/approvals; SQLite scale/OS sandbox gaps documented |
| Evaluation — engineering judgment | Prioritized P0/P1, preserved S0, small meaningful enhancement, truthful mocks, retained failed evidence and human-note placeholders |

## Acceptance status and conclusion

All 18 v3 acceptance categories are exercised by the service, engine and three
scenario tests/commands. “Human approval” means a genuine blocking mechanism;
recorded sample decisions are simulated, and no actual human sign-off is claimed.
Requirement interpretation/decomposition is a configured deterministic prototype,
not arbitrary autonomous understanding. Security policy is a trusted local tool
boundary, not enterprise compliance enforcement. These practical limits are
material to the review and must not be represented as production certification.

Read `docs/testing.md` and the final validation manifest for executed commands and
results. Review `docs/limitations.md` before expanding scope. Next investment should
be authenticated reviewers, OS-isolated tools, live-agent evaluation, stronger
artifact semantic gates, retention and measured service scalability.
