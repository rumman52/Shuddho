# PA-10 reminder expiry admission contract

- Objective: no expired reminder may create a new outbox notification during catch-up.
- Baseline: `67d187f972c8069e4369ebc9fdb28dae55c40e3f`.
- Branch: `fix/pa10-reminder-expiry-admission-20261125`.
- Existing interface: `AutomationRepository.accept_reminder_occurrence`; preserve stable occurrence key, replay, goal revision checks and delivery fences.
- Root cause: expiry compared to due time only, despite the scheduled Agent path comparing expiry to the later of current admission and due time.
- Regression: test at expiry and one second after, both within catch-up; expect one skipped occurrence, replay of the same ID, no notification and no Agent run.
- Implementation: read the admission clock once under the existing database transaction, use it for expiry and catch-up. No API, migration, new authority, additional provider invocation or scheduler changes.
- Verification: local isolated predicate check failed both original cases; corrected predicate passed four cases including before expiry and future due after expiry. These are not integration-test results. Run `uv run --extra coworker pytest tests/test_automations.py -k 'simple_reminder or catchup_window_and_expiry' -q -rs` and required full exact-head CI.
- Rollback: revert source and tests together; no persistent schema change. Retain existing notification delivery authorization.
- External: approved persistent worker, Temporal credentials, staging release freeze, synthetic identities, provider and device qualification, and independent review.
- Out of scope: other scheduler profiles, one-time scheduling, live qualification and production activation.

| Level | Status | Evidence |
| --- | --- | --- |
| Implemented | Proposed | source commit 4c1661a5b010717350470c90d5beba88f39084d9 |
| Repository verified | Pending | integrated test and exact-head CI required |
| Staging verified | No | no live operation |
| Production qualified | No | not authorized |
| Activated | No | unchanged |

No scenario receipts have been fabricated. Independent review remains pending.
