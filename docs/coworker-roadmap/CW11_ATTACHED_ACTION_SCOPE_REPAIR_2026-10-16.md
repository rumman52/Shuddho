# CW-11 — Preserve exact attached actions in restricted planner menus

Date: 16 October 2026 (Asia/Dhaka)  
Baseline: `main` `41f457b04f2b1e466cbaafd7bbfff04cc5993186`, merged PR #432.  
Scope: A-04 / CW-11 legacy intelligent planner, plan conversion and replan. No new provider authority, migrations or rollout flags.

## Failure and security contract

PR #432 correctly filters ordinary registered task tools against the persisted `AgentRun.tool_allowlist`. Independent review found that `intelligent_tool_names` mistakenly also required an **empty** grant to include `attached.*` handles. For a restricted run with an explicitly attached, awaiting-approval action, the model therefore cannot select it; `proposal_to_plan` rejects its handle; `release_unselected_actions` can detach an otherwise valid authorized draft. The same menu helper feeds initial planning and replanning.

Task-tool grants and attached consequential actions are different sources of authority. Attached handles are generated only from the current run's bound `actions`, are transient opaque choices (not free-form external actions), and remain gated by the existing `ExternalAction` binding, approval, and dispatch checks. The model must never be able to attach an arbitrary action or grant itself a normal tool.

## Bounded change

- Always add bound, awaiting-approval `attached.*` candidates when `agent_action_selection_enabled` is true, irrespective of the ordinary-task allowlist.
- Keep all ordinary task names filtered by the nonempty persisted allowlist.
- Retain the existing `proposal_to_plan`, `AgentRepository.save_plan`/`replace_remaining_plan` and approved `ExternalAction` authorization checks; no direct send occurs during planning.
- Exercise run-scoped model menu, opaque-handle translation, preservation of selected action, release of unselected action, and replan after action-index renumbering.

## Verification requirements and limits

Focused: `uv run --extra coworker pytest tests/test_coworker.py -k 'intelligent_planner_resolves_only_opaque_attached_action_handles or agent_action_selection_releases_only_unselected_pending_drafts or restricted_run_planner_and_fallback_never_offer_extra_tools' -q`.

Require the exact final PR-head `test-and-build`, zero-mandatory-skip `coworker`, and `ci-merge-gate` checks; inspect independent review findings. A reviewable code change is not repository verification until those checks pass. CI fixtures use synthetic actions and no actual external provider send. Operated PostgreSQL/Temporal races, real provider uncertainty, staging, production qualification, and broad CW-11 reviewed skill publication/rollback are separate unsatisfied gates.

No autonomous merge, deployment, paid provisioning, external send, or activation is authorized.
