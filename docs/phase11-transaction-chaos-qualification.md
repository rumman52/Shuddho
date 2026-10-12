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
commit. The process-recovery slice described below adds executable evidence at these
boundaries, but does not complete the entire matrix. CI is repository evidence; deployed provider approval,
human quality review and an operated availability window remain separate release gates.

## CW-02 counted HTTP, process and Temporal recovery

`tests/test_transaction_chaos_temporal.py` adds a counted loopback provider outside the
disposable worker process. It executes the real Google adapter, authorization boundary,
transaction/action ledgers and production Temporal workflow/activity definitions.
The simulator intentionally counts repeat applications rather than masking them with
its own deduplication.

Workers are killed before claim, after claim, after provider application and after receipt
commit. Each boundary runs directly and through real Temporal activity recovery. HTTP
401/403/429, an accepted 500, malformed receipt and dropped response have independent
dispatch/application counters. Authenticated API duplicate admission runs on PostgreSQL;
a separately spawned API is terminated after transaction commit to verify exact replay.
A real test Temporal server is stopped before workflow admission, proving queued outbox
preservation and eventual one-attempt recovery.

The heavy CI job requires the disposable PostgreSQL database/role before migrations,
sets `SHUDDHO_TRANSACTION_CHAOS_POSTGRES_REQUIRED=true`, runs all seventeen tests with
the real Temporal test server and rejects skips/errors/failures. JUnit properties are
labelled `integration_simulated_provider`; they cannot be imported as real staging or
provider observations. Local SQLite may exercise transport/process paths but skips the
PostgreSQL admission race and never qualifies database concurrency.

See [the task contract](coworker-roadmap/CW02_PROCESS_RECOVERY_TASK_2026-10-12.md) for exact
boundaries, counter expectations, safe target checks and remaining release requirements.
