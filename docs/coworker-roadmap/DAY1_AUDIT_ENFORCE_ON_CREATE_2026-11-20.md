# Day 1 — Required-check enforce-on-create governance audit

- **Objective and user-visible behavior:** The read-only GitHub governance audit must reject a ruleset that permits matching branch creation without required status checks, rather than returning a compliant candidate.
- **Dependency tasks and current evidence:** [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), [governance #737](https://github.com/rumman52/Shuddho/issues/737), [merged PR #828](https://github.com/rumman52/Shuddho/pull/828) fixes a different status publisher bug. The current `infra/github/main-ruleset.json` requires explicit `do_not_enforce_on_create=false`; `scripts/day1_ruleset_drift.py` already enforces the same rule.
- **Base branch/SHA:** `main` at `450105020f962a86197e7c5f2cc7bf865388b3d7`.
- **Work branch/PR:** `fix/day1-audit-enforce-on-create-20261120`, [draft PR #833](https://github.com/rumman52/Shuddho/pull/833).
- **Existing interfaces to reuse:** `scripts.main_protection_audit.audit_governance(branch, rulesets)`, `_has_required_rules(rule)`, `GovernanceAuditError`; no new public function.
- **Exact files to create/modify:** `scripts/main_protection_audit.py`; `tests/test_main_protection_audit.py`; this task contract, `docs/coworker-roadmap/PROGRESS.md`, and the [bounded plan](../superpowers/plans/2026-11-20-day1-enforce-on-create-audit.md).
- **New interface signatures / schema and compatibility:** No new public interface or schema. A status-check rule only qualifies when `strict_required_status_checks_policy is True` and `do_not_enforce_on_create is False`. A missing field or type-coerced equivalent is not accepted.
- **Acceptance scenarios and assertions:** Existing reviewer, scope, no-bypass, strictness and App-ID checks remain unchanged. `True`, `None`, `0`, `"false"`, `"False"`, and absence of the enforcement field must each raise `GovernanceAuditError`; literal `False` plus the existing required checks/independent review remains accepted.
- **Reproduction / initial failure:** Test-only exact SHA `7b235a5cf005f0e1e4ccd55a11dca20bfe4e5b6e`, [CI #44783850122](https://github.com/rumman52/Shuddho/actions/runs/44783850122), `test-and-build` **6 expected FAIL / 2,786 PASS / 103 SKIP / 6 WARN**; all six cases failed with `Failed: DID NOT RAISE GovernanceAuditError`. This RED run is not successful final-head acceptance.
- **Expected failure outcomes:** Native exempt/missing/ambiguous creation enforcement is rejected by the local configuration-read auditor, before it can be used to present a passing governance configuration. The auditor never writes policy.
- **Tests and required CI commands:** `uv run --locked pytest -q tests/test_main_protection_audit.py tests/test_day1_ruleset_drift.py tests/test_reconcile_main_ruleset.py`; exact-final-head CI `test-and-build`, frontend, browser-qualification, PostgreSQL 18 compatibility, coworker, governance-audit and ci-merge-gate. Explicitly distinguish skips from passes.
- **Secrets / owner / grant / approval / egress boundaries:** No secret reading/writing, token, repository permission, GitHub App change, live ruleset mutation or egress added by this PR. Owner C/repo admin must independently configure protected `V01_RULESET_APP_CLIENT_ID` and `V01_RULESET_APP_PRIVATE_KEY`; an independent human reviewer must approve a current head.
- **Budget / timeout / cancellation / revocation behavior:** Unchanged CI and operator timeouts. No additional provider calls or resources; no inference or billing.
- **Default-off gate and rollback:** Governance audit is read-only. No pilot release, staging transition or production flag changed. Rollback means reverting this code-only audit predicate after formal review; it never changes live settings.
- **External prerequisites:** Native ruleset `27324410` negative/positive merge-control receipts; authorized staging backup and isolated restore, exact API/worker/schema identity and real recoveries; independent D custody; separate Founder+C approval.
- **Out of scope:** Blindly applying rulesets; creating paid Render resources; Supabase staging migration `0070`→`0072_merge_0071_heads`; telemetry activation; private data; human signoff.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Source fix committed; exact review head at PR | [PR #833](https://github.com/rumman52/Shuddho/pull/833) |
| Repository-verified | Pending final-head CI | [PR #833 Checks](https://github.com/rumman52/Shuddho/pull/833/checks) |
| Staging-verified | Not attempted / BLOCKED_EXTERNAL | No authenticated native merge-test, staging restore or paired worker readback |
| Production-qualified | NO-GO | No independent evaluation, recovery or release approvals |
| Activated | No | No runtime, ruleset, pilot or telemetry mutation |

- **Test pass/fail/skip counts:** RED 6/2786/103 (6 warnings); GREEN pending exact-head CI readback.
- **Exact-head CI links:** RED [#44783850122](https://github.com/rumman52/Shuddho/actions/runs/44783850122); GREEN see [latest PR head Checks](https://github.com/rumman52/Shuddho/pull/833/checks), not a superseded run.
- **Review findings and resolution:** Read-only auditor accepted native create-ref exemptions, inconsistent with reviewed policy and offline Day 1 diagnostic. Corrected to exact boolean False.
- **Residual risks:** A local script cannot prove native merge enforcement or operator identity; a merged PR without review is not independent acceptance. Hosted staging remains unmigrated and unqualified.
- **Next exact action:** Read exact final-head required checks; seek human independent code review; have authorized C/admin run configured governance audit and independently prove denied/permitted merges. Keep pilot NO-GO until remaining gates have separate receipts.
