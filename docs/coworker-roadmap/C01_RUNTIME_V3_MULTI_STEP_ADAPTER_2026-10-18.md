# C-01 Runtime v3 grounded multi-step handoff — 18 October 2026

- Objective: verify one successful Runtime v3 workflow through the real DeepSeek planner adapter, Temporal worker, server-owned tools, verified observations, owner-scoped handoff sources and the completion boundary.
- Dependency tasks and current evidence: PR #455 cancellation/terminal-state fence is merged with matching exact-head and merged-main CI evidence. The planner retry assertion correction is on main; exact-head CI run [#39111138510](https://github.com/rumman52/Shuddho/actions/runs/39111138510) passed the bounded planner-retry gate and all three required jobs. CW-02 target-isolation hardening is on separate open PR #460 and is not treated as merged.
- Base branch/SHA: `main` `8bc5596ce7b3cce42d1d6f6f19b779156233009e`.
- Work branch/PR: `codex/c01-runtime-v3-adapter-e2e-20261018`; draft PR [#461](https://github.com/rumman52/Shuddho/pull/461).
- Existing interfaces to reuse: `DeepSeekAgentPlanner.decide`, `AgentRuntime.decide_v3`, `AgentWorkflowV3`, `AgentActivities`, `AgentRepository.handoff_context`, `DocumentRunner`, `make_worker`, `dispatch_tick`, and the existing `WorkModel`. No new production interface or orchestration layer.
- Exact files to create/modify: `tests/test_coworker_temporal.py`; this contract; `docs/coworker-roadmap/PROGRESS.md`; `docs/coworker-roadmap/ARCHITECTURE_CORE_ACCEPTANCE_INVENTORY_V1.md`; `docs/coworker-roadmap/ROADMAP.md` (refresh stale CW-01 status).
- New interface signatures / schema and compatibility: none. No migration, runtime, API, feature-flag default or provider-authority change. The test enables existing handoff flags only in its synthetic test settings and uses HTTPX `MockTransport`; it makes no live DeepSeek request and does not activate the capability in any deployment.
- Acceptance scenarios and assertions:
  1. The actual `DeepSeekAgentPlanner` parses three valid responses: `document.create`, `email.draft`, then `complete`.
  2. The actual Temporal worker executes both tools; the second planner request receives the verified document observation, and the completion request receives both completed observations.
  3. The downstream email draft consumes the exact completed upstream task artifact through the existing bounded handoff path; its source ID, SHA-256 and invocation provenance match the upstream `document.create` receipt.
  4. The persisted run reaches `completed`, with exactly three planner calls, 150 reported tokens, two completed tool receipts, and the expected decision order.
  5. Model requests remain non-streaming JSON and explicitly state that the model cannot expand authority.
  6. Temporal history contains neither the goal/document body nor the synthetic API key.
  7. Exact final-head `test-and-build`, mandatory zero-skip `coworker`, and `ci-merge-gate` pass.
- Evidence boundary: a deterministic transport verifies adapter and workflow/handoff integration, not live provider/model quality, staging, production qualification or activation. The GitHub-only editing session cannot claim local test execution; final-head CI is required.
- Current status: implementation committed to the work branch; final-head CI pending. Run #39125901905 was started on the previous head and is stale after the handoff assertion update.
- Next action: inspect required CI on the latest head, fix genuine failures without weakening assertions, and update this checkpoint with exact evidence. Keep staging and activation gates separate.
