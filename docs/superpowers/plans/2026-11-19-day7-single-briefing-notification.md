# Day 7 single briefing notification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each scheduled daily briefing occurrence produce exactly one owner-visible completion notification, with replay remaining idempotent.

**Architecture:** Reuse the existing `Notification` row and outbox, whose `occurrence_id` is unique. Do not enqueue an early `automation_started` notification for the `briefing` profile; let the existing completion hook create the single `automation_completed` notification. Keep all other automation profiles unchanged. Align the live staging probe and two-day evidence gate with that one-notification contract.

**Tech Stack:** Python 3.11+, SQLAlchemy, existing coworker notification repository, pytest, GitHub Actions.

**Spec:** Uploaded `04_Rukh_AI_Routine_and_Cost(1).docx`, pages 1–2; issue #733; issue #734; `docs/coworker-roadmap/SPEC.md`.

## Global Constraints

- Preserve the unique `cw_notifications.occurrence_id` constraint and existing NotificationOutbox; no new notification ledger or migration.
- A replay of the same occurrence must not create another AgentRun or notification.
- Keep `automation_started` behavior for non-briefing profiles.
- Do not create a live owner goal, Temporal schedule, notification, worker, deployment, provider call, or PostHog event in staging.
- Source and synthetic CI evidence are not natural Temporal firing or release qualification evidence.

## Review Focus

1. Briefing occurrence accepted but run never completes: no owner notification should be delivered.
2. Completion hook replayed after restart: same occurrence still has exactly one completion notification.
3. Existing started notice from a pre-fix occurrence: do not silently claim that old data satisfies the new contract; the staging probe must fail closed.
4. Other automation profiles: existing started-notice behavior must remain unchanged.
5. Missing, duplicate, or non-completion notice in staging evidence: two-day gate must reject it.

---

### Task 1: Pin the one-notification behavior with tests

**Files:**
- Modify: `tests/test_automations.py`
- Modify: `tests/test_staging_pa10_scheduled_profile.py`
- Modify: `tests/test_staging_day7_two_day_gate.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_day8_telemetry_ci_gate.py`

- [ ] Add a real repository test for a `briefing` occurrence: zero notices before completion, exactly one `automation_completed` notice after completion, and still one after replaying the completion hook.
- [ ] Change scheduled-profile probe fixtures to one completion notice and test that zero, started-only, or two notices are rejected.
- [ ] Change the two-day gate fixture to one completion-notification ID per occurrence; reject wrong counts and duplicate IDs across days.
- [ ] Include the scheduled-profile probe tests in the mandatory no-skip Day 8 CI gate.

### Task 2: Implement the smallest behavior change

**Files:**
- Modify: `services/coworker/automation_repository.py`
- Modify: `scripts/staging_pa10_scheduled_profile.py`
- Modify: `scripts/staging_day7_two_day_gate.py`

- [ ] Do not enqueue `automation_started` for `run_profile == "briefing"`; retain current behavior for every other profile.
- [ ] Require exactly one `automation_completed` notification in the staging probe and record its single ID.
- [ ] Require exactly one completion-notification ID in each natural-day evidence envelope and require the IDs to be distinct across the two occurrences.

### Task 3: Document and verify

**Files:**
- Modify: `docs/PA10_NOTIFICATION_SERVICE.md`
- Modify: `docs/coworker-roadmap/PROGRESS.md`

- [ ] Document the briefing-specific notification lifecycle and the unchanged behavior of other profiles.
- [ ] Record source/CI status separately from blocked live Temporal, worker, privacy, and 80-case benchmark evidence.
- [ ] Run the focused Day 7 tests and the full Coworker CI suite on the exact PR head; record any failed governance checks without weakening them.

### Task 4: Review and open the pull request

- [ ] Review the exact diff for duplicate notification paths, legacy evidence compatibility, and unrelated changes.
- [ ] Open a pull request against `main`; do not merge or deploy.
- [ ] Leave issue #734 open until its operated acceptance gates have authentic evidence.
