# Day 1 Governance Audit Status Row Ambiguity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure the read-only CI governance audit does not report a protected-main configuration candidate when required-status entries are duplicate, malformed, or issued by an unreviewed integration.

**Architecture:** Tighten the existing `scripts.main_protection_audit._has_required_rules` required-checks predicate. Validate every entry first, require unique nonblank contexts, and only then ensure the existing reviewed three contexts are present. Do not change native rulesets, approval counts, merge gates, the approved policy or any live settings. The script remains a minimum-policy candidate audit, not a native merge guarantee.

**Tech Stack:** Python 3.11, pytest, GitHub Actions.

**Spec:** The authoritative [10-day completion plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 ¶141–152, [governance issue #727](https://github.com/rumman52/Shuddho/issues/727), [execution board #737](https://github.com/rumman52/Shuddho/issues/737); `infra/github/main-ruleset.json`, `scripts/day1_ruleset_drift.py`, `scripts/reconcile_main_ruleset.py`.

## Global Constraints

- Keep three mandatory GitHub Actions statuses `test-and-build`, `coworker`, and `ci-merge-gate`, each pinned to `integration_id=15368`; approvals `>=1`, strict checks, `do_not_enforce_on_create=false`, no bypass, target protected `main`.
- Additional uniquely named checks from the same authenticated publisher may strengthen enforcement and need not invalidate the **minimum-policy candidate** audit; native reconciliation separately forbids unknown rows without human review. Reject ambiguous or unauthenticated rows.
- A successful source audit is NOT native denied/permitted merge evidence. Audit is read-only and must not be treated as permission to merge or launch the pilot.
- No production/staging mutation, new spending, PostHog collection, external action, credential change, independently held-out data read, provisioning or autonomous release.
- Preserve Bangla writing experience, current backend-only credential model, old run histories and all existing checks.

## Review Focus

1. Duplicate required context with the **same** approved publisher must fail; existing auditor only rejects a duplicate with an **untrusted** publisher.
2. Extra context with untrusted/null/wrong-type integration ID must fail instead of being ignored.
3. Malformed non-dict, empty/whitespace context or unknown check-row fields must fail.
4. Exact reviewed status rows still pass.
5. A unique additional first-party GitHub Actions context remains accepted as an extra restriction, since this auditor measures a **minimum** and the explicit native reconciler governs changes.

---

### Task 1: Pin RED against the existing auditor

**Files:**
- Modify: `tests/test_main_protection_audit.py`

**Interfaces:**
- Consumes: `audit_governance(branch: dict, rulesets: list[dict]) -> int`, `GovernanceAuditError`, `approved_ruleset()`.
- Produces: No public API changes.

- [ ] **Step 1: Add test cases** for duplicate valid row, extra untrusted/missing publisher, malformed/blank row, and unexpected status-check keys. Add a positive unique-extra first-party check.
- [ ] **Step 2: Run full repository `test-and-build` CI on the test-only commit** and capture the actual failures as RED. Failures must be `DID NOT RAISE GovernanceAuditError`, not collection or environment faults.
- [ ] **Step 3: Record exact test-only SHA and failing CI run**.

### Task 2: Minimal fix and GREEN

**Files:**
- Modify: `scripts/main_protection_audit.py`.

- [ ] **Step 1: Validate `required_status_checks` is a list of unique, nonblank string contexts with exact GitHub Actions integration ID `15368`, and no unknown fields.
- [ ] **Step 2: Assert `CHECKS.issubset(seen_contexts)` instead of counting matches; do not change the broader approval, bypass, branch or strictness logic.
- [ ] **Step 3: Verify focused command** `uv run --locked --extra coworker pytest -q tests/test_main_protection_audit.py tests/test_day1_ruleset_drift.py tests/test_reconcile_main_ruleset.py`.
- [ ] **Step 4: Verify final-head CI**, recording test-and-build, Coworker, PostgreSQL, frontend, browser and merge gate separately; never convert `SKIPPED` to `SUCCESS`.

### Task 3: Evidence handoff

**Files:**
- Create: `docs/coworker-roadmap/DAY1_STATUS_ROW_AUDIT_2026-11-21.md`.
- Modify: `docs/coworker-roadmap/PROGRESS.md`.

- [ ] **Step 1: Record red/green evidence and current exact head/base and risk boundaries**.
- [ ] **Step 2: Open a reviewable draft PR, link current CI and the owner blockers on Linear MD-5**.

**Release:** **SOURCE_ONLY / NO-GO** until privileged App admin explicitly proves actual native merge restrictions, staging restore/runtime identity, independent evaluation custody and the Founder+Owner C approvals.
