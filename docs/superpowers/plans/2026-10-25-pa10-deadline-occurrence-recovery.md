# PA-10 deadline occurrence recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deadline automation occurrences safely recoverable after transient admission failures and worker restarts without allowing stale or ineligible work to start.

**Architecture:** Reuse the existing durable `AutomationOccurrence` ledger, stable deadline key, and shared narrow admission-error recorder. Find an existing pending occurrence before any early return that could strand it; only re-enter an `accepting` occurrence, revalidate current authority and goal state, and enforce the automation's catch-up window against current time. Terminal states remain terminal.

**Tech Stack:** Python 3.11, pytest, SQLAlchemy, FastAPI, existing AgentRun idempotency boundary.

**Spec:** GitHub issue #566 and `docs/PA10_GOAL_DRIVEN_PROACTIVITY.md`.

## Global Constraints

- Do not create a second occurrence, AgentRun, or start notification for the same deadline occurrence.
- Resume only an existing `accepting` occurrence; preserve accepted, blocked, skipped, and buffered states.
- Only `active_agent_limit` with HTTP 429 is retryable; other admission errors remain terminal.
- Revalidate the kill switch, automation revision/state/expiry, goal state/revision, deadline target, and catch-up window before admission.
- No schema migration, provider/credential change, deployment setting change, or production activation.

## Review Focus

- A pending occurrence is terminalized if its automation, goal, authority, or target is no longer eligible.
- A retry uses the original occurrence identity and remains inside the configured catch-up window.
- Worker restart after transient capacity rejection creates exactly one AgentRun and one start notification.
- Replaying accepted/blocked/skipped occurrences does not reopen them.
- No action is admitted when the catch-up window has expired.

---

## Tasks

### Task 1: Regression tests and focused CI gate

**Files:**
- Modify: `tests/test_automations.py`
- Modify: `.github/workflows/ci.yml`

- [ ] Add tests for transient `active_agent_limit` recovery across a fresh Container instance, duplicate-run/notification prevention, expired catch-up, target removal, goal revision change, and pause.
- [ ] Add a focused mandatory CI step that runs the deadline recovery tests with JUnit output and rejects skips/failures/errors through `scripts.mandatory_test_gate`.
- [ ] Open a draft PR and verify the new regression tests fail against the current implementation for the expected reasons.

### Task 2: Implement safe deadline recovery

**Files:**
- Modify: `services/coworker/automation_repository.py`

- [ ] Locate the existing pending occurrence before validation/target early returns can strand it.
- [ ] Revalidate current automation/goal eligibility and the catch-up window; terminalize pending rows with a safe reason when they are no longer eligible.
- [ ] Re-enter only an `accepting` occurrence; reuse the deterministic deadline idempotency key and `_record_occurrence_admission_error`.
- [ ] Preserve terminal-state replay behavior and one-run/one-notification semantics.

### Task 3: Verify and hand off

- [ ] Confirm the focused red-green cycle on the PR head.
- [ ] Run the complete coworker suite and all available required CI jobs; verify the mandatory tests have zero skips.
- [ ] Review the complete diff for authority expansion, duplicate admission, and stale catch-up bypasses.
- [ ] Leave the PR unmerged pending independent review and repository-native merge protection. Do not deploy or change production settings.
