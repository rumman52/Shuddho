# CW-11 Worker Registration / Fleet Snapshot Fence — 17 October 2026

## Objective

Prevent a worker from being inserted into the configured coworker queue between the fleet compatibility snapshot and the reviewed-skill selection/admission/rollback commit. A PostgreSQL row lock on existing worker rows cannot protect an empty or concurrently changing queue from a phantom insert.

## Implementation

- Add a transaction-scoped PostgreSQL advisory lock keyed deterministically by task queue.
- Acquire the same queue-membership lock before the worker inventory query in `_require_compatible_worker_fleet()` and before inserting a row in `register_worker()`.
- After the lock is acquired, worker registration checks the current reviewed-skill selection for the configured queue. A missing/non-authoritative selected publication fails closed; a worker revision that differs from the selected publication is rejected with `worker_fleet_incompatible`.
- Keep other task queues isolated from the configured queue's reviewed-skill selection.
- Keep the existing row lock order after the queue lock: worker rows in stable ID order → selection row → publication row(s).
- No schema migration, public API change, new grant, provider call, release activation, or deployment.

The advisory lock is transaction-scoped and is released on commit/rollback. The implementation uses PostgreSQL's advisory-lock mechanism only when the active database dialect is PostgreSQL; production safety qualification must therefore use PostgreSQL, not infer this guarantee from SQLite behavior.

## Regression coverage

1. SQLite-backed contract test: after a reviewed publication is selected, registration of a worker from a different source revision is denied; a worker on an unrelated queue remains isolated.
2. PostgreSQL interleaving test: pause selection after its fleet snapshot, attempt to register an incompatible worker concurrently, prove registration blocks on the same advisory lock, release selection, and prove the registration is then rejected.
3. The PostgreSQL regression must be included in the mandatory CW-11 JUnit gate and must pass with zero skips.

## Validation status

Implementation and tests are on branch `codex/cw11-worker-registration-fence-20261017`. Exact-head CI and independent review are pending; no local execution, CI pass, staging evidence, or production qualification is claimed in this document.

## Remaining work

- Add per-claim drain fencing for Agent/action outboxes so a drain cannot be reported complete while a claim or dispatch can still proceed.
- Run protected `CW11-STAGING` with authorized real worker identities, verified drain, process-recovery evidence, and an inspectable artifact bound to the exact deployed revision.
- Complete the four operated coworker scenarios and independent operational review.
- Keep production qualification and activation disabled until their separate authorization and evidence gates pass.
- Investigate the intermittent parallel SQLite malformed-schema/duplicate-index symptoms separately; a serial rerun is not root-cause evidence.
