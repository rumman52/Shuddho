# Day 1 ambiguous native status-check reconciliation — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement and verify this bounded plan. Check each step against the exact branch revision.

**Goal:** Prevent the administrator-only Day 1 ruleset reconciler from silently replacing ambiguous existing required-status-check entries when producing a reviewed policy update.

**Architecture:** Keep the existing non-mutating dry-run, branch-SHA/fingerprint compare-and-swap, exactly one pre-authorized ruleset ID, first-party mandatory contexts and manual apply confirmations. Harden only `_safe_target`'s inspection of the **existing** native check rows; leave missing or unscoped known check contexts repairable. Do not change `infra/github/main-ruleset.json` or any live GitHub ruleset.

**Tech stack:** Python 3.11, pytest, GitHub Actions.

**Spec:** `01_Rukh_AI_Foundation(1).docx` Part 01 Day 1 (pages 3–5), issues #727 and #737, repository instructions `AGENTS.md` and `.agents/skills/shuddho-engineering/SKILL.md`.

## Boundaries and review focus

- Reject duplicate existing check contexts, even when both use the pinned GitHub Actions integration, in **both** the 'already configured' and proposed-update paths.
- Reject fields other than `context` and `integration_id` in existing check rows; these may represent native controls the reconciler does not understand.
- Preserve existing unknown additional contexts as manual reconciliation, not automatic deletion.
- Allow a known context with a missing/null integration ID to be tightened to the approved provider in a dry run.
- Preserve read-only behavior by default and reject an ambiguous state before any native PUT.
- Retain protection, approval count, strict first-party checks, no-bypass policy and explicit administrator confirmation. Do not claim operated merge enforcement.

## Execution / evidence

- [x] **RED:** On exact base `d88e606615195b88a876317ebb5a8ef79852da41`, branch `fix/day1-ruleset-status-check-ambiguity-20261120`, add two parametrized negative cases and one positive case in `tests/test_reconcile_main_ruleset.py`.
- [x] **Reproduce:** [PR #823 test-only run #44774534026](https://github.com/rumman52/Shuddho/actions/runs/44774534026) failed exactly the two new safety cases: 2 failed, 2665 passed, 102 skipped, 6 warnings; existing `_safe_target` did not raise.
- [x] **Fix:** `scripts/reconcile_main_ruleset.py` shares `_require_unambiguous_existing_checks` between ordinary reconciliation and the early 'already configured' readback. Ambiguous native rules cannot be treated as configured or silently replaced. The unscoped known status-check positive case stays supported. Code commits: `81790ce1dace118408336070522dab3a556dda2c`, `91bc6653280c63eb281b5c3dadb47c814e5b1b84`.
- [x] **Short-circuit regression:** test commit `29afffb9650c0bd497a96dc87ffc4ef3d03e4e06` adds duplicate and unknown-row cases for an otherwise compliant ruleset; these must raise before returning `already_configured`.
- [ ] **GREEN:** Verify focused `tests/test_reconcile_main_ruleset.py` and `tests/test_day1_ruleset_drift.py` on the final PR head, then collect required application, Coworker, frontend, browser and PostgreSQL 18 CI outcomes.
- [ ] **Review:** An independent human submits a current-head approval; C/admin verifies the effective native ruleset `27324410`, actual platform negative/positive controls and audit App identity.

## Blockers / release handoff

**SOURCE_ONLY / pilot NO-GO.** The repository administrator must configure the private scoped App identity in both protected GitHub environments and reconcile the live ruleset under the existing runbook; this PR is neither an authorization nor a live ruleset mutation. C must approve the isolated staging restore, schema and runtime identity; D must prove independent holdout custody; Founder and C must separately approve any eventual exact release. No deployment, paid infrastructure, telemetry, schema migration, credentials, user data or new provider activity is part of this patch.

**Resume commands:** from repository root, after an authorized administrator has configured the protected audit identity and captured the exact current main revision:

```bash
git fetch origin
REVIEWED_SHA=$(git rev-parse origin/main)
uv run --locked --extra coworker pytest -q tests/test_reconcile_main_ruleset.py tests/test_day1_ruleset_drift.py
uv run --locked --extra coworker python scripts/reconcile_main_ruleset.py \
  --repository rumman52/Shuddho --expected-main-sha "$REVIEWED_SHA"
```

A dry-run needs an appropriate administrator `GITHUB_TOKEN` in the operator's protected environment. Do not invoke `--apply` without verified policy fingerprint, exact ID, repository, current source SHA and the administrator's explicit confirmation. The dry-run does not qualify Day 1.
