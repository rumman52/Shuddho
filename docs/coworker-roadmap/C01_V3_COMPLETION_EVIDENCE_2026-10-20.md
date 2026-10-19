# C-01 / A-02 — Runtime v3 completion evidence

- Objective: the final completion activity must enforce the same verified-result contract as the planner, atomically with the completed state.
- Base: main `b6e57dd8f378b0b878c66fd6ef8ceb1d09dbcb4d`; branch `codex/c01-v3-completion-evidence-20261020`.
- Reuse: `AgentRepository.complete_run`, `v3_can_complete`, existing AgentRun lock and ToolReceipt records. No new store, schema or workflow name.
- Root cause under test: finalization counts allow zero invocations/zero receipts and ignore missing-information or unconfirmed-action receipt summaries. A stale/direct completion activity can bypass planner validation.
- Files: `services/coworker/agent_repository.py`, `tests/test_agent_v3_terminal_finality.py`, canonical progress/inventory.
- Acceptance: reject empty v3 runs and missing-information/unconfirmed-action results without adding completion checkpoints/events; preserve valid receipt finalization and exact completed replay; preserve v1/v2 behavior.
- Execution plan: write and run failing regressions; reuse `v3_can_complete(run_id, _db=db)` under the completion row lock; run focused/full suite and mandatory collection gate; independent agent review; publish a dedicated review PR and inspect exact-head CI.
- Review focus: legacy partial outcomes; cancellation and competing terminal states; replay after deadline; missing receipts; no false automation completion notification on rejected finalization.
- Boundaries: no additional model/provider calls, permissions, approval bypass, capability flag, paid provisioning or activation. Synthetic persisted receipts test repository semantics, not real provider outcomes.
- External prerequisites: full PostgreSQL/Temporal/browser mandatory CI and operated qualification remain separate gates.

## Completion evidence

Implemented: yes on review branch. Focused verification: 56 passed, zero skips; pre-fix 3 failed/3 passed. Independent read-only agent review: no Critical/Important findings. Full suite and mandatory final-head CI: pending. Staging/production qualification: unverified. Activated: no.
