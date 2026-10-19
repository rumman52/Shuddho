# C-01 / A-02 — Runtime v3 late-inference deadline write fence

Date: 20 October 2026 (Asia/Dhaka)
Base main: `b1cb627b620a6ab7706efb5e41a67018a46100af` (PR #488 merged).
Review: [PR #489](https://github.com/rumman52/Shuddho/pull/489).

## Reproduced source condition

`AgentRuntime.decide_v3` reserves model capacity and then awaits a provider
outside its database transaction. The task deadline may elapse during that
await. `commit_v3_decision` ensures cancellation, exact committed replay and
other boundaries before writing a new decision, but the underlying
`record_v3_decision` lacks a deadline check. Therefore new `needs_input`,
`blocked`, `wait` or uncommitted decisions may be recorded after the
deadline, even when step dispatch has a separate deadline gate.

## Bounded correction

Insert the existing `_assert_within_deadline(run)` inside the
`record_v3_decision` transaction **after** the existing decision-idempotency
and terminal checks and **before** recording new model output/checkpoints.
`commit_v3_decision` calls that method inside its existing AgentRun row
lock. Exact committed activity-key replay in `commit_v3_decision` is
unchanged; the already-reserved model call still settles actual provider
usage in the runtime's `finally` path on denial.

No change to v1/v2, request identity, Temporal history, provider selection,
source/owner authorization, external actions, schema, features or rollout.

## Tests and qualification limits

Five test instances were committed at
`fb4c8ace40e75f3c1e42f29fa0b57c4f2d3b7b76` **before** implementation.
Four decisions are simulated with a deadline advancing after inference;
the fifth verifies exact earlier committed identity replay and usage
settlement after expiry. A sixth direct-repository rejection check was
added with the implementation.

Mandatory coworker CI already collects
`tests/test_agent_v3_decision_recovery.py` and enforces a no-skip module
gate. Test-only CI may be cancelled by a subsequent push and **is not**
claimed as executed failing-first evidence without a finished run.
Final-head `test-and-build`, `coworker`, `ci-merge-gate` and independent
review remain mandatory. Live PostgreSQL/Temporal failover and provider
metrics cannot be established with these SQLite/fixture-level tests;
real staging, code/browser containment, migration replay and human
security signoff remain open. No activation.
