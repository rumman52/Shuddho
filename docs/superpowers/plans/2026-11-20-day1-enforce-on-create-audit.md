# Day 1 Governance Audit Enforce-on-Create Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the read-only native main-branch governance audit reject required status checks that GitHub is configured not to enforce on newly created refs.

**Architecture:** Align the existing `scripts.main_protection_audit._has_required_rules` status-check acceptance predicate with the already-reviewed `infra/github/main-ruleset.json` and `scripts.day1_ruleset_drift.analyze`. Keep the audit a read-only defense-in-depth gate, preserve the existing administrator-only reconciliation tool, and avoid any live GitHub rule mutation.

**Tech Stack:** Python 3.11, pytest, GitHub Actions.

**Spec:** [Ruke AI Ten Day Completion Implementation Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 ¶141–152; [Day 1 issue #727](https://github.com/rumman52/Shuddho/issues/727), [CTO board #737](https://github.com/rumman52/Shuddho/issues/737); checked-in `infra/github/main-ruleset.json`.

## Global Constraints

- Protect `main` by exactly the reviewed native ruleset `27324410`, with zero bypass actors.
- Keep the required first-party contexts `test-and-build`, `coworker`, and `ci-merge-gate`, each pinned to GitHub Actions integration ID `15368`.
- Existing review minimum: 1 approving reviewer, stale approval dismissal, last-push approval, and resolved threads; strict required checks and `do_not_enforce_on_create=false`.
- No source test may imply verified native merge enforcement. Real positive/negative merge-control receipts, privileged audit identity, independent current-head review, and staging recovery remain external prerequisites.
- No deployment, billing, paid infrastructure, ruleset PUT, migration, credentials, privacy-sensitive events, or production/pilot release.

## Review Focus

1. Existing status-check configuration with `do_not_enforce_on_create=true` must NOT pass `audit_governance`.
2. Existing status-check configuration with no `do_not_enforce_on_create` field must NOT pass (missing is not equivalent to explicitly enforced).
3. Explicit null, numeric zero or textual `"false"` must NOT pass (type-safe comparison).
4. The exact bool `false` remains accepted with approved checks and reviews.
5. Untrusted check publisher, missing context or bypass actor must still reject as before.

---

### Task 1: Regression evidence, RED → GREEN

**Files:**
- Modify: `tests/test_main_protection_audit.py`
- Modify: `scripts/main_protection_audit.py`

**Interfaces:**
- Consumes: `audit_governance(branch: dict, rulesets: list[dict]) -> int`, `_has_required_rules(rule: dict) -> bool`.
- Produces: No new API; stricter acceptance predicate for the existing read-only audit.

- [ ] **Step 1: Add failing tests** for all four weakened/ambiguous `do_not_enforce_on_create` forms, plus an exact-false approved fixture.
- [ ] **Step 2: Verify RED**: execute the tests before code change, confirming failures specifically because `audit_governance` does not raise for these mutations; record exact commit and test log.
- [ ] **Step 3: Implement minimal code** to accept only `p.get("do_not_enforce_on_create") is False` in `valid_checks`.
- [ ] **Step 4: Verify GREEN** using `uv run --locked pytest -q tests/test_main_protection_audit.py tests/test_day1_ruleset_drift.py tests/test_reconcile_main_ruleset.py` and review exact-head GitHub CI results.
- [ ] **Step 5: Commit code and regression** on an isolated branch; review the diff and verify the policy file has not changed.

### Task 2: Evidence handoff and PR

**Files:**
- Create: `docs/coworker-roadmap/DAY1_AUDIT_ENFORCE_ON_CREATE_2026-11-20.md`
- Modify: `docs/coworker-roadmap/PROGRESS.md`

- [ ] **Step 1: Record task contract** with observed red and green tests, current base/head SHA, risk boundary, exact CI and manual blockers.
- [ ] **Step 2: Create or update a draft PR**, include test evidence and exact-head CI; never self-approve, merge, mutate the live ruleset, or claim operational day completion.

**Release state:** Source-only and pilot NO-GO until separately operated native control, staging, independent D custody and Founder/Owner-C approval gates have passed.
