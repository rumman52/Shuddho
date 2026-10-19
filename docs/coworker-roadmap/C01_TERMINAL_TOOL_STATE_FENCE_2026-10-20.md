# C-01 / A-02 — Prevent Runtime v3 tool resurrection after terminal state

Date: 20 October 2026 (Asia/Dhaka).
Base main: `79c111d7bc3ec8ae1ad65b55e4f78595aec54e46` (merged PR #485).
Review: [PR #486](https://github.com/rumman52/Shuddho/pull/486).

## Demonstrated source-level defect

Five trusted AgentRepository write boundaries checked cancelled runs but did not
fence a separate winning terminal `needs_input` or `blocked` state:
`append_v3_step` could add a new tool plan; `begin_invocation` could turn
the terminal run back into `running`; `finish_invocation` could persist a new
receipt and overwrite the terminal run's state. The `save_plan` compatibility path and `action_waiting` approved-action
observer had the same missing terminal guard. These all run in the owning
PostgreSQL transaction under the existing AgentRun row lock, so the authority
check belongs there rather than in an untrusted planner response.

## Bounded correction

- After cancellation checks, `append_v3_step` rejects terminal runs.
  This method only supports Runtime v3 already.
- `begin_invocation` and `finish_invocation` reject terminal runs when
  `run.runtime_version == 3`. Preserve legacy v1/v2 behavior.
- Return a typed `agent_run_closed` conflict rather than reporting a later
  tool as successfully started/observed.
- Apply the same v3-only guards to `save_plan` and `action_waiting`;
  neither may create tool work or mark an action ready after terminal.
- Preserve all existing exact activity replay, model budget, provider and
  ExternalAction approval controls; no schema/migration or worker workflow
  history version change.
- Six regression instances were committed on the review branch before
  implementation. Pre-fix CI may be superseded; do not claim observed
  failing-first results if it did not complete.

## Qualification

Require exact final PR-head `test-and-build`, `coworker`, and `ci-merge-gate`
with required collection/no skips; independent code/security review, deployed
PostgreSQL/Temporal crash/race scenarios and separate human-controlled staging
remain open. No production activation or consequential action authorized.

This is a narrow C-01/A-02 implementation improvement, **not** closure of
all Architecture/Core acceptance IDs or a declaration of production readiness.
