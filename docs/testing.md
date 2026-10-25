# Testing and execution evidence

The S0 baseline was re-executed in this session before extension: 27 tests passed,
with lint/type checks. See `runs/evidence/v3-baseline-20261025T171231601803Z.json`.

Current suite covers the service, general engine, preserved S0, security and
OpenAPI contracts. The final command records and logs are the authority for exact
counts, versions, exit status, time and output. The latest final-checks record is
listed in `runs/evidence/final-validation.json` after packaging.

| Command | Scope / expected artifact |
| --- | --- |
| `make check` | Ruff, strict mypy for both packages, all tests and per-module coverage |
| `make security` | Executable URL/alias/auth/error-disclosure security regressions |
| `make contract` | OpenAPI 3.1, protected management declaration, real response schemas/statuses |
| `make smoke` | Real Uvicorn process, loopback HTTP create/redirect/stats/delete and key permissions |
| `make demo-greenfield` | Real sandbox build, concurrent branches, joined validation and approvals |
| `make demo-brownfield` | AST analysis, new route/module/test, failed change compensation and retry |
| `make demo-ambiguous` | Block/decision/resume/replan/scoped change with validation |
| `scripts/acceptance.py` | All sample files exist, hashes match, scenario gates/command evidence pass |

Service tests use isolated real file SQLite databases initialized through Alembic.
They verify auth and owner separation, expiry/deletion, duplicate aliases, input
abuse, deterministic collision injection, persistent per-key quotas despite proxy
header changes, atomic concurrent clicks, storage failures, restart persistence,
OpenAPI and migration downgrade/re-upgrade. Downgrade is tested only on disposable
DBs; it intentionally removes service tables and is not an operational backup.

Engine tests verify cycles/missing dependencies, actual parallel barrier, joins,
blocked approval and distinct reviewers, rejection, failure context, exact retry
limits, fallback, byte-verified restore/removal, SIGKILL and fresh-object recovery,
safe-stop, transitive invalidation with unaffected-node preservation, input-bound
reapproval, audit/lineage and event-derived metrics. Each scenario has an E2E test
executing real commands against its sandbox. Source and scenario tests are trusted
code, as documented in limitations.

Before final packaging, the full suite passed with 97 tests and 93.15% total
statement+branch coverage; `shortener/app.py` was 99.44%. Final evidence may supersede
these numbers if additional checks change them. The executable server entrypoint
is tested by the separate HTTP smoke and is outside the in-process coverage data.

One TestClient/httpx deprecation warning is retained. No test warning is hidden.
CI config runs the checks on Python 3.11/3.12, but remote CI has not been executed.
Local verification uses Python 3.12; other platform claims are limited accordingly.

Earlier failed evidence is retained: an initial S0 type issue, a brownfield timing
assertion that incorrectly compared the successful retry to an earlier branch,
and the first server smoke before refreshing the editable package after adding
`shortener`. Their fixes and later passing outputs are visible; no evidence was
fabricated or replaced to conceal a failure.

## Fresh setup verification

Runtime source commit `221dd6b` was cloned with `--no-local` into a new directory.
`make quickstart` created a fresh Python 3.12 virtual environment and passed the
actual HTTP smoke plus greenfield workflow. `make check` in that clone passed all
97 tests, lint and strict types with 93.15% coverage. The portable acceptance check
also passed with its working directory set to the clone. Command records are in
`final-validation.json`. Download caches were shared; environments and checkouts
were fresh. This is a local verification, not remote CI execution.
