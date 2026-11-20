# Day 2 Empty Source Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the user's Part 02 pre-seeding full object inventory possible on a currently empty private Supabase staging bucket without falsely qualifying Day 2 task restore.

**Architecture:** Add explicitly opted-in empty-baseline mode to the existing source object archive and isolated restore helper, with a distinct manifest/receipt status. Preserve default refusal for empty snapshots and preserve fail-closed Day 2 task attestation when no private PDF object is present. Reuse all existing source identity, target separation and private output-path checks.

**Tech Stack:** Python 3.11, existing S3ObjectStore / LocalObjectStore adapter, SHA-256 JSON manifests, pytest.

**Spec:** `02_Rukh_AI_Private_Staging.docx` Part 02, "Back up then align staging" steps 1-3, and `docs/DAY2_PRIVATE_OBJECT_BACKUP.md`; current connected staging SQL 2026-11-20: schema 0070, zero Auth users and zero objects in private staging bucket.

## Global Constraints

- Keep production off; do not mutate connected staging without Founder+C authorization.
- No backup or restore claim based solely on CI; the empty baseline must not satisfy D02.T09/G04 private-task recovery by itself.
- Store key/digest inventory only in 0600 protected operator receipts, never GitHub.
- Preserve default behavior rejecting empty source/target for private-task restore; add an explicit opt-in.
- Fail closed on corrupted/forged zero-count manifests or target nonempty.

## Review Focus

- [ ] Fresh zero-object source snapshot with explicit opt-in creates a schema-checked baseline manifest.
- [ ] Default object archive refuses zero objects as before.
- [ ] Baseline manifest restore requires explicit opt-in and empty distinct target; no writes and a baseline-only receipt.
- [ ] A zero-object baseline cannot pass archive attestation or the Day 2 private-PDF acceptance gate.
- [ ] Nonempty archive in baseline mode is rejected rather than silently misclassified.
- [ ] CLI requires the existing staging guard and clearly labels archive/restore baseline-only status.

### Task 1 — Red tests for pre-seeding empty bucket

**Files:** `tests/test_staging_object_backup.py`, `tests/test_staging_day2_archive_attestation.py`.

- [ ] Add tests expecting an explicit zero-object baseline archive/restore with distinct identity and baseline-only receipts.
- [ ] Retain default empty-source error test; add negative tests for baseline mode with nonempty source, ordinary restore of baseline archive and occupied restored target.
- [ ] Add archive attestation test that rejects baseline-only manifest/receipt.
- [ ] Observe first CI's failing tests before implementation.

### Task 2 — Minimal guarded implementation

**Files:** `scripts/staging_object_backup.py`, `scripts/staging_day2_archive_attestation.py`.

- [ ] Add `allow_empty_baseline=False` keyword to test-callable `archive_store` and `restore_store`; add `--allow-empty-baseline` opt-in only to the relevant CLI subcommands.
- [ ] Encode distinct manifest status `baseline_archived` and restore receipt `baseline_verified` for zero-object archives. Reject status/count inconsistencies.
- [ ] Enforce explicit opt-in on restore, no object PUTs, empty target, source/target separation, receipt preservation and unchanged default nonempty path.
- [ ] Reject any baseline manifest in the Day 2 full-task archive attestation, even when a valid isolated baseline-only restore exists.
- [ ] Run the Day 2 no-skips CI including object tests.

### Task 3 — Operator documentation and review

**Files:** `docs/DAY2_PRIVATE_OBJECT_BACKUP.md`, `docs/CONTROLLED_STAGING_BACKUP_RESTORE.md`.

- [ ] Document exact source pre-seed empty-baseline and restore CLI with guards/approved target.
- [ ] State baseline-only preserves 0-object state but cannot prove a PDF/task or satisfy D02.T09/G04.
- [ ] Create a reviewable draft PR, read CI and keep Linear/issue #728 explicitly blocked pending live authorization.
