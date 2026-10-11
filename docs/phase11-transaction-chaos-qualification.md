# Phase 11 transaction chaos qualification

The invariant is at most one consequential mutation per approved execution identity.
Identical binding replay returns the existing link; binding another action is rejected.
A lost reply after possible provider acceptance requires read-only reconciliation, never
an automatic resend. Expired approvals and execution claims fail closed.

## CW-01 repository checks

The mandatory CI step installs the locked coworker extra, runs the safety suite, emits
JUnit evidence and rejects empty, skipped, failed or errored reports through
`scripts/mandatory_test_gate.py`. The existing `ci-merge-gate` depends on this job.
A separate workflow that installs `requirements.txt` cannot run in this repository.

The safety suite exercises real repositories, the credential broker, ActionService and
Google adapter with simulated HTTP transport. It checks identical/different bindings,
accepted-then-lost response, approval/claim expiry, repeat success, receipt hash and
independent HTTP dispatch/provider-applied mutation counts. No production APIs changed.

## Full fault matrix and remaining qualification

The complete 16-case expected-outcome contract is in
[coworker-roadmap/ROADMAP.md](coworker-roadmap/ROADMAP.md#phase-11-all-requested-failure-outcomes).
Its cases are model 429/500/timeout; provider 401/403/429/500; malformed response;
database/S3 disconnect; Temporal outage; worker/API crash; duplicate message; lost
provider response; and approval after expiration. Each requires the stated counter,
state, receipt, budget or process evidence. Defining a row does not execute its fault.

CW-01 covers repository regressions for binding replay, lost reply, expiry and repeated
success. CW-02 remains pending until actual public API/PostgreSQL/Temporal process
interruption cases pass, including before/after claim, provider application and receipt
commit. Existing PostgreSQL and Temporal suites supply reusable fixtures, not automatic
completion of the full matrix. CI is repository evidence; deployed provider approval,
human quality review and an operated availability window remain separate release gates.
