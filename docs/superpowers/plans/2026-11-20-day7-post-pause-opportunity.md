# Day 7 post-pause scheduled-opportunity verification — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Work through regression tests, fail-closed implementation, and exact-head verification in that order.

**Goal:** Do not label the Day 7–8 two-date briefing evidence gate passed until a subsequent genuine scheduled opportunity has elapsed after pause, including the approved catch-up horizon, with zero new owner-scoped occurrences, runs, and notifications.

**Architecture:** Keep the existing first/second/paused evidence objects and their real schedule/owner lineage. Add an explicit post-pause observation collected from the existing synthetic, authenticated, owner-scoped staging API. The offline gate validates the expected next local-calendar opportunity and zero counts. Temporal natural-timer and physical delivery provenance remain independent operator requirements; no simulated evidence or manual trigger qualifies.

**Tech stack:** Python 3, pytest, httpx, IANA zoneinfo, GitHub Actions; no new dependencies or database migration.

**Spec:** User's Rukh AI Engineering Execution Prompt Part 04, page 1: "On a scheduled opportunity verify zero new admissions and deliveries for the paused profile"; Day 7 D07.T08/G04; Day 8 D08.G01; existing docs/PA10_SCHEDULED_PROFILE_STAGING.md.

## Global constraints

- Never send paid provider requests, create users, enable PostHog, or change staging/prod without the required approvals.
- Preserve owner scope, release SHA / provider-policy lineage, exact automation ID, pause revision, and original per-day source pins.
- Do not infer actual Temporal natural firing from offline JSON, or confuse persisted notification rows with downstream transport delivery.
- No operator probe can pass before the next local due time plus the approved catch-up window.
- The pause mutation must remain prevalidated; the later observation command is separate and read-only.

## Review focus

1. A pause acknowledged immediately must remain **BLOCKED**, not qualified.
2. A false zero during the catch-up window must be rejected.
3. A new occurrence/run/notification, removed baseline item, changed owner/release, or resumed schedule must fail closed.
4. Consecutive local days around DST must compute the next opportunity in the owner's time zone, not UTC+24 hours.
5. A reused, missing or malformed operator receipt must not bypass counts or the same-release checks.

## Tasks

### Task 1 — RED: demonstrate false passed pause

**Files:** tests/test_staging_day7_two_day_gate.py

- [ ] Assert that a pause-only readback (the current operator output) raises GateFailure by default.
- [ ] Assert that a post-opportunity receipt after the correct next local due + catch-up window with zero counts passes.
- [ ] Parametrize missing, early, wrong-due, non-zero, resumed, mismatched-revision and unrelated-case evidence; verify each blocks.
- [ ] Run the focused tests and record failing output before implementation.

### Task 2 — GREEN: bound the offline gate

**Files:** scripts/staging_day7_two_day_gate.py

- [ ] Add a kw-only preflight parameter to verify_two_day for the guarded pause operation; only the final default path requires a post-pause observation.
- [ ] Pin overlap policy and catch-up window between both natural-date receipts, calculate the next scheduled due in IANA local time, and require the pause before it.
- [ ] Require late-enough observation, correct owner/automation/release and pause revision, zero counts for occurrences/runs/notices.
- [ ] Mark preflight report nonqualified and keep the existing independent-Temporal-provenance limitation.

### Task 3 — GREEN: stage real read-only observation

**Files:** scripts/staging_pa10_scheduled_profile.py, tests/test_staging_day7_two_day_gate.py

- [ ] Capture owner-scoped occurrence/run/notification baselines while confirming the paused revision.
- [ ] Expose a guarded `verify-paused-opportunity` subcommand which reads current owner-scoped history/notifications after the next local due + catch-up window and rejects baseline disappearance or any new IDs.
- [ ] Independently read back the deployed release, same synthetic account, paused revision and applied state before writing final evidence. No synthetic/simulated clock counts as live staging qualification.
- [ ] Update preflight calls so the pause mutation is not blocked by an observation that can only occur later.
- [ ] Add focused mocked transport tests showing no new HTTP mutation during verification.

### Task 4 — documentation and verify

**Files:** docs/PA10_SCHEDULED_PROFILE_STAGING.md

- [ ] Show the separate post-opportunity read-only command and explain that pause-only receipts cannot qualify.
- [ ] Correct the outdated briefing sentence to one completion notice; other profiles still use two notices.
- [ ] Run the scoped pytest suite and GitHub CI at the exact branch head; report any failed/blocked gates.
- [ ] Open a PR to main; preserve owner/Founder sign-off requirements and open external blockers.
