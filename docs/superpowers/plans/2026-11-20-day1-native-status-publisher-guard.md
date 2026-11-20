# Day 1 Native Status-Check Publisher Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refuse to silently overwrite an unreviewed GitHub status-check publisher while reconciling the existing main-branch ruleset.

**Architecture:** The existing administrator-only dry-run reconciler validates the read-back ruleset before deciding whether it is already configured or can safely be repaired. Extend `_require_unambiguous_existing_checks(existing, reviewed)` to compare any explicitly present publisher integration ID for each recognized context against the reviewed policy. Preserve the previously tested null/unset publisher remediation; do not change the policy template or live ruleset.

**Tech Stack:** Python 3.11, pytest, GitHub Actions.

**Spec:** [Ruke AI 10-Day Completion Plan, Day 1](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit), paragraphs 141–152; GitHub #727 (D01.T04/G02), #737, and `docs/coworker-roadmap/TASK_TEMPLATE.md`.

## Global Constraints

- Reviewed native ruleset is `27324410`, name `Shuddho main review and CI`.
- `test-and-build`, `coworker` and `ci-merge-gate` must be pinned to the approved GitHub Actions integration ID `15368`.
- Independently required review, stale-review dismissal, last-push approval, resolved threads, no bypass, branch-SHA and reviewed-fingerprint checks remain unchanged.
- Dry-run stays read-only by default. A live `PUT` requires explicit administrator confirmation; no deploy, migration, spending, stored credential, or release unlock.

## Review Focus

1. Existing known context + unknown numeric publisher (`98765`): **manual reconciliation**, no proposed update.
2. Existing known context + type-confused publisher (`"15368"`, `15368.0`, `true`, `0`): **manual reconciliation**, never silently coerce or replace.
3. Existing known context + missing or null integration: **allowed to tighten** to reviewed `15368` in dry-run.
4. Existing known context + correct integer `15368`: **allowed to preserve** existing contract.
5. Duplicate existing context, extra fields, unrelated native checks: remain **fail closed** as proven by PR #823.

---

### Task 1: Reject unreviewed existing publisher identity

**Files:**
- Modify: `tests/test_reconcile_main_ruleset.py`
- Modify: `scripts/reconcile_main_ruleset.py`

**Interfaces:**
- Consumes: `_require_unambiguous_existing_checks(existing: dict, reviewed: dict) -> None`.
- Produces: `ApplyMainRulesetError` on unreviewed publisher; unchanged `reconcile_main_ruleset(...)` public interface.

- [x] **Step 1: Write failing regressions** for numeric mismatch, missing/null, and type-confused IDs. Assert fail before any `PUT`, and retain allowed null/missing and pinned publisher paths.
- [x] **Step 2: Verify RED** on exact test-only SHA `cf2e4eec040f606eb824ffd7d357d13737697291`, [CI #44778941841](https://github.com/rumman52/Shuddho/actions/runs/44778941841): 5 new missing-exception FAIL, 2726 PASS, 102 SKIP, 6 WARN in test-and-build.
- [x] **Step 3: Implement the minimal guard.** Build context→reviewed integration lookup from already-validated policy, reject any explicit non-null unexpected publisher with type-strict comparison.
- [ ] **Step 4: Verify GREEN** using `uv run --locked --extra coworker pytest -q tests/test_reconcile_main_ruleset.py tests/test_day1_ruleset_drift.py` and required exact-head CI. Record incomplete/failed/skipped results without disguising them.
- [x] **Step 5: Commit, review patch, and create a draft PR** with RED/GREEN evidence and independent-review blocker.

### Task 2: Document the exact source-only handoff

**Files:**
- Create: `docs/coworker-roadmap/DAY1_NATIVE_STATUS_PUBLISHER_GUARD_2026-11-20.md`
- Modify: `docs/coworker-roadmap/PROGRESS.md`

- [x] **Step 1: Record the task template**, old and final SHA, test evidence, no-write scope, external administrator/reviewer/staging limitations.
- [ ] **Step 2: Confirm the final PR head, required CI, and draft status** before any acceptance claim.

**Release state:** SOURCE_ONLY / NO-GO until administrator-controlled native negative/positive merge tests, independently approved current-head PR, actual staging restore and identity pairing, independent D holdout custody, and distinct Founder/Owner C release authorization.
