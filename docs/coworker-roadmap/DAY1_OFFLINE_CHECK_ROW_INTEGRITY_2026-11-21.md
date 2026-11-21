# Day 1 — Offline main-ruleset status-row integrity

- **Objective and user-visible behavior:** Offline Day 1 report must show `blocked_configuration` and public drift code `checks.unambiguous_first_party_rows` for malformed, duplicated, unauthenticated or unexpected native required-check rows. A compliant snapshot remains only `configuration_candidate`, never native merge proof.
- **Dependency tasks and current evidence:** [10-day completion plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) ¶141–152; [Day 1 #727](https://github.com/rumman52/Shuddho/issues/727), [board #737](https://github.com/rumman52/Shuddho/issues/737), merged [PR #838](https://github.com/rumman52/Shuddho/pull/838), reviewed `infra/github/main-ruleset.json`. The main CI candidate auditor rejects malformed/untrusted native status rows, while the offline drift analyzer previously ignored extra untrusted/duplicate rows.
- **Base branch/SHA:** `main` `1dc6422a51e0309c48ca8c26298e3dd4443842a7`.
- **Work branch/PR:** `fix/day1-offline-check-row-integrity-20261121`, [draft PR #846](https://github.com/rumman52/Shuddho/pull/846).
- **Existing interfaces to reuse:** `scripts.day1_ruleset_drift.analyze(branch, live_ruleset, policy, *, expected_main_sha, expected_ruleset_id=27324410) -> dict`; `validate_reviewed_policy(policy) -> dict`; `EvidenceError`. No public API/schema change.
- **Exact files to create/modify:** `scripts/day1_ruleset_drift.py`, `tests/test_day1_ruleset_drift.py`, this contract, `docs/coworker-roadmap/PROGRESS.md`, [implementation plan](../superpowers/plans/2026-11-21-day1-offline-native-status-row-integrity.md).
- **New interface signatures/schema and compatibility:** Private `_live_status_rows_are_unambiguous(params: dict) -> bool` checks each current live status row's exact `{"context","integration_id"}` keys, unique nonblank string context, exact integer GitHub Actions publisher `15368`. Adds one public drift code but preserves other codes and all report keys. Rejects unknown keys in the reviewed policy before comparison. Unique additional first-party live check is a **minimum-policy candidate**, not an authorized native ruleset update.
- **Acceptance scenarios/assertions:** 11 parametrized bad extra rows (duplicate trusted extra, wrong/missing/null/bool/string app, blank/empty name, unknown key, null/string row), one mandatory row with unknown metadata, one edited reviewed policy with unknown key, and one compliant extra first-party status. Existing valid and missing mandatory status fixtures remain unchanged.
- **Reproduction/initial failure:** [test-only SHA `017a958d7ad494b160cff0bb9ce8f4593e391ccb`](https://github.com/rumman52/Shuddho/commit/017a958d7ad494b160cff0bb9ce8f4593e391ccb); [GitHub Actions #44886807268](https://github.com/rumman52/Shuddho/actions/runs/44886807268) `test-and-build` **13 expected FAIL / 2930 PASS / 105 SKIP / 6 WARN**. Eleven cases improperly returned `configuration_candidate`; the unknown mandatory key produced no drift; the policy unexpectedly did not raise `EvidenceError`. No test collection/environment errors were used as a RED substitute.
- **Expected failure outcomes:** No false candidate on malformed or untrusted native status row regardless of whether reviewed minimum contexts are present. The script still cannot prove native permission enforcement.
- **Tests and required CI commands:** `uv run --locked --extra coworker pytest -q tests/test_day1_ruleset_drift.py tests/test_main_protection_audit.py tests/test_reconcile_main_ruleset.py`; full exact-head GitHub CI `test-and-build`, frontend, browser, PostgreSQL-18, coworker, `ci-merge-gate` (and governance-audit SKIPPED on PR should be reported SKIPPED).
- **Secrets/owner/grant/approval/egress boundaries:** No credentials, private data or models. Offline read-only files. Admin/C owns native ruleset `27324410` and protected audit App, independently verifies denied/allowed merges. No human review is asserted without GitHub evidence.
- **Budget/timeout/cancellation/revocation behavior:** Unchanged. No new network, cloud call, timed job, spend or retries. Diagnostic remains bounded by existing `MAX_READ_BYTES=512000` and immutable/new output file semantics.
- **Default-off gate and rollback:** Pilot and all telemetry remain off. Rollback means a reviewed source revert, never policy weakening. Native GitHub ruleset unchanged.
- **External prerequisites:** C/repo admin must bind App credentials and prove native denied/allowed merge enforcement; C/Founder must approve reviewed staging recovery/worker/API/schema parity; D must independently custody blinded holdout; Founder+C must approve release separately.
- **Out of scope:** Runtime migrations, service provision, deployment, PR merging, native rule mutation, paid inference, evaluation holdout access, telemetry activation.

## Completion evidence

| Level | Status | Exact revision/evidence |
| --- | --- | --- |
| Implemented | Fix and regressions committed | [PR #846](https://github.com/rumman52/Shuddho/pull/846), source correction `40cc5bb5cddb5f2c89cab7d27b267bb072800950` |
| Repository-verified | **Pending exact final-head CI** | [PR #846 checks](https://github.com/rumman52/Shuddho/pull/846/checks) |
| Staging-verified | **BLOCKED_EXTERNAL** | No authorized native negative/positive merge or DB restore receipts |
| Production-qualified | **NO-GO** | No release-bound scores, operated recovery, independent D custody or release authorization |
| Activated | **No** | No native ruleset, staging, production, telemetry or pilot mutations |

- **RED pass/fail/skip counts:** 2930 pass / 13 expected fail / 105 skipped / 6 warnings. GREEN counts await final-head run.
- **Exact-head CI links:** [RED #44886807268](https://github.com/rumman52/Shuddho/actions/runs/44886807268); [current PR checks](https://github.com/rumman52/Shuddho/pull/846/checks).
- **Review findings and resolution:** Former per-mandatory-context comparison accepted untrusted extras; now validates all rows and reports one stable drift code. No extra first-party check is silently removed by this read-only script.
- **Residual risks:** GitHub merged PR #838 despite zero submitted human GitHub reviews and a failed `ci-merge-gate` run. Native protection unproven. Supabase hosted schema remains `0070` vs source `0072_merge_0071_heads`; no authorized recovery or worker parity.
- **Next exact action:** Run/read exact final-head full CI, obtain independent current-head human code review, then C/admin must prove live native denied and permitted merge controls with protected App credentials; do not infer Day 1 completion from a configuration candidate.
