# Day 5 Reciprocal Owner and In-Flight Memory Acceptance: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. GitHub-connected source edits; no authorization for hosted staging changes.

**Goal:** Make Part 03's Day 5 receipt verifier fail closed when owner denial receipts are not tied to the other managed owner's *real* private fact/context/output, or when a v1→v2 memory correction does not cause a new in-flight stale decision commit to be denied.

**Architecture:** Extend the existing read-only `scripts.staging_days3_6_acceptance.check_day5` contract; store no secrets or private user data. Authenticate these new receipt claims later against a live frozen release via the independent reviewer. Keep `evidence_internally_consistent_not_live_attested` as the only verifier success disposition. Production task logic and schema are intentionally unchanged.

**Tech stack:** Python 3.12+, pytest, GitHub Actions, frozen owner-scoped model receipts; no new dependencies, migrations, deployment, or paid-model calls.

**Spec:** User-uploaded `03_Rukh_AI_Product_Workflows.docx`, pp. 6–7 (D05.T01–T10; G01–G05), and p. 10 independent platform authentication. GitHub issue #731, Linear MD-7; Day 2 MD-6 is a prerequisite for hosted acceptance.

## Task 1 — Bind each owner-negative probe to the opposite positive owner's exact resource

**Files:** `tests/test_staging_days3_6_acceptance.py`, `scripts/staging_days3_6_acceptance.py`

- [x] Add to both owner-positive records exact `own_fact_id`, `own_context_id`, `own_output_id`, `own_output_sha256`, three owner-positive 200 statuses, and per-resource positive readback refs.
- [x] For each foreign denial require exact `foreign_{fact,context,output}_target_id` and `foreign_{fact,context,output}_owner_ref`, matching the opposite positive resource and the frozen opposite owner, plus existing 403/404 and denial receipt. Ensure A context refers to an actual three-arm run and output SHA; B context must be a separate B-owned run.
- [x] Add synthetic adversarial cases for self-denials, unrelated/nonexistent IDs, wrong owner, forged positive status, stale context/output and omitted refs.
- [x] Commit tests **before production**. RED GitHub Actions [#44886562655](https://github.com/rumman52/Shuddho/actions/runs/44886562655): **85 required adversarial cases failed** because the previous verifier did not raise, **2,930 passed / 105 skipped** overall.
- [x] Implement the minimal reciprocal identity and positive-read proof gate.

## Task 2 — Require observed preview-to-run memory identity and actual in-flight stale-commit outcome

**Files:** same two files

- [x] Add exact per-arm `preview_digest_sha256` and `admitted_preview_digest_sha256`; require equality within each arm and distinct digests across none/v1/v2.
- [x] Require per-arm model started/finished timestamps with v1 before the corrected fact and v2 after it, within the Day 5 hosted window.
- [x] Require `inflight_correction` bound to frozen owner A, selected fact v1→v2, a separate provider request and run, with provider started before correction, provider finished before the attempted fresh commit, and an observed `memory_pins_changed` rejection after the update. New committed decisions, tool invocations and outbox effects must all be zero. Require provider, memory update, rejection and decision store receipts.
- [x] Require v1 historical replay **after** the correction and v2 run: original run/output identity retained, zero new decisions and outbox effects, and decision readback reference.
- [x] Verify RED using the test-only commit, then implement the minimal production guards.

## Task 3 — Verify and hand off without inventing hosted PASS

- [ ] Run GitHub Actions exact-head Python full suite and focused Days 3–6 acceptance tests; record counts from runner logs.
- [ ] Verify Coworker, frontend, browser, PostgreSQL and CI ancestry jobs at the same SHA; record governance audit and merge-gate state separately.
- [ ] Request independent review before merging. Audit that the verifier still does *not* fetch bytes, authenticate provider histories, or itself conduct a two-owner browser session.
- [ ] Update GitHub #731, Linear MD-7 with PR and test receipts, while keeping the hosted Day 5/Part 03 issue status blocked until managed A/B owners, staging DB, API, worker, model and browser evidence is reviewed.

## Hosted operator requirements (NOT performed by this PR)

Freeze reviewed release and owner A/B identities; record real A positive fact/context/output retrievals and B negatives, then B positives/A negatives on actual APIs. Capture all three provider runs, user-facing preview and admitted canonical digests. Correct selected v1 while a provider planner call is *in-flight*; independently inspect provider timing, DB rejection at fresh decision commit, zero inserted AgentDecisions/tools/outbox and unchanged old v1 result on historical replay. Verify the same fixed source/brief/model/budget/policy and new v2 output, independent reviewer after receipts. A paper or synthetic receipt is never sufficient.

**Boundaries:** Do not choose Render workspace without user confirmation, create paid resources or model calls, run staging DDL, expose owner data, email externally, or claim live acceptance. Connector context may lack Shuddho-specific PostHog, ProductOS and Vercel projects; do not attribute unrelated accounts to this release.
