# PA-10 deadline occurrence recovery — implementation plan and result

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make deadline automation occurrences safely recoverable after transient admission failures and worker restarts without allowing stale or ineligible work to start.

**Architecture:** Reuse the existing durable `AutomationOccurrence` ledger, stable deadline key, and shared narrow admission-error recorder. Find an existing pending occurrence before any early return that could strand it; only re-enter an `accepting` occurrence, revalidate current authority and goal state, and enforce the automation's catch-up window against current time. Terminal states remain terminal.

**Tech Stack:** Python 3.11, pytest, SQLAlchemy, FastAPI, existing AgentRun idempotency boundary.

**Spec:** GitHub issue #566 and `docs/PA10_GOAL_DRIVEN_PROACTIVITY.md`.

## Implementation and verification status — 25 October 2026

- Source fix, eight regression tests, and the focused mandatory no-skips CI gate are merged in [PR #568](https://github.com/rumman52/Shuddho/pull/568), main merge SHA `79d4e59a69350b3af9d7404102e285fd606fb04d`.
- Exact PR-head run [#40192139821](https://github.com/rumman52/Shuddho/actions/runs/40192139821) passed `test-and-build` and the full `coworker` suite. Its `ci-merge-gate` failed because no independent current-head review was recorded.
- PR #568 merged at 16:08:07 UTC while later exact-head run [#40210212873](https://github.com/rumman52/Shuddho/actions/runs/40210212873) was still running. It subsequently completed `test-and-build=success` and `coworker=success` at 16:26:30 UTC, then failed `ci-merge-gate` at 16:26:40 UTC because independent review was missing. Merged-main run [#40210229328](https://github.com/rumman52/Shuddho/actions/runs/40210229328) completed `test-and-build=success` and `coworker=success` at 16:33:20 UTC, but `governance-audit=failure` and `ci-merge-gate=failure` at 16:33:29 UTC because main branch protection was not confirmed.
- The missing independent-review/native-protection gate was **not satisfied before merge**. This is recorded in [V-01 issue #484](https://github.com/rumman52/Shuddho/issues/484). Do not treat later green tests as retroactive approval or merge-control evidence.

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

- [x] Add tests for transient `active_agent_limit` recovery across a fresh Container instance, duplicate-run/notification prevention, expired catch-up, target removal, goal revision change, and pause.
- [x] Add a focused mandatory CI step that runs the deadline recovery tests with JUnit output and rejects skips/failures/errors through `scripts.mandatory_test_gate`.
- [x] Opened the draft PR and reproduced the expected red phase before the production fix against the current implementation for the expected reasons.

### Task 2: Implement safe deadline recovery

**Files:**
- Modify: `services/coworker/automation_repository.py`

- [x] Locate the existing pending occurrence before validation/target early returns can strand it.
- [x] Revalidate current automation/goal eligibility and the catch-up window; terminalize pending rows with a safe reason when they are no longer eligible.
- [x] Re-enter only an `accepting` occurrence; reuse the deterministic deadline idempotency key and `_record_occurrence_admission_error`.
- [x] Preserve terminal-state replay behavior and one-run/one-notification semantics.

### Task 3: Verify and hand off

- [x] Confirm the focused red-green cycle on the PR head; the mandatory deadline-recovery JUnit gate passed with no skips.
- [x] Run the complete coworker suite and test/build jobs on the exact PR head: [run #40192139821](https://github.com/rumman52/Shuddho/actions/runs/40192139821) passed both code jobs.
- [ ] Confirm full coworker completion on merged main SHA `79d4e59a69350b3af9d7404102e285fd606fb04d`; [run #40210229328](https://github.com/rumman52/Shuddho/actions/runs/40210229328) was still running the full integration step at this snapshot, and its governance audit failed.
- [x] Perform a source-level review of the diff for authority expansion, duplicate admission, catch-up bounds, and replay semantics. This is not an independent review.
- [ ] Obtain a real independent review and prove repository-native merge protection. This gate was **missed before PR #568 merged**; record the incident in #484 and do not claim pre-merge review or enforced controls.
- [ ] Before any subsequent release/activation, verify exact merged-main CI, configured endpoint health, staging API/worker identity, frozen PA-10 evidence, and explicit release authorization.

**Post-merge disposition:** deadline occurrence recovery is implemented and merged; PA-10 staging qualification and overall production readiness remain incomplete. The merge automatically triggered a Render production deploy; no deployment settings were changed by this implementation. See the refreshed release handoff in `docs/coworker-roadmap/PROGRESS.md`.
