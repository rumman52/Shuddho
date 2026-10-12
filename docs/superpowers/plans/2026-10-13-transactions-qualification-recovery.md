# Transactions qualification recovery implementation plan

> **For agentic workers:** Use `shuddho-engineering` and `superpowers:executing-plans` to implement this bounded continuation. The user authorized implementation; proceed in this session without a new approval round.

**Goal:** Restore mandatory transaction qualification on main after PR #379, while preserving the real authorization, claim and uncertainty boundaries.

**Architecture:** Keep PostgreSQL and ExternalAction as the execution authority and the existing Temporal workflow unchanged. Repair optional-dependency collection and control only the test server's retry clock. A delayed disposable worker must not cause the test harness to skip past the workflow deadline.

**Tech stack:** Existing Python/pytest, SQLAlchemy/PostgreSQL, Temporal test server, counted loopback HTTP provider and GitHub Actions.

**Spec:** `docs/coworker-roadmap/SPEC.md`; CW-01/CW-02 in `2026-10-12-coworker-evolution.md`.

## Task contract

- Base: main `fb1a08059cd242f5da4d72dbf72da0c6971bfe30`, PR #379.
- Branch: `codex/transactions-ci-recovery-20261013`.
- Review: [PR #380](https://github.com/rumman52/Shuddho/pull/380); initial implementation `7ae84f757a696116f3aade9aaeeced296b7078a3`. Required final-head CI is pending at this checkpoint.
- Initial evidence: [main CI 38292932568](https://github.com/rumman52/Shuddho/actions/runs/38292932568) failed lightweight collection (`ModuleNotFoundError: sqlalchemy`) and Temporal `before_claim` recovery (`Workflow timed out`).
- Lightweight reproduction: the boundary module errors in a frozen dev-only environment before collecting its tests.
- Interfaces: reuse `ActionRepository.claim_execution`, `ActionService.execute`, `ApprovedActionWorkflow`, `WorkflowEnvironment.sleep`, `auto_time_skipping_disabled` and `scripts.mandatory_test_gate`. Test-only polling control remains in `tests/transaction_process_harness.py`.
- Acceptance: dev-only collection succeeds; all transaction boundary/reconciliation modules collect in mandatory heavyweight CI with zero skips; all four hard Temporal crash boundaries preserve their existing independently counted outcomes, including delayed restart polling.
- Compatibility: no migration, runtime API, workflow history, provider registration, budget, approval, cancellation or release-flag changes.
- Secrets/egress: synthetic identities, disposable loopback database and loopback provider only. Parent counters deliberately do not deduplicate sends. Owned child processes are cleaned up after success or failure.
- External prerequisites: real PostgreSQL is available in CI; operated staging/provider credentials and human reviews remain external gates.
- Rollback: revert this test/CI patch; all production capabilities retain their current default-off release gates.
- Out of scope: production activation, real messages/purchases/bookings, provider registration, staging attestation and unrelated coworker features.

## Global constraints

- Preserve free multilingual/Bangla writing and backend-only provider credentials.
- Reuse the existing ExternalAction ledger; never blindly resend an uncertain action.
- Do not change production timeouts or skip a mandatory heavyweight test to make CI green.
- Report repository, staging, production and activation evidence separately.

## Review focus

- A slow restarted worker: hold its polling with a parent-owned event; retain all four receipt/count assertions.
- Optional dependencies absent: reproduce with a separately frozen lightweight environment.
- Optional tests silently omitted: require the newly merged boundary/reconciliation modules in heavyweight JUnit.
- Provider acceptance before worker death: retain exactly one counted application and no reclaim.
- API/Temporal outage: retain the existing actual process/server fault cases and owned-resource teardown.

## Task 1: Repair mandatory qualification

**Files:** `tests/test_transaction_execution_boundary_contract.py`, `tests/test_transaction_chaos_temporal.py`, `tests/transaction_process_harness.py`, `tests/test_transaction_reconciliation_boundary.py`, `.github/workflows/ci.yml`, `docs/coworker-roadmap/PROGRESS.md`.

- [x] Reproduce lightweight collection and capture the current Temporal failure evidence.
- [x] Add a parent-controlled restart-polling barrier to the real process test and demonstrate the result-wait failure with the old unbounded virtual clock.
- [x] Add optional-dependency collection protection and require the execution/reconciliation tests in the heavyweight safety report. This exposed a nonexistent `SimulatedGoogle.provider` fixture field; replace it with the literal configured provider and check real cross-owner denial.
- [x] Advance only the interrupted activity's retry interval, then disable automatic skipping while the restarted real worker executes; preserve all independent state/receipt/counter assertions.
- [ ] Run focused Temporal/transaction checks, the lightweight project suite and applicable full CI; reject mandatory skips.
- [x] Review the final diff and publish a draft PR with the verified local counts and remaining live gates; append exact-head CI results when available.

## Completion evidence

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Yes | Test/CI repair on the task branch; production workflow unchanged |
| Repository-verified | Pending | Require exact-head required CI |
| Staging-verified | Pending | No operated staging access established |
| Production-qualified | Pending | Provider/security/release evidence still required |
| Activated | No | No activation authorized |

Local checks: 1,052 lightweight tests passed (65 optional skips); 41 focused tests passed (one PostgreSQL-only skip); 25 mandatory safety cases passed without skips and all five required modules were collected; 103 neighboring tests passed. The fresh read-only review found no confirmed Critical/Important defect. An additional balanced unlock was retained after atomic sleep alone timed out for all four killed-activity cases; production timeouts remain unchanged.

Next exact action: publish the reviewed draft PR, inspect the exact final-head PostgreSQL/full CI results, then mark review readiness only when all required jobs pass. Operated staging/provider qualification remains separate.
