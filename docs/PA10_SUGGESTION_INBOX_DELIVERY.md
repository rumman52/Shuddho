# PA-10 Deterministic Suggestion-to-Inbox Delivery

This bounded slice delivers already-defined deterministic personal suggestions
through the existing durable in-app notification service. It adds no second
scheduler, model call, provider channel, autonomous Agent run or ExternalAction.

## Consent and release boundary

Suggestion preview and suggestion delivery are separate permissions.
`delivery_enabled` is default-off, requires preview to remain enabled, and is
also subordinate to the existing master in-app notification preference.

The current Notifications inbox remains gated by PA-02 Automations. This slice
does not broaden that release boundary.

## Durable identity and timing

Migration 0036 adds nullable `source_kind` and `source_id` to
`cw_notifications` plus owner/source uniqueness. Automation notices leave both
fields null. Suggestion notices bind `source_kind=personal_suggestion` to the
existing 64-character revision-bound deterministic suggestion digest.

The existing `cw_notification_outbox` supplies lease/retry/restart recovery.
Future goal reviews are pre-enqueued at the start of the existing 48-hour
relevance window and deadlines at the existing seven-day window. Context-ready
suggestions may be visible immediately. The shared quiet-hours helper delays
visibility during 22:00-07:00 in the goal timezone.

## Revalidation

Before claim and immediately before delivery, source-bound notices recompute
the owner-scoped deterministic candidate. A pending notice is suppressed when
the exact suggestion is no longer valid, including goal revision/state change,
dismissal, delivery/master opt-out, active-automation changes, a linked run for
the exact goal revision, or loss of authorized owner-scoped context.

Suppression does not alter goals, automations, runs or external-action authority.

## Non-goals

No push/email/SMS/collaboration delivery, model-assisted relevance, provider
action, autonomous execution, new Temporal Schedule, or production activation
is added.

## Acceptance

Tests must prove separate default-off delivery consent, stable source dedupe,
durable inbox delivery, dismissal/revision invalidation, pre-delivery opt-out
rechecks, zero Agent/Automation creation from delivery, migration compatibility,
and preservation of existing automation notifications.
