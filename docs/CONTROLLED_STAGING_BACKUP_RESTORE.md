# Controlled Staging Backup and Restore Drill

This gate proves that both Coworker PostgreSQL state and private object bytes can be restored into a separate staging target.

It does **not** run a destructive restore against the active staging environment.

## Preconditions

Use the normal staging backend credentials for the prepare phase and set:

```bash
SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<short-lived disposable staging account token>
```

## Phase 1 — prepare synthetic restore evidence

Run:

```bash
uv run --extra coworker python scripts/staging_backup_restore.py prepare \
  --state /secure/path/backup-restore-state.json
```

The prepare step:

- resolves the disposable staging owner through the deployed API;
- creates one synthetic uploaded TXT source;
- stores the source in private object storage;
- creates and cancels one synthetic Coworker task referencing that source;
- records IDs, byte size, SHA-256, and hashed source-environment fingerprints only.

No customer content is used.

## Phase 2 — take the real backups

Use the actual managed-service backup mechanisms selected for Shuddho:

1. take a PostgreSQL backup/snapshot;
2. take or confirm the private object-storage backup/versioned copy;
3. record durable backup references.

Do not claim the gate passed from backup creation alone.

## Phase 3 — restore into isolated targets

Restore both the database and object storage into separate staging resources.

The verification environment must point to those restored resources. The verifier rejects the original database and object-storage fingerprints.

## Phase 4 — verify

Run in the restored environment:

```bash
uv run --extra coworker python scripts/staging_backup_restore.py verify \
  --state /secure/path/backup-restore-state.json \
  --backup-reference postgres-snapshot-123/object-backup-456 \
  --restore-reference isolated-restore-run-789 \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.restore.json
```

The gate becomes `passed` only if:

- the restored account and workspace exist;
- the source document/version exists and is still uploaded;
- restored document metadata matches the pre-backup manifest;
- the synthetic task still exists in its cancelled state;
- task event history is present;
- private restored object bytes match the exact pre-backup SHA-256 and byte size;
- the database target differs from the source fingerprint;
- the object-storage target differs from the source fingerprint;
- non-empty backup and restore references are supplied.

## Evidence boundaries

The evidence file contains no JWTs, database URLs, storage endpoints, object keys, source bytes, or provider credentials.

A successful drill promotes only `backup_restore`. Retention/deletion, orphan cleanup, v2→v1 rollback, and live provider checks remain separate production gates.
