# CW-11 / A-04 — Preserve pinned reviewed research after flag rollback

**Date:** 16 October 2026 (Asia/Dhaka)  
**Base:** `main` `c4d047dc9ede00b3caac81239621f3dcca28d6ab`, merged [PR #434](https://github.com/rumman52/Shuddho/pull/434).  
**Branch:** `codex/cw11-reviewed-skill-rollback-boundary-20261016`.

## Objective and user-visible behavior

A research Task admitted by the reviewed-skill gate must never silently lose its review checks when a newer or rolled-back worker has `SHUDDHO_AGENT_REVIEWED_RESEARCH_SKILL_ENABLED=false`. It must fail closed at worker resume, idempotency replay and paid search reservation. Standalone and previously admitted unpinned legacy research must retain their existing behavior.

## Dependency and reproduction

The merged PR #434 persisted a `Step(task_id, phase="reviewed_skill_identity")` containing exact manifest and ToolSpec identity; the worker, replay and search-reservation code nevertheless decided whether to check it **only** from the current process feature flag. Turning off that flag for a run admitted when it was on caused an unqualified legacy fallthrough in all three paths. This is a concrete release/rollback hazard even though the flag is default-off. The merged [PR-head CI #38904915894](https://github.com/rumman52/Shuddho/actions/runs/38904915894) passed, but it never exercised that post-admission flag change. Three independent review threads on the earlier PR remain unresolved after operationally failed Codex re-review requests; this new PR does not claim to clear them.

## Implementation contract

- An Agent-owned reviewed Task is admitted with the distinct `work_research_reviewed_v1` **task workflow version**, separate from the `work_research_v1` source-reviewed WorkSkill manifest identity. This acts as a deployment version fence: previous workers do not recognize it in `skill_for_version` and `reserve_search`, and fail closed rather than run a reviewed Task as legacy research. The SQL `reviewed_skill_identity` Step remains authoritative for the exact source-review digest and current tool grants. No new database table, grant, provider or manifest publication is introduced.
- `Repository.worker_task` checks the persisted identity **and distinct workflow version** for all nonterminal Tasks, including when admission is now disabled. Missing original owner binding, pinned review Step or wrong Task workflow fails closed. New worker and runner map the reviewed task workflow to the existing reviewed `research` WorkSkill for instruction/render behavior without changing the audited manifest source.
- `Repository.reserve_search` selects the same review requirement and validates the distinct workflow version, maintaining AgentRun→Task lock order before consuming search credit. Older workers only accept `work_research_v1` at that reservation boundary, so cannot reach paid search for newly fenced tasks.
- `Repository.create_task` idempotent replay revalidates an **active** previously pinned task even when the current flag is off. Terminal reviewed tasks may return their already-committed result without new work, preserving lost-response idempotence.
- The existing `_require_reviewed_agent_research` intentionally returns no manifest when the flag is off, causing the checked pinned Task to reject with `skill_manifest_unreviewed`. Re-enabling the flag does not bypass owner, tool grant, review SHA, Task version, query or document-version checks.
- Legacy tasks without a review record and without the distinct reviewed workflow remain eligible under their existing WorkSkill/ToolSpec/feature gates. Existing pre-fence reviewed tasks admitted by merged #434 still have legacy `work_research_v1` plus a pinned review Step; new workers **deny these older in-flight tasks** rather than silently upgrade them. A controlled migration and restart strategy is required before activating the pilot on mixed versions. Cohort health counters include both legacy and reviewed workflow versions. No onboarding or public skill/tool authority changes.

## Expected outcomes / acceptance

1. Feature enabled + exact authorized `research.search` Agent run → reviewed Task accepted; worker read succeeds and review Step exists.
2. Same nonterminal Task after disabling the reviewed admission flag → worker read denies, search reservation denies **without a search-attempt record**, matching active idempotent replay denies. Previously pinned completed/failed/cancelled Task replies remain idempotently replayable.
3. Legacy standalone Task under disabled reviewed gate → remains usable; no invented reviewed Step. Old `skill_for_version` must reject the new reviewed Task version and old reserve-search must reject the same version, not silently issue provider calls.
4. Re-enable reviewed gate on unchanged owned run → pinned task may resume only under its still-valid policy and grant.
5. Existing tests for changed review SHA, expired/revoked run, changed query/tool/version, source version, public key collision and pre-provider cancellation continue passing.
6. Required exact-final-head `test-and-build`, mandatory zero-skip `coworker` and `ci-merge-gate`, plus independent review before closure.

**Focused command:** `uv run --extra coworker pytest tests/test_coworker.py -k 'reviewed_research_gate_disable_never_downgrades_pinned_task or reviewed_agent_research_requires_exact_worker_grant_and_version or reviewed_research_rechecks_revocation_after_search_reservation' -q`.

## Interfaces / boundaries / rollback

Files: `services/coworker/repository.py`, `services/coworker/task_workflow_versions.py`, `services/coworker/runner.py`, `scripts/cohort_health_gate.py`, `tests/test_coworker.py`, this contract, inventory and progress. No database schema migration; the new workflow identity occupies the existing Task.workflow_version field. Old readers may be unable to display a reviewed Task even though they correctly refuse its execution; staged mixed-worker compatibility/recovery needs separate evidence. Process-config toggle never grants tool authority. No new model/provider calls or action execution. The safe response to disabling the pilot on a current-schema worker is **denial for already-pinned Tasks**, not unchecked resume; user-facing recovery requires an explicit reviewed-version/rollout plan.

**Limitations:** The *newly admitted* distinct workflow version causes pre-fix workers to reject rather than execute it, but older `work_research_v1` reviewed Tasks may exist without this fence and cannot be declared safe across mixed old workers. No safe mixed-release/readability proof, version publication, multi-version selection, task migration, staging/production qualification or activation can be claimed without operated rollout tests. Flag-disabled Tasks that never had a reviewed record are not retroactively reviewed. Other CW-09/CW-10 and A/P/V inventory gates remain separate.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Committed, verification pending | Review branch (final SHA recorded in PR) |
| Repository verified | Pending | Final-head CI and independent review |
| Staging verified | Not established | Matching API/worker roll-forward/rollback and PG/Temporal |
| Production qualified | No | Full release evidence absent |
| Activated | No | Gate remains off; no deployment authorized |

No merge, deploy, production activation, external provider send or paid provisioning is authorized.
