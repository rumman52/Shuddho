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

## Phase 0 — preserve and verify the **original** 0070 source before seeding

After fresh Founder/C authorization for the hosts, private backup custody, cost,
isolated destinations and rollback owner, obtain the protected source database
and S3 credentials through the approved operator environment. Do this **before
creating synthetic Auth accounts, uploading documents or starting tasks**.
Use a new private mode-0700 parent, read-only source snapshot and frozen writers
(or an approved cross-system snapshot) to prevent drift:

```bash
# Original source: stage 0070, *before* synthetic activity.
uv run --extra coworker python -m scripts.staging_postgres_backup \
  --directory /secure/private-backups/original-db
SHUDDHO_STAGING_ALLOW_OBJECT_ARCHIVE=true \
uv run --extra coworker python -m scripts.staging_object_backup archive \
  --directory /secure/private-backups/original-empty-objects \
  --allow-empty-baseline

# EARLY: directly verify the archive against still-unmodified source 0070
# before migrations, Auth provisioning or any synthetic API/object calls.
SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true \
uv run --extra coworker python scripts/staging_backup_restore.py attest-original \
  --original-postgres-verification /secure/private-backups/original-db/verification.json \
  --original-postgres-archive /secure/private-backups/original-db/coworker.dump \
  --original-object-archive-directory /secure/private-backups/original-empty-objects \
  --output /secure/private-backups/original-attestation.json
```

The original PostgreSQL helper generates
`original-db/verification.json` and `original-db/coworker.dump`.
The object helper generates `original-empty-objects/manifest.json`
with `baseline_archived`, exactly zero objects and zero bytes. This
zero-object source requirement deliberately blocks `prepare` if the private
bucket already has documents; recover the true pre-seed baseline through an
independently approved prior snapshot, not by deleting or skipping objects.

The early `attest-original` command hashes the PostgreSQL dump and
validates all 84+ table counts, row digests and structural schema SHA-256,
migration ledger `0070`, checked-in schema graph to `0072_merge_0071_heads`
and explicit zero-object archive. It reads both **current source**
fingerprints and full PostgreSQL inventory under a read-only repeatable-read
transaction, lists the current private bucket, and refuses any drift before
writing an exclusive mode-0600 `original-attestation.json` receipt.
No owner API or synthetic operation is performed at this stage.

After the authorized 0070→0072 migration and real task activity, a later
`prepare` **rehashes all three original archives and validates the early
attestation**, requiring the same source database/bucket identities. It
does **not** compare the already-migrated live rows to the old 0070
snapshot. Missing/mismatched original evidence blocks `prepare` before
its first owner API call, upload, object PUT or task creation. The protected
prepared receipt includes a digest-only `preseed_baseline` summary and
early attestation timestamp, never private object keys, rows, credentials
or source bytes. Independent D must still corroborate the actual source
snapshot timeline and hosted operator events.

The pre-seeding archive preserves the **original** state, not a post-task
backup. It does not qualify an owner PDF restore, provider inference, worker
replacement or hosted D02.T09/G04 independently.

## Phase 1 — prepare synthetic restore evidence

Run:

```bash
uv run --extra coworker python scripts/staging_backup_restore.py prepare \
  --state /secure/path/backup-restore-state.json \
  --rollout /secure/release/cohort-rollout.json \
  --original-postgres-verification /secure/private-backups/original-db/verification.json \
  --original-postgres-archive /secure/private-backups/original-db/coworker.dump \
  --original-object-archive-directory /secure/private-backups/original-empty-objects \
  --original-baseline-attestation /secure/private-backups/original-attestation.json
```

The prepare step:

- captures the source environment fingerprints before contacting the owner API or seeding records;
- resolves the disposable staging owner through the deployed API;
- creates one synthetic uploaded TXT source;
- stores the source in private object storage;
- creates and cancels one synthetic Coworker task referencing that source;
- records IDs, byte size, SHA-256, and hashed source-environment fingerprints only.

No customer content is used.

## Phase 2 — take a **separate post-synthetic** task-state backup

Only after the original-state baseline has been independently captured, the
prepared synthetic task-state now exists and requires its **own later** full
archive. Use the actual managed-service backup mechanisms selected for Shuddho:

1. take a PostgreSQL backup/snapshot. For Supabase staging, use the
   [private schema archive and isolated database verification](../infra/README.md#back-up-and-verify-the-staging-database);
2. copy and hash every private object with the [guarded Day 2 object archive tool](DAY2_PRIVATE_OBJECT_BACKUP.md), or use an approved immutable provider-native object snapshot;
3. independently restore into a distinct empty object bucket and read back each SHA-256 byte digest before claiming the object part of D02.T09;
4. retain the actual PostgreSQL archive verification.json plus private object manifest and restore receipt; free-text backup/restore references alone are **not** independent backup evidence.

Do not claim the gate passed from backup creation alone.

## Phase 3 — restore into isolated targets

Restore both the database and object storage into separate staging resources.

The verification environment must point to those restored resources. Before opening the restore target, the verifier requires the prepared state to contain both source fingerprints as lowercase SHA-256 digests. It rejects either target when its fingerprint matches the corresponding source.

## Phase 4 — verify the isolated restore **and its authenticated API**

Before running the verifier, the approved operator must deploy a **separate**
staging API bound to the isolated restored PostgreSQL database **and**
isolated restored private object bucket. A distinct hostname is not proof of
backend isolation: independently check the API service's actual DB/storage
environment binding and same-reviewed-SHA runtime. Retain deployment identity
and nonsecret health/source readback in the private evidence directory.

Require managed, distinct synthetic A/B JWTs accepted by this restored API,
with enough validity for the readback. The source and isolated origins must
be different clean public HTTPS origins. No bearer tokens or presigned URLs
may be passed on the command line or written into a receipt.

```bash
export SHUDDHO_STAGING_ALLOW_RESTORED_API_READBACK=true
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true
export SHUDDHO_STAGING_API_BASE_URL=https://source-staging.example.com
export SHUDDHO_STAGING_RESTORED_API_BASE_URL=https://isolated-restore.example.com
export SHUDDHO_STAGING_TOKEN_A="<approved-restore-owner-A-JWT>"
export SHUDDHO_STAGING_TOKEN_B="<approved-restore-owner-B-JWT>"
```

The verifier performs the PostgreSQL schema/row and private object byte
comparison **first**, then issues **read-only GETs** through the isolated API:
staging runtime manifest at the reviewed SHA; both authenticated `/me`
identities with distinct subjects/workspaces; A's source document contents
matching the archived byte size and SHA-256; B's document content denied with
404 and absent from B's document catalog; owner A's cancelled task read
verified and B's task read denied with 404. Redirects fail closed; no HTTP
writes, token values, private bytes or public signed URLs are emitted.

`archive_integrity.restored_api_access` contains only statuses, booleans,
digests and byte counts. Without this proof, neither `backup_restore: passed`
nor the final Day 2 acceptance reconciliation may be emitted. The independent
D reviewer must additionally validate the hosting provider's **actual isolated
API resource bindings**; this check alone cannot cryptographically establish
which backend a separate HTTPS hostname uses.

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
  --original-postgres-verification /secure/private-backups/original-db/verification.json \
  --original-postgres-archive /secure/private-backups/original-db/coworker.dump \
  --original-object-archive-directory /secure/private-backups/original-empty-objects \
  --original-baseline-attestation /secure/private-backups/original-attestation.json \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.restore.json
```

The verifier independently rehashes the original three pre-seeding paths,
revalidates the protected early attestation with its timestamp, requires that
their nonsecret summary exactly equals the protected prepare state and that
both original source resource fingerprints match the later source identity. It then verifies the **different, nonempty task-state**
backup and isolated restoration. The final `archive_integrity.preseed_baseline`
is strictly baseline-only; the main `archive_integrity` still requires a
verified synthetic probe and private object SHA-256. Missing legacy original
baseline receipts must not be retroactively invented or marked passed.

The verifier now **rejects free-text-only evidence**: nonempty backup/restore references remain trace IDs, but four mandatory protected file paths supply the real verified PostgreSQL dump and readback, entire private-object byte archive and isolated object restore receipt. The PostgreSQL source archive must attest the same database fingerprint captured in the prepare state; its dump SHA-256 and 84+ per-table row counts/digests must be valid. The verifier runs a new read-only, repeatable-read inventory on the isolated PostgreSQL target and requires exact schema, revision, table and row-digest equality. It rehashes every archived object, matches the complete isolated object restore receipt, and proves the selected probe object occurs in that full manifest. The source and restored database/object resource fingerprints must differ.

The resulting `archive_integrity` object contains only hashed source/target identities, counts, revisions, the `postgres_schema_sha256` structural catalog digest and archive SHA-256 values; no object keys, credentials or document bytes are returned. The PostgreSQL source inventory and restored-target inventory now include `schema_sha256` computed over read-only catalog definitions for relations, columns/defaults, constraints, indexes, triggers, RLS policies, sequences, routines and enum/domain types. The check is performed inside each database's repeatable-read snapshot, together with all table row digests; a changed index or column default fails the equality check even when every table row digest is unchanged. Column ordinals are normalized to **visible logical order**, avoiding false mismatches from internal dropped-column slots after a rollback/replay while still detecting visible order, type and default changes. Owner/ACL differences from `pg_restore --no-owner --no-privileges` are intentionally excluded from the structural digest and controlled separately by the private-schema grant audit. The acceptance reconciler requires it alongside the original `backup_restore` stage. Existing legacy `backup_restore` receipts lacking this structure must be rerun, not edited to look current.

**Important:** independently review the actual native PostgreSQL archive/restore output, object restore operator actions, approved custody, owner A/B API denial and matching release identity; these structured receipts establish mutual consistency, not cryptographic authentication of the cloud operator or live hosted Day 2 PASS. Do not execute these managed operations without fresh Founder/C authorization.

The gate becomes `passed` only if:

- the restored account and workspace exist;
- the source document/version exists and is still uploaded;
- restored document metadata matches the pre-backup manifest;
- the synthetic task still exists in its cancelled state;
- task event history is present;
- private restored object bytes match the exact pre-backup SHA-256 and byte size;
- two distinct managed synthetic owner tokens are accepted by the **isolated restored** API, owner A retrieves identical document bytes and the cancelled task, and owner B receives document/task denials;
- the database target differs from the source fingerprint;
- the object-storage target differs from the source fingerprint;
- non-empty backup and restore references are supplied.

## Local evidence-file protection

The prepare state manifest and verified evidence output are created atomically with POSIX mode 0600. The writer refuses to overwrite an existing target and removes its temporary file after publication. Keep both files in a private operator-controlled directory and do not upload them to public issue comments.

## Evidence boundaries

The evidence file contains no JWTs, database URLs, storage endpoints, object keys, source bytes, or provider credentials.

A successful drill promotes only `backup_restore`. Retention/deletion, orphan cleanup, v2→v1 rollback, and live provider checks remain separate production gates.


A passing `backup_restore` record includes its verification timestamp, release ID, deployed source revision, and exact rollout-manifest SHA-256. PA-11 incident/restore compilation requires those values to match the reviewed release.
