# Controlled Staging Retention and Deletion Exercise

This gate verifies real Coworker deletion operations using a dedicated synthetic staging account.

It covers task erasure, full account erasure, referenced-object protection and inventory-based orphan cleanup.

## Safety model

The retention service is intentionally **not** exposed as a public API route in this increment. It is an administrative backend capability used by controlled operations.

Account erasure is rejected while owned tasks, Agent runs or external actions are active.

Database records are erased transactionally first. Physical object deletion follows. If object deletion fails, the object becomes unreferenced and is recoverable through the orphan-cleanup inventory process.

Orphan cleanup:
- compares storage inventory against durable DocumentVersion, Artifact and export-checkpoint references;
- is dry-run first;
- ignores objects newer than the minimum age;
- never deletes referenced objects.

## Phase 1 — prepare

Set only in controlled staging:

```bash
SHUDDHO_STAGING_ALLOW_DELETION_EXERCISE=true
```

Then run:

```bash
uv run --extra coworker python scripts/staging_retention_deletion.py prepare \
  --state /secure/path/retention-state.json
```

This creates a new synthetic Coworker account, one uploaded source, one completed synthetic task/output artifact, and one deliberately unreferenced object.

No customer account or customer content is used.

## Phase 2 — wait for the orphan safety window

The default minimum orphan age is one hour. This prevents a just-written object from being deleted merely because its database transaction has not committed yet.

Do not reduce the production cleanup age below the documented operational safety window.

## Phase 3 — verify

```bash
uv run --extra coworker python scripts/staging_retention_deletion.py verify \
  --state /secure/path/retention-state.json \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.deletion.json
```

Verification passes only when:

- the synthetic standalone task is erased from the database;
- its output artifact is physically removed;
- dry-run inventory detects the aged orphan;
- the still-referenced source object is **not** classified as orphaned;
- real orphan cleanup deletes the synthetic orphan;
- full synthetic-account erasure removes account/workspace/documents/tasks and related Coworker records;
- the remaining owned source object is physically removed;
- no physical deletion reports failure.

Only then is the `deletion` staging gate promoted to `passed`.

## Operational boundary

This increment provides the deletion mechanism and staging proof. Product/legal retention periods still need an approved policy describing when automated task/account erasure is initiated and which minimal security/audit records, if any, may be retained independently.
