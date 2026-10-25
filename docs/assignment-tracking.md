# Historical S0 criterion tracking

Superseded by `docs/engineering-summary.md` and the verified
`runs/evidence/requirement-coverage.json` after V3 continuation.

## Original S0 ledger

This is a scope ledger, not the final evidence gate. Every criterion remains in
scope for S8. Pending rows are not satisfied by the existence of this document.

| Assignment criterion | S0 evidence or explicit pending stage |
| --- | --- |
| Core 1: interpret intent, ambiguity, normalization | Fixture intake only; real ambiguity processing S1/S6 |
| Core 2: actionable tasks/dependencies/sequencing | `orchestrator/engine.py` fixed three-node DAG; decomposition S1/S3 |
| Core 3: brownfield impacted modules/APIs/data flows | Pending S5 real codebase analysis |
| Core 4: full SDLC coordination | Bootstrap only; S1–S6 |
| Core 4: explicit graph/entry/exit gates | `engine.py`, local schemas, `tests/test_bootstrap.py` |
| Core 4: sequential/parallel synchronization | Sequential S0; parallel barriers S1 |
| Core 4: context/state and lineage | SQLite store, input hashes, CLI lineage; richer context S1 |
| Core 4: approval checkpoints and autonomy | Pending S1; no fabricated approvals |
| Core 4: retry/fallback/rollback/safe-stop | Explicit between-node pause only; remaining controls S1 |
| Core 4: security/compliance/change-control policy | `policy.yaml` marked unenforced; enforcement S1, scans S7 |
| Core 4: observability/traceability | JSONL events + gate/artifact hashes; reliability metrics S1 |
| Core 4: success/retry/rollback/MTTR/latency metrics | Pending S1 and repeated scenario execution |
| Core 4: dynamic re-planning and governance | Pending S1/S3–S6 |
| Core 5: production-quality code/API/schema/tests/docs | S0 infrastructure code/tests/docs; product/OpenAPI S2 |
| Core 6: risks/trade-offs/failure scenarios/guardrails | Decision log, limitations, corruption/failure tests; STRIDE S4 |
| Core 7: agents execute; human oversight/approvals | Static MockLLM seam; no sandboxed tool agents yet; S1/S2 |
| Core 8: final summary including rationale/artifacts/risks/assumptions | S0 report only; final summary S8 |
| Deliverable: runnable end-to-end prototype | Bootstrap runnable; full engineering outcome S3–S8 |
| Deliverable: architecture/components/model/flow/decisions | `architecture.md`, `decision-log.md`; extend with each stage |
| Deliverable: greenfield/brownfield/ambiguous scenarios | Pending S3/S5/S6 |
| Deliverable: setup instructions | README, `make quickstart`, `uv.lock` |
| Deliverable: tests/limitations/trade-offs | S0 tests + limitations + decision log; product suite S2–S7 |
| Evaluation: effectiveness of orchestration | S0 persistence/gates evidence only; non-linearity S1–S6 |
| Evaluation: architecture/system design | Architecture/decision log; full design S1/S2 |
| Evaluation: decomposition/execution depth | Bootstrap scope only; S1/S3–S6 |
| Evaluation: realism/quality of outputs | Real engine; fixture outputs labeled; service code S2 |
| Evaluation: validation/risk rigor | Negative tests and stored command results; security/load S4/S7 |
| Evaluation: clarity/defensibility | Decision log, honest mock boundary, staged limitations |
| Evaluation: modular/testable/reliable/secure/scalable/safe changes | S0 tests and transaction boundaries; approvals/parallelism/security pending |
| Evaluation: engineering judgment | Explicit scope/trade-offs and human-review placeholders |

No employer-specific source text is reproduced. The separate user request adds
more detailed Must items, all tracked by `PROGRESS.md` and `limitations.md`.
