# PA-10 bounded proactive Meeting Coworker

**Status: repository implementation slice; default-off behind the existing automation/runtime/connector gates.**

## User outcome

A user can bind one active persistent goal to one explicitly authorized calendar-read grant and choose a preparation window. Temporal periodically wakes a bounded scan in the automation timezone. When a synchronized calendar event enters that window, Shuddho admits at most one Meeting Coworker run for that exact calendar snapshot/start-time identity.

The run uses the existing `meeting.prepare` work service to prepare a private agenda, talking points, questions, risks and outstanding actions. It may include still-authorized goal documents plus deterministically related snapshots from explicitly selected email-read grants.

## Authority and trust boundary

Meeting Coworker does not create a second scheduler, notification store, connector framework or write-authority path.

- Temporal remains the durable wake-up authority.
- PostgreSQL remains the automation, occurrence, Agent-run and notification ledger.
- The calendar grant must be owner-bound, active, unexpired, `calendar_read`, scoped to `agent_context -> planner_context`, and have an active/pending/renewing provider subscription.
- Optional related-email grants must independently pass the same execution-time checks and be `email_read`.
- Provider content remains untrusted data and cannot grant tools or alter system policy.
- Runtime v3 persists `tool_allowlist=["meeting.prepare"]`; the proactive run has no ExternalAction IDs.
- Email send, calendar writes, invitations, publishing, booking, purchase, payment and negotiation commitment remain outside this authority and continue to require their existing explicit approval boundaries.

## Exact context scope

Migration 0041 adds:

- `cw_agent_runs.connector_snapshot_ids`;
- `cw_automation_occurrences.trigger_snapshot_id`;
- `cw_automation_occurrences.trigger_start_at`.

Meeting admission freezes the exact active calendar snapshot. Optional email context is selected deterministically from explicitly authorized email grants using meeting-title/attendee metadata and is frozen by snapshot ID. Context retrieval filters connected data to those exact snapshot IDs rather than exposing unrelated events/messages from the same grant.

## Deduplication and recovery

A meeting occurrence identity is derived from owner + automation + automation revision + calendar snapshot + canonical meeting start instant. Repeated scans therefore reuse one occurrence/run.

An `accepting` occurrence is reclaimable after the existing durable lease. Recovery retains the calendar snapshot/start identity, so a worker restart resumes the same meeting rather than discovering arbitrary new work.

Cancellation or a changed meeting start fails closed before admission. The exact synchronized snapshot is rechecked before the start notification is committed. The run itself has only private preparation authority.

## Notifications

Start and verified-completion notices reuse the existing notification repository/outbox, quiet-hours calculation, consent and Browser Push mirror path. Copy is generic and does not leak provider content. Completion notification identity is deterministic, so repeated completion handling produces one logical notice.

## Qualification boundary

Repository implementation and CI do not equal live-provider or staging qualification. Controlled staging still must prove:

- Google Calendar and Microsoft Calendar event synchronization;
- preparation-window timing and timezone/DST behavior;
- recurring meetings and changed occurrence times;
- cancellation before preparation;
- optional authorized email/document context;
- grant/subscription revocation;
- worker/API restart recovery;
- exact one-run/one-notification behavior;
- quiet hours and Browser Push delivery when separately enabled.

No production activation is introduced by this slice.
