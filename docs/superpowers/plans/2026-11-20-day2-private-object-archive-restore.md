# Day 2 Private Object Archive and Isolated Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the D02.T09 source-code gap by archiving every private object with its own SHA-256 and verifying the bytes after restoring to a distinct, empty object-storage target.

**Architecture:** Implement a guarded, operator-only `scripts/staging_object_backup.py` module with two phases: (1) a private, immutable directory archive that enumerates all objects and downloads/sha256-hashes each exact byte sequence; (2) a preflighted isolated-target restore that checks all archive digests *before* its first PUT and re-reads all restored objects afterwards. Use the existing `S3ObjectStore` interface, metadata for real S3 content types, and the existing 0600 atomic private receipt writer.

**Tech Stack:** Python 3, object-store abstraction, boto3-backed S3 in production, LocalObjectStore in tests, pytest, SHA-256.

**Spec:** `02_Rukh_AI_Private_Staging(1).docx`, Part 02 Day 02 Platform Operation #2–#3 and D02.T09; existing `scripts/staging_backup_restore.py`, `scripts/staging_postgres_backup.py`.

## Global constraints

- NEVER run an archive or restore against managed staging in CI. Local tests run only against disposable temporary storage.
- Hosted mutation needs Founder/C's recorded approval, reviewed source SHA, cost ceiling, distinct restore targets and rollback owner (issue #291).
- Never expose private object bytes, raw keys, connection credentials, or model tokens in logs/PR artifacts. The manifest stays mode 0600 in a newly created owner-controlled private directory.
- Refuse source==target, existing objects on restore, incomplete/truncated listings, oversized objects, symlinked archive files, corrupt manifests, and stale listings.
- Archive verification alone is NOT hosted acceptance: independent database schema/data fingerprints, API owner A/B checks, and external restore/service evidence are still required.

## Review focus

1. Incomplete S3 pagination or duplicate keys can produce a false full backup.
2. A mutated object between listing and GET cannot be counted as a stable source snapshot.
3. Unverified or symlinked local archive bytes could be uploaded on restore.
4. Existing target objects must not be overwritten or mixed into a claimed clean restore.
5. A forged target identifier must never permit writing into the original bucket, and every restored object must be read back and SHA-256 verified.

## Task 1: Test red path

**Files:** Create `tests/test_staging_object_backup.py`.

- [ ] Write real LocalObjectStore tests for binary/newline/Unicode exact bytes and nested private keys.
- [ ] Assert corrupted archive, forged manifest, source==target, nonempty target and changed listing fail before the first `put`.
- [ ] Assert missing/oversized objects fail archive without any success manifest.
- [ ] Assert target byte corruption after PUT fails and produces no green restore receipt.
- [ ] Run CI to observe the tests fail before implementation.

## Task 2: Implement constrained tool

**Files:** Create `scripts/staging_object_backup.py`.

- [ ] Implement `archive_store(storage, fingerprint, directory)` with exact complete inventory, SHA-256 readback, private files and source-inventory comparison.
- [ ] Implement `restore_store(storage, fingerprint, directory, receipt_output)` with full preflight, empty distinct target, verified writes and second full-target inventory/readback.
- [ ] Preserve S3 MIME types through `head_object` and `put_object` path; restrict archive key usage and document fail-closed size limits.
- [ ] Use explicit staging/S3 guards in CLI; the test-callable functions never open an API or remote backend themselves.
- [ ] Re-run tests and inspect CI logs.

## Task 3: Operator docs and PR

**Files:** Create `docs/DAY2_PRIVATE_OBJECT_BACKUP.md`, update `docs/CONTROLLED_STAGING_BACKUP_RESTORE.md`.

- [ ] Document source and distinct target settings, private archive permissions, source and restore inventory receipts, how to retain original raw failure output.
- [ ] Mark source objects without versioning as a consistency limitation; do not accept snapshot of a moving bucket as an atomic cross-service backup.
- [ ] Explain how this supplements (not replaces) `staging_postgres_backup`, two-owner hosted negative authorization tests and a real worker restart.
- [ ] Submit a PR linked to #728 and MD-6, and report independent CI without claiming hosted D02 acceptance.
