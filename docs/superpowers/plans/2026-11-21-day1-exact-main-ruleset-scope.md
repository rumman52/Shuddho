# Day 1 exact main-branch ruleset scope — implementation plan

> Superpowers: execute this task test-first. Changes remain source-only; no administrator mutation or release decision.

**Goal:** Align offline and privileged live V-01 governance candidate checks with the existing administrator reconciliation requirement that the inspected repository-owned ruleset scope exactly targets `main`, not extra branches or ambiguous selector fields.

**Source authority:** [Ruke AI Ten-Day Completion Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 paragraphs 141–152, [Day 1 issue #727](https://github.com/rumman52/Shuddho/issues/727), [CTO board #737](https://github.com/rumman52/Shuddho/issues/737), `infra/github/main-ruleset.json`, `scripts/reconcile_main_ruleset.py::_read_unique_existing`.

**Exact base:** `main` `112e85fbe53e7ad983444414c2d6cb410b93ad96`. **Branch:** `fix/day1-exact-main-ruleset-scope-20261121`.

## Existing discrepancy and safe design

- `scripts/day1_ruleset_drift.py::analyze` currently accepts any `conditions.ref_name.include` array containing `~DEFAULT_BRANCH` or `refs/heads/main`, plus unknown selectors or duplicate values. `validate_reviewed_policy` accepts extra conditions properties. Thus a broader/unreviewed scope can become `configuration_candidate`.
- `scripts/main_protection_audit.py::_targets_main` also accepts mixed include sets. This helper is reused by the creation-policy validator `scripts/apply_main_ruleset.py` and MUST remain unchanged: it expresses possible targeting, not exact readback ownership.
- The operator `scripts/reconcile_main_ruleset.py::_read_unique_existing` already requires `set(conditions)=={"ref_name"}`, `include` exactly `["refs/heads/main"]` or `["~DEFAULT_BRANCH"]`, and `exclude==[]`. Make the offline/live audit consistent without narrowing the existing conservative discovery semantics.

**Ruling:** In both audits, require `conditions` to be precisely `{"ref_name": {"include": [exact selector], "exclude": []}}`; reject unexpected keys in either nested object. Accept the default branch alias or literal main as exact single-entry arrays. An extra branch, duplicate selector, broad `~ALL` or extra condition key is not sufficient V-01 evidence. The rule still remains `qualified=false` without native operated controls.

## Task 1 — RED

**Files:** `tests/test_day1_ruleset_drift.py`, `tests/test_main_protection_audit.py`

- [x] Add offline negative cases for an extra branch selector, mixed `~DEFAULT_BRANCH`/literal, duplicate selector, unreviewed glob, unknown conditions or ref_name properties; test both reviewed policy tampering and live readback. Preserve positive candidate for each sole exact selector.
- [x] Add live native-audit negative cases for identical invalid scopes, plus redacted-bypass diagnostic: malformed/broader rule must not claim redaction is the *only* missing evidence. Preserve good exact main and alias candidates.
- [x] Push test-only commit and inspect real GitHub Actions RED logs; expected target failures should be incorrect `configuration_candidate` or missed `EvidenceError`, not environment/collection faults.

## Task 2 — minimal GREEN

**Files:** `scripts/day1_ruleset_drift.py`, `scripts/main_protection_audit.py`

- [x] Tighten `validate_reviewed_policy` to reject extra selector keys; add exact readback predicate to existing `ruleset.main_scope` drift code while leaving `ruleset.no_exclusions` unchanged.
- [x] Add private helper `_exact_main_scope` in live auditor, enforced **only in `audit_governance` candidate and redacted-bypass diagnostic**; preserve `_targets_main` and `_active_main_ruleset` for creation-template and conservative overlap use.
- [ ] Run full GitHub Actions at final PR head; separately inspect `test-and-build`, Coworker, PostgreSQL-18, frontend, browser, ancestry, `ci-merge-gate` and PR-skipped `governance-audit`. Run `uv run --extra coworker pytest tests/test_day1_ruleset_drift.py tests/test_main_protection_audit.py tests/test_apply_main_ruleset.py tests/test_reconcile_main_ruleset.py -q -rs` locally if an authorized checkout exists. Never claim unrun local commands.

## Task 3 — handoff

**Files:** `docs/coworker-roadmap/DAY1_EXACT_MAIN_RULESET_SCOPE_2026-11-21.md`, `docs/coworker-roadmap/PROGRESS.md`, this plan.

- [x] Record exact RED/GREEN SHAs, CI links, scope, reviewer and external blockers in task contract and progress.
- [x] Open draft PR to `main` (never merge without independent human review); link to GitHub #727 and Linear MD-5.
- [x] Preserve source-only / NO-GO: no privileged App provisioning, native ruleset PUT, production promotion, paid Render worker, Supabase migration/restore without approval, PostHog user telemetry, private D custody, or exact-release Founder/Owner-C GO.

**Verification standard:** Passing unit tests and a draft PR are *repository evidence* only; they do not demonstrate protected-main negative+positive merge controls, independent reviewer, recoverable staging, held-out evaluation, or pilot qualification.

### Test-first checkpoint — 21 November 2026 (Asia/Dhaka)

- **Test-only RED head:** `68c6ea6112d5fce3d42d2c1435e2326adbe828c7`; [run #44914417577](https://github.com/rumman52/Shuddho/actions/runs/44914417577) `test-and-build` **19 expected FAILED / 3,214 PASSED / 105 SKIPPED / 6 WARNINGS**. All targeted failures were scope acceptance / wrong error routing, not infrastructure or test collection.
- **Source corrections:** offline `d700b88691fef714cbf71ba4a9ee58b7207357a7`, live `2953f1c407c870f1f2cbb3cefdeb77ca5be2b13f`.
- **Task contract:** [DAY1_EXACT_MAIN_RULESET_SCOPE_2026-11-21.md](../../coworker-roadmap/DAY1_EXACT_MAIN_RULESET_SCOPE_2026-11-21.md); [draft PR #861](https://github.com/rumman52/Shuddho/pull/861). Exact final-head CI and independent human review remain separate checks.
- **Ruling:** Keep the conservative candidate/overlap discovery helper unchanged; only the live native evidence decision becomes exact-scope. This prevents breaking `apply_main_ruleset._validate_candidate` while making V-01 audit consistent with `reconcile_main_ruleset._read_unique_existing`.
