# C-01 durable Runtime v3 decision recovery

- Objective: a retried committed Temporal decision returns the exact stored result without another planner call, step, memory proposal or token settlement. Distinct logical decisions retain loop detection.
- Base: main `8a83844b148a811357b8906c58deb3ba8b76f1d3`; branch `codex/core-v3-durable-decision-retry-20261019`.
- Reuse: AgentRun row lock, AgentDecision, AgentCheckpoint uniqueness, provider capacity lease, existing step/memory repositories. No new ledger or migration.
- Interface: internal optional `activity_key` on runtime; stable Temporal workflow-run/activity identity derived inside the existing activity. Workflow names, arguments and command sequence remain unchanged. Legacy direct calls omit the key and represent new decisions.
- Atomicity: decision, proposed memory, prepared step/terminal state, exact bounded result and successful token settlement commit together. Inference remains outside the transaction. A crash before commit may infer again within the reserved budget; a crash after commit replays. Concurrent actual model attempts remain individually charged, while one local result wins.
- Cancellation/deadline: cancellation is checked before replay and again under the run lock; fresh decisions retain original conversation/source revalidation. No authorization is conveyed by cached metadata. Execution retains all current grants and source checks.
- Settlement: a per-call checkpoint under the run lock prevents repeated finally/commit settlement from double-counting actual tokens/cost. Unknown provider responses retain conservative reservation accounting.
- Failing-first: actual Temporal ActivityEnvironment attempt 2 raised `agent_loop_detected` after attempt 1 committed; new activity-key tests failed before the implementation existed.
- Tests: `tests/test_agent_v3_decision_recovery.py` covers actual activity identity, committed response loss, pre-step rollback, single memory/step/charge, wait/terminal replay, cancellation, and distinct-decision loop detection. CI runs this module with mandatory zero-skip gate.
- Boundaries: no new tools, secrets, external actions or flags; Runtime v3 remains default-off. Rollback restores prior implementation without schema changes; drain in-flight activities before downgrade to avoid losing new retry semantics.
- External prerequisites: deployed Temporal crash/restart evidence, PostgreSQL concurrency and full exact-head CI must be distinguished from local SQLite and ActivityEnvironment coverage. No staging or activation claimed.

## Completion evidence

Implemented; focused and surrounding checks, independent review and exact-head CI recorded in the PR. Publication is not merge, deployment, production qualification or activation. The finite architecture/core inventory remains the scope denominator.
