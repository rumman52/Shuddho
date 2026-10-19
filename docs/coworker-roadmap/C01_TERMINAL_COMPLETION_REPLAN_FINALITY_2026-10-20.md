# C-01 / A-02 — Runtime v3 terminal completion and replan finality

Date: 20 October 2026 (Asia/Dhaka)
Base main: `79c111d7bc3ec8ae1ad65b55e4f78595aec54e46` (merged #485).
Review: [PR #487](https://github.com/rumman52/Shuddho/pull/487).

## Defect and authority boundary

`AgentRepository.complete_run` checks cancellation and receipt completeness,
but prior to this correction did not refuse `needs_input` or `blocked`.
When the invocation ledger is empty or all steps have completed, a stale
completion request could overwrite a terminal outcome and misreport success.

`replace_remaining_plan` likewise checked cancellation but not a winning
non-cancel terminal outcome, permitting a late legacy planner pathway to
replace an already-prepared Runtime v3 step.

Both operations hold the existing `AgentRun` row lock and therefore can
reject terminal transitions at the authoritative write boundary. They need
no duplicate ledger, model behavior or new orchestrator.

## Acceptance

- `needs_input` / `blocked` Runtime v3 runs never become completed from a
  later `complete_run` call; preserve event sequence and reported terminal state.
- A late v3 replan cannot replace existing prepared steps after a terminal outcome.
- An active run with unfinished steps is not silently marked completed.
- Preserve idempotent calls to `complete_run` for already completed runs,
  existing cancellation outcome and v1/v2 compatibility.
- Recheck and reject while holding existing AgentRun lock, no network/model
  calls, new provider claims or external action authority.
- Required exact-head CI, independent review, matching operated staging and
  deployable recovery evidence remain separate acceptance gates.

## Scope and evidence

Five regression test instances committed at
`0da047043142867424c4cdd22b03d38380b28ba6`
before the implementation, in
`tests/test_agent_v3_terminal_finality.py`.
The test-only run may be superseded; no executed failing-first result is
claimed without finished CI evidence.

This patch is separate from concurrent PR #486 (late step invocation and
receipt guards). Both require independent review, integration and mandatory
post-merge checks. The repository test harness cannot certify real live
PostgreSQL/Temporal interleavings, model quality, protected staging or
production activation. The complete A/C/P/V inventory remains open.
