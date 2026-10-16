# CW-11 / A-03 — Historical reviewed Task inventory before worker rollback

Date: 16 October 2026 (Asia/Dhaka)  
Starting `main`: `d757d165bbb36eaea829b683714f03b37d7206d9` (merged #435).  
Branch: `codex/cw11-legacy-reviewed-rollback-preflight-20261016`.

## Threat and observed limitation

The merged source-reviewed pilot (#434) admitted some Agent-owned `research.search` Tasks under the legacy `work_research_v1` workflow and persisted a Task-local `reviewed_skill_identity` Step. Its old workers could ignore the review Step when the gate was off. Merged #435 introduces distinct `work_research_reviewed_v1` for *new* reviewed admissions, which old workers fail to execute; it **does not retroactively fence already accepted legacy reviewed Tasks**. If one of those is queued or active when an older worker processes it during rollback, authorization checks can be skipped.

A successful code merge or synthetic test cannot prove that no old worker, provider dispatch or Temporal activity is still active. No trustworthy fleet-discovery/worker-drain signal is available inside a standalone DB query. Do **not** silently migrate an in-flight workflow version or treat a rollback flag as a safety proof.

## Read-only preflight

`python -m scripts.reviewed_skill_rollback_preflight`

Provide `SHUDDHO_COWORKER_DATABASE_URL` through backend environment secrets, never CLI flags or logs. Run on a consistent snapshot after new admissions are stopped. The script reads the existing `cw_tasks` and `cw_steps` tables with **one aggregate SQL statement** (a single PostgreSQL statement snapshot), rather than multiple count queries observing inconsistent states. It performs **no writes, claims, migrations, task cancellations, external actions, provider calls, credential output or activation**. The result is still a point-in-time observation, not a transaction-level lock or worker-fleet barrier. Return only aggregate counts:

- `active_unfenced_reviewed_tasks`: nonterminal Tasks with a persisted review identity but without `work_research_reviewed_v1`. **Block**; includes old pilot instances.
- `active_fenced_tasks_missing_review_identity`: nonterminal new-version Tasks without review Step. **Block**; version without identity does not authorize execution.
- `active_legacy_agent_research_without_review_identity`: nonterminal legacy `work_research_v1` Tasks tied to an Agent run but **without** a reviewed Step. **Block conservatively**: an absent review record cannot prove that the task was safely unreviewed, and an older worker may execute it.
- `active_fenced_reviewed_tasks`: nonterminal new-version Tasks with review Step, informational; old readers reject these by version.
- `terminal_legacy_reviewed_tasks`: terminal historic reviewed Tasks that may be replayed for status without new effect; informational.
- `BLOCKED_TASK_LEDGER` and nonzero process exit when either blocker count is positive. Empty result is only `TASK_LEDGER_CHECK_ONLY` and is **not rollout approval**, worker-drain proof or staged recovery evidence.

A missing database URL, schema access error or malformed environment must cause a failed preflight, not a synthetic zero count. Run the check again **after** worker drain to avoid a stale snapshot; a single clean query still cannot close an in-flight dispatch race.

## Acceptance

- SQL integration test includes one active old-reviewed workflow + Step, one active new-reviewed workflow + Step, one new workflow missing Step, one active legacy Agent research Task missing Step, and one terminal old-reviewed workflow. Assert all three blockers and zero authority flags, and that terminal tasks are not active blockers.
- After synthetic terminalization of unsafe Tasks, assert `TASK_LEDGER_CHECK_ONLY`, never `GO` or `rollout_authorized`.
- Missing URL fails closed. CI must run `tests/test_cohort_health_gate.py` in mandatory coworker job and all final-head required jobs must pass.
- Independent review checks ownership assumptions, grouping/count completeness, SQL consistency and absence of accidental rollout authority.

## Next operated qualification (not solved by this PR)

1. Identify exact API/Temporal/worker source revisions and enabled flags on matching staging identities.
2. Block **new** old-version admission at the actual entry point; drain/stop all old workers and any in-flight external provider activity under a documented controlled procedure.
3. Inspect **all** existing Task and Step records, account for historical active legacy-reviewed work and reconcile/recover its state. If migration is unavoidable, design a separate atomic owner-safe version/backfill process with temporal replay and old-reader compatibility tests; do not mutate running tasks casually.
4. Re-run preflight and prove a whole-system mixed-worker/Temporal replay/provider no-effect test. Save dated evidence and source/workflow identity in the release ledger.
5. Independently review and authorize any activation/deployment. Current reviewed-research capability remains default-off; staging and production qualification are not established.

Related review: [#435](https://github.com/rumman52/Shuddho/pull/435) and [#436](https://github.com/rumman52/Shuddho/pull/436). A green CI run tests code behavior, not live cluster safety.
