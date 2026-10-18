# CW-02 Planner Failure Retryability at the Temporal Boundary

**Date:** 18 October 2026 (Asia/Dhaka)  
**Roadmap mapping:** Phase 11 — model HTTP 429, HTTP 500, and timeout cases.  
**Status:** Implemented on the review branch; exact-head CI pending.

## Objective

Preserve the planner adapter's typed retryability when `AgentActivities` converts `CoworkerError` into Temporal `ApplicationError`. Transient model failures must use the workflow's existing bounded retry policy. Permanent failures must not be retried. Exhausted planning failures must not fabricate a decision or dispatch work.

## Observed defect

`DeepSeekAgentPlanner` already marks HTTP 408/429/500/502/503/504 and timeouts as retryable through `PlannerFailure.retryable`. The `AgentActivities.replan` and `AgentActivities.decide_v3` wrappers previously discarded this property: every error outside the small capacity-error allowlist became non-retryable, so the existing Temporal retry policy could not retry transient planner failures.

## Implementation

- Add `_agent_error_is_retryable` in `services/coworker/worker.py`.
- Preserve the existing capacity-error allowlist and additionally honor `PlannerFailure.retryable`.
- Apply the shared predicate at Agent planning, replanning, and Runtime v3 decision activity boundaries.
- Keep the workflow's existing maximum of two attempts; do not increase retry ceilings or silently change providers.
- Test the actual planner adapter with synthetic `httpx.MockTransport` responses and a real Temporal test workflow.

## Acceptance criteria

1. HTTP 429, HTTP 500, and timeout each cause exactly two attempts under the existing workflow policy.
2. Permanent HTTP 400 causes exactly one attempt.
3. After exhaustion, the run reaches a visible failed state.
4. No `AgentDecision`, `MemoryProposal`, `ToolInvocation`, or Runtime v3 step is created from a failed decision.
5. Provider error bodies and private timeout details do not appear in Temporal workflow history.
6. The replan activity preserves both retryable and non-retryable `PlannerFailure` classifications.
7. The dedicated CI gate runs both regressions with mandatory module evidence and zero required skips.

## Verification

- `tests/test_coworker_temporal.py::test_agent_v3_model_failures_retry_within_bound_without_creating_work`
- `tests/test_coworker.py::test_agent_replan_activity_preserves_planner_retryability`
- Dedicated `coworker` CI JUnit artifact: `cw02-planner-retry-evidence`
- Required exact-head jobs: `test-and-build`, mandatory `coworker`, and `ci-merge-gate`.

## Boundaries and non-claims

All model responses are synthetic; no live model/provider is contacted. No schema, public API, provider authority, retry ceiling, paid service, staging secret, deployment, or activation is changed. This is one repository-level recovery slice, not completion of the 16-fault CW-02 matrix, operated provider-side reconciliation, staging qualification, or production qualification. Independent review remains outstanding.
