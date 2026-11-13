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
