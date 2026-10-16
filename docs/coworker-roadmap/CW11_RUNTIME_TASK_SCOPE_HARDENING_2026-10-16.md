# CW-11 / A-04 — enforce durable task grants across plan, replan and worker

**Base:** `main` `9b9e23a182ec212ce7f30e87d7a235ba886c2f5f` (16 October 2026).
**Branch:** `codex/cw11-task-run-scope-claim-20261016` (review only).
**Scope:** One bounded architecture/core authorization hardening slice. This does **not** activate or complete reviewed skill publication (CW-11) or production qualification.

## 16 October continuation — post-merge planner scope

The initial plan/replan/worker scope guard from [PR #431](https://github.com/rumman52/Shuddho/pull/431) **merged** into `main` at `18068a48aae1dcd3f354638e525cdd2cf88fc185`. This continuation is on the separate review branch `codex/cw11-planner-scope-continuation-20261016`, forked after #431's last reviewed head; it does not replace the merged patch.

An independent missing admission boundary remains: `AgentRuntime.plan_for_worker` and `replan` had unfiltered `intelligent_tool_names`, while deterministic planning and model proposal conversion omitted the durable `tool_allowlist`. That could expose inappropriate candidate names to the planner and cause restrictive fallbacks to error at SQL admission even when an allowed tool matched.

This follow-up filters the actual planner tool menu, the proposal-conversion allowlist and deterministic fallback using the persisted nonempty run grant. Empty grant remains the legacy unrestricted path; exact attached consequential actions remain separately authorized. A mocked-planner/real SQL test checks initial planning, replan, fallback after planner failure and denial when the goal has no permitted tool. No new provider, model authority, permissions, source access, runtime flag or schema.

**Required evidence:** final-head mandatory `test-and-build`, no-skip `coworker` and `ci-merge-gate`, plus code review; operated staging and CW-11 reviewed skill publication are still unqualified. Neither PR #431's prior checks nor its merge attest this later source revision.

## Defect and acceptance

A restricted Agent run has a durable `cw_agent_runs.tool_allowlist`, but the legacy `save_plan`, `replace_remaining_plan` and `AgentRuntime.execute_step` path did not independently enforce it. The v3 planner already filters admitted tools; that is not a sufficient worker boundary. A direct deterministic plan, saved replan or corrupted/stale persisted invocation could attempt a different enabled task, sandbox or browser capability.

Keep existing unspecialized user runs with an empty allowlist unchanged. For a run with a nonempty allowlist:
- A non-approved-action tool outside that exact recorded scope is rejected at initial plan, replan and worker execution, even if globally enabled. This includes browser and sandbox tools not present in the allowlist.
- Rejection happens before task creation, provider calls, receipt writes or artifacts. Rejected plan/replan transactions roll back.
- Tool selection does not inherit a manifest's authority. Existing attached consequential actions continue through exact ExternalAction approval bindings, not a nonconsequential run grant.
- No new orchestrator, credential, schema, feature flag, publish path, capability activation or provider permission.

## Implementation

- `services/coworker/agent_repository.py`: recheck `run.tool_allowlist` in initial and replacement plan SQL admission.
- `services/coworker/agent_runtime.py`: pass the persisted grant through initial intelligent planning, deterministic fallback, replan and task execution. The model never receives ungranted task names for restricted runs.
- `services/coworker/agent_planner.py`: restrict deterministic and model proposal conversion to the run grant; preserve unchanged behavior for unrestricted runs and server-bound approved actions.\n- `tests/test_coworker.py::test_agent_task_scope_survives_plan_replan_and_worker_claim`: real SQLite repository and AgentRuntime path. Deny unlisted task/browser steps in plan/replan; persist an allowed task, simulate an altered persisted browser invocation and prove the worker refuses to create any Task or browser session.\n- `tests/test_coworker.py::test_restricted_run_planner_and_fallback_never_offer_extra_tools`: real run initial planner, replan, provider failure and deterministic fallback keep the single allowed tool and reject goals with no permitted matching tool. Existing unscoped path remains covered by prior tests.

## Required checks before repository verified

1. `uv run --extra coworker pytest tests/test_coworker.py -k 'agent_task_scope_survives_plan_replan_and_worker_claim or restricted_run_planner_and_fallback_never_offer_extra_tools' -q`
2. `uv run --extra coworker pytest tests/test_coworker.py tests/test_automations.py tests/test_coworker_skill_manifests.py -q`
3. Mandatory exact PR HEAD `test-and-build`, zero-skip `coworker` and `ci-merge-gate`.
4. Independent review of time-of-check/time-of-use, model-selected steps, plan replay, old invocations, action paths and mixed-version behavior.

These checks are acceptance obligations, not claimed pass results until their logs are inspected. Source/test additions alone are not operated PostgreSQL/Temporal restart, concurrent worker claim or staging evidence.

## Remaining gates

CW-11 reviewed persisted publication/version rollback, runtime selection of a pinned reviewed skill version with actual immutable grant binding, utility evaluations and staging remain incomplete. CW-10 operated isolated-worker and CW-09 browser security plus A/P/V coworker scenarios are separate unresolved tasks. This branch must not deploy, merge or activate release flags automatically.
