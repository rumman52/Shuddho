# Restore required CI source-contract checks — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair three independently reproduced, deterministic source/fixture mismatches that currently prevent the mandatory main CI gates from running to completion.

**Architecture:** Consume the existing return contract of `_day8_cases` without weakening any comparison criteria. Correct the precise fail-closed Day 2 error assertion and reuse the existing explicit Day 7 briefing prerequisites helper; leave production feature flags default-off.

**Tech Stack:** Python 3.11/3.12, pytest, uv, GitHub Actions.

**Spec:** [Part 05 qualification and handoff](https://github.com/rumman52/Shuddho/issues/736), [Day 1 baseline](https://github.com/rumman52/Shuddho/issues/727), [Day 2](https://github.com/rumman52/Shuddho/issues/728), [Day 8](https://github.com/rumman52/Shuddho/issues/734).

## Global constraints

- This is a source/CI repair only, not staging qualification or a pilot GO decision.
- Keep `_day8_cases` validation and the Day 8 quality/latency/budget/receipt thresholds unchanged.
- Keep Day 2 positive/negative owner isolation and fail-closed missing-owner-B control checks unchanged.
- Keep production proactive briefing capability default-off. Enable prerequisites only inside the test fixture via existing `_enable_briefings`.
- No provider calls, hosted writes, infrastructure provisioning, schema migrations, release flags, spending, telemetry or external sends.
- Leave governance audit failures visible; an admin must supply the App identity and enforce native branch protection.

## Review focus

- A missing owner-B artifact must fail **before** a private document write.
- Both positive and negative owner A/B isolation must still be tested.
- Missing required Runtime v3 briefing prerequisites must still return `briefing_unavailable`.
- Day 8 reused run identity and reused usage receipt must still be rejected.
- Day 8 comparison must never imply live qualification from synthetic development evidence.

---

### Task 1: Day 8 evaluator result contract

**Files:** `scripts/core_agent_observability.py`; existing regression suite `tests/test_core_agent_observability.py`.

**Interfaces:** `_day8_cases(report, expected, label) -> (by_id, reruns_by_id, attempt_provenance_complete)`, `compare_day8_development(baseline, candidate, suite)`.

- [x] **RED:** [main CI #44598107021](https://github.com/rumman52/Shuddho/actions/runs/44598107021), `coworker` / Day 8 step, 28 failed and 168 passed; `AttributeError: 'tuple' object has no attribute 'values'` in `compare_day8_development`.
- [x] **Root cause:** the parser returns a tuple, but the consumer applies mapping operations to the entire tuple.
- [x] **Minimal fix:** unpack the parser's three results, preserving the case-ID mapping for existing comparison operations; do not alter the parser or qualifying thresholds.
- [ ] **GREEN:** Run mandatory Day 8 CI test step on the exact PR head; record pass/fail/skip counts.

### Task 2: Day 2 failure assertion

**Files:** `tests/test_staging_day2_execution.py`; existing production path `scripts/staging_day2_execution.py`.

- [x] **RED:** same main CI, `test-and-build`: 1 failed, 2531 passed, 93 skipped. Actual error `Owner B synthetic artifact is not present exactly once ...`; regex expected lowercase `owner`.
- [x] **Minimal fix:** use exact error capitalization in the test assertion; keep the pre-write denial test and runtime authorization unchanged.
- [ ] **GREEN:** Run targeted Day 2 regression and full main Python test gate.

### Task 3: Day 7 test prerequisite alignment

**Files:** `tests/test_automations.py`; existing `_enable_briefings` test helper.

- [x] **RED:** main Coworker Day 8 step calls `test_briefing_occurrence_emits_one_completion_notification_only`, receiving `briefing_unavailable` (409) instead of creation (201).
- [x] **Root cause:** this case omitted `_enable_briefings`; neighboring positive-path briefing tests call it and the negative-path test intentionally omits it.
- [x] **Minimal fix:** call `_enable_briefings(automation_container)` before creating the schedule.
- [ ] **GREEN:** Run the positive/negative briefing tests in the required CI gates.

### Task 3b: Recover missing briefing completion-to-occurrence link

**Files:** `services/coworker/automation_repository.py`, `tests/test_automations.py`.

- [x] **RED:** [PR #808 run #44602686715](https://github.com/rumman52/Shuddho/actions/runs/44602686715) narrowed the Coworker Day 8 step from 28 failures to **one failure / 195 passes**. `test_briefing_occurrence_emits_one_completion_notification_only` found zero notifications by `occurrence_id` after two completion callbacks.
- [x] **Root cause:** `notify_run_completed` did not pass `occurrence_id` when enqueuing the single briefing completion notification; briefing intentionally emits no start notice to preserve the unique occurrence notification slot.
- [x] **Minimal fix:** pass `occurrence_id` only for the briefing profile. Other profiles already attach the unique occurrence ID to the *start* notification and need a separate completion notification keyed by deterministic notification ID.
- [x] **Additional guard:** assert the proactive profile still records one start and a separate completed notification; only its start notice carries the occurrence ID.
- [ ] **GREEN:** exact-head Coworker Day 8 step and general Python test suite, with no new skips.

### Task 4: Verify and hand off

- [ ] Inspect exact-head PR tests, required Coworker Day 8 suite and general Python suite, and all other required checks.
- [ ] Update evidence ledger with final head, test counts, review status and remaining blockers.
- [ ] Obtain independent human review. Do **not** merge while `ci-merge-gate` / governance review is red.

**Rollback:** revert this bounded source/fixture commit; no schema, runtime or infrastructure rollback is required.
