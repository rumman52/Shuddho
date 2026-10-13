# CW-09 corrective task — browser receipt cancellation race and PostgreSQL qualification

**Date:** 14 October 2026 (Asia/Dhaka)  
**Workstream:** Architecture design / Core agent / CW-09  
**Base:** `main` `fd4cb99a2d7925bcdd0faafad5a3eae041496a80`  
**Branch:** `codex/cw09-receipt-lock-postgres-fixture-20261014`  
**Code/test revision before documentation:** `7afabac1dc6c1fdada5ffdfe20994c60a0cc3aa9`

## Source and reproduced failure

Corrective [PR #388](https://github.com/rumman52/Shuddho/pull/388) is merged into main, **not qualified**. Its final-head [CI #38432751315](https://github.com/rumman52/Shuddho/actions/runs/38432751315) failed: `test-and-build` passed, the mandatory PostgreSQL/conversation step failed with 59 passed, 1 failed, the brokered Agent browser no-skip suite did not run and `ci-merge-gate` failed. The failure is `ValueError: Actions require Google OAuth credentials and an HTTPS frontend /oauth/google/callback redirect URI` while configuring `test_agent_browser_cancel_and_worker_control_are_serialized_on_postgres`. The suite has existing inert development OAuth fixtures in `tests/action_samples.py::enable_actions`; this additional PostgreSQL regression omitted them.

The final security review of PR #388 identified [a P1 row-lock inversion](https://github.com/rumman52/Shuddho/pull/388#discussion_r4261477538): `AgentRepository.finish_invocation` locks `BrowserCommand` first, then indirectly `BrowserSession` inside `_settle_agent_browser_session`. Meanwhile browser cancellation and worker control lock session first, then command. Under concurrent receipt/revocation PostgreSQL may abort one transaction or race the intended terminal precedence.

## Authority and patch

No new orchestration, ledger, database schema, worker, provider, OAuth integration or runtime feature flag is introduced. `SHUDDHO_AGENT_BROWSER_READ_ENABLED` remains **default-off**.

- **`services/coworker/agent_repository.py`:** For brokered browser receipts only, recover the previously owned session id from the AgentStep output, lock that exact `BrowserSession` and revalidate owner, server-reserved Agent identity and active/revocation state; **then** lock `BrowserCommand` with exact id, owner, session and succeeded state. Preserve existing run/step/invocation locking, one receipt, atomic session close and rollback on stale/revoked/foreign evidence. No changes to other tool receipt kinds.
- **`tests/test_coworker_postgres.py`:** Use the same simulated OAuth configuration required by production `Settings.validate`, not relaxed validation. Keep existing multiworker Agent cancel/worker control race; add real PostgreSQL concurrent `finish_invocation` versus `browser.cancel` test with barrier, bounded timeout and mutually exclusive assertions. No fake network or external provider mutation.
- **`docs/coworker-roadmap/PROGRESS.md`:** Persist current main/PR/CI and unmet acceptance.

## Expected outcomes

1. Previously failing PostgreSQL race test actually reaches the browser concurrency assertion with intact settings validation.
2. A receipt/cancellation race completes without deadlock. If a verified receipt commits first, session becomes completed and there is exactly one verified browser observation; if revocation commits first, session is cancelled and no receipt persists. Never approve a late read on a revoked session.
3. Cross-owner session and command mismatches still fail; worker DNS/IP and read-only interaction protections remain unchanged. No duplicate browser command, new Agent run or external mutation.
4. Mandatory `test-and-build`, `coworker` with no-skipped `tests/test_agent_browser_tool.py`, PostgreSQL race suites, and `ci-merge-gate` pass on the **exact final PR head**, not a superseded run. Independent review findings resolved before repository-verified claim.

## Scope and operational limits

This fixes an evidenced correctness/safety defect, **not** full CW-09 completion. Browser tool currently returns metadata-only observations; body capture/private content hash, real isolated-worker/SSRF/redirect/egress bypass qualification, release eligibility checks, human review and staging identity remain open. Keep capability disabled, do not merge automatically, and do not infer production readiness from a green commit.

**Rollback:** Keep the tool disabled; revert this bounded patch only if another reviewed patch retains session-before-command locks and mandatory PostgreSQL race assertions. The new tests use simulated OAuth placeholders for local validation only.

## Evidence checkpoint

| Level | Status |
| --- | --- |
| Implemented | Corrective review branch; final implementation SHA to be confirmed from PR |
| Repository-verified | Pending exact-head CI |
| Staging-verified | Not run |
| Production-qualified | Not established |
| Activated | No |
| Review | Prior P1 documented; fresh independent review pending |

**Next exact action:** Open draft PR and require final-head `test-and-build`, `coworker` including PostgreSQL and browser mandatory suites, and `ci-merge-gate`. Diagnose and correct any new failing assertion with actual job logs. Do not merge or activate.
