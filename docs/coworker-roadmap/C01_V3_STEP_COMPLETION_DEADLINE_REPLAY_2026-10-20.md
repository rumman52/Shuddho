# C-01 / A-02 — Runtime v3 completed-step retry across deadline

Date: 20 October 2026 (Asia/Dhaka)
Baseline main: `7aa69522d8be40360123c4ec6d21896c3c9792cd` (#489 merged).
Review: [PR #490](https://github.com/rumman52/Shuddho/pull/490).

## Defect

`AgentRuntime.execute_step` called `assert_within_deadline` before querying
the durable ToolInvocation state. A successful tool call whose Temporal
activity response was lost or delayed until after the run deadline would
reject a retry as `agent_deadline` despite a persisted completed invocation.

The repository's existing ToolReceipt, step and completion persistence
remain authoritative; replay must not dispatch the tool again. This does
not confer permission to replay a cancelled or competing terminal run.

## Bounded change

- For runtime v3, read the owner-bound run snapshot and the recorded step.
  Reject cancelled, failed, needs-input and blocked terminal outcomes before
  considering completion.
- When the invocation is already `completed`, return the existing
  `{"status":"completed"}` activity result without any new tool call.
- Otherwise enforce the existing task deadline before dependency evaluation,
  provider calls and all new tool work.
- Preserve the existing deadline-before-replay behavior for runtimes v1/v2;
  retain current run context/source revalidation, tool allowlists and grant
  enforcement. No ledger, schema, Temporal activity signature or provider
  configuration changes.

## Evidence and limitations

Five deterministic regression test instances were added in
`76649452613518f3d75a5d46216c0434f59ca855` before the implementation:
completed-step replay, fresh-step expiry, cancellation precedence and two
non-cancelled terminal outcomes. A test receipt is deliberately synthetic,
not independently confirmed provider delivery or live Temporal recovery.

Tests are part of the existing explicitly collected
`tests/test_agent_v3_decision_recovery.py` mandatory no-skips CI module.
The pre-fix workflow may be cancelled by the subsequent source commit;
no executed red result is claimed unless CI finished on that test-only SHA.

Full final-head `test-and-build`, `coworker` and `ci-merge-gate`,
independent review, real PostgreSQL/Temporal retry, owner/source isolation
and staging recoverability are independent gates. Architecture/Core A/C/P
completion and production activation remain unverified.
