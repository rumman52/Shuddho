# CW-11 Worker Registration / Fleet Snapshot Fence — 17 October 2026

## Objective

Prevent a worker from being inserted into the configured coworker queue between the fleet compatibility snapshot and the reviewed-skill selection/admission/rollback commit. A PostgreSQL row lock on existing worker rows cannot protect an empty or concurrently changing queue from a phantom insert.

## Implementation

- Add a transaction-scoped PostgreSQL advisory lock keyed deterministically by task queue.
- Acquire the same queue-membership lock before the worker inventory query in `_require_compatible_worker_fleet()` and before inserting a row in `register_worker()`.
- Require a worker registering for the configured queue to match the deployment-attested runtime revision. A candidate runtime may join while an older publication remains selected; selection itself still blocks until all active workers match the candidate revision.
- Add Alembic migration `0061` with a PostgreSQL `BEFORE INSERT` trigger. It rejects worker-row inserts that lack a transaction-local `shuddho.worker_source_revision` attestation matching the inserted row. Updated code sets this context from the configured runtime revision; a legacy binary that predates the protocol cannot register a new worker after the migration is applied.
- Keep other task queues isolated from the configured queue's application-level revision check.
- Keep the existing row lock order after the queue lock: worker rows in stable ID order → selection row → publication row(s).
- No public API change, new grant, provider call, release activation, or deployment. A schema migration is required for the PostgreSQL legacy-binary guard.

The advisory lock is transaction-scoped and is released on commit/rollback. The PostgreSQL trigger protects against old binaries that do not cooperate with that lock. SQLite does not install this trigger, so SQLite tests do not establish the production legacy-binary guard.

## Regression coverage

1. SQLite-backed contract test: after a reviewed publication is selected, registration of a worker from a different source revision is denied; a worker on an unrelated queue remains isolated.
2. PostgreSQL interleaving test: pause selection after its fleet snapshot, attempt to register an incompatible worker concurrently, prove registration blocks on the same advisory lock, release selection, and prove the registration is then rejected.
3. PostgreSQL trigger test: prove a direct worker-row insert without transaction-local revision attestation is rejected.
4. All PostgreSQL regressions must be included in the mandatory CW-11 JUnit gate and pass with zero skips.

## Validation status

PR #448 merged the initial advisory-lock and PostgreSQL trigger guard as commit `6b5aa1e2743bdbbdaa7c38a55670f6d39e8043da`. Follow-up branch `codex/cw11-worker-registration-guard-followup-20261017` refines the configured-queue runtime-revision check and updates regression fixtures to model already-running legacy rows. Exact-head CI and independent review for the follow-up are pending; no local execution, CI pass, staging evidence, or production qualification is claimed in this document.

## Remaining work

- Add per-claim drain fencing for Agent/action outboxes so a drain cannot be reported complete while a claim or dispatch can still proceed.
- Existing legacy worker processes can continue running after migration, but their new registrations are rejected; drain/rollback planning must account for a legacy process crash that cannot restart until it is upgraded.
- Run protected `CW11-STAGING` with authorized real worker identities, verified drain, process-recovery evidence, and an inspectable artifact bound to the exact deployed revision.
- Complete the four operated coworker scenarios and independent operational review.
- Keep production qualification and activation disabled until their separate authorization and evidence gates pass.
- Investigate the intermittent parallel SQLite malformed-schema/duplicate-index symptoms separately; a serial rerun is not root-cause evidence.
