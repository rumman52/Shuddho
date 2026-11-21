# Day 2 Original-State Archive Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this test-first implementation; retain red/green CI evidence.

**Goal:** Enforce Part 02's "preserve original state before any synthetic account or document is seeded" requirement within the Day 2 source operator, while keeping the later task-state archive separate.

**Architecture:** A read-only baseline reconciler checks a verified PostgreSQL `0070` dump, full private-table inventory and structural SHA against a real zero-object source manifest. An **early** `attest-original` operator reads the still-unmodified live database/object inventories and writes an exclusive timestamped receipt before any migration, synthetic account or document. Later `staging_backup_restore.prepare` rehashes the three original artifacts, validates that early receipt and matches the original source resource identities, **without comparing post-migration rows to 0070**. Isolated `verify` rechecks the same original artifacts/attestation plus the separately required post-task nonempty archive, and final acceptance binds the observed early timestamp.

**Tech stack:** Python 3.11, psycopg3, SQLAlchemy, existing `staging_postgres_backup` / `staging_object_backup` / `staging_day2_archive_attestation` utilities and pytest CI.

**Spec:** Original attachment `02_Rukh_AI_Private_Staging.docx`, p.2, items 1–3; p.4 D02.T09. Related `docs/CONTROLLED_STAGING_BACKUP_RESTORE.md` and issue #728.

## Constraints

- No actual managed source backup, schema DDL, account seeding, paid worker, deployment or provider inference without fresh dated Founder+C approval and approved isolated targets.
- Require **real archives** and fresh read-only source inventory before mutation. Reject missing, malformed, symlinked, wrong-identity and stale-original-baseline evidence. Do not leak keys, secrets, bytes or private row data to summary/PR.
- Source baseline must have PostgreSQL revision `0070`, 84+ private tables, valid `schema_sha256`, correct archive SHA-256, schema DAG with code head `0072_merge_0071_heads`, and a **zero-object** `baseline_archived` manifest.
- Keep the initial baseline and post-synthetic task archive as distinct, immutable artifacts. A zero-object baseline cannot prove PDF/object recovery.
- Preserve current `staging_backup_restore.verify` source/target distinct resource checks, task-state restore verification, and private output protection.
- Do not mark hosted Day 2 exits or Part 04 as passed. Independent verifier D still must read underlying hosted evidence.

## Review focus

- [ ] Archive source is byte-hash matched and its verified inventory includes `0070`, structural fingerprint, 84 tables, private ACL.
- [ ] The empty-object manifest cannot be replaced by a nonempty one or a claimed empty receipt.
- [ ] The **early** attest-original command checks full live original rows at 0070; the **later** prepare does not reject legitimately migrated 0072 rows.
- [ ] The early attestation file is exclusive, mode 0600, timestamped, and bound to the original dump/manifest digests; forged/late receipts are rejected.
- [ ] Correct original database and object-store identities match live source before any `create_upload`, `put`, `create_task` or `cancel`.
- [ ] Tables/rows/schema that drift after the archived source snapshot block synthetic seeding.
- [ ] Missing paths, wrong source identity and corrupt receipts block before contacting hosted owner API.
- [ ] Later restore re-hashes original three baseline files and requires exact persisted summary alongside its later task-state archive.
- [ ] Final acceptance refuses missing/unqualified original-state baseline and doesn't conflate baseline with private task recovery.

### Task 1: RED tests

- [ ] Add offline baseline fixture from synthetic PG receipt + source dump and `LocalObjectStore` zero-object manifest.
- [ ] Add tests for absent/forged baseline, present verified baseline, stale database inventory, and nonempty original object store.
- [ ] Add acceptance and verify tests for missing/changed baseline records.
- [ ] Push regression tests first and read expected failing CI.

### Task 2: GREEN source changes

- [ ] Create `scripts/staging_preseed_baseline.py` purely read-only baseline validator.
- [ ] Add `scripts/staging_backup_restore.py attest-original` to compare original 0070 live fingerprints, full schema/table inventories and empty source listing, writing a protected timestamped receipt **before migration/seeding**.
- [ ] Require the three original archive paths and early attestation in later `prepare`, validating their hashes and same DB/storage resource identity before any API call while allowing legitimate 0072 schema/row changes.
- [ ] Persist only baseline hashes/counts in the prepared state.
- [ ] Require and rehash the same baseline paths **and early attestation** on `verify`; attach the validated baseline summary and attestation timestamp to `archive_integrity` evidence.
- [ ] Require the summary in `staging_day2_acceptance.py` without claiming independent hosted authorization.

### Task 3: Tests, docs, PR

- [ ] Update `tests/test_staging_backup_restore.py`, `tests/test_staging_day2_acceptance.py`, CI if needed.
- [ ] Update `docs/CONTROLLED_STAGING_BACKUP_RESTORE.md` and Day 2 execution contract with explicit original-state backup first, task-state backup later.
- [ ] Verify exact-head mandatory Day 2 and general CI, PostgreSQL 18 compatibility, remaining checks.
- [ ] Create reviewable PR and record blockers on GitHub issue #728 / Linear MD-6.
