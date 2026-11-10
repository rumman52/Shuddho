# C-01 / A-02 — finalization cancellation and missing-run integrity

**Source:** `main` at `c2d029c4782768b8aba04c96105eae978d7e2c07` (includes merged PRs #491–#494).  
**Branch:** `codex/c01-finalization-cancel-notfound-fence-20261020`  
**Scope:** one bounded Runtime v3/Temporal final-activity integrity correction; no workflow/schema/provider/flag changes.

## Reproduction and root cause

The existing `AgentRepository.complete_run` finalization row lock returned silently for **missing** rows and **cancelled/cancel-requested** rows. `AgentRuntime.complete` then returned normally to the Temporal `shuddho_agent_complete_v1` activity, even though it had committed no successful completion. An automation notifier already checks for `run.state == "completed"`, but this does not repair a falsely acknowledged completion activity.

## Contract

- Missing run: raise existing `not_found` instead of acknowledging success. No notification or checkpoint.
- Runtime v3 cancelled or cancellation-requested run: raise existing `agent_cancelled` **inside the locked finalization transaction**. Activity maps it to a non-retryable Temporal application error. Keep cancellation terminal; no completion event, checkpoint, notification or outbound call.
- Previously completed runs: exact activity replay remains a no-op; no duplicate completion evidence.
- Legacy Runtime v1/v2 cancelled completion: preserve existing no-op behavior. Do not change old workflow contracts.
- All other Runtime v3 verified-result/terminal/deadline checks from merged #491 remain intact.

## Evidence and gates

- Regression tests committed first in `c4af537a75f929443613d2776b71ce47fa2c054e`. This is ordering evidence **only**, not an executed failing-first test run.
- New cases exercise cancellation, persisted cancel-request flag, unknown run, Temporal application-error classification, no notification and legacy compatibility. Existing verified completion/replay tests remain the positive control.
- Mandatory exact-final-head `test-and-build`, `coworker`, `ci-merge-gate` and independent review must pass before considering merge. No local full-suite or live Temporal-server test is claimed here.
- This proves at most a bounded repository source-level finalization boundary. Full 17-row A/C/P/V acceptance, 16 operated CW-02 artifacts, browser/sandbox isolation, CW-11 mixed-worker drain/rollback, old-history replay, staging, human security/quality review and production activation remain open.

**Activation:** none. **Production rollout authority:** none.
