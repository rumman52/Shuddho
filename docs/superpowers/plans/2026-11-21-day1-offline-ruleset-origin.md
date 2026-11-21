# Day 1 Offline Ruleset Repository-Origin Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a Day 1 offline governance diagnostic from reporting `configuration_candidate` unless its captured GitHub ruleset clearly belongs to the expected `rumman52/Shuddho` repository, rather than an inherited or ambiguous organization ruleset.

**Architecture:** Keep `scripts/day1_ruleset_drift.py.analyze` fully read-only and append one stable `ruleset.repository_origin` drift code unless both `source == "rumman52/Shuddho"` and `source_type == "Repository"` are explicit. This follows the same existing admin reconciliation requirement in `scripts/reconcile_main_ruleset.py::_read_unique_existing`. Preserve existing status checks, review, bypass, source-qualification and report structure.

**Tech Stack:** Python, pytest, GitHub Actions.

**Spec:** [10-day pilot plan Day 1 §141–152](https://docs.google.com/document/d/1JvuAYTmP-0pp7VhOGdV4YnMYLvv0vffuRBqJ0P8Pd8E/edit); [GitHub issue #727](https://github.com/rumman52/Shuddho/issues/727); [execution board #737](https://github.com/rumman52/Shuddho/issues/737); checked-in `infra/github/main-ruleset.json` and admin `scripts/reconcile_main_ruleset.py`.

## Global constraints

- One bounded SOURCE_ONLY change per draft PR; no native GitHub ruleset PUT, secret access, merge permission or protected environment modifications.
- Only match actual `Repository` source type plus exact expected repository path on the captured readback. Do not infer ownership from ruleset name, ID or branch protection alone.
- Preserve the offline CLI's existing report fields, no-qualification semantics, prior drift codes and existing accepted `~DEFAULT_BRANCH` conditional target.
- Keep all required first-party status, approval, bypass and creation-enforcement checks; no unrelated application, migration, model, cost, telemetry or infrastructure change.
- Live merge-control denied/permitted cases and administrator App credentials remain independent requirements; an offline candidate is **never** release approval.

## Review focus

1. Spoofed or inherited `Organization` origin despite matching name/ID/required checks must be marked blocked.
2. A foreign repository name or case mismatch must block.
3. Missing or null `source` or `source_type` must block; no guessing.
4. Exact repository origin on the native ruleset must retain a non-qualifying `configuration_candidate`.
5. Existing malformed status, no bypass, SHA and independent review validations remain unchanged.

---

### Task 1: Demonstrate RED

**Files:**
- Modify: `tests/test_day1_ruleset_drift.py`

**Interface:** `analyze(branch, live_ruleset, policy, *, expected_main_sha, expected_ruleset_id=RULESET_ID) -> dict`.

- [ ] Update the synthetic native ruleset fixture to include the explicit true repository source.
- [ ] Add positive origin test and parameterized negative tests for missing, foreign and inherited origin.
- [ ] Push a test-only commit and inspect the exact failing GitHub Actions test job. It must demonstrate `configuration_candidate` for these negative cases, not environment failures.

### Task 2: Minimal GREEN source patch

**Files:**
- Modify: `scripts/day1_ruleset_drift.py`

- [ ] Add `require(r.get("source") == REPOSITORY and r.get("source_type") == "Repository", "ruleset.repository_origin")` with no other behavior changes.
- [ ] Run focused test suite `uv run --locked --extra coworker pytest -q tests/test_day1_ruleset_drift.py tests/test_main_protection_audit.py tests/test_reconcile_main_ruleset.py`.
- [ ] Inspect final exact-head GitHub workflow (test-and-build, coworker, frontend, browser, PostgreSQL 18, ancestry, merge gate and PR-skipped governance audit distinctly), never claim a running/skipped job passed.

### Task 3: Handoff

**Files:**
- Create: `docs/coworker-roadmap/DAY1_OFFLINE_RULESET_REPOSITORY_ORIGIN_2026-11-21.md`.
- Modify: `docs/coworker-roadmap/PROGRESS.md`.

- [ ] Record true base/head, RED/GREEN CI evidence and blockers; no synthetic admin merge controls.
- [ ] Open a draft PR and add Linear MD-5 handoff.
- [ ] Retain **SOURCE_ONLY / pilot NO-GO** pending administrator-owned live protected ruleset, authentic independent review, staging restore and API-worker parity, D's private holdout custody and distinct Founder/C release approvals.

**Ruling:** GitHub's effective `rulesets?includes_parents=true` includes inherited organization rules. A repository branch may be protected by one such rule, but the project Day 1 acceptance and existing admin reconciler explicitly target a known repository-owned ruleset `27324410`. A snapshot missing `source` or `source_type` is inadequate evidence for that gate; reject it without making any live change.
