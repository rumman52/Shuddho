# CW-11 — Fence historical reviewed-task migration before dispatch

**Date:** 17 October 2026 (Asia/Dhaka)  
**Base:** `main` `75521bdc77fea7366127c18ee854731880cff58b`, after merged PR #451.  
**Branch:** `codex/cw11-legacy-migration-dispatch-fence-20261017`.

## Objective

Never rewrite a historical reviewed Task's workflow/publication identity if its parent Agent workflow may already have been dispatched, started, or completed with an uncertain response. A queued Task phase alone does not prove that the parent Temporal workflow never started.

## Reproduced gap

`Repository.migrate_legacy_reviewed_tasks()` required `task.phase == "queued"` and no `search_attempt`, but did not require the Task state, parent Agent outbox, run state, invocation state, step linkage, or receipt to prove the workflow was still pre-dispatch. A delivered or uncertain parent workflow can remain at the Task's initial phase. Rebinding it in place could change the policy observed by an existing Temporal execution.

## Bounded implementation

- Require the Task to remain queued and in its initial queued phase.
- Lock and inspect the existing parent `AgentOutbox`. Reject a missing row, a delivered row, any previous attempt, or any lease. Any dispatch attempt is treated as uncertain because the workflow start may have succeeded even if its response was lost.
- Require the parent Agent run to remain in its undispatched planning state (`state=planning`, `phase=planned`), non-cancelled and unexpired; require a planned, never-started `research.search` step and a prepared, never-started matching invocation.
- Reject an already-linked step resource or any persisted `ToolReceipt`.
- Keep the current exact source-review hash, selected publication, grant, deadline, no-search-attempt and worker-drain checks. All candidates remain an all-or-nothing transaction: one unsafe row blocks the batch without rebinding another task.
- Do not infer Temporal quiescence from SQL state. A failed preflight requires controlled recovery/reconciliation, not a forced workflow-version rewrite.

## Acceptance

- Regression tests cover delivered/attempted/leased/missing Agent outbox state, a running Agent run, a running Task, a started invocation, a linked step resource, and an existing receipt.
- Every blocked migration leaves Task workflow version and legacy identity unchanged and records no migration event.
- A genuinely undispatched queued task still migrates under the existing safe path.
- Exact-head `test-and-build`, mandatory zero-skip `coworker`, and `ci-merge-gate` must pass. PostgreSQL/Temporal staging and independent operational review remain separate evidence.

## Boundaries

No schema change, new ledger, provider call, task cancellation, deployment, capability activation, or automatic merge. The existing CW-11 capability remains default-off. This slice closes a repository migration guard; it does not prove fleet-wide drain, mixed-version recovery, or production qualification.
