# STRIDE risk analysis and security validation

Assets: API credentials, management authorization, link destinations and lifecycle,
click integrity, run state, approval decisions, source files and test evidence.
Trust boundaries: unauthenticated redirect clients; authenticated management;
local CLI operators; fixture reasoning → scoped tools; SQLite → JSONL projection.

| Category | Threat | Implemented control and verification | Residual risk |
| --- | --- | --- | --- |
| Spoofing | Unauthenticated management or owner impersonation | Strong generated API key, constant-time hash comparison; owner-isolation tests | No SSO/rotation; CLI reviewer labels are self-asserted |
| Tampering | Alias injection, malicious redirect input, corrupted artifacts | Strict alias/URL rules, SQLAlchemy parameters, unique constraints, SHA-256 and input checks; negative tests | DNS/phishing abuse; local DB owner can alter records |
| Repudiation | Unrecorded approvals, claims without evidence | Recorded input-bound decisions, event IDs/parents/rationale, command logs | No externally signed immutable audit or real reviewer authentication |
| Information disclosure | API keys/PII/SQL internals leak | Hashed owner IDs, no IP/user-agent analytics, generic exception responses, minimal tool environment, secret marker rejection | Destination data remains in SQLite; local disk encryption/retention needed |
| Denial of service | Create abuse, SQLite contention, event growth | Persistent per-key management quota, request length limits, bounded workers/retries/timeouts | Public redirects unthrottled; no distributed limiter/load validation |
| Elevation of privilege | Agent modifies unrelated files or executes shell | Sandbox path checks, declared write scopes, command module allowlist, high-risk design approval | Trusted Python can execute code; OS/container isolation required for untrusted code |

Executed security scope: authorization/owner isolation, URL schemes/private literal
addresses, traversal/header injection, request error redaction, rate-key spoofing,
workspace escape/symlinks/command denials, and approval/replanning tests. Dedicated
security regression command: `make security`; full API cases also run in `make test`.
See `docs/testing.md` for evidence. These are security regressions, not a claim of
a comprehensive penetration test. No organic vulnerability finding is asserted.
The documented brownfield change failure is a reliability injection, not a pentest.

## Operational guidance

Bind to loopback for interview use. Never expose Swagger's local management key.
Use 302 for links that may be deactivated. If storage fails, return 503 without SQL
internals; inspect file permissions, disk free space and SQLite contention, then
rerun health and API tests. If clicks grow unexpectedly, isolate the instance and
inspect aggregate counters; avoid collecting IP addresses as an ad hoc fix.
If workflow retries exhaust, inspect saved command output and review scope before
starting a corrected run. For audit corruption, stop and preserve both DB and log;
never silently truncate evidence to make a run green.
