# Rukh AI Day 4 and Day 6 safe integration — 13 November 2026

## Reason for replacing #694 and #695

Both old PRs were branched from commit `ce8a21046970a94a65d0b53a31da4c55d048e51a`. GitHub reported `dirty` mergeability after eighteen commits reached main. The visible merge blockers are not reason to discard Day 4's reviewed-task implementation.

**Day 6 #694:** The existing production implementation was separately fixed and merged in #692. Current main already opens native Plugins management on an explicit action-review entry using `openForReview`. The stale #694 `expandApprovals` component and caller edits would overwrite it. Preserve the narrower unique improvements only: authored fact scoring excludes copied citations, its negative tests, and an approval-preview regression adapted to current `openForReview` / mount behavior. Do not auto-approve or send mail.

**Day 4 #695:** Preserve all 16 distinct changed files as they did not overlap the 18 intervening main commits. This includes a reviewed brief, owner/source/project snapshot validation, canonical digest, one-run atomic dispatch, migration 0069, and backend regressions. Existing CI on main already references `tests/test_conversation_task_briefs.py`, which was absent from main prior to this integration.

## Verification and release boundaries

- Run the full exact-head required GitHub CI, including frontend, browser, PostgreSQL 18, Coworker, quality gate, and CI merge gate, with no skipped mandatory tests.
- Review actual failure logs. A previous #694 browser CI timed out waiting for `#cw-conversation-message` on line 446 after navigation. This was **not** proved fixed by removing conflicting code, so a green full Chromium run is required.
- Compare the checked revision to main again before any merge; no force-merges, no skipped branch ancestry checks. Require independent human review and protected-main governance; GitHub currently reports `main.protected=false`.
- This branch does not authorize staging/production deployment, paid Render changes, model claims, real live worker receipt, natural two-day briefing, independent holdout results, or Day 10 pilot activation.
- Render workspace has not been selected or confirmed, so no Render service mutations or live environment acceptance performed.

## Critical non-Git source collision resolved

The prior #695 commit overwrote `services/coworker/task_brief_schemas.py` and `tests/test_conversation_task_briefs.py`, which already define Day 5 versioned `MemoryPin`/`TaskBriefMemorySelection` behavior and its owner/version isolation tests. This is a **functional regression** that GitHub conflict markers cannot detect because #695 was modifying files already present on its own base. The clean branch instead combines both schema contracts, restores the Day 5 test file verbatim and places the Day 4 regression in `tests/test_conversation_reviewed_briefs.py`. Add a separate mandatory CI test/evidence gate for Day 4 without weakening Day 5. Any further source collisions must be reconciled through exact-head CI before merge.

## Exact-head CI diagnosis and patch-level integration

The first consolidated head failed in the general test job because the new Day 4 tests imported SQLAlchemy without the module-level optional-dependency guard expected by baseline CI. The frontend run exposed missing Day 5 `memory_pins` and `Task preview` behavior and a missing grounded source prompt after the stale #695 UI replaced later updates. The true git common ancestor of #695 and current main is `f3bd787764a5a6c7ff4bbc54c986543ff7a745cf`, **189 commits** behind the current main, not merely the 18 commits since the PR's displayed base.

The revised integration reconstructs the changed Day 4 backend methods on current-main source, combines optional memory pins with reviewed task digest in one atomic dispatch, and preserves Day 5 pin version validation. Day 4 project digest excludes memory pins while the run fingerprint and worker memory validation still bind them. Frontend client and workspace now retain direct Ask Rukh chat, selected memory preview, and explicit reviewed-task confirmation. The Day 4 integration module skips dependency collection in baseline and must pass the separate no-skip Coworker-extra CI step. All claims still require exact-head CI evidence; no production release.
