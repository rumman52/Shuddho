# C-01 / A-02 — Committed Runtime v3 activity replay across deadline

Date: 20 October 2026 (Asia/Dhaka)  
Repository: `rumman52/Shuddho`  
Starting main: `9d830f3d7f9fe405020a45c42ab99bf05dea5b65` (merged #486 and #487)  
Review: [PR #488](https://github.com/rumman52/Shuddho/pull/488)

## Source-level defect

`AgentRuntime.decide_v3` read the run and checked cancellation, then enforced
the task deadline **before** loading the committed logical activity checkpoint.
A Temporal activity that had committed `next_step`, `needs_input`, or `blocked`
could lose its reply; after the deadline, the retry failed with
`agent_deadline` instead of returning the result owned by its unchanged
activity key. No model inference is required for exact checkpoint replay.

`AgentRepository.block_v3_unavailable_tools` had the same ordering inside its
run-locked transaction if a competing no-tools attempt committed near deadline.

## Acceptance and smallest correction

1. Preserve runtime-version verification and the existing cancellation-first
   rule: a cancelled run does not replay a previously committed result.
2. Look up **only the exact persisted activity-key checkpoint** before checking
   the deadline. Never replay a different identity or infer a new result.
3. Keep the deadline check before new context ingestion, model capacity,
   provider inference or terminal blocked state persistence.
4. In the atomic no-tools helper, check an already-committed result under its
   row lock before the deadline gate; the fresh no-result path still expires.
5. The existing v3 complete/terminal, revocation, receipt, ownership and
   ExternalAction constraints remain intact. No schema, flag, workflow args,
   provider selection, extra permission or deployment change.

## Regression/evidence

Five test cases were committed before the code change at
`41be1dcdf2b5bcba334f5469c910d7bcbc001c41`; an additional direct
repository helper test covers the internal race. Cases assert unchanged
model-call count, no extra steps/checkpoints, failure for uncommitted fresh
activity, and cancellation supremacy. The existing required `coworker` CI
collection executes `tests/test_agent_v3_decision_recovery.py` with a
mandatory module gate/no skips.

Test-only CI may be superseded by later commits. **Do not claim failing-first
execution unless that exact run completed.** Require final-head
`test-and-build`, `coworker` and `ci-merge-gate`, independent review and
separate operated PostgreSQL/Temporal recovery and protected staging. All
Architecture/Core acceptance and production activation remain incomplete.
