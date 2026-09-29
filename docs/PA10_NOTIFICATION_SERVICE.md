# PA-10 First-Class In-App Notification Service

This slice separates durable in-app notification ownership from the PA-02
automation repository so later PA-10 suggestion/event/channel work can extend one
notification boundary instead of creating a parallel pipeline.

## Scope

The existing `cw_notifications` and `cw_notification_outbox` tables remain the
only durable in-app notification ledger. No migration is added.

A new `NotificationRepository` now owns:

- owner-scoped notification preferences;
- quiet-hours visibility calculation;
- durable pending notification enqueue;
- outbox claim leasing;
- delivery-time consent rechecks;
- delivered/read inbox listing;
- read acknowledgement.

The existing automation path still creates the same `automation_started`
notification, with the same message, expiry and quiet-hours behavior. It now
delegates enqueue and delivery operations to the notification service.

## Compatibility

Existing API paths are unchanged:

```text
GET /api/v1/notification-preferences
PUT /api/v1/notification-preferences
GET /api/v1/notifications
POST /api/v1/notifications/{notification_id}/read
```

For compatibility, `AutomationRepository` retains thin forwarding methods for
notification callers while new API/worker code uses the first-class
notification service directly.

The inbox admission behavior is intentionally unchanged in this extraction:
when PA-02 automations are disabled, the current notifications API remains
disabled. A later PA-10 slice may broaden that boundary only with explicit
release/compatibility review.

## Consent and authority

Consent semantics are unchanged:

- in-app delivery must be enabled;
- `automation_started` additionally requires automation-update consent;
- consent is checked before claim and again immediately before delivery;
- revoked pending notices are suppressed and their outbox rows are closed.

This refactor grants no new authority. It adds no Agent run, Temporal schedule,
ExternalAction, provider call, model call, push/email/messaging channel, or
automatic suggestion delivery.

## Why this slice exists

PA-10 now has deterministic suggestions and in-app notification controls, but
notification ownership was still embedded in `AutomationRepository`. Extending
that class for future suggestion/event delivery would couple unrelated PA-10
capabilities to PA-02 scheduling.

This extraction establishes one reusable notification service before any future
proactive delivery work.

## Verification

Repository tests continue to cover:

- occurrence notification dedupe;
- durable outbox lease/reclaim;
- owner-scoped preferences;
- suppression before claim;
- revocation after claim but before delivery;
- delivered/read inbox behavior;
- strict preference schema validation.

Additional coverage verifies that the container exposes the first-class
notification repository while existing automation forwarding remains
compatible.

Repository CI is implementation evidence only. Controlled staging and
production qualification remain separate.
