# Interview walkthrough — 5–10 minutes

Prepare once: `make quickstart`. Have `docs/architecture.md` and the submission
index open. Say explicitly: “Reasoning is deterministic for offline repeatability;
the engine, file effects, validation and recovery controls are real.”

1. **Minute 0–1 — Architecture:** show the components and DAG. Explain that SQLite
   stores authoritative state/events and JSONL is a checked projection. Show the
   distinct source-of-truth and projection failure boundary.
2. **Minute 1–2 — Service:** `make serve` in one terminal. Use README curl commands
   from another terminal: create, 302 redirect, click stats, deactivate → 410.
   Open `/docs` if network permits CDN assets; do not display the API key.
3. **Minute 2–4 — Greenfield:** `make demo-greenfield`. Open its DAG and events.
   Point to both concurrent branches and the validation join. Show command exit 0,
   artifact hashes and simulated approval records. These are sandbox file writes.
4. **Minute 4–6 — Brownfield:** `make demo-brownfield`. Show AST impact analysis,
   actual diff, new reporting test and validation log. Follow TASK_FAILED →
   ROLLBACK_VERIFIED → RETRY_QUEUED → GATE_PASSED. Explain injected failure honestly.
5. **Minute 6–8 — Ambiguity:** start `run --scenario ambiguous` through the CLI.
   Inspect BLOCKED/zero attempts for unapproved work and clarification questions.
   For a short demo run `make demo-ambiguous` to record labeled demo decisions;
   show REPLAN, revised scope and new design approval fingerprint.
6. **Minute 8–10 — Reliability/judgment:** show `metrics RUN_ID`, failed-to-passed
   MTTR where observed and null where no repair occurred. Point to SIGKILL and
   real parallel barrier tests. Finish with limitations and criterion-evidence map.

## Likely reviewer questions

- **Is the LLM really writing code?** Offline mode copies/patches versioned templates
  via real scoped tools. It is not independent model reasoning. The optional live
  JSON gateway seam is implemented but no provider run is claimed.
- **Why SQLite?** Zero external services, reproducible transactions and easy state
  inspection. Redirect writes serialize; production scale would need a different
  analytics/write architecture based on measured traffic.
- **What stops unsafe work?** Input-bound design/release approvals, path/write scopes,
  command allowlist, bounded attempts/timeouts and compensation. This is a trusted
  local tool boundary; untrusted code needs OS isolation and real reviewer identity.
- **How is resume safe?** PASSED artifact/input hashes are checked; RUNNING tasks
  restore persisted snapshots before retry. Actual SIGKILL interruption is tested.
  Torn JSONL tails intentionally fail closed rather than silently deleting evidence.
- **What changes on upstream revision?** The engine traverses descendants, marks
  them STALE, preserves unrelated successes, invalidates old input approvals, and
  records a REPLAN event. The completed-downstream reapproval test proves it.
