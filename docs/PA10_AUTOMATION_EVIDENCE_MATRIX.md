# PA-10 Automation / Proactive Coworker Evidence Matrix

This matrix separates implementation, repository verification, live-provider verification, staging qualification, production qualification and activation. A stronger state is never inferred from a weaker one.

## Repository freeze verification — 1 October 2026

Cumulative Automation / Proactive Coworker repository implementation and staging tooling are **REPOSITORY VERIFIED** on current merged `main` revision `55a6980d0c3906e199b9552d7f1fa4c77a2623ae` (PR #279 checkpoint merge). Merged-main CI #1071 / run `36850391865` completed successfully with both required jobs, `test-and-build` and heavyweight `coworker`, passing. The implementation-producing proactive provider/read-event probe from PR #278 was already verified by exact-head CI #1068 and merged-main CI #1069.

PR #279 is documentation/checkpoint evidence; it does not convert repository verification into live staging evidence. Google, Microsoft, Browser Push, managed recovery, human multilingual proactive quality, real task economics, staging, production qualification and activation remain independently unverified until controlled evidence exists.

## Repository scope

| Capability | Repository state | Live / staging state | Evidence / remaining gate |
| --- | --- | --- | --- |
| Durable scheduling | **REPOSITORY VERIFIED** on current merged main CI #1071 | NOT VERIFIED in controlled staging for this expanded PA-10 scope | PA-02 Temporal schedule/reconciliation, occurrence ledger and recovery tests |
| Occurrence dedupe | **REPOSITORY VERIFIED** on current merged main CI #1071 | NOT VERIFIED in controlled staging | canonical UTC occurrence keys; event IDs; meeting snapshot/start identity; deadline urgency identity |
| Pause / resume / cancel | **REPOSITORY VERIFIED** on current merged main CI #1071 | NOT VERIFIED in controlled staging | revisioned automation state + reconciliation |
| Connected events | **REPOSITORY VERIFIED** on current merged main CI #1071 | LIVE NOT VERIFIED | authenticated provider intake, stable event ID, owner/grant/subscription checks |
| Notification outbox | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED | shared `NotificationRepository`, `cw_notifications`, `cw_notification_outbox` |
| Deterministic suggestions | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED for expanded program | PA-10 suggestion contracts |
| Model relevance | **REPOSITORY VERIFIED**; separately gated | LIVE/STAGING NOT VERIFIED | exact-set relevance path; no execution authority |
| Browser Push | **REPOSITORY VERIFIED**; live/staging delivery still separate | LIVE/STAGING NOT VERIFIED | real browser permission, push egress, endpoint retirement and multi-device tests required |
| Daily Coworker | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED | timezone/DST/restart/quiet-hours controlled staging required |
| Weekly Coworker | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED | progress/deadline/meeting/follow-up controlled staging required |
| Meeting Coworker | **REPOSITORY VERIFIED** on current merged main CI #1071 | LIVE/STAGING NOT VERIFIED | real Google/Microsoft calendar reschedule/cancel/recurrence/revocation required |
| Email Coworker | **REPOSITORY VERIFIED** on current merged main CI #1071 | LIVE/STAGING NOT VERIFIED | real Gmail/Outlook duplicate/out-of-order/delayed/revoke/token/deleted-message tests required |
| Deadline Coworker | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED | threshold timing, edited deadline, overdue and restart staging required |
| Goal-driven proactivity | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED | real finite no-action/useful-action quality + cost runs required |
| Automation controls | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING UX NOT VERIFIED | edit/reconciliation/recent-activity usability required |
| Permission revalidation | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED | real revocation race exercises required |
| Context revocation | **REPOSITORY VERIFIED** on current merged main CI #1071 | STAGING NOT VERIFIED | real connector/document deletion during waits required |
| Restart recovery | **REPOSITORY VERIFIED** in repository/Temporal tests | STAGING NOT VERIFIED | real worker/API/Temporal replacement drill required |
| Provider qualification | Connector implementations **REPOSITORY VERIFIED**; live providers remain separate | **NOT VERIFIED** | controlled Google + Microsoft credentials/environment required |
| Observability | Repository trace/usage/notification paths **REPOSITORY VERIFIED**; staging trace review remains | STAGING review required | confirm traces contain IDs/usage/failure class without secrets |
| Economics | Economics framework **REPOSITORY VERIFIED**; proactive live measurement remains separate | proactive cohort measurement NOT VERIFIED | collect real completed proactive-task measurements with reviewed pricing inputs |
| Quality | Offline agent + multilingual suites **REPOSITORY VERIFIED**; human proactive cohort remains separate | human proactive cohort quality NOT VERIFIED | relevance/timing/correctness/grounding/actionability/noise/safety/reliability review |

## Required controlled-staging scenarios

The automation staging gate must not be signed until all applicable scenarios have fresh evidence from the same reviewed release:

1. simple scheduled reminder with app/browser closed, exactly one `automation_reminder` notice and zero Agent runs;
2. Daily Coworker across timezone/DST and restart;
3. Weekly Coworker using progress, deadlines, meetings and follow-ups;
4. Meeting Coworker including reschedule, cancel, recurring event and grant revocation;
5. Email Coworker including duplicate, delayed/out-of-order, deleted message, malicious content and explicit draft-only boundary;
6. Deadline Coworker including 7d/72h/24h/overdue transitions and unchanged-state suppression;
7. goal-driven finite Runtime-v3 wake-up with useful-action and no-action cases;
8. worker/API/process loss with one recovered outcome;
9. source/connector revocation before a wake-up;
10. duplicate provider event with one accepted run;
11. consequential action prepared but not executed until immutable preview + explicit approval + fresh authorization;
12. malicious external content causing no authority expansion or secret disclosure;
13. Browser Push opt-in/delivery/expiry/removal/retry/quiet-hours/owner-isolation;
14. proactive multilingual samples including Bangla and English;
15. task-economics artifact reporting cost per completed useful proactive task.

## Staging tooling checkpoint — proactive provider/read events

A dedicated staging-only evidence collector is merged through PR #278 in `scripts/staging_proactive_read_event.py` with focused regression coverage in `tests/test_staging_proactive_read_event.py`. It is fail-closed behind explicit controlled-staging and synthetic-account guards, binds evidence to the deployed runtime revision, reviewed rollout hash/release ID, reviewed provider-policy hash and deployment reference, reads only owner-scoped Shuddho staging APIs, exposes owner-scoped persisted trigger identity for evidence, verifies that the Agent run actually used a provider snapshot changed by the exercise, and never injects provider callbacks or accepts provider credentials.

Tooling repository verification is **COMPLETE**: PR #278 exact-head CI #1068 passed both `test-and-build` and heavyweight `coworker`, merged-main CI #1069 passed both required jobs on `8c5c0a3e22cfe4224a9f7a810082f2e032ec34f9`, and the subsequent PR #279 checkpoint merge is verified by current-main CI #1071 / run `36850391865`, with both required jobs passing on `55a6980d0c3906e199b9552d7f1fa4c77a2623ae`. This is still not live provider evidence. Google, Microsoft, Meeting/Email proactive flows and all other staging rows remain **NOT VERIFIED** until the probe is executed around actual approved synthetic provider changes in controlled staging.

## External blockers

No safe claim is made for real Gmail, Google Calendar, Outlook Mail, Microsoft Calendar, Web Push delivery or managed Temporal/restart behavior without controlled staging credentials and infrastructure.

The repository contains only the normal CI workflow; there is no dedicated PA-10 live-provider workflow that can be safely invoked from repository CI. Live/staging evidence therefore requires an approved controlled environment and must not be fabricated.

## Completion interpretation

If all repository PRs and merged-main CI are green while the external rows above remain unverified, the correct program statement is:

`AUTOMATION / PROACTIVE COWORKER — REPOSITORY IMPLEMENTATION COMPLETE; STAGING QUALIFICATION REMAINS.`

Do not mark the overall phase complete or enable production flags until the controlled-staging evidence and final release review satisfy the expanded `automations` release-contract gate.


## Simple reminder repository slice — 1 October 2026

This slice adds a dedicated notification-only `reminder` automation profile. It reuses Temporal daily/weekly schedules and the existing canonical occurrence ledger, emits one durable `automation_reminder` notice, keeps `run_id` null, and revalidates automation/goal authority both at occurrence admission and notification delivery. Duplicate Temporal delivery and process restart replay the same occurrence/notice; pause, cancel, stale automation revision, expiry, goal-state revocation and goal-revision changes fail closed. The profile rejects connector-read and Agent-tool authority.

The dedicated controlled-staging collector is `scripts/staging_pa10_simple_reminder.py`. The full PA-10 evidence compiler additionally rejects scheduled-reminder evidence unless it proves `agent_run_count=0`, `notification_count=1` and `notification_kind=automation_reminder`.

Repository implementation does not make the live/staging row pass. The simple-reminder staging scenario remains NOT VERIFIED until the guarded collector runs around a real Temporal occurrence on the reviewed deployed release.
