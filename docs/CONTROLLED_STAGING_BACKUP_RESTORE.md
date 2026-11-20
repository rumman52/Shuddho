# Controlled Staging Backup and Restore Drill

This gate proves that both Coworker PostgreSQL state and private object bytes can be restored into a separate staging target.

It does **not** run a destructive restore against the active staging environment.

## Preconditions

Use the normal staging backend credentials for the prepare phase and set:

```bash
SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<short-lived disposable staging account token>
SHUDDHO_SOURCE_REVISION=<full-40-character-deployed-git-sha>
```

**Pre-seeding zero-object state:** if the private source bucket is empty,
preserve its inventory with the *explicit* object-helper
`archive --allow-empty-baseline` and verify the isolated zero-object target
with `restore --allow-empty-baseline` (see
[Day 2 private object archive](DAY2_PRIVATE_OBJECT_BACKUP.md)).
These produce **baseline-only** `baseline_archived` /
`baseline_verified` receipts. Such receipts cannot replace the later
nonempty private-PDF task archive and **must never** satisfy
`staging_backup_restore.py verify`, D02.T09 or D02.G04. No staging cloud
operation is authorized by these source instructions.

## Phase 1 — prepare synthetic restore evidence

Run:

```bash
uv run --extra coworker python scripts/staging_backup_restore.py prepare \
  --state /secure/path/backup-restore-state.json \
  --rollout /secure/release/cohort-rollout.json
```

The prepare step:

- captures the source environment fingerprints before contacting the owner API or seeding records;
- resolves the disposable staging owner through the deployed API;
- creates one synthetic uploaded TXT source;
- stores the source in private object storage;
- creates and cancels one synthetic Coworker task referencing that source;
- records IDs, byte size, SHA-256, and hashed source-environment fingerprints only.

No customer content is used.

## Phase 2 — take the real backups

Use the actual managed-service backup mechanisms selected for Shuddho:

1. take a PostgreSQL backup/snapshot. For Supabase staging, use the
   [private schema archive and isolated database verification](../infra/README.md#back-up-and-verify-the-staging-database);
2. copy and hash every private object with the [guarded Day 2 object archive tool](DAY2_PRIVATE_OBJECT_BACKUP.md), or use an approved immutable provider-native object snapshot;
3. independently restore into a distinct empty object bucket and read back each SHA-256 byte digest before claiming the object part of D02.T09;
4. retain the actual PostgreSQL archive verification.json plus private object manifest and restore receipt; free-text backup/restore references alone are **not** independent backup evidence.

Do not claim the gate passed from backup creation alone.

## Phase 3 — restore into isolated targets

Restore both the database and object storage into separate staging resources.

The verification environment must point to those restored resources. Before opening the restore target, the verifier requires the prepared state to contain both source fingerprints as lowercase SHA-256 digests. It rejects either target when its fingerprint matches the corresponding source.

## Phase 4 — verify

Run in the restored environment:

```bash
uv run --extra coworker python scripts/staging_backup_restore.py verify \
  --state /secure/path/backup-restore-state.json \
  --backup-reference postgres-snapshot-123/object-backup-456 \
  --restore-reference isolated-restore-run-789 \
  --rollout /secure/release/cohort-rollout.json \
  --postgres-verification /secure/private-backups/source-db/verification.json \
  --postgres-archive /secure/private-backups/source-db/coworker.dump \
  --object-archive-directory /secure/private-backups/staging-source-objects \
  --object-restore-receipt /secure/private-backups/object-restore-receipt.json \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.restore.json
```

The verifier now **rejects free-text-only evidence**: nonempty backup/restore references remain trace IDs, but four mandatory protected file paths supply the real verified PostgreSQL dump and readback, entire private-object byte archive and isolated object restore receipt. The PostgreSQL source archive must attest the same database fingerprint captured in the prepare state; its dump SHA-256 and 84+ per-table row counts/digests must be valid. The verifier runs a new read-only, repeatable-read inventory on the isolated PostgreSQL target and requires exact schema, revision, table and row-digest equality. It rehashes every archived object, matches the complete isolated object restore receipt, and proves the selected probe object occurs in that full manifest. The source and restored database/object resource fingerprints must differ.

The resulting `archive_integrity` object contains only hashed source/target identities, counts, revisions and archive SHA-256 values; no object keys, credentials or document bytes are returned. The acceptance reconciler requires it alongside the original `backup_restore` stage. Existing legacy `backup_restore` receipts lacking this structure must be rerun, not edited to look current.

**Important:** independently review the actual native PostgreSQL archive/restore output, object restore operator actions, approved custody, owner A/B API denial and matching release identity; these structured receipts establish mutual consistency, not cryptographic authentication of the cloud operator or live hosted Day 2 PASS. Do not execute these managed operations without fresh Founder/C authorization.

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

## Local evidence-file protection

The prepare state manifest and verified evidence output are created atomically with POSIX mode 0600. The writer refuses to overwrite an existing target and removes its temporary file after publication. Keep both files in a private operator-controlled directory and do not upload them to public issue comments.

## Evidence boundaries

The evidence file contains no JWTs, database URLs, storage endpoints, object keys, source bytes, or provider credentials.

A successful drill promotes only `backup_restore`. Retention/deletion, orphan cleanup, v2→v1 rollback, and live provider checks remain separate production gates.


A passing `backup_restore` record includes its verification timestamp, release ID, deployed source revision, and exact rollout-manifest SHA-256. PA-11 incident/restore compilation requires those values to match the reviewed release.
