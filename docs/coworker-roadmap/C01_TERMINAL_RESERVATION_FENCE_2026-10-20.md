# C-01 / A-02 — Reject fresh Runtime v3 inference on terminal runs

Date: 20 October 2026 (Asia/Dhaka)
Baseline `main`: `7c2eced6396f2cdf93106bf05e006b7c423eecfb` (merged #483).
Review: [PR #485](https://github.com/rumman52/Shuddho/pull/485).

## Root cause

The existing `AgentRepository.reserve_planner()` checked cancellation and task
deadline but not the other terminal states. Although `record_v3_decision()`
already refused fresh output after terminal transitions, a late Runtime v3
activity could still reserve token/provider capacity and invoke model inference
before reaching that check. C-01 requires bounded execution *and* fail-closed
late activity admission, not merely late output rejection.

## Bounded implementation

- `AgentRuntime.decide_v3()`: reject fresh logical decisions on completed,
  failed, needs-input and blocked runs, after the established exact committed
  result replay but before reading context or submitting inference.
- `AgentRepository.reserve_planner()`: repeat this gate under the existing
  `AgentRun` row lock for runtime_version=3, before allocating tokens,
  provider leases or daily allowance. The database check also protects a
  terminal transition committed after the initial runtime snapshot.
- Preserve cancellation's established `agent_cancelled` code and v1/v2
  behavior. Do not change existing committed v3 replay or charging.

## Regression and evidence

Five parameterized test instances were committed at
`c61dc9574972d212689c91dedb3d10b62c0122bb` before implementation:
terminal needs_input/blocked rejection in direct reservation and new activity
entry, plus exact prior decision replay. Pre-fix CI results must be inspected;
a test-only commit is not proof of executed failing-first checks.

Require final-head PR CI `test-and-build`, `coworker`, and `ci-merge-gate`,
independent review, and operated recovery before stronger acceptance. Synthetic
SQLite + Temporal activity environment tests cannot qualify live PostgreSQL
races, model provider cost, worker restart or staging deployment. All
Architecture/Core A/C/P acceptance remains incomplete until separately proven.

No external action, flags, schema, provider choice, infrastructure deployment,
production activation or owner scope changed.
