# Day 1 — Native status-row ambiguity in read-only governance audit

- **Objective and user-visible behavior:** Reject a native required-status-check rule that contains duplicated, malformed, unknown-field or unauthenticated rows, instead of displaying a protected-main `configuration_candidate`.
- **Dependency tasks and current evidence:** [10-day authoritative plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 §141–152, [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), [board #737](https://github.com/rumman52/Shuddho/issues/737), merged [PR #833](https://github.com/rumman52/Shuddho/pull/833). `scripts/reconcile_main_ruleset.py` already refuses duplicate/unknown native status rows; its read-only audit counterpart still accepted such rows.
- **Base branch/SHA:** `main` at `4b6c747475aa881c979d0eabf52f415fe6100b3d`.
- **Work branch/PR:** `fix/day1-governance-audit-status-row-ambiguity-20261121`; [draft PR #838](https://github.com/rumman52/Shuddho/pull/838).
- **Existing interfaces to reuse:** `audit_governance(branch: dict, rulesets: list[dict]) -> int`, `_has_required_rules(rule: dict) -> bool`, `GovernanceAuditError`; `approved_ruleset` test fixture. No new public API.
- **Exact files to create/modify:** `scripts/main_protection_audit.py`, `tests/test_main_protection_audit.py`, this contract, `docs/coworker-roadmap/PROGRESS.md`, `docs/superpowers/plans/2026-11-21-day1-governance-audit-status-row-ambiguity.md`.
- **New interface signatures / schema and compatibility:** No API/schema change. Native `required_status_checks` must be a list of dictionaries each containing only `context` and `integration_id`, with a unique nonblank string context and `integration_id` exactly the integer GitHub Actions ID `15368`. Required contexts remain `test-and-build`, `coworker` and `ci-merge-gate`. Extra unique first-party contexts are accepted as stronger checks by the **minimum-policy** read-only auditor; policy **reconciliation** still requires separate human approval before accepting any addition.
- **Acceptance scenarios and assertions:** A duplicated approved first-party context, extra untrusted publisher, missing/type-confused publisher, blank/whitespace context, unknown row key or malformed row each raises `GovernanceAuditError`. Exact approved three-context rule qualifies as a candidate; an additional distinct first-party context qualifies as a minimum-policy candidate. Existing no-bypass/review/strictness/creation-enforcement protections are unchanged.
- **Reproduction / initial failure:** Test-only exact SHA `f44c59d2b7b812c33167b882d0c8096e6d56cc12`, [GitHub Actions #44790402009](https://github.com/rumman52/Shuddho/actions/runs/44790402009), `test-and-build` **8 expected FAIL / 2,858 PASS / 103 SKIP / 6 WARN**. Each failure specifically reported `Failed: DID NOT RAISE GovernanceAuditError`. RED is not a passing test run.
- **Expected failure outcomes:** Read-only candidate audit fails closed for all malformed or ambiguous native status rows, rather than hiding extras. It continues to report `configuration_candidate`, not native merger-permission proof, when valid.
- **Tests and required CI commands:** `uv run --locked --extra coworker pytest -q tests/test_main_protection_audit.py tests/test_day1_ruleset_drift.py tests/test_reconcile_main_ruleset.py`; exact final PR head `test-and-build`, `coworker`, frontend, browser, PostgreSQL-18 compatibility, ancestry, `ci-merge-gate`. PR-event `governance-audit` is normally SKIPPED and must never be reported GREEN.
- **Secrets / owner / grant / approval / egress boundaries:** This read-only code path neither reads staging secrets nor writes rulesets, App installations, private sources or user data. Privileged GitHub App credentials belong to approved Owner C/repo-admin environment; no secret values in PR or log.
- **Budget / timeout / cancellation / revocation behavior:** Existing CI and GitHub audit network readback limits unchanged; no paid runtime, additional provider call or request volume. No new timers, retries or external mutation.
- **Default-off gate and rollback:** Read-only enforcement audit only. Pilot default-off and the live ruleset unchanged; rollback requires a reviewed code reversion, not an unreviewed policy change.
- **External prerequisites:** Administrator-backed native denied/permitted merge evidence for ruleset `27324410`; reviewed staging restore and exact worker/API/schema identity; independent 40-case holdout custody; separate Founder+C pilot authorization.
- **Out of scope:** Staging or production rollout; merging without independent review; `shuddho-staging` schema migration `0070`→`0072_merge_0071_heads`; paid Render worker, Vercel deploy, PostHog collection, ProductOS unrelated workspace, unrelated application changes.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Source fix committed | [draft PR #838](https://github.com/rumman52/Shuddho/pull/838) |
| Repository-verified | Final-head CI pending | [PR #838 Checks](https://github.com/rumman52/Shuddho/pull/838/checks) |
| Staging-verified | Not attempted / BLOCKED_EXTERNAL | No native merge-control or actual staging restore receipts |
| Production-qualified | **NO-GO** | No independent holdout, operational controls or release authorization |
| Activated | **NO** | No infrastructure, pilot, telemetry or code merge mutation |

- **Test pass/fail/skip counts:** RED **8/2858/103**, 6 warnings; GREEN must be read back from final-head CI.
- **Exact-head CI links:** RED [#44790402009](https://github.com/rumman52/Shuddho/actions/runs/44790402009); GREEN check [PR #838](https://github.com/rumman52/Shuddho/pull/838/checks) for current head, not a superseded run.
- **Review findings and resolution:** The prior auditor checked each mandatory status in isolation, allowing a second identically trusted context or unrelated malformed row to pass. Validate each row once, check unique set and pinned publisher before the three mandatory contexts.
- **Residual risks:** A source audit only proves inspected JSON passed a minimum predicate; actual GitHub ruleset enforcement, installation permission and human review require native, separately operated receipts.
- **Next exact action:** Verify all required final-head CI results; obtain independent human review; Owner C/admin must perform readback and native denied/permitted merge experiments with genuine credentials, then stage recovery qualification separately.
