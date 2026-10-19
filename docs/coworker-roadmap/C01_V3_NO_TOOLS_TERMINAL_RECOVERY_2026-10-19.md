# C-01 / A-02 — Runtime v3 no-tool terminal retry integrity

Date: 19 October 2026 (Asia/Dhaka)  
Base main: `129fa78a578df10ad861a9ded7a3a3a4fec90cf8` (merged PR #481)  
Review branch: `codex/c01-v3-no-tools-recovery-20261019`  
Review PR: [#482](https://github.com/rumman52/Shuddho/pull/482)

## Scope and defect

`AgentRuntime.decide_v3` used a special no-registered-tools branch that called
`v3_terminal(..., "blocked", ...)` independently of the committed decision-result
checkpoint. Unlike the ordinary Runtime v3 decision path, a lost activity response
therefore had no durable result identity. More seriously, after an earlier snapshot
reported no tools, cancellation or a competing terminal state could commit before
`v3_terminal`; that method intentionally returns on already-terminal states, so
the caller reported `blocked` even though a different outcome won.

## Required behavior

- For one logical Temporal decision-activity identity, commit the `blocked`
  terminal event and `v3_activity_result` checkpoint in the same run transaction.
- The same logical activity replays the exact bounded result without inference or
  another event; different activity identities cannot claim a closed run.
- Cancellation, expiration and competing terminal states win under the existing
  AgentRun row lock; no misleading `blocked` result or checkpoint is created.
- Selected-context admission remains revalidated before new durable state.
- Preserve legacy direct-call use without an activity key, runtime flags,
  planner budgets, schema, workflow arguments, grants and ExternalAction boundaries.

## Changes

- `services/coworker/agent_repository.py`: `block_v3_unavailable_tools` uses
  the existing AgentRun transaction, event, audit and AgentCheckpoint mechanisms.
- `services/coworker/agent_runtime.py`: delegates the no-tools result to
  the atomic repository operation.
- `tests/test_agent_v3_decision_recovery.py`: regression assertions for durable
  replay, late cancellation, a competing `needs_input` transition,
  lost commit responses and transaction rollback when checkpoint persistence fails.

## Evidence and qualification boundary

The test-only PR revision `6f0501c96c78cfe4f1b6019642dedaf50fdd36fd` was
submitted with three regression tests before the implementation. Its CI coworker
job was cancelled when a newer PR push superseded it; **no failing-first CI result
is claimed**. The original code path and absent checkpoint were inspected
directly. The final exact-head CI and any subsequent corrective commits must be
checked in the PR before declaring repository verification.

This slice does **not** supply operated Temporal/PostgreSQL deployment recovery,
protected staging, human security review, end-to-end model quality or activation.
C-01/A-02 and the full architecture/core acceptance inventory remain incomplete.
