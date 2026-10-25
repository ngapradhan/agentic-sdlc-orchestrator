# Decision log

| ID | Context and options | Decision | Consequence / trade-off | Requirement |
| --- | --- | --- | --- | --- |
| D01 | Full SDLC at once vs verified stages | Deliver S0 only and stop for its report | Does not yet meet final acceptance; avoids concealing unfinished controls | Protocol §1, stages §8 |
| D02 | Dual writes vs transactional event source | Commit state and events together in SQLite; append JSONL projection with prefix checks | Recoverable missing appends; torn tail requires manual recovery until S1; application append-only is not cryptographic immutability | Persistence §3, state §4.4 |
| D03 | Pretend generation vs explicit templates | Version prompts, schemas and deterministic fixtures; CLI selects MockLLM only | Reproducible offline behavior, no semantic requirement understanding or service generation in S0 | Honest mock boundary §3 |
| D04 | Complete platform schema upfront vs staged schema | SQLAlchemy creates S0 bootstrap tables locally; introduce Alembic before versioned schema changes | Existing S0 databases may need an explicit compatibility decision in S1; service migrations still mandatory S2 | Stack §3, S0/S2 |
| D05 | Unbounded concurrent access vs bootstrap isolation | One executor per workspace via POSIX flock; serial fixed DAG | Simple truthful resume semantics; no Windows support or scheduler parallelism yet | S0 graph, future §4.2 |
| D06 | Persist arbitrary prompt text vs minimal input | Store requirement fingerprint only; pass dependency artifacts to mock | Avoids raw sensitive data retention; live semantic processing needs approved context storage in S1/S2 | No secrets §3, lineage §4.4 |
| D07 | Provider-specific SDK vs minimal live seam | HTTPS schema-aware JSON gateway adapter, tested with MockTransport | Implemented adapter, no real-provider verification; not available through CLI | LLMClient §3 |
| D08 | Dependency drift vs reproducible bootstrap | uv frozen lock; Python 3.11+ on macOS/Linux | uv is an extra local prerequisite; first setup downloads packages, runtime is offline | One local command §3 |

These decisions are implementation judgments. No human approval is asserted.

## V3 continuation decisions

| ID | Context/options | Decision | Consequences / requirement |
| --- | --- | --- | --- |
| D09 | V2 stage stops vs V3 continuous delivery | V3 controls continuation; preserve S0 and complete P0/P1 | No repeated stage permission requests; user explicitly authorized continuation |
| D10 | Rewrite bootstrap vs additive engine | New workflow task/approval tables share existing store/events; one CLI dispatches by graph version | Keeps S0 tests/interface; bootstrap table migrations still future work |
| D11 | Brownfield Redis vs genuine small enhancement | Owner-protected daily reporting over existing click events | Real source diff/new route/test; no extra infrastructure or schema change |
| D12 | Broad enterprise claims vs measurable approved slice | Block on clarification, explicitly approve only security headers and tests | Questions/out-of-scope visible; no fabricated business requirements |
| D13 | Retry changes in source repo vs isolated compensation | Snapshot declared sandbox files; verify restoration before retry | Actual recoverability without touching user's other resources; not general OS rollback |
| D14 | Unverified sophistication vs practical security scope | Executable regressions and STRIDE; defer comprehensive pentest/load/cloud | Honest prototype boundary under V3 priorities |
| D15 | Key in source/docs vs local generation | Generate random API key into mode-0600 file; env override; never log it | No external credential needed; local operator manages key lifecycle |
| D16 | Ruff B008 vs FastAPI dependency idiom | Allow FastAPI Depends/Security as immutable dependency declarations | Narrow linter configuration preserves framework's supported injection style |
