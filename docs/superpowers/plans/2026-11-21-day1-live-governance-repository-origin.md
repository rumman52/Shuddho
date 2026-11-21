# Day 1 Live Governance Ruleset Repository-Origin Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Checkboxes are execution instructions, not claims of prior completion.

**Goal:** Close a false-positive in `scripts/main_protection_audit.py`: the privileged read-only V-01 auditor must not accept an inherited organization ruleset, a ruleset from a different repository, or missing ownership metadata as proof of a repository-owned `main` governance candidate.

**Architecture:** Retain existing `inspect_repository(repository, token, *, ruleset_token)` public entry, branch and check validation, and no-redirect token handling. Pass the exact validated `repository` into `audit_governance` as a keyword-only `repository` argument with existing default `rumman52/Shuddho` for direct caller compatibility. Require `source_type="Repository"` and `source == repository` before any ruleset is eligible or classed as lacking only `bypass_actors`. Do not demand an exact ruleset ID here: this read-only audit checks V-01 minimum enforcement, whereas `scripts/reconcile_main_ruleset.py` demands the specific approved existing ID `27324410` and full operator signoff. Keep candidate status nonqualifying.

**Spec:** [Ruke AI Ten-Day Completion Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit), Day 1 paragraphs 141–152; [Day 1 issue #727](https://github.com/rumman52/Shuddho/issues/727); checked-in `AGENTS.md`, `docs/coworker-roadmap/SPEC.md` and admin reconciliation. Parallel [draft #850](https://github.com/rumman52/Shuddho/pull/850) protects the separate *offline* `day1_ruleset_drift.py`; do not modify that file in this PR.

**Tech stack:** Python, pytest, GitHub Actions.

## Worktree and approval boundaries

- Base `main` at `d92e2ecd6f5c899e9acdc079b9f620870d613dfc`; isolated GitHub branch `fix/day1-live-governance-repository-origin-20261121`. No local checkout, GitHub App private key, admin permission or native ruleset write.
- **NO-GO** remains for Day 1 release acceptance and the pilot: actual denied/unreviewed and permitted/independently-reviewed merges, staging backup/restore and runtime pairing, D's independent held-out 40, approved spending, Founder and C signoff.
- Do not relax PR review gates, alter workflow secrets, disable safety checks, deploy paid workers or declare that a passing read-only check proves enforcement.

### Task 1 — RED: prove foreign/inherited native readback accepted

**Files:** `tests/test_main_protection_audit.py`.

- [x] Extend `approved_ruleset()` fixture with explicit `source_type="Repository"`, `source="rumman52/Shuddho"` and keep ID `123` to preserve minimum-policy behavior.
- [x] Add parameterized cases for foreign repository, case mismatch, Organization/Enterprise source type, null/blank/missing ownership: these must raise `GovernanceAuditError` instead of returning candidate ID.
- [x] Test the full `inspect_repository` path binds expected repository passed to GitHub REST, including positive `owner/repo` (with matching source) and foreign `other/repo` negative.
- [x] Push test-only commit and inspect actual RED GitHub Actions failure log. Do not proceed based only on expected failing assumptions.

### Task 2 — GREEN: minimal provenance guard

**Files:** `scripts/main_protection_audit.py`.

- [x] Use a small `_is_repository_owned_ruleset` or equivalent predicate, checking exact `source` and `source_type`, in `audit_governance`, leaving the one-argument `_active_main_ruleset(rule)` creation-template helper intact.
- [x] Pass the validated requested repository from `inspect_repository` into `audit_governance` (keyword-only optional, default unchanged).
- [x] Keep redacted-bypass explanation constrained to matching repository-owned candidates, so an inherited/foreign rule cannot produce misleading privileged-audit credential guidance.
- [ ] Run `uv run --locked --extra coworker pytest -q tests/test_main_protection_audit.py tests/test_day1_ruleset_drift.py tests/test_reconcile_main_ruleset.py` or equivalent actual GitHub Actions suite; capture pass/fail/skip counts.

### Task 3 — evidence, review and PR

**Files:** `docs/coworker-roadmap/DAY1_LIVE_RULESET_ORIGIN_2026-11-21.md`, `docs/coworker-roadmap/PROGRESS.md`, this plan.

- [x] Record task contract, test-only RED SHA/run, code GREEN SHA/run, actual check statuses and external blockers.
- [x] Create one **draft** PR against `main`. Distinct independent human reviewer required; draft PR's `ci-merge-gate` failure for missing review does not authorize bypass.
- [x] Update GitHub #727 and Linear MD-5 with exact evidence and continued SOURCE_ONLY / NO-GO status.
- [ ] Inspect exact PR HEAD workflow, including separately mandatory source, Coworker, frontend, browser, PostgreSQL18, ancestry; governance-audit PR skip is not a pass.

### Verification checkpoint, 21 November 2026

- RED test-only head `d5032953d2bcdeb5eb84a99ea8eb52876076aba6`; [Actions #44910176240](https://github.com/rumman52/Shuddho/actions/runs/44910176240) source/build **13 expected FAIL, 3,087 PASS, 105 SKIP, 6 WARN**. Targeted failures establish missing ruleset origin checks; full RED is not a release pass.
- Source correction `63ff12ce1182d31910025c56ccf88156a5910889`; positive full-readback fixtures `7f5a6a909482f24d26ad75cd8cd6745c2eb8c92b`. Source/readback contract and PROGRESS.md checkpoint are committed on [draft PR #853](https://github.com/rumman52/Shuddho/pull/853).
- Exact final-head GREEN, independent review and native administrator controls **pending**. PR-triggered governance audit is skipped, not privileged proof. A draft independent-review merge gate is expected to fail until an authorized reviewer submits a valid current-head approval; do not bypass.
- **Ruling:** inherited organization restrictions may contribute to effective protection, but cannot prove the specific repository-owned V-01 rule demanded by the Day 1 admin contract; reject them without changing the native config.

### Cross-module compatibility ruling / intermediate GREEN failure

- Intermediate source run [#44910418521](https://github.com/rumman52/Shuddho/actions/runs/44910418521) **FAILED**: 46 tests failed, 3,054 passed, 105 skipped, 6 warnings. Actual failures traced to `scripts/apply_main_ruleset.py` importing `_active_main_ruleset(rule)` with one argument. The first implementation required a second repository argument, which broke pre-creation policy validation because server-assigned `source` and `source_type` do not exist on reviewed creation templates.
- **Ruling:** preserve the old one-argument helper and separate `_repository_owned_ruleset` for the native readback in `audit_governance`. Corrected commit `96f4e9a9da342464c98a5196dcc4fac0caaf892a`; protective regression `6b09fc8ab0e8deade902dd49513b872fe693731b` asserts the creation template remains valid before GitHub assigns origin. No native ruleset change.
- This was a real intermediate failed GREEN run. It is not concealed or relabeled passed. Final-head CI must be checked anew after all documentation commits.


## Current main ancestry update

Originally developed and TDD-tested on main `d92e2ecd6f5c899e9acdc079b9f620870d613dfc`. After separately reviewed PRs #850, #851 and #852 merged, this branch was faithfully transplanted onto current main `7b8b47c5edfd6d152eebbd3345a1bd8c84b9f7a7`. Source and test files had no main-side overlap; PROGRESS.md preserves the newer main history below this PR's one top entry. All prior test-only RED and intermediate failed-GREEN SHAs remain cited as historical evidence. **This ancestry update requires fresh exact-final-head CI**, not reuse of previous runs.

### GitHub detail fixture after main merge

- Exact rebased head `9819cb88508da3f97dc2368e3ee61e892ba41dc7` [Actions #44911260802](https://github.com/rumman52/Shuddho/actions/runs/44911260802) **FAILED** main source/build: 3 / 3,198 passed / 105 skipped / 6 warnings. Remaining positive mocks in `tests/test_apply_main_ruleset.py::detail()` omitted native GET-assigned `source`/`source_type`, so the code correctly rejected them. No production check should be relaxed to accept missing provenance.
- Fix **test fixture only** in `c2115f408facf9891728e6c4dd4dfe16621c0e76`: the candidate POST template remains without source fields, while the simulated native detail returned by GET now includes `source="rumman52/Shuddho"`, `source_type="Repository"`. Preserve negative unknown-response, bypass and anti-duplicate mutation tests. Final head CI pending after docs checkpoint.
