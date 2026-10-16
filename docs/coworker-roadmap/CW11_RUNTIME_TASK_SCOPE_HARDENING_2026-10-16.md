# CW-11 / A-04 — enforce durable task grants across plan, replan and worker

**Base:** `main` `9b9e23a182ec212ce7f30e87d7a235ba886c2f5f` (16 October 2026).
**Branch:** `codex/cw11-task-run-scope-claim-20261016` (review only).
**Scope:** One bounded architecture/core authorization hardening slice. This does **not** activate or complete reviewed skill publication (CW-11) or production qualification.

## Defect and acceptance

A restricted Agent run has a durable `cw_agent_runs.tool_allowlist`, but the legacy `save_plan`, `replace_remaining_plan` and `AgentRuntime.execute_step` path did not independently enforce it. The v3 planner already filters admitted tools; that is not a sufficient worker boundary. A direct deterministic plan, saved replan or corrupted/stale persisted invocation could attempt a different enabled task.

Keep existing unspecialized user runs with an empty allowlist unchanged. For a run with a nonempty allowlist:
- A task outside that exact recorded scope is rejected at initial plan, replan and worker execution, even if globally enabled.
- Rejection happens before task creation, provider calls, receipt writes or artifacts. Rejected plan/replan transactions roll back.
- Task selection does not inherit a manifest's authority. Existing attached consequential actions continue through exact ExternalAction approval bindings, not a task grant.
- No new orchestrator, credential, schema, feature flag, publish path, capability activation or provider permission.

## Implementation

- `services/coworker/agent_repository.py`: recheck `run.tool_allowlist` in initial and replacement plan SQL admission.
- `services/coworker/agent_runtime.py`: recheck the same persisted grant before task execution.
- `tests/test_coworker.py::test_agent_task_scope_survives_plan_replan_and_worker_claim`: real SQLite repository and AgentRuntime path. Deny an unlisted step in plan/replan; persist an allowed step, simulate an altered persisted tool identity and prove the worker refuses to create a Task. Existing unscoped path remains covered by prior tests.

## Required checks before repository verified

1. `uv run --extra coworker pytest tests/test_coworker.py -k agent_task_scope_survives_plan_replan_and_worker_claim -q`
2. `uv run --extra coworker pytest tests/test_coworker.py tests/test_automations.py tests/test_coworker_skill_manifests.py -q`
3. Mandatory exact PR HEAD `test-and-build`, zero-skip `coworker` and `ci-merge-gate`.
4. Independent review of time-of-check/time-of-use, model-selected steps, plan replay, old invocations, action paths and mixed-version behavior.

These checks are acceptance obligations, not claimed pass results until their logs are inspected. Source/test additions alone are not operated PostgreSQL/Temporal restart, concurrent worker claim or staging evidence.

## Remaining gates

CW-11 reviewed persisted publication/version rollback, runtime selection of a pinned reviewed skill version with actual immutable grant binding, utility evaluations and staging remain incomplete. CW-10 operated isolated-worker and CW-09 browser security plus A/P/V coworker scenarios are separate unresolved tasks. This branch must not deploy, merge or activate release flags automatically.
