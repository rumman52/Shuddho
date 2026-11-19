# Day 2 Bidirectional Owner-Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Day 2 evidence prove positive and negative document/artifact access for both synthetic owners without adding a second provider-backed task.

**Architecture:** Extend the existing Day 2 operator with a required pre-existing owner-B artifact control ID and a B-owned TXT document. Emit structured owner A/B evidence; make the Day 2 acceptance gate reject missing, one-way, or mismatched proofs.

**Tech Stack:** Python 3.12, httpx, pytest, existing Coworker API and GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-19-day2-bidirectional-owner-isolation-design.md`

## Global Constraints

- Preserve the single owner-A provider-backed PDF task.
- Never create paid resources, provision identities, expose credentials, migrate staging, or run hosted writes without separate approval.
- Require a real B-owned artifact control; do not infer ownership from a guessed or nonexistent ID.
- Keep private source bytes, tokens, signed URLs, and raw account identifiers out of evidence.
- Source/CI completion is not hosted operational acceptance.

## Review Focus

- Missing, malformed, or foreign owner-B artifact IDs must fail before document/task writes.
- Owner B's artifact must be positively readable by B and denied to A for both content and download.
- Owner A's artifact must be positively readable by A and denied to B for both content and download.
- Each owner must read its own document; the opposite owner must receive 404 for read/write and must not enumerate it.
- The acceptance gate must reject a missing direction, duplicate resource IDs, or altered receipts copied through recovery/restore.

---

### Task 1: Add failing Day 2 execution tests

**Files:**
- Modify: `tests/test_staging_day2_execution.py`

**Interfaces:**
- The tests define the required `run_probe(..., owner_b_artifact_id=...)` input and structured `owner_isolation` receipt.
- The test transport models separate owner-A and owner-B documents/artifacts and the API's owner-scoped lists.

- [ ] **Step 1: Add `test_day2_proves_bidirectional_document_and_artifact_access`**; assert both owners have distinct document/artifact IDs, own reads/downloads pass, both foreign directions return `denied_404`, and both foreign listings are excluded.
- [ ] **Step 2: Add `test_day2_requires_owner_b_control_artifact_before_any_private_write`**; assert a missing B artifact fails before any POST/PUT.
- [ ] **Step 3: Add `test_day2_rejects_cross_owner_access_in_either_direction`**; parameterize A→B and B→A document read/write plus artifact content/download.
- [ ] **Step 4: Add `test_day2_rejects_foreign_resource_enumeration`**; cover document and artifact list leakage in both directions.
- [ ] **Step 5: Run the focused test file and confirm failures are caused by the missing behavior**

Run: `uv run --locked --extra coworker pytest -q tests/test_staging_day2_execution.py`

Expected before implementation: failures for the missing B-artifact argument and missing structured bidirectional proof.

### Task 2: Implement bidirectional operator evidence

**Files:**
- Modify: `scripts/staging_day2_execution.py`
- Modify: `scripts/staging_api_exercise.py`
- Test: `tests/test_staging_day2_execution.py`
- Test: `tests/test_staging_api_exercise.py`

**Interfaces:**
- Extend `run_probe(client, token_a, token_b, freeze, source, *, owner_b_artifact_id, timeout_seconds=180, trusted_storage_host=None)`.
- Add private helpers to validate the B-owned artifact metadata and test each owner's document/artifact access.
- Return `owner_isolation = {status, identities_distinct, owners: {a, b}}`; each owner record contains distinct `document_id`/`artifact_id` and explicit own-read, foreign-denial, and foreign-list statuses.

- [ ] **Step 1: Validate the B artifact UUID and both JWTs' issuer, audience, expiry window, role and distinct subject before any write**
- [ ] **Step 2: Verify B's positive artifact content/download and A's 404 denial with digest checks**
- [ ] **Step 3: Create B's synthetic TXT document and A's selected PDF; verify both document directions**
- [ ] **Step 4: Verify A's report artifact and B's denial; capture both owner records and the API-bound subject proof**
- [ ] **Step 5: Require `--owner-b-artifact-id` in the CLI and pass it to `run_probe`**
- [ ] **Step 6: Expose `task_id` and `artifact_id` from `staging_api_exercise.py --artifact` receipts so a separately approved B control artifact can be supplied without logging secrets**
- [ ] **Step 7: Run the focused execution/API-exercise tests and confirm all pass**

Run: `uv run --locked --extra coworker pytest -q tests/test_staging_day2_execution.py`

### Task 3: Make the acceptance gate validate both directions

**Files:**
- Modify: `scripts/staging_day2_acceptance.py`
- Modify: `tests/test_staging_day2_acceptance.py`

**Interfaces:**
- Add `validate_owner_isolation(value, document_id, artifact_id)`.
- Require owner keys `a` and `b`, distinct document/artifact IDs, owner A IDs matching the primary PDF task, and exact positive/negative/list-exclusion statuses in both directions.
- Keep the structured `owner_isolation` receipt in the returned evidence summary and preserve exact equality across recovery/restore.

- [ ] **Step 1: Update `proofs()` with distinct `owners.a` and `owners.b` records and all exact status fields.
- [ ] **Step 2: Add `test_acceptance_rejects_missing_or_leaky_bidirectional_owner_proof` for each direction and resource type.
- [ ] **Step 3: Add `test_acceptance_rejects_duplicate_or_mismatched_owner_resource_ids` and `test_acceptance_rejects_missing_owner_direction_or_identity`.
- [ ] **Step 4: Run the acceptance tests and confirm the new tests fail against the current gate.
- [ ] **Step 5: Implement `validate_owner_isolation` and require it from `validate_evidence`.
- [ ] **Step 6: Run the acceptance tests and confirm all pass.

Run: `uv run --locked --extra coworker pytest -q tests/test_staging_day2_acceptance.py`

### Task 4: Update the operator contract and current readback

**Files:**
- Modify: `docs/coworker-roadmap/DAY2_EXECUTION_CONTRACT_2026-11-12.md`

- [ ] **Step 1: Document the required pre-existing B-owned artifact ID and the separately authorized reversed-token control exercise**
- [ ] **Step 2: Document both document/artifact directions and the schema-version-1 structured receipt**
- [ ] **Step 3: Record the 19 November Render/Supabase/Vercel readback without credentials or raw receipts**
- [ ] **Step 4: State explicitly that a missing B artifact blocks before the A task and does not authorize a second provider call**

### Task 5: Full verification and review

**Files:**
- Verify: `tests/test_staging_day2_execution.py`
- Verify: `tests/test_staging_day2_acceptance.py`
- Verify: `tests/test_staging_migration_alignment.py`
- Verify: `tests/test_staging_backup_restore.py`

- [ ] **Step 1: Run the exact Day 2 required test command**
- [ ] **Step 2: Run repository CI on the exact PR head and inspect every job**
- [ ] **Step 3: Review the complete diff for secret leakage, unintended staging calls, and scope drift**
- [ ] **Step 4: Open a ready-for-review PR; do not merge or deploy**

Run:
```bash
uv run --locked --extra coworker pytest -q \
  tests/test_staging_day2_execution.py tests/test_staging_day2_acceptance.py \
  tests/test_staging_migration_alignment.py tests/test_staging_backup_restore.py
```

