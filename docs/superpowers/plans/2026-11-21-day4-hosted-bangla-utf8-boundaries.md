# Day 4 Bangla Canonical UTF-8 Hosted Boundary Evidence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development, superpowers:verification-before-completion, and superpowers:requesting-code-review. Never equate structural fixture validation with independent hosted acceptance.

**Goal:** Require individually witnessed, owner-bound 4,096- and 16,000-byte canonical Bangla reviewed-brief boundary operations as a condition for Day 4 receipt consistency, including exactly one byte over HTTP 422 and zero new AgentRun/outbox effects.

**Architecture:** Extend the read-only `scripts.staging_days3_6_acceptance.check_day4` schema. Each canonical size probe uses a distinct synthetic owner-A conversation scope; submit the +1-byte over-limit request to both preview and dispatch *first*, record no new effects, then approve exact-limit preview and Start with one new run/effect. Keep the actual transaction handling, migrations, runtime and existing golden Start/race checks unchanged. A reviewer must independently authenticate actual canonical bytes, HTTP traces and database rows.

**Tech stack:** Python/pytest/GitHub Actions, no new dependency.

**Spec:** Uploaded `03_Rukh_AI_Product_Workflows.docx`, pp. 4–5 (D04.T01, T04, T06, T09, G01/G03), p. 10 independent reviewer and same-release checks. Existing source test `tests/test_conversation_reviewed_briefs.py::test_exact_multibyte_bangla_snapshot_boundary_and_atomic_admission` proves the local code path, not hosted acceptance. Related GitHub #730 and Linear MD-7, upstream MD-6.

## Task 1 — Test first (RED)

- [x] Update only `tests/test_staging_days3_6_acceptance.py` fixture with two explicit `utf8_boundary_probes` and adversarial cases (missing/duplicated limit or scope, wrong owner, non-multibyte, mismatched canonical SHA/digest, invalid exact or +1-byte sizes, preview/dispatch HTTP mismatch, error-code mismatch, altered run/outbox deltas, absent readback refs and timing).
- [x] Preserve a successful synthetic receipt with existing scoped run/outbox history; test order of the 4,096 and 16,000 rows is irrelevant.
- [x] Commit tests only `4552b1f4f81b5b9ac249b8b4c5bef1ce6f03960d` and observe CI RED: [#44889864265](https://github.com/rumman52/Shuddho/actions/runs/44889864265) `Run Python tests` **53 expected `DID NOT RAISE` failures; 3,081 passed, 105 skipped, six warnings**.

## Task 2 — Minimal production gate (GREEN candidate)

- [x] Extend `scripts/staging_days3_6_acceptance.py::check_day4` with exactly two canonical limits `{4096, 16000}`, nonboolean integer limits, frozen owner A, multibyte Bangla assertion, distinct source conversation scopes, unique boundary run IDs and distinct accepted canonical digests.
- [x] For each over-limit request: canonical payload digest and length exactly `limit+1` bytes; preview and dispatch HTTP 422 with `task_brief_snapshot_too_large`; no new scoped agent or outbox rows; receipt references for actual canonical byte counts, both denied HTTP calls and database readback.
- [x] For each accepted request: canonical payload length exactly `limit`; preview HTTP 200 and dispatch HTTP 202; preview and Start digests identical to the canonical payload digest; exactly one new run and one new outbox effect from the same scope, with the no-effect over-request counters unchanged.
- [x] Require chronological over-limit denial before exact admission inside the Day 4 operated receipt, and preserve old golden task/409 conflict/retry checks. Accept historical owner scope counts above zero.
- [x] Commit minimal verifier change `0eda01de5e82e4546d657dce1fe5c49baed08b8b`.

## Task 3 — Verification / review / handoff

- [ ] Verify the final exact-head full Python suite, isolated Days 3–6 verifier tests, browser, frontend, PostgreSQL and extended Coworker CI jobs; record actual outcomes and linked workflows.
- [ ] Confirm the PR has an independent reviewer and mandatory governance audit before merging, and distinguish source CI from frozen staging.
- [ ] Add PR and evidence status to GitHub #730 and Linear MD-7 with required synthetic-managed owner and approved private staging prerequisites.

**Output:** Only the existing `evidence_internally_consistent_not_live_attested` structural status; the verifier does not itself generate canonical bytes, call real browser/API, fetch protected source data, count the hosted DB, or authenticate the independent reviewer.

**No unapproved actions:** No creation of accounts, staging DDL, model provider calls, paid resources, production email sends, or selection of a Render workspace without explicit user authorization. Full Part 03 hosted acceptance remains gated on frozen same-SHA release, Day 2 isolated backup/migration/recovery, private source, two live owners, four actual workflows, provider model receipts, original native artifact byte readback, and independent human review.
