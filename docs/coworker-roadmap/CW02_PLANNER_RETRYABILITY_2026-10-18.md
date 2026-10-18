# CW-02 Planner Failure Retryability at the Temporal Boundary

**Date:** 18 October 2026 (Asia/Dhaka)
**Roadmap mapping:** Phase 11 model HTTP 429/500/timeout behavior.
**Status:** Source retryability change merged; regression assertion corrected in a follow-up branch; final-head CI pending.

## Objective

Preserve the planner adapter's typed retryability when AgentActivities converts CoworkerError into Temporal ApplicationError. Transient model failures must use the workflow's existing bounded retry policy. Permanent failures must not be retried. Exhausted planning failures must not fabricate a decision or dispatch work.

## Observed defect

DeepSeekAgentPlanner already marks HTTP 408/429/500/502/503/504 and timeouts as retryable through PlannerFailure.retryable. AgentActivities.replan and AgentActivities.decide_v3 previously discarded that property: errors outside the existing capacity-error allowlist became non-retryable, so Temporal could not apply its existing bounded retry policy.

## Implementation and regression correction

- PR #456 merged the shared retryability predicate in services/coworker/worker.py.
- The regression uses synthetic httpx.MockTransport responses and a real Temporal test workflow.
- The four new Temporal cases initially failed because the test incorrectly expected saved steps to be empty. AgentRepository.create intentionally inserts one ordinal-zero sentinel to represent the run itself; this sentinel is not executable plan work.
- The follow-up test now asserts an empty executable plan, the single ordinal-zero sentinel with no tool name, and zero tool invocations.
- The follow-up adds a dedicated no-skip CI gate and uploads the JUnit report as cw02-planner-retry-evidence.

## Acceptance criteria

1. HTTP 429, HTTP 500, and timeout each cause exactly two attempts under the existing workflow policy.
2. Permanent HTTP 400 causes exactly one attempt.
3. After exhaustion, the run reaches a visible failed state.
4. No AgentDecision, MemoryProposal, ToolInvocation, or executable plan step is created from a failed decision.
5. Provider error bodies and private timeout details do not appear in Temporal workflow history.
6. The replan activity preserves retryable and non-retryable PlannerFailure classifications.
7. The dedicated CI gate passes both regressions with mandatory module evidence and zero required skips.
8. Exact-head test-and-build, mandatory coworker, and ci-merge-gate all pass before repository verification.

## Verification state

- Merged source change: PR #456, merge commit 1b665c03b8dbaf7d39104a7ae5f599d27220c5ec.
- Failed exact-head run: CI #39098101062 — test-and-build passed; coworker failed with 4 assertion failures and 1413 passing tests; ci-merge-gate failed.
- Follow-up branch: codex/cw02-planner-retryability-test-fix-20261018.
- Final-head verification of the follow-up: pending.

## Safety boundaries and non-claims

All model responses are synthetic; no live model/provider is contacted. No schema, public API, provider authority, retry ceiling, external transaction, protected staging secret, deployment, or capability activation is changed. This is one repository-level recovery slice, not completion of the full 16-fault CW-02 transaction-chaos matrix, operated provider-side reconciliation, staging qualification, or production qualification. Independent review does not substitute for passing CI.