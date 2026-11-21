# Day 3 Same-Source Revocation and Bilingual Reply Evidence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development, superpowers:verification-before-completion and superpowers:requesting-code-review. Do not infer live hosted PASS from a synthetic structural verifier.

**Goal:** Prevent a Day 3 receipt from claiming mid-inference source revocation by referring to a different private source than the actual cited bilingual answers. Require independently readable, per-answer A/B access and zero-new-task-effect receipt scopes, then browser/database proof of no stale content.

**Architecture:** Extend the existing read-only `scripts/staging_days3_6_acceptance.py::check_day3` contract without modifying the dispatch path or migrations. Require two distinct A-owned successful language replies first, the injection witness bound to the exact provider/browser reply, and then a *separate* actively running request whose same selected source is deleted/revoked during provider generation. Verify after provider completion both browser zero deltas and database zero stale bytes with failed final reply state. Raw platform receipts still require a live independent operator.

**Tech stack:** Python 3.12, pytest, GitHub Actions; no new dependencies, provider calls or external writes.

**Source of truth:** User-uploaded `03_Rukh_AI_Product_Workflows.docx`, pages 1–3 D03.T03/T04/T05/T09/T10 and G02/G03/G04/G05; page 10 independent platform authentication, Day 2 same-SHA release prerequisite. GitHub #729 and Linear MD-7; upstream MD-6.

## Task 1 — Write failing adversarial tests

- [x] Extend `tests/test_staging_days3_6_acceptance.py` synthetic fixture with per-answer owner A message IDs, provider/browser timing and refs, A-positive / B-denied selected source reads, and owner-scoped run/outbox before/after readbacks.
- [x] Extend the separate revocation receipt with exact selected document ID/version/SHA, owner A, unique message ID, delete/revoke action, A-positive pre / denied post source status, provider receipt, browser and database readbacks after provider completion, failed reply state, zero browser/stored stale bytes, and zero new effects.
- [x] Add red negative tests for wrong owner/source/version/digest, reused message, invalid source HTTP statuses or missing refs, pre-provider/after-provider mutation timing, no actual model overlap, stale browser bytes, stored bytes, and inconsistent owner historical counters.
- [x] Commit tests alone `6d13f369f3e31f5f1907dbd793a7a154e32711f0`, verify [GitHub Actions RED #44914345519](https://github.com/rumman52/Shuddho/actions/runs/44914345519) Python test step: **84 expected missing guard failures; 3,213 passed, 105 skipped, 6 warnings**.

## Task 2 — Implement focused fail-closed verifier

- [x] Cache day-level owner A run/outbox readback and assert every successful bilingual and revoked request individually matches it, preserving nonzero historical counts.
- [x] For each bilingual answer, require source retrieval status A 200 and B 403/404, owner, distinct message/provider ID, provider/browser chronological transcript and nonempty real readback refs.
- [x] Require revocation owner/source ID/version/digest match exact bilingual source pin; require separate message/provider request and A-source status 200 before, 403/404/410 after.
- [x] Require both positive answers finish and be browser verified before the revocation probe starts, and strictly chronological provider start < mutation < provider finish <= browser readback <= database readback within frozen Day 3 release.
- [x] Require failed revoked reply, zero visible/stored stale bytes and zero run/outbox effects. Tie the prompt-injection provider receipt timestamps to the exact selected successful model request.
- [x] Commit production implementation `a89c97a1e1289b9368a29ced839446b1dc2045d3`; update existing owner history regression tests in `05c223b2d6ee884d9f2e967705ba21539e001c0e` so old history is represented consistently in each readback.

## Task 3 — Exact-head verification and governance

- [ ] Verify full Python suite, isolated Days 3–6 receipt tests, frontend, browser, Coworker, PostgreSQL 18 and PR head ancestry on the **same final HEAD**, inspect logs for real counts and failure details.
- [ ] Require independent code review and mandatory governance CI before merge. Update GitHub #729 and Linear MD-7 with source-vs-hosted distinction.
- [ ] The operated hosted suite must actually revoke/delete owner-A's pinned source during the real model call, trace each browser delta, authenticate the A/B HTTP source reads and observe real DB rows; a JSON fixture or source-level CI does not satisfy D03.G02–G05.

**Status boundary:** The only allowed verifier result is `evidence_internally_consistent_not_live_attested`. No staging deployment, schema modification, billable inference, account creation, or provider send. Render workspace/services need explicit owner confirmation, connected Vercel has no Shuddho project, Supabase Auth/storage and managed owner receipts are not proven, ProductOS connected project is unrelated, and PostHog release telemetry target is not authenticated. This PR makes it harder to falsely claim a hosted PASS; it is not an operated substitute.
