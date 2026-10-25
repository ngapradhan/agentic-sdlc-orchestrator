# S0 stage report

Status: **S0 complete and stopped for the required stage report.** Implementation,
local checks and clean-clone quickstart verified. This report covers S0 only.

## Built

- Python 3.11+ package, frozen uv dependencies, Makefile, CI configuration.
- LLMClient, deterministic JSON fixtures/system prompts/schemas, optional HTTPS
  gateway adapter (offline transport tests only).
- Three-node DAG, entry dependencies and independently enforced schema gates.
- SQLAlchemy/SQLite state, transactional event source, append-only JSONL
  projection with recovery of committed-but-unprojected records.
- Artifact fingerprints, input fingerprints, chronological decision lineage.
- CLI run/resume/inspect/trace/lineage, deliberate pause/resume across processes.
- Evidence recorder, portable sample run, tests, staged requirement tracking.

## Verified

| Command actually run | Result | Evidence |
| --- | --- | --- |
| `make check` | Exit 0; lint/format, strict mypy, 27 tests; 97.95% S0 coverage | `runs/evidence/s0-checks-20261025T074527872451Z.json` and `.log` |
| `make quickstart PYTHON=<installed Python 3.12> UV_CACHE_DIR=<local cache>` | Exit 0; HALTED then PASSED, one attempt/node | `runs/evidence/s0-quickstart-20261025T074557416845Z.json` and `.log` |
| `git clone --no-local <source> <fresh directory>` | Exit 0; code commit `ed54d51` cloned | `runs/evidence/s0-clone-20261025T074737600557Z.json` and `.log` |
| `make -C <fresh directory> quickstart PYTHON=<installed Python 3.12> UV_CACHE_DIR=<local cache>` | Exit 0; created new venv, installed 27 locked packages, resumed bootstrap successfully | `runs/evidence/s0-clean-quickstart-20261025T074737675566Z.json` and `.log` |

The exact command arguments and installed interpreter path are in each JSON
record. Clean-clone verification used a fresh checkout and venv with a shared
download cache. It proves S0 quickstart only, not the S8 final-product acceptance.
Subsequent changes to the tested code commit are handoff documentation/evidence.

Initial `make check` failed at mypy due to reuse of an ORM loop variable; fixed
with a separately named recovery variable. The failed command record is retained
as `runs/evidence/s0-initial-checks-20261025T074205970052Z.json` (exit 2).
The initial package installation failed before network access was granted; the
subsequent installation succeeded. No CI execution or external live-model test
is claimed.

Tests include invalid artifact rejection independent of client self-check,
deterministic fixtures, HTTP adapter contracts/error handling, no-network default
execution, new-process resume, idempotent completed resume, incomplete projection
recovery, interrupted-computation requeue, corrupted artifact/input/DAG refusal,
audit corruption fail-closed behavior, workspace exclusion, and CLI views/stubs.
The default engine test blocks outbound socket connections and still passes.

## Example trace

Run `4b95357e49824f0998997e6ba17c9b56`, captured by the quickstart command:

```text
RUN_CREATED
RUN_STARTED
NODE_STARTED intake -> GATE_PASSED intake.exit
RUN_PAUSED (run HALTED)
RUN_STARTED (separate process)
NODE_STARTED plan -> GATE_PASSED plan.exit
NODE_STARTED summary -> GATE_PASSED summary.exit
RUN_PASSED
```

The full event log, artifacts, DAG JSON/Mermaid, state and lineage are in
`runs/evidence/bootstrap-4b95357e49824f0998997e6ba17c9b56/`.
Approvals: none required or claimed by this bootstrap. S1 will enforce approval
rules; `approve`/`reject` currently fail explicitly with exit 2.

## Deferred / needs from the user

All S1–S8 requirements remain pending as listed in `limitations.md`, including
parallel scheduling, approval enforcement, policies, rollback/retry/fallback,
re-planning, metrics, SIGKILL proof, real service and security/scenario work.
There is no bank-grade or full-assignment-completion claim.

No further input is needed to finish S0. The next stage starts only after the
user's next instruction, following the requested stage-stop protocol. Before
S2/S4/S8, resolve the missing original sections or record explicit assumptions.

## Run from this checkout

```sh
make quickstart
make evidence
```

Requires Python 3.11+, uv, make and a POSIX host. S1 plan/interfaces/test strategy
are in `docs/architecture.md`; every incomplete Must remains listed in
`docs/limitations.md` and `docs/assignment-tracking.md`.
