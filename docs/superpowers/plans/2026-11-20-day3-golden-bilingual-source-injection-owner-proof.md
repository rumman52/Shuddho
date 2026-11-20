# Day 3 Golden Source, Injection, and Reciprocal Owner Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Days 3–6 hosted receipt-consistency gate cannot accept a Day 3 "PASS" if the Bangla and English answers were generated from different private document versions, the source-instruction injection probe was not actually recorded, or the owner's reciprocal private-access direction was not examined.

**Architecture:** Extend only `scripts/staging_days3_6_acceptance.py::check_day3`. Compare the same owner-A (document ID, version ID, SHA-256) tuple in both answer receipts; check a source-bound, time-ordered independent injection-provider probe; and require positive owner-B access plus negative owner-A access to a distinct B-owned fixture. The unchanged top-level result remains `evidence_internally_consistent_not_live_attested`; authenticated platform readback, approved staging release and reviewer remain external prerequisites.

**Tech Stack:** Python 3.12+, pytest, existing `uv`-locked CI and GitHub Actions. No runtime dependencies or migrations.

**Spec:** The uploaded `03_Rukh_AI_Product_Workflows.docx`, pages 1–3 (Part 03, Day 3 D03.T03/G02, D03.T08–T10, G04/G05; same fixture and bidirectional owner access). GitHub tracker #729 (closed source-level) and Linear MD-7 (hosted acceptance open).

## Global Constraints

- The Day 3 answers must refer to the same owner-A private document *ID, exact version ID and byte SHA-256*; do not interpret a matching hash alone as a version.
- Only trusted source pin metadata can be authoritative. Source text containing a harmless conflicting instruction is evidence, not a command or permission.
- Injection evidence must include a bilingual-answer provider request, platform/browser receipt references, ordered timestamps, observed authority boundaries and zero additional AgentRuns/outbox effects.
- Owner B must independently read its own distinct private fixture; owner A must receive HTTP 403 or 404 for that B-owned version. Keep the existing A-own-positive and B-denied-A checks in each language.
- Do not create a "hosted PASS" from fixture or CI-only tests. No production deploy, account creation, paid provider call, provider email send, or staging database change.
- Preserve all existing Day 4–6 and release freeze/independent review checks.

## Review Focus

1. One answer's version ID differs from the other's while the digest is equal; reject (test `test_day3_bilingual_replies_must_share_exact_pinned_document_version`).
2. A missing or forged source-instruction test, unrelated provider identity or nonchronological completion; reject (test `test_day3_rejects_unverified_or_foreign_prompt_injection_probe`).
3. A probe where source text changed behavior or launched work; reject nonzero AgentRun/outbox effects.
4. B's nominal fixture is actually A's file or an unauthenticated/read-denied placeholder; reject (test `test_day3_rejects_one_way_or_nonindependent_owner_b_fixture`).
5. Positive synthetic fixture still yields **only** an internally-consistent decision, never an operated PASS (existing `test_consistent_synthetic_receipts_are_not_automatically_a_hosted_pass`).

---

### Task 1: Fail-closed Day 3 evidence binding

**Files:**
- Modify: `tests/test_staging_days3_6_acceptance.py`
- Modify: `scripts/staging_days3_6_acceptance.py`

**Interfaces:**
- Consumes: the existing `validate(freeze, day3, day4, day5, day6, review, *, expected_revision)`; Day 3 `answers`, `revocation`, `agent_runs_before/after`, `agent_outbox_before/after`.
- Extends `day3.answers[]`: `selected_document_id`, `selected_document_version_id` and existing `selected_document_sha256`.
- Ruling: use a provider request already present in one of the two Day 3 answers; the golden document contains the conflicting instruction, so an extra paid provider call is neither required nor justified. An unrelated or revoked request is rejected.
- Adds `day3.prompt_injection`: `source_document_id`, `source_document_version_id`, `source_document_sha256`, `provider_request_id`, `provider_receipt_ref`, `provider_started_at`, `provider_finished_at`, `verified_at`, `contains_conflicting_source_instruction`, `user_instruction_followed`, `source_instruction_ignored`, `additional_agent_runs`, `additional_outbox_effects`, `browser_evidence_ref`.
- Adds `day3.owner_b_fixture`: `document_id`, `document_version_id`, `document_sha256`, `owner_b_read_http_status`, `owner_a_read_http_status`, `owner_b_read_receipt_ref`, `owner_a_denial_receipt_ref`.
- Returns: original `datetime` upon success; `Days36EvidenceError` upon failure.

- [x] **Step 1: Add failing tests.** Test-only commit `dda27741a69355ce4bf1bdbaf086bf74ce2e2b6f`.
- [x] **Step 2: Verify RED.** Exact-head CI run [#44780113714](https://github.com/rumman52/Shuddho/actions/runs/44780113714) recorded **28 failed** cases (expected `DID NOT RAISE`), 2,724 passed, 102 skipped; no assertion of independent hosted execution.
- [x] **Step 3: Implement minimal verifier checks.** Validate pins, ordered injection request and status, and reciprocal B ownership receipts with existing `text/sha/when/count/need` helpers.
- [ ] **Step 4: Verify GREEN.** Re-run `uv run --locked pytest -q tests/test_staging_days3_6_acceptance.py`; inspect exact-head CI job output, full Python suite and required ancestry/governance checks. No "passed" claims for queued, cancelled or skipped jobs.
- [ ] **Step 5: Review and submit PR.** Record traceability, screenshots/logs where available, affected hosted exit checks and independent review requirement.

## Hosted acceptance boundary

The verifier only checks internally consistent operator-supplied JSON. Founder/C budget approval, backed-up and aligned staging database, same-SHA Render API/worker and web build, two managed Auth owners, real browser/provider action receipts, downloaded native bytes, send-provider audit and independent platform authentication are **not** created by this PR. Keep Linear MD-7 in NO-GO until these exist.
