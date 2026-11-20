# Day 1 — Native status-check publisher drift guard

- **Objective and user-visible behavior:** A reviewed administrator dry-run or explicit native-ruleset apply cannot silently replace a previously configured but unreviewed publisher identity for a required GitHub status context.
- **Dependency tasks and current evidence:** Day 1 governance #727, #737. Existing native ruleset reconciler and PR #823 source fixes merged; native administrator audit/negative-positive control remains an external prerequisite. The source plan is `docs/superpowers/plans/2026-11-20-day1-native-status-publisher-guard.md`.
- **Base branch/SHA:** `main`, `4be5ea5c2fdccc2d718f0b37b958bdc2b5fa9577`.
- **Work branch/PR:** `fix/day1-native-check-publisher-drift-20261120`, [draft PR #828](https://github.com/rumman52/Shuddho/pull/828).
- **Existing interfaces to reuse:** `reconcile_main_ruleset.reconcile_main_ruleset`, `_require_unambiguous_existing_checks`, `_validate_candidate`, `ruleset_fingerprint`, `_read_unique_existing`; existing scoped `ApplyMainRulesetError`.
- **Exact files to create/modify:** `scripts/reconcile_main_ruleset.py`; `tests/test_reconcile_main_ruleset.py`; this task contract, plan and `PROGRESS.md`.
- **New interface signatures / schema and compatibility:** No new public API, runtime schema or externally visible endpoint; new validation inside `_require_unambiguous_existing_checks(existing: dict, reviewed: dict) -> None`. For the three approved contexts, an explicit non-null publisher must match the reviewed context-specific ID as an exact Python integer. Missing/null publisher remains repairable.
- **Acceptance scenarios and assertions:** Existing `coworker` publisher `98765`, `0`, `"15368"`, `15368.0`, `True` ⇒ fail closed before any PUT; existing null publisher and exact integer `15368` ⇒ normal dry-run and zero writes. Previously tested duplicate/unknown-field/cross-context and already-configured preflight paths remain unaffected.
- **Reproduction / initial failure:** Test-only SHA `cf2e4eec040f606eb824ffd7d357d13737697291`, [GitHub Actions run #44778941841](https://github.com/rumman52/Shuddho/actions/runs/44778941841), Python `test-and-build` **5 expected FAIL / 2726 PASS / 102 SKIP / 6 WARN** (all five new negative publisher test cases returned without raising). Positive cases passed. No live GitHub ruleset write.
- **Expected failure outcomes:** `ApplyMainRulesetError("unexpected required status check publisher needs manual reconciliation")` before dry-run or apply can normalize unreviewed native publisher.
- **Tests and required CI commands:** `uv run --locked --extra coworker pytest -q tests/test_reconcile_main_ruleset.py tests/test_day1_ruleset_drift.py`; final PR-head `test-and-build`, frontend, `coworker`, browser qualification, PostgreSQL 18 compatibility, governance audit and merge gate.
- **Secrets / owner / grant / approval / egress boundaries:** C and repository administrator must supply the protected `V01_RULESET_APP_CLIENT_ID` and `V01_RULESET_APP_PRIVATE_KEY`; independent GitHub reviewer must review the exact head. No access rights, provider send, third-party key, native policy, live infrastructure, user content, telemetry or egress changed in this PR.
- **Budget / timeout / cancellation / revocation behavior:** No inference, worker, Temporal, deployment or paid provisioning in scope; existing operator network timeouts and exact-SHA/fingerprint checks remain unchanged.
- **Default-off gate and rollback:** Dry-run remains default; no `--apply` invoked. Roll back this PR's isolated code if independently reviewed integration regresses; never roll back native main protection from here.
- **External prerequisites:** Authorized native ruleset readback and negative/positive merge-control receipts, staging isolated restore + worker/API/schema identity, independent D holdout custody, Founder and C release approvals.
- **Out of scope:** Staging migration `0070`→`0072`, private data seeding, paid Render resources, live app secrets, bypass actors, production/pilot flags, actual native ruleset mutation.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Source change committed; final head to confirm | `8b7f04438aa969cbc11c14df85368562bd0c62a0` initial fix |
| Repository-verified | Pending exact-head CI | [PR #828 Actions](https://github.com/rumman52/Shuddho/pull/828/checks) |
| Staging-verified | Not attempted / BLOCKED_EXTERNAL | No staged read/write, backup, synthetic owner, or live negative/positive operator control |
| Production-qualified | NO-GO | No real staging/runtime/evaluation approval |
| Activated | No | No native policy change, deployment or pilot enrolment |

- **Test pass/fail/skip counts:** RED 5/2726/102 with 6 warnings; GREEN pending exact-head readback.
- **Exact-head CI links:** RED [#44778941841](https://github.com/rumman52/Shuddho/actions/runs/44778941841). For GREEN, inspect the **latest commit** and its jobs on [PR #828 Checks](https://github.com/rumman52/Shuddho/pull/828/checks); earlier runs are superseded by subsequent test and documentation commits. Do not credit cancelled runs.
- **Review findings and resolution:** Mismatched/type-confused existing publisher should be manually reviewed; validation now reads approved context IDs from validated reviewed policy instead of hardcoding an extra version. Human review pending.
- **Residual risks:** Native governance and independent reviewer may remain absent despite source CI. GitHub can merge without review if live ruleset remains weak. Do not treat source changes as native enforcement.
- **Next exact action:** Inspect GREEN required CI on final PR head; have independent maintainer review. C/administrator must perform fresh main SHA + ruleset fingerprint dry-run in protected environment, then after separate authorization prove native negative and positive merge-control cases.
