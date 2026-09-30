# PA-10 Automation / Proactive Coworker Evidence Matrix

This matrix separates implementation, repository verification, live-provider verification, staging qualification, production qualification and activation. A stronger state is never inferred from a weaker one.

## Repository scope

| Capability | Repository state | Live / staging state | Evidence / remaining gate |
| --- | --- | --- | --- |
| Durable scheduling | Implemented; CI required on final stack | NOT VERIFIED in controlled staging for this expanded PA-10 scope | PA-02 Temporal schedule/reconciliation, occurrence ledger and recovery tests |
| Occurrence dedupe | Implemented; repository tests | NOT VERIFIED in controlled staging | canonical UTC occurrence keys; event IDs; meeting snapshot/start identity; deadline urgency identity |
| Pause / resume / cancel | Implemented; repository tests | NOT VERIFIED in controlled staging | revisioned automation state + reconciliation |
| Connected events | Implemented; repository tests | LIVE NOT VERIFIED | authenticated provider intake, stable event ID, owner/grant/subscription checks |
| Notification outbox | Implemented; repository tests | STAGING NOT VERIFIED | shared `NotificationRepository`, `cw_notifications`, `cw_notification_outbox` |
| Deterministic suggestions | Implemented / existing repository coverage | STAGING NOT VERIFIED for expanded program | PA-10 suggestion contracts |
| Model relevance | Implemented / separately gated | LIVE/STAGING NOT VERIFIED | exact-set relevance path; no execution authority |
| Browser Push | Implemented / existing repository coverage | LIVE/STAGING NOT VERIFIED | real browser permission, push egress, endpoint retirement and multi-device tests required |
| Daily Coworker | Implemented / repository tests | STAGING NOT VERIFIED | timezone/DST/restart/quiet-hours controlled staging required |
| Weekly Coworker | Implemented / repository tests | STAGING NOT VERIFIED | progress/deadline/meeting/follow-up controlled staging required |
| Meeting Coworker | Implemented / repository tests | LIVE/STAGING NOT VERIFIED | real Google/Microsoft calendar reschedule/cancel/recurrence/revocation required |
| Email Coworker | Implemented; exact-head CI passed before merge | LIVE/STAGING NOT VERIFIED | real Gmail/Outlook duplicate/out-of-order/delayed/revoke/token/deleted-message tests required |
| Deadline Coworker | Implemented on PR stack; CI required | STAGING NOT VERIFIED | threshold timing, edited deadline, overdue and restart staging required |
| Goal-driven proactivity | Implemented on PR stack; CI required | STAGING NOT VERIFIED | real finite no-action/useful-action quality + cost runs required |
| Automation controls | Implemented on PR stack; CI required | STAGING UX NOT VERIFIED | edit/reconciliation/recent-activity usability required |
| Permission revalidation | Implemented; repository tests | STAGING NOT VERIFIED | real revocation race exercises required |
| Context revocation | Implemented; repository tests | STAGING NOT VERIFIED | real connector/document deletion during waits required |
| Restart recovery | Implemented; repository/Temporal tests | STAGING NOT VERIFIED | real worker/API/Temporal replacement drill required |
| Provider qualification | Connector implementations exist | **NOT VERIFIED** | controlled Google + Microsoft credentials/environment required |
| Observability | Existing run/decision/usage/notification evidence + automation activity view | STAGING review required | confirm traces contain IDs/usage/failure class without secrets |
| Economics | Existing PA-11 task-economics evidence framework | proactive cohort measurement NOT VERIFIED | collect real completed proactive-task measurements with reviewed pricing inputs |
| Quality | Existing offline agent + multilingual quality suites | human proactive cohort quality NOT VERIFIED | relevance/timing/correctness/grounding/actionability/noise/safety/reliability review |

## Required controlled-staging scenarios

The automation staging gate must not be signed until all applicable scenarios have fresh evidence from the same reviewed release:

1. simple scheduled reminder with app/browser closed and exactly one notice;
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

## External blockers

No safe claim is made for real Gmail, Google Calendar, Outlook Mail, Microsoft Calendar, Web Push delivery or managed Temporal/restart behavior without controlled staging credentials and infrastructure.

The repository contains only the normal CI workflow; there is no dedicated PA-10 live-provider workflow that can be safely invoked from repository CI. Live/staging evidence therefore requires an approved controlled environment and must not be fabricated.

## Completion interpretation

If all repository PRs and merged-main CI are green while the external rows above remain unverified, the correct program statement is:

`AUTOMATION / PROACTIVE COWORKER — REPOSITORY IMPLEMENTATION COMPLETE; STAGING QUALIFICATION REMAINS.`

Do not mark the overall phase complete or enable production flags until the controlled-staging evidence and final release review satisfy the expanded `automations` release-contract gate.
