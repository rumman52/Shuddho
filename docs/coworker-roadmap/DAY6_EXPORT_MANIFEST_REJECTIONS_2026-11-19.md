# Day 6 native export manifest rejection — task contract

- **Objective and user-visible behavior:** A Day 6 report/email task must never publish malformed native files, and must never complete if its persisted export manifest is missing, duplicated or contains an unexpected artifact.
- **Dependency tasks and current evidence:** Day 6 issue [#732](https://github.com/rumman52/Shuddho/issues/732); Day 1 baseline [#727](https://github.com/rumman52/Shuddho/issues/727); the native rendering/recovery fixture repair in [#774](https://github.com/rumman52/Shuddho/pull/774) is already merged. Preserve the current DocumentRunner and validate_day6_exports contracts.
- **Base branch/SHA:** main at 8afcfccf409c5a01fd70a7966fb4b538575f502f.
- **Work branch/PR:** codex/day1-native-export-rejection-gate-20261119 / [draft PR #802](https://github.com/rumman52/Shuddho/pull/802).
- **Existing interfaces to reuse:** DocumentRunner.phase, DocumentRunner.export, DocumentRunner.complete, validate_day6_exports, the persisted Step checkpoint, owner-scoped get_task, and private storage.inventory.
- **Exact files to create/modify:** tests/test_export_manifest_rejections.py, .github/workflows/ci.yml, docs/superpowers/plans/2026-11-19-native-export-rejection-regressions.md, this task contract, and docs/coworker-roadmap/PROGRESS.md.
- **New interface signatures / schema and compatibility:** None. No API, database schema, migration, provider or runtime identity changes.
- **Acceptance scenarios:**
  1. Valid native renderer output with missing, duplicate or unexpected file inventory is rejected during export before any object PUT/checkpoint.
  2. Correct MIME with unreadable DOCX or PDF bytes is rejected during export before publication.
  3. After a valid native export, persisted manifest corruption (missing, duplicate or unexpected entry) prevents completion; task remains running and has zero published Artifact records.
  4. The focused regression module is collected and run in mandatory CI with zero skips.
  5. The four Day 1 #664 baseline regressions remain mandatory and skip-free.
- **Reproduction / initial failure:** PR #802's first RED run [#44580859860](https://github.com/rumman52/Shuddho/actions/runs/44580859860) ran at 0a1465e2c86550b028f8b49b2c8ff80deed8ef04 and failed all three existing cases before their completion assertion. The test fixture used placeholder native bytes, so DocumentRunner.export correctly rejected the files first.
- **Expected failure outcomes:** Early invalid output raises export_invalid before storage/checkpoint publication. Persisted-manifest corruption raises export_invalid at completion and leaves the task nonterminal with no published artifacts.
- **Tests and required CI commands:**
  - uv run --locked --extra coworker pytest -q tests/test_export_manifest_rejections.py -k missing_duplicate_or_unexpected
  - uv run --locked --extra coworker pytest -q tests/test_export_manifest_rejections.py tests/test_coworker_office.py tests/test_coworker_research.py tests/test_coworker_services.py
  The PR's required Coworker job also runs the four #664 baseline cases and mandatory-module/no-skip gates.
- **Secrets / owner / grant / approval / egress boundaries:** No secrets or provider access are needed. No network calls, email sends, external actions or permission changes.
- **Budget / timeout / cancellation / revocation behavior:** No budget or runtime policy changes. Tests use isolated local fixtures.
- **Default-off gate and rollback:** No capability flag changes. Revert the test/CI/documentation commit if the regression gate itself is invalid; do not change production validators to make an invalid fixture pass.
- **External prerequisites:** Independent human review for merge; repository administrator must separately repair the existing governance App/ruleset controls. Render workspace confirmation and staging prerequisites are not needed for this source-only task.
- **Out of scope:** Live bilingual workflows, provider-side send audit, owner retrieval/cross-owner denial, deployed worker restart, 40-case holdout, 20 operated recovery receipts, staging migration, release decision and pilot admission.

## Completion evidence

| Level | Status | Exact revision / evidence |
| --- | --- | --- |
| Implemented | Pending CI | Test/CI/doc changes on PR #802 |
| Repository-verified | Pending | Exact-head CI must finish |
| Staging-verified | Not established | Requires authorized paired staging API/worker/schema |
| Production-qualified | No | Day 9/10 release gates remain blocked |
| Activated | No | No pilot admission |

- **Test pass/fail/skip counts:** Initial RED: three failures on the pre-correction tests; corrected exact-head counts pending.
- **Exact-head CI links:** [PR #802 checks](https://github.com/rumman52/Shuddho/pull/802/checks).
- **Review findings and resolution:** Independent human review pending.
- **Residual risks:** Full Day 6 product acceptance and all Day 9/10 qualification gates remain unverified.
- **Next exact action:** Complete the corrected exact-head Coworker CI, then obtain a fresh independent review. Do not merge while native governance/review controls are unmet.
