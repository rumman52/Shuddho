# CW-11 — Trusted Reviewed-Skill Publication, Selection, Rollback and Worker Drain

## Release boundary

CW-11 treats the reviewed Agent research skill as a release artifact rather than a mutable feature flag.

A publication is bound to:

- reviewed skill identity;
- publication version;
- task-workflow version;
- exact deployment source revision;
- immutable manifest snapshot;
- reviewed manifest hash;
- publication hash;
- tool allowlist;
- resource limits;
- explicit rollback target.

Publishing never selects a version.

Selection is an explicit operator action and is blocked unless the task queue has a fresh running worker whose deployment revision exactly matches the selected publication and no incompatible worker is active.

## Runtime enforcement

A new Agent research task must pass all of these checks:

1. The Agent run, Agent step and `research.search` invocation are owned by the same account.
2. The invocation is the exact reviewed tool version and input fingerprint.
3. The reviewed manifest is valid.
4. A reviewed publication is explicitly selected.
5. The selected publication is still `published`.
6. The selected publication hash and review hash match the stored identity.
7. The current worker revision matches the publication revision.
8. No incompatible worker is active or draining.
9. The task stores the complete publication identity before execution.

Every worker phase and paid-search reservation revalidates the persisted identity. A publication rollback therefore fails closed for tasks pinned to the rolled-back publication instead of silently executing them under a different release.

## Operator controls

The operator-only CLI is:

```text
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py publish ...
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py select ...
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py rollback ...
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py inventory ...
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py drain ...
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py verify-drain ...
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py migrate-legacy ...
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py history
uv run --extra coworker python scripts/cw11_reviewed_skill_ops.py runtime
```

All mutating controls require an operator reference and a reason. Control transitions are retained in the append-only `cw_reviewed_skill_registry_events` table.

## Controlled mixed-version rollout

Use this sequence; do not reverse it.

### 1. Build and attest the candidate

Deploy the candidate worker from the exact reviewed Git revision.

The worker records its deployment-attested revision at startup. Outside development, `RENDER_GIT_COMMIT`/the CI commit is preferred over a manually supplied revision.

### 2. Start the candidate beside the existing worker

Do not select the candidate yet.

Verify:

```text
... inventory --task-queue shuddho-documents-v1
... runtime
```

The selection gate must reject a candidate selection while an incompatible active worker remains.

### 3. Drain the legacy worker

For a worker running CW-11 code:

```text
... drain --task-queue shuddho-documents-v1 \
    --source-revision <old-revision> \
    --actor-reference <operator> \
    --reason "CW-11 mixed-version drain"
```

The dispatcher stops claiming new queued work, while already accepted Temporal work is allowed to finish. The worker then records `drained`.

For a pre-CW-11 worker that cannot participate in the registry heartbeat, use the deployment platform's controlled graceful shutdown and independently verify that the old deployment has stopped. Do not mark an unobserved worker as drained.

### 4. Verify the drain

```text
... verify-drain \
    --task-queue shuddho-documents-v1 \
    --old-source-revision <old-revision>
```

A stale or `lost` worker is treated as an uncertainty blocker, not as drained.

### 5. Select explicitly

Only after the old worker is drained:

```text
... select \
    --publication-version <candidate-version> \
    --worker-source-revision <candidate-revision> \
    --actor-reference <operator> \
    --reason "CW-11 staging selection"
```

There is no automatic fallback from selection to another publication.

### 6. Migrate only safe pre-fence reviewed tasks

Historical reviewed tasks admitted under `work_research_v1` can only be migrated after the legacy worker drain.

Migration is atomic: if any active pre-fence reviewed row is ambiguous, expired, already executed, or missing its exact reviewed binding, the complete migration is rejected and no row is changed.

### 7. Collect staging evidence

Use the protected GitHub Actions workflow:

- Workflow: `CW-11 staging evidence`
- Confirmation: `CW11-STAGING`
- Environment: `staging`
- Inputs: expected publication version and old source revision.

The workflow first runs a separate confirmation job that fails unless the exact `CW11-STAGING` token is supplied. That job has no staging environment or secrets; the protected evidence job cannot start unless it succeeds. Render API credentials are scoped to the live-service check, the database URL to migration and evidence collection, and the auth issuer to evidence collection; checkout and dependency installation receive no staging credentials. The workflow fails before staging access unless it is dispatched from protected `main` with the exact confirmation token. User-supplied publication/revision inputs are passed through step-scoped environment variables and quoted shell expansions, never interpolated into shell source. Render service IDs must match the API response identity, and the old revision must be a full lowercase Git SHA. The evidence job verifies live Render service identity, confirms that the legacy service has zero instances, and confirms that the candidate has a live instance on the exact qualification revision **before** applying pending staging migrations. It then runs the read-only evidence collector and stores `cw11-staging-evidence.json` as an artifact. This ordering does not replace the operator's controlled drain procedure or prove the absence of in-flight Temporal/provider work.

The evidence gate proves:

- explicit publication selection;
- selected publication is the expected version;
- selected publication revision equals the candidate deployment revision;
- a fresh compatible worker is running;
- no incompatible active/draining worker remains;
- no active pre-fence reviewed tasks remain;
- any registered legacy worker row is explicitly `drained` and has a durable
  `drained_at` timestamp; missing or inconsistent drain evidence blocks;
- every row marked `drained`, regardless of source revision, has zero active
  dispatch claims; a false-drain claim blocks evidence collection;
- control-event history is retained;
- the shared read-only rollback task-ledger classifier reports no blockers:
  active unfenced reviewed Tasks, active reviewed-workflow Tasks missing their
  identity, and ambiguous active legacy Agent research without an identity all
  block collection;
- the evidence artifact includes aggregate task-ledger counts only, not Task
  IDs, owner identifiers or private Task content;
- the collector itself revalidates external Render evidence for strict schema
  and boolean types, distinct worker service IDs, exact instance-count types,
  and full commit SHAs matching the requested old revision and candidate
  deployment revision.

The external payload's `verified` field is not trusted on its own: the
protected workflow first reads live Render service, instance and deployment
state, then the collector validates the resulting payload again. The task
ledger remains a point-in-time database snapshot; it cannot prove admission
quiescence, absence of in-flight Temporal/provider work, or complete worker-fleet
drain without the separate operated procedure.

## Rollback

Rollback is explicit and constrained to the publication's declared rollback target:

```text
... rollback \
    --target-publication-version <declared-target> \
    --worker-source-revision <compatible-worker-revision> \
    --actor-reference <operator> \
    --reason "CW-11 rollback"
```

The target must already be a published compatible publication and must exactly equal the current publication's declared `rollback_target_version`.

The current publication is moved to `rolled_back`; tasks pinned to it subsequently fail closed. This is intentional: rollback must not silently reinterpret an already accepted task under another skill release.

## CI

`.github/workflows/ci.yml` runs `tests/test_cw11_registry.py` through the mandatory test gate and retains its JUnit evidence.

The staging workflow is separate from CI. A passing unit-test run is not staging evidence.

## Required staging secrets

Configure the protected GitHub `staging` environment with:

- `SHUDDHO_STAGING_DATABASE_URL`
- `SHUDDHO_STAGING_AUTH_ISSUER`

Protect the environment with the repository's normal required-reviewer policy before using the workflow.

## Qualification invariant

The release is not CW-11 qualified until all three evidence layers pass:

1. **Code/CI:** registry, selection, rollback, duplicate-admission and drain tests pass.
2. **Controlled staging:** mixed-version worker drain and exact selected publication evidence pass.
3. **Operational review:** an authorized reviewer confirms the exact candidate revision, publication version, rollback target, worker inventory and evidence artifact.

Do not substitute a unit-test result for the staging or operational layer.

## Registry and worker-registration serialization

For PostgreSQL, reviewed-skill controls and worker registration must acquire the same transaction-scoped advisory lock for the target task queue before changing or snapshotting queue membership. The lock key is deterministic for the queue, so registration cannot appear as a phantom between the fleet snapshot and the registry transaction's commit.

After acquiring the queue-membership lock, registry controls use this row-lock order:

1. Lock every worker row for the task queue in stable worker-ID order and validate liveness/drain state.
2. Lock the reviewed-skill selection row and revalidate that it remains selected.
3. Lock the publication row or rows required by the operation.

Admission may use non-locking reads to preserve precise early error responses, but those reads are observations only. It must acquire the queue-membership lock and worker locks, then re-read and validate the selection and publication under lock before admitting work. Selection and rollback must never hold selection/publication locks while waiting for the worker inventory.

Worker registration acquires the same queue lock before inserting its inventory row. On the configured coworker queue, the incoming revision must match the deployment-attested revision of the running runtime. A candidate runtime may register while an older publication remains selected; registry selection remains blocked until the incompatible old fleet has completed drain.

Alembic migration 0061 installs a PostgreSQL `BEFORE INSERT` trigger on `cw_worker_instances`. Updated code sets the transaction-local `shuddho.worker_source_revision` value before inserting; the trigger rejects rows without that context or with a mismatched revision. This database guard prevents a legacy binary that predates the advisory-lock protocol from inserting a new worker row after the migration is applied. Existing legacy worker rows remain visible and must still be drained. A legacy process that crashes may not be able to restart until upgraded, so the rollout/rollback plan must account for that availability trade-off.

The advisory lock and trigger require PostgreSQL. SQLite tests verify repository behavior but do not establish the PostgreSQL legacy-binary guard. These controls do not by themselves fence in-flight Agent/action claims, prove whole-fleet quiescence, or replace protected staging evidence.

## Per-claim dispatch drain fencing

Migration 0062 adds the durable `cw_worker_claims` ledger. Every task, Agent, or approved-action outbox claim made by the registered dispatcher is recorded in the same transaction that locks the worker and leases the outbox row. Claiming requires a fresh registered worker in `running` state and the configured task queue; calls without a worker identity fail closed and cannot claim dispatchable rows.

The lock order is **WorkerInstance → outbox/resource row → WorkerClaim**. Drain requests lock worker rows in stable ID order. Since claim and drain transactions serialize on the same worker row, a claim either commits before the worker transitions to `draining` (and remains visible as active), or sees a non-running worker and does not start. Exact Agent dispatch also revalidates the active claim immediately before starting the workflow.

Each claim remains active until its dispatch attempt returns. The dispatcher then marks it completed whether the workflow was accepted, already existed under the deterministic workflow ID, or the dispatch call returned an error. A failed item does not cause unattempted claims from the same claimed batch to remain active: those claims are closed without marking their outbox rows delivered, so ordinary lease-based retry remains available. A process crash or cancellation that bypasses completion leaves active evidence and deliberately blocks drain certification; claims are not silently expired.

`mark_worker_drained()` now locks the worker and refuses to record a drained state while any active claim remains. Worker inventory reports `active_claim_count`, and `assert_worker_drain_complete()` requires an explicit drained state, a completion timestamp, and zero active claims for every legacy worker. The production worker still publishes drain completion only after Temporal `Worker.__aexit__` finishes; the claim ledger covers dispatcher claims and does not replace that process-shutdown boundary for activities already accepted by Temporal.

Completed claim rows are retained as an audit trail. No automatic cleanup of active claims is permitted. If a worker process disappears with an active claim, an operator must reconcile the dispatch outcome and the durable claim evidence before drain can be certified; this change intentionally does not guess that the claim is safe to clear.
