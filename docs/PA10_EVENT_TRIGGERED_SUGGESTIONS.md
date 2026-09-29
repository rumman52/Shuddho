# PA-10 Event-Triggered Connected-Context Suggestions

This bounded slice turns already-verified PA-06 connector event intake into a
review-only in-app notice. It does not add event-triggered execution, a second
scheduler, a model call, an external notification channel, or an ExternalAction.

## Authority and consent

Event-triggered notices are default-off behind a new
`event_delivery_enabled` preference inside the existing personal-suggestion
preference document. The hierarchy is explicit:

1. deterministic personal suggestions must be enabled;
2. in-app suggestion delivery must be enabled;
3. event-triggered connected-context notices must be separately enabled;
4. master in-app notification consent must remain enabled.

The event mode is available only when PA-06 connected reads and the existing
PA-02 Notifications inbox are enabled. It adds no provider scope and no
background Agent authority.

## Trigger and data boundary

The only trigger is a connector event that has already passed PA-06 provider
identity/token checks, owner/grant/subscription binding, dedupe and cursor-sync
processing. PA-10 consumes only persisted server-held event metadata:

- owner ID;
- connector read grant ID;
- capability (email_read or calendar_read);
- event identity/timestamp.

Provider message subjects, bodies, snippets, calendar titles/descriptions,
attachments and remote instructions are not read to decide whether to notify.
The notice says only that subscribed connected context changed and asks the user
to review it before choosing whether to start work.

## Coalescing, quiet hours and durability

A stable SHA-256 source identity binds owner, grant, capability and a six-hour
event bucket. Multiple verified callbacks in the same bucket therefore enqueue
at most one notice. The existing `cw_notifications` and
`cw_notification_outbox` provide durable storage, restart recovery and leases.

The user's saved event timezone controls the existing 22:00-07:00 quiet-hours
delay. Event notices expire after 24 hours and source revalidation considers
only recent persisted connector events.

## Revalidation and failure behavior

Before outbox claim and again before delivery, the shared notification boundary
requires:

- master in-app consent;
- deterministic suggestion and delivery consent;
- event-notice consent;
- PA-06 and PA-02 capability availability;
- an active, unexpired owner-scoped connector read grant;
- a matching recent processed connector event.

Grant revocation/expiry or opt-out suppresses a pending notice. A failure in the
optional PA-10 notice consumer never changes a successful PA-06 connector sync
into a failed/retried provider event.

## Non-goals

No model-assisted relevance, email/push/SMS/collaboration delivery, provider
content classification, auto-run, auto-reply, calendar mutation or new Temporal
Schedule is included.

## Acceptance

Repository tests must establish consent hierarchy, stable event coalescing,
provider-content exclusion from notice text, quiet/durable enqueue, grant
revocation and post-claim opt-out suppression, inertness, and independence of
PA-06 sync success from PA-10 notification faults. Exact final-head CI remains
required; staging and production qualification are separate.
