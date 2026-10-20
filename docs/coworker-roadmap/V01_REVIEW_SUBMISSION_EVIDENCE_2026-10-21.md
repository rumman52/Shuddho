# V-01 bounded corrective task — independent review submission evidence

**Date:** 2026-10-21 (Asia/Dhaka)  
**Base main:** `d335fe98dcd277daa02011c0900ad957f62e7495` (merged PR #521)  
**PR:** [#522](https://github.com/rumman52/Shuddho/pull/522) — draft / unmerged at authoring.

## Safety boundary and root cause

The live CI reviewer gate, `scripts/independent_review_gate.py`, already checks open/non-draft PR state, exact-head SHA, independent human identity, trusted association, author exclusion, review state and pagination. It **did not** validate the `submitted_at` evidence for actionable reviews and **did not** reject repeated GitHub review IDs in the paginated input. A malformed `APPROVED` item lacking a trustworthy time could satisfy the source-code review gate; duplicated IDs could ambiguously override another submission.

This is **fail-closed validation of the existing read-only review gate**, not GitHub-native approval/merge enforcement. Preserve the current approval policy and revalidation order. Do not introduce write permission, production activation, new external providers or cost.

## TDD trace

1. Test-only SHA `4b5848c4088f672c7e86521413aee7d3afe4888d` modifies only `tests/test_independent_review_gate.py`. Existing positive fixtures now carry plausible ISO-8601 UTC `submitted_at`. Cases cover missing/null/malformed/offset-less approval time, undated dismissal next to a good approval, duplicates across pages, and valid pending/comment entries with no timestamp.
2. Actual [RED CI #39484280083](https://github.com/rumman52/Shuddho/actions/runs/39484280083), `test-and-build`: **6 failed, 1,256 passed, 71 skipped, six warnings**. All six expected failures reported `DID NOT RAISE ReviewGateError` for the named new negative cases. The positive pending/comment case passed. This demonstrates the prior acceptance bug.
3. Minimal implementation SHA `e907878b3b5cca3252405131637f20f5792d0cf4` checks unique integer IDs and timezone-aware ISO-8601 `submitted_at` for `APPROVED`, `CHANGES_REQUESTED`, and `DISMISSED`. `PENDING`/`COMMENTED` still do not count as approval; they may lack timestamps. Future or missing trust at GitHub's API boundary is not accepted as proof of native protection.
4. **GREEN evidence:** inspect the exact final PR head CI and the mandatory coworker integration job. Never substitute the RED workflow or an earlier head. Do not declare full CI green while coworker is running/cancelled.

## Release / governance

[PR #521](https://github.com/rumman52/Shuddho/pull/521) merged at **2026-10-20 19:26:14 UTC** with zero submitted reviews; its exact-head [CI #39481714982](https://github.com/rumman52/Shuddho/actions/runs/39481714982) had `test-and-build` success at 19:16:21, `coworker` **cancelled at 19:27:28**, and `ci-merge-gate` **failed at 19:27:36**. The last two conclusions followed the merge, proving the merge occurred before required jobs completed; they were not failed before merge. Recorded in [V-01 owner/admin issue #484](https://github.com/rumman52/Shuddho/issues/484#issuecomment-6299558811).

**BLOCKED:** native `main` rule enforcement and negative-control validation remain the owner/admin's job. Keep PR #522 draft and unmerged without human final-head approval and independent branch-protection proof. Green code tests alone do not satisfy V-01. Staging issue #291 and production qualification remain separate and unverified.

## Review / rollback

Compare the source/test diff against the tests-first SHA, inspect invalid UTF-8/missing/malformed time and duplicate-ID cases, and verify unaffected current-head pagination/TOCTOU tests. To roll back, revert the source change and this bounded test/documentation unit on the feature branch; do **not** alter security controls to force acceptance.
