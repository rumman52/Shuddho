# Approved Calendar Reminders

This Wave D increment adds one explicit reminder to a user-created calendar action while preserving Shuddho's existing consequential-action approval boundary.

The capability is disabled by default:

```dotenv
SHUDDHO_ACTION_REMINDERS_ENABLED=false
```

It also requires `SHUDDHO_ACTIONS_ENABLED=true`.

## Action contract

The new registered action kind is:

```text
calendar_create_with_reminder
```

It uses the same owned calendar connection and existing Google/Microsoft calendar scopes as `calendar_create`. No mailbox-read permission, calendar-list permission expansion, background scheduling service, recurrence engine, update route, or deletion route is added.

The user may choose exactly one reminder from the bounded set:

- 5, 10, 15, or 30 minutes before start;
- 1 or 2 hours before start;
- 1 day before start.

The server rejects arbitrary reminder values.

## Approval boundary

The reminder is not inferred from model text. It is selected explicitly in the action UI.

The immutable preview binds:

- exact provider and owned connection/account;
- event title, description, location and attendees;
- timezone-aware start/end timestamps;
- exact reminder minutes;
- `reminders=single_explicit` policy;
- guest-notification and primary-calendar policy;
- approval expiry.

The reminder minutes are part of the payload SHA-256 inside the v2 approval scope. Changing the reminder therefore invalidates the approved preview and requires a fresh preview/approval.

Agent action proposals intentionally remain reminder-blind in this increment. Their schema continues to accept only normal `calendar_create`, so model output cannot silently add a reminder. Agent-run action attachment is also fail-closed: only legacy `email_send` and `calendar_create` may be attached to an Agent run, so a reminder action stays under direct user review end to end.

## Provider execution

Google Calendar receives one explicit popup override with the approved minute value and `useDefault=false`. Receipt validation requires the returned reminder object to exactly match the approved payload.

Microsoft Graph receives `isReminderOn=true` and the exact approved `reminderMinutesBeforeStart`. Receipt validation requires both fields to match.

Normal `calendar_create` remains unchanged and explicitly carries no reminder.

## Unknown outcomes and idempotency

The existing durable action claim, approval hash, provider-specific idempotency/reconciliation behavior and audit ledger are reused. Adding a reminder does not create a second scheduler or retry path.

Google recovery may reconcile the deterministic event ID exactly as normal calendar creation does. Microsoft retains the existing no-blind-retry rule after an uncertain mutation result.

## Release boundary

Shipping this code does not authorize production reminders.

The controlled rollout manifest understands `action_reminders` and its exact kill switch:

```text
SHUDDHO_ACTION_REMINDERS_ENABLED=false
```

but the release gate intentionally returns `action_reminders_release_gate_pending` if a reviewed production rollout attempts to set `action_reminders=true`.

The next release-safety increment must add independent live Google/Microsoft reminder validation, production activation evidence, and release-ledger/scale/recovery consumption before the flag can be enabled for a controlled cohort.
