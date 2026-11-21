# Day 2 D02.T09: Private Object Archive and Isolated Restore

This is an operator-only helper for Part 02 of the RUKH AI Day 2 prompt:
**copy every private object, record its exact SHA-256, restore bytes into a
distinct target, and read every restored object back**.

It complements the separate private-schema PostgreSQL archive
(`scripts/staging_postgres_backup.py`) and synthetic account/task drill
(`scripts/staging_backup_restore.py`). **It is not a substitute** for a
real Supabase backup/restore, a cross-system consistent snapshot, a hosted
API owner A/B authorization test, the PDF/provider run, worker interruption,
or the D02.T09/G04 independent acceptance receipts.

## Authorization, preparation and protection

Per [issue #291](https://github.com/rumman52/Shuddho/issues/291), **NO-PROVISION**
remains effective. Before using these commands against managed resources,
the Founder and C must record the approved staging/restore hosts, cost ceiling,
duration, deployment and backup/restore authority, private restore targets and
rollback owner. Approval must be fresh, dated, and separate from historic
$7/month worker discussions. Do not create paid resources from this document.

Choose a new owner-controlled private directory under a mounted private
backup volume with mode 0700. The command refuses to overwrite the archive
directory and writes object files and the manifest with mode 0600. Object
keys and SHA-256 belong only in this private directory, not GitHub or logs.

The archive has a deliberate **64 MiB per-object ceiling**, and a
**10,000-object ceiling** and a **256 MiB aggregate byte ceiling**, to avoid unbounded in-memory downloads. If the
reviewed source exceeds these ceilings, use a separately reviewed streaming,
version-aware backup method rather than deleting or skipping objects. An empty bucket can be preserved **only with the explicit `--allow-empty-baseline`
opt-in**. Its archive and restore statuses are `baseline_archived` and
`baseline_verified`, never `archived` or `verified`. This is preservation
of the initial zero-object state, **not** proof of private PDF recovery;
it cannot satisfy the Day 2 `archive_integrity` gate, D02.T09 or D02.G04.

**Original-state sequencing:** preserving the currently empty source bucket
is now a strict precursor to any Day 2 synthetic upload, worker/API migration
or account reconciliation. First capture verified source PostgreSQL 0070 with
`scripts.staging_postgres_backup`, then run
`scripts.staging_object_backup archive --allow-empty-baseline`.
While the source is still unchanged, run
`scripts/staging_backup_restore.py attest-original` with both original
PostgreSQL file paths and this zero-object archive, writing a private
`original-attestation.json` receipt. Only *after* that early source-state
attestation and separately approved migration may
`staging_backup_restore.py prepare` create its synthetic TXT/task.
Both `prepare` and later isolated `verify` require the original
attestation and rehash all three original backup artifacts. See
[controlled restore ordering](CONTROLLED_STAGING_BACKUP_RESTORE.md).
This does not turn an empty-bucket receipt into private PDF recovery proof.

## Phase 1 — archive the approved source bucket (read only)

Use the approved S3 server-side credentials from a **secure environment**.
Never put access tokens or database/S3 secrets in shell transcripts, receipts
or GitHub. The required nonsecret settings include:

```bash
SHUDDHO_COWORKER_ENV=staging
SHUDDHO_COWORKER_STORAGE=s3
SHUDDHO_COWORKER_BUCKET=shuddho-coworker-staging
SHUDDHO_COWORKER_S3_ENDPOINT=https://bsmbvjenpvcyfjzwtuax.storage.supabase.co/storage/v1/s3
AWS_DEFAULT_REGION=us-west-1
SHUDDHO_STAGING_ALLOW_OBJECT_ARCHIVE=true

uv run --locked --extra coworker python -m scripts.staging_object_backup archive \
  --directory /secure/private-backups/staging-source-objects
```

Use `Settings.from_env`'s current setting names in your protected
environment; the example is descriptive, not an authorization to create
or mutate resources. It lists all objects using the existing pagination-safe
object store, reads their bytes and S3 MIME metadata, validates any published
SHA-256 metadata, writes all bytes in flat SHA-256(key)-named files and
records full inventory, size, modification time, content type and digest.
It compares the first and last source listings and only then publishes
`manifest.json`. The source fingerprint is SHA-256 of
`storage_backend|endpoint|bucket|region`.

**Consistency boundary:** object-store versioning / immutable snapshot
semantics are not inferred from identical listings. Concurrent writes
between reads can escape comparison. To qualify actual hosted restoration,
freeze writers or capture an approved versioned/object-store snapshot and
correlate it with the PostgreSQL snapshot.

## Phase 1a — preserve the zero-object pre-seeding baseline

The 20 November read-only staging inventory showed **zero objects** in the
named private bucket. Part 02 explicitly requires preserving this source
state *before* any synthetic account or document is seeded. With the same
approved secure source credentials and `SHUDDHO_STAGING_ALLOW_OBJECT_ARCHIVE=true`,
run:

```bash
uv run --locked --extra coworker python -m scripts.staging_object_backup archive \\
  --directory /secure/private-backups/preseed-empty-objects \\
  --allow-empty-baseline
```

This opt-in refuses **nonempty** source buckets, verifies two stable empty
listings and writes a fresh protected 0600 manifest with `object_count=0`,
`total_bytes=0`, `objects=[]` and `status=baseline_archived`. The
source fingerprint is included. Do not rename this receipt or claim that
any private document bytes were backed up. The default `archive` command
still refuses an empty bucket for task-recovery evidence.

To test restoring that empty starting state, first authorize a *separate
empty target* and enable the existing
`SHUDDHO_STAGING_ALLOW_OBJECT_RESTORE=true` and
`SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true` guards:

```bash
uv run --locked --extra coworker python -m scripts.staging_object_backup restore \\
  --archive-directory /secure/private-backups/preseed-empty-objects \\
  --output /secure/private-backups/preseed-empty-restore.json \\
  --allow-empty-baseline
```

The tool requires source and destination fingerprints to differ and refuses
a nonempty target. It performs **no object PUTs** and writes
`status=baseline_verified` plus zero object counts. Neither the ordinary
restore mode nor `staging_day2_archive_attestation` accepts a baseline
manifest as a successful private-task restore. Once owner A uploads a
synthetic PDF, create a **new full nonempty archive and isolated restore**
to demonstrate the actual task and bytes; never reuse the preseed baseline
as that task's proof.

## Phase 2 — restore only to a separately authorized empty target

Prepare an isolated **different bucket or endpoint** with protected S3 keys,
and load the corresponding target settings from the secure environment.
Keep all production flags OFF. Set *both* guards after approval:

```bash
SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true
SHUDDHO_STAGING_ALLOW_OBJECT_RESTORE=true

uv run --locked --extra coworker python -m scripts.staging_object_backup restore \
  --archive-directory /secure/private-backups/staging-source-objects \
  --output /secure/private-backups/object-restore-receipt.json
```

The tool refuses the original source storage fingerprint and any nonempty
target. Before the first PUT it verifies the entire manifest schema, key/file
mapping, sort order, unique keys, every local byte count and SHA-256, prevents
symlink reads, and preflights the final private receipt destination. If one
archive object fails, no target PUT is attempted.

The target verification runs only after every PUT: full key/size listing
parity, exact stored-byte SHA-256 readback, S3 MIME metadata and SHA-256
metadata parity. Failure **does not generate a passed receipt**; treat the
partially filled target as quarantined and reset via a separately authorized
process, never blindly rerun over an occupied bucket.

The success receipt contains source/target hashed identities, manifest
checksum, item count, byte total, each private key/digest, timestamp and
a conspicuous local-object-restore caveat. Keep that receipt private; it
does **not** automatically promote a Day 2 acceptance gate.

## Tests that do not contact S3 or modify staging

```bash
uv run --locked --extra coworker pytest -q tests/test_staging_object_backup.py
```

Tests use only disposable `LocalObjectStore` directories. They check
bit-for-bit binary/Unicode data, zero objects, mutation during archive,
over-limit objects, a same-resource target, an occupied target, forged or
corrupted manifests, symlinks, missing bytes, an existing receipt path,
corrupted target readback, and safe new-directory creation.

## Required independent hosted evidence

A/D/C must still verify PostgreSQL `0070` source archive, both Alembic
parents on **restored** data, per-table digests, final SQL/runtime revision,
actual authorized storage copying, **owner A positive and owner B negative**
API downloads (and reverse direction), immutable same-SHA API/Temporal
worker identity, real model-generated PDF content and outbox, and a
genuine worker restart while child tasks are active.

All of D02.T09 and D02.G04 remain **BLOCKED** until that hosted evidence
is collected; source-code CI is not a hosted pass.
