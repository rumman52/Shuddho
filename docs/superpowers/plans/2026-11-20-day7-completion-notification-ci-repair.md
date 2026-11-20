# Day 7 completion-notification acceptance CI repair

**Date:** 2026-11-20  
**Issue:** #733 (D07.T05/T06/T09), #734 (D08.G01)  
**Repository baseline:** `main` @ `193aa4939c3d4258c34c45402d79a37936b149b1`  
**Related work:** merged PR #803, open PR #809

## Goal

Restore the CI acceptance tests for the existing one-notification briefing contract. The repository already suppresses `automation_started` for `run_profile="briefing"` and enqueues one `automation_completed` on completion, but two older tests still assert the contradictory start-notice behavior.

## Reproduction

- GitHub Actions main run `44611285257`: 2 failed, 1709 passed, 4 skipped in the Coworker job.
- GitHub Actions PR #809 run `44611891181`: the same 2 stale tests failed (1715 passed, 4 skipped).
- Failures: `test_daily_briefing_starts_one_runtime_v3_daily_plan_run_and_notifies_completion` and `test_day7_briefing_refreshes_document_versions_replays_and_pauses`.
- The real schema enforces unique notification per occurrence; PR #803 deliberately makes briefing completion the only notice.

## Implementation checklist

- [ ] Replace start-notice expectations with proof of zero notices *before completion*.
- [ ] After notifying completion twice, assert exactly one `automation_completed` row for the original occurrence and no start notice.
- [ ] Exercise the quiet-hours boundary by pinning the completion clock to the scheduled due time in the controlled test; verify the completion notice is deferred.
- [ ] Complete the second controlled occurrence after document revision and worker restart, verify two distinct completion notices, and preserve replay/expiry/deleted-source/pause checks.
- [ ] Confirm the fix does not modify production code, scheduler state, host settings, notification delivery, PostHog or database schema.
- [ ] Run focused and full CI on the exact PR head; report unrelated CI failures instead of hiding them.

## Non-goals and release gates

These are *controlled local tests*, **not** two natural Temporal firings. They do not satisfy the Day 7 operated evidence, the Day 8 80 paid first-run experiments, independent review, privacy sign-off or freeze requirements. PR #809 is already fixing Day 8 first-run/rerun cost accounting, so this PR must not duplicate it.
