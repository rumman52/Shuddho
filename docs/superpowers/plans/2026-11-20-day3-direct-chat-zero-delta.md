# Day 3 Direct-Chat No-Side-Effects Receipt Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Implement each step with test-first evidence before the source change.

**Goal:** Accept a Day 3 owner-scoped direct-chat receipt when pre-existing AgentRun/outbox counts are nonzero but each before/after delta remains exactly zero; still reject any new record.

**Architecture:** In the existing fail-closed Days 3–6 receipt verifier, compare the validated nonnegative before/after counts as matched pairs. Change no model, runtime, API, storage, or provider functionality.

**Tech Stack:** Python, pytest, existing GitHub Actions zero-skip JUnit gate.

**Spec:** User-supplied `03_Rukh_AI_Product_Workflows(1).docx`, Day 3 “Check the side effects”: record owner-scoped counts immediately before and after browser replies, which must add zero AgentRuns and dispatch entries; see Day 3 G05 and tracking #729.

## Global Constraints

- No fabricated hosted owner, browser or platform receipts.
- No new direct-chat agent authority, dispatch, migration, or storage writes.
- Preserve the existing exact source/model/runtime release identity and two-owner fail-closed checks.
- Keep the verifier's `evidence_internally_consistent_not_live_attested` result; only independent operated evidence can close hosted rows.

## Review Focus

1. Pre-existing owner-scoped AgentRun/outbox counts of 3/7 must permit unchanged 3/7.
2. A new AgentRun (before 3, after 4) must reject.
3. A new outbox entry (before 7, after 8) must reject.
4. Negative and boolean counts must reject.
5. Existing zero-to-zero synthetic receipt remains valid.

---

### Task 1: RED — expose the over-restrictive baseline requirement

**Files:** `tests/test_staging_days3_6_acceptance.py`.

- [ ] Add a positive test for nonzero preexisting AgentRun and outbox counts with unchanged after counts.
- [ ] Add negative tests for positive deltas on each individual counter.
- [ ] Run on test-only PR head: positive test must fail against old zero-baseline logic, negatives remain rejected.

### Task 2: GREEN — compare counts, not absolute zero

**Files:** `scripts/staging_days3_6_acceptance.py::check_day3`.

- [ ] Validate `agent_runs_before` and `agent_outbox_before` via `count`.
- [ ] Validate corresponding after values with `count(..., expected=before)`; do not allow arithmetic increments, negative or boolean.
- [ ] Preserve all other Day 3 revocation/citation/owner isolation checks.

### Task 3: Qualify and review

- [ ] Verify exact-head full fast Python and mandatory Days 3–6 JUnit gate.
- [ ] Record observed RED→GREEN and external evidence caveat in PR.
- [ ] Open for independent review; no live acceptance claims or automatic merge.
