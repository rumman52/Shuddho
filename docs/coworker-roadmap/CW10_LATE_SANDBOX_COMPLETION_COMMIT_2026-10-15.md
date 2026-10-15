# CW-10 — persist late sandbox completion rejection before raising

**Date:** 15 October 2026. **Base:** `main` `9bdb73a9142bce6e9e9848373dddde44514ca144` (merged [PR #413](https://github.com/rumman52/Shuddho/pull/413); [main CI #38746278784](https://github.com/rumman52/Shuddho/actions/runs/38746278784): `test-and-build`, `coworker`, `ci-merge-gate` all successful). **Work branch:** `codex/cw10-late-completion-commit-20261015`. This is a bounded CW-10 recovery safety slice, not an authorization to run model-generated Python.

## Reproduced defect and outcome

When `SandboxRepository.complete_execution` sees an owned, still-claimed worker execution whose session was cancelled or expired *after claim*, it scrubs the source, clears the lease, sets a terminal state and then raises `CoworkerError("sandbox_session_closed")` **inside** `sessions.begin()`. SQLAlchemy rolls that transaction back. A controlled SQLite/SQLAlchemy transaction probe confirmed this rollback property; the full Shuddho regression must run in CI. The caller correctly gets HTTP 409, but the intended terminal state and source erasure do not persist at this boundary. Subsequent expiry scavenging may incidentally repair some cases, but cannot be treated as evidence that worker completion safely persisted cleanup.

**Required user-visible behavior:** Reject a late worker completion with the same typed 409, do not accept the result or artifact, atomically persist terminal session/execution state and source scrubbing, clear worker claim/lease, and retain a cleanup obligation. No alternate claimant may execute the old source.

## Bounded implementation

- Preserve the public `complete_execution` entry point. Move the existing transaction body into a private `_complete_execution` helper. For a closed session, return a private rejection sentinel **after the transaction commits**; the public entry point raises the original `sandbox_session_closed` typed 409 after commit. Normal completion still returns the exact existing execution DTO; other validation failures still roll back.
- Audit `sandbox_execution.late_completion_rejected` in the same atomic transaction. On rejection: terminalize the execution, scrub request source, revoke claim/lease, and require sandbox cleanup conservatively.
- No schema, API shape, feature flag, generated-code grant, provider, external action or release configuration changes.

## Regression and acceptance

- `tests/test_sandbox_control_plane.py::test_late_sandbox_worker_completion_persists_terminal_failure` parameterizes **expired** and **cancelled** session state after a legitimate claim; asserts same typed rejection, persisted scrub/terminal state, no observation accepted, no lease, no reclaim, and a stale worker cannot complete.
- Inspect persisted rows directly before calling any expiry scavenger; otherwise another endpoint's cleanup could conceal the rollback.
- Required exact final-head CI: `test-and-build`, no-skip mandatory `coworker` (including PostgreSQL, Temporal, sandbox and browser), `ci-merge-gate`. Local full-repository execution not available in the connector-only workspace; no staging claim is made. Review receipt boundary and worker cleanup with an independent reviewer before merge.

## Boundaries and next work

Model-generated Python still requires immutable owner/run/source/input/limit proposal, explicit human review/expiry/revocation, and **atomic worker claim approval revalidation**. Do not activate until those and operated sandbox isolation qualify. CW-09 live browser/DNS/SSRF, CW-11 skill publication/grants, cross-purpose context and end-to-end coworker scenarios remain open. This slice may be reviewed as a PR, but **do not auto-merge, deploy or activate**.
