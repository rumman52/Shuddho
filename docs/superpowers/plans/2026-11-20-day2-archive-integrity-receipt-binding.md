# Day 2 Archive Integrity Receipt Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the legacy Day 2 restore probe from emitting a `backup_restore=passed` receipt based only on unverified text references and one restored object.

**Architecture:** Preserve the existing isolated PostgreSQL snapshot/restore verifier and private-object byte archive/restore tools. Attach the database server fingerprint to the snapshot receipt. A new read-only receipt reconciler verifies the real archive byte checksum, the per-table snapshot inventory against the actual restored database, complete object archive bytes against the restore receipt, distinct source/target fingerprints and the synthetic probe's object identity before the Day 2 pass label can be written. The acceptance gate requires a structured archive-integrity summary and continues to disclaim independently operated hosted acceptance.

**Tech Stack:** Python, psycopg 3, SQLAlchemy, PostgreSQL, existing S3 storage abstraction, SHA-256, pytest.

**Spec:** `docs/coworker-roadmap/DAY2_EXECUTION_CONTRACT_2026-11-12.md`; attached Part 02 staging prompt; `docs/CONTROLLED_STAGING_BACKUP_RESTORE.md`.

## Global Constraints

- Source staging `bsmbvjenpvcyfjzwtuax`, private schema `shuddho_coworker`; observed ledger `0070`, code target `0072_merge_0071_heads`.
- No remote staging mutations, provider calls, paid resource provision, secrets in logs or success labels from CI alone.
- Validate and compare both full PostgreSQL per-table inventories and all archived private-object SHA-256 bytes.
- Source and restored database and object storage must be distinct; reject malformed or missing receipts before publishing.
- The output must remain secret-free and bound to existing immutable release evidence.

## Review Focus

- [ ] Missing or forged PostgreSQL verification JSON / wrong dump checksum fails before any pass receipt.
- [ ] PostgreSQL source fingerprint mismatch or restored table-level row digest mismatch fails.
- [ ] Corrupt object archive bytes or missing objects fail; no partial archive accepted.
- [ ] Different object restore source, manifest checksum, target fingerprint or probe object fails.
- [ ] Invalid private file paths / symlinks / reused output destination fail with no pass receipt.

---

### Task 1: Bind the database backup to its source environment

**Files:** Modify `scripts/staging_postgres_backup.py`; test `tests/test_staging_postgres_backup.py`.

**Interface:** `dump_source(url, archive, pg_bin) -> tuple[source_inventory, source_database_fingerprint]`; `run_backup` includes `source_database_fingerprint`.

- [ ] Write test requiring a lowercase database fingerprint bound to the source archive.
- [ ] Verify failure before implementation.
- [ ] Compute the same hash over `server_address|port|database` used by restore state; preserve existing per-table snapshot equality and archive SHA-256.
- [ ] Run PostgreSQL backup tests and check the result.

### Task 2: Reconcile authentic archive/restore evidence

**Files:** Create `scripts/staging_day2_archive_attestation.py`; test `tests/test_staging_day2_archive_attestation.py`.

**Interface:** `attest_archives(state, target_fingerprints, postgres_verification, postgres_archive, object_archive, object_restore_receipt) -> (summary, source_inventory, restored_objects)`.

- [ ] Write positive synthetic local-object receipt and negative forgery/tamper tests.
- [ ] Verify failure before implementation.
- [ ] Parse only bounded JSON; validate source database fingerprint, PostgreSQL revision, full table count/hash inventory and raw dump SHA, object archive bytes/manifest digest, source/target object identities, exact object list and SHA matching.
- [ ] Run targeted tests, preserving no-key logs or cloud side effects.

### Task 3: Require full restored database and source-object parity

**Files:** Modify `scripts/staging_backup_restore.py`; test `tests/test_staging_backup_restore.py`.

**Interface:** Require `--postgres-verification`, `--postgres-archive`, `--object-archive-directory`, `--object-restore-receipt` for `verify`; restore SQL readback must match `source_inventory`, and restored probe object must appear in the full verified object inventory.

- [ ] Add negative tests for missing receipts and mismatched target inventory.
- [ ] Verify failures before implementation.
- [ ] Compare actual restored database inventory with source PostgreSQL snapshot in a read-only repeatable-read transaction.
- [ ] Reject mismatch before writing `passed`; record only structured nonsecret hashes/counts in `archive_integrity`.

### Task 4: Make Day 2 reconciliation fail closed and document the operator contract

**Files:** Modify `scripts/staging_day2_acceptance.py`, `tests/test_staging_day2_acceptance.py`, `docs/CONTROLLED_STAGING_BACKUP_RESTORE.md`, `docs/coworker-roadmap/DAY2_EXECUTION_CONTRACT_2026-11-12.md`.

- [ ] Add malformed/absent `archive_integrity` acceptance tests.
- [ ] Reject old free-text-only synthetic restore receipts; preserve the explicit operator-supplied evidence caveat.
- [ ] Document new required CLI paths, separate private PostgreSQL archive/object receipts and independent D readback.
- [ ] Verify focused tests and exact-head repository CI, create a draft PR; do not claim hosted acceptance.
