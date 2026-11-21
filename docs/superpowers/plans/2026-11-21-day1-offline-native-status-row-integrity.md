# Day 1 Offline Native Status-Row Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Day 1 offline ruleset drift diagnostic fail closed on malformed, duplicated or untrusted native status rows even if the three required first-party check contexts are present.

**Architecture:** Keep `scripts/day1_ruleset_drift.py` read-only. Reuse the existing `MINIMUM_CHECKS`, `ACTIONS_INTEGRATION_ID` and reviewed policy identity. Extend the existing `_reviewed_check_contexts` validator to enforce an exact row shape; add a separate live-row integrity predicate in `analyze`, emitting a new deterministic drift gap without altering previous drift messages or permitting hidden extra checks. The newer `main_protection_audit.py` (merged PR #838) already rejects these rows; the offline reporter must agree.

**Tech Stack:** Python 3.11, pytest, GitHub Actions, no external dependencies.

**Spec:** [Ruke AI Ten Day Completion Plan](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit) Day 1 paragraphs 141–152; [GitHub Day 1 #727](https://github.com/rumman52/Shuddho/issues/727); [execution board #737](https://github.com/rumman52/Shuddho/issues/737); `infra/github/main-ruleset.json`; `scripts/main_protection_audit.py`.

## Global Constraints
- Checked-in approved required statuses are `test-and-build`, `coworker`, `ci-merge-gate`, each with exact integer GitHub Actions App ID `15368`.
- Required review is at least one independent approval, current-head strictness, no bypass, no creation exemption; read-only candidate evidence is **not** an operated native merge control.
- Extra uniquely named, first-party statuses can only strengthen a **minimum-policy diagnostic candidate**; authorization to mutate existing rules remains separate and explicitly manual in `reconcile_main_ruleset.py`.
- No paid service, native GitHub policy PUT, credential/protected environment change, deployment, database mutation, PostHog ingestion, user data, evaluation holdout access, real release, or pilot admission.
- Keep all existing report keys, behavior of compliant and absent required checks, exit semantics, and current CLI shape. No new schema migrations or output artifact locations.

## Review Focus
1. A duplicate *extra* status with the approved publisher must not be ignored merely because all three mandatory statuses are present.
2. An extra status with wrong, null, missing, string or Boolean publisher must not pass.
3. Malformed row (non-object, blank name, unknown field) must not be silently ignored.
4. An altered reviewed policy must itself fail closed if any status row has unknown keys.
5. Fully compliant policy and one unique additional first-party live check must continue to be a non-qualifying `configuration_candidate` with no drift.

---

### Task 1: RED reproduction

**Files:**
- Modify: `tests/test_day1_ruleset_drift.py`

**Interfaces:**
- Consumes: `analyze(branch, live_ruleset, policy, *, expected_main_sha, expected_ruleset_id=RULESET_ID) -> dict`; `EvidenceError`; existing `policy()/branch()/live()` synthetic fixtures.
- Produces: Test-only additions, no API changes.

- [ ] Step 1: Write parametrized negative tests for duplicate/untrusted/malformed additional live rows and altered reviewed policy, plus a positive extra trusted status.
- [ ] Step 2: Commit tests **without** implementation and run GitHub CI against the test-only SHA; confirm actual expected failures because `analyze` returned `configuration_candidate` or accepted a malformed policy, not environment/collection failures.
- [ ] Step 3: Record the RED run link, test-only SHA, exact fail/pass/skip counts.

### Task 2: GREEN implementation

**Files:**
- Modify: `scripts/day1_ruleset_drift.py`

- [ ] Step 1: Reject reviewed policy entries unless `set(row) == {"context", "integration_id"}` while preserving mandatory context and exact publisher rules.
- [ ] Step 2: Add local live-row predicate checking list type, each row's exact keys, nonblank string context, unique context and int publisher `15368`; append drift code `checks.unambiguous_first_party_rows` if it fails; keep the three existing individual missing-context gap codes.
- [ ] Step 3: Run focused tests (`uv run --locked --extra coworker pytest -q tests/test_day1_ruleset_drift.py tests/test_main_protection_audit.py tests/test_reconcile_main_ruleset.py`) and full final-head GitHub CI. Do not mark skipped PR governance audit as success.
- [ ] Step 4: Review diff for no new external actions, no policy modifications, and compatibility with exact source readback.

### Task 3: Evidence and handoff

**Files:**
- Create: `docs/coworker-roadmap/DAY1_OFFLINE_CHECK_ROW_INTEGRITY_2026-11-21.md`
- Modify: `docs/coworker-roadmap/PROGRESS.md`

- [ ] Step 1: Write task contract and checkpoint with RED and GREEN evidence, exact head and source-only status, and current platform blockers.
- [ ] Step 2: Open a **draft** PR to `main`, include exact-head CI results and request real independent human review; post the evidence on Linear MD-5.
- [ ] Step 3: Keep operational NO-GO until genuine native merge-control positive/negative receipts, protected audit App, owned staging recovery/worker identity, D-only holdout custody and independent Founder/C approval exist.

**Ruling:** The script detects minimum native status protection, not equality with the checked-in template: a unique extra trusted status is permitted in the offline report, while a duplicate or untrusted status is prohibited. This keeps parity with merged `main_protection_audit.py` and preserves separately guarded administrative reconciliation.
