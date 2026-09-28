# PA-10 In-App Notification Consent

This slice adds a bounded user-control foundation for PA-10 proactive behavior by
extending Shuddho's existing durable in-app notification pipeline. It does not
create a second scheduler, notification ledger, external channel, model-driven
suggestion engine, or consequential-action authority.

## Scope

The existing PA-02 automation notification path remains the only durable
notification store and outbox. Account preferences now carry a reserved
`notifications` object with two reviewed booleans:

- `in_app_enabled`: master consent for in-app personal-agent notifications.
- `automation_updates_enabled`: consent for `automation_started` notices.

Both default to `true` only when no notification preference has ever been
stored, preserving the behavior of existing accounts. Once a notification
preference object exists, missing or malformed booleans fail closed as disabled.

The API exposes:

```text
GET /api/v1/notification-preferences
PUT /api/v1/notification-preferences
```

Only the authenticated owner can read or change the account-scoped values.

## Delivery boundary

Consent is checked twice:

1. when an eligible durable notification outbox row is claimed;
2. immediately before the claimed notification is marked delivered.

If consent is absent at either point, the notification becomes `suppressed`,
the outbox row is closed, and the item never appears in the delivered/read
inbox. This second check prevents an opt-out that happens after claim from being
ignored.

Suppression affects the notice only. It does not pause or cancel a persistent
goal, Temporal schedule, accepted Agent run, or any other durable work.

## Preference compatibility

Coworker writing preferences and notification preferences share the existing
account JSON preference record. Writing-preference updates merge their reviewed
fields instead of replacing the complete JSON document, so they cannot silently
erase notification consent.

No database migration is required for this bounded slice.

## UI

The existing Automations workspace exposes two controls:

- Show personal-agent notifications in Shuddho.
- Scheduled-work updates.

The UI states explicitly that turning notices off does not stop scheduled work
and grants no external-action authority.

## Security and authority

This slice adds no provider credential, email/push/messaging channel, browser
authority, transaction operation, ExternalAction type, planner tool, or model
call. Unknown preference fields are rejected by the strict API schema.

Broader PA-10 work remains separate, including relevance-ranked proactive
suggestions, event-triggered suggestions, mobile/browser push, collaboration
channels, channel-specific consent and delivery receipts.

## Verification

Repository tests cover:

- existing notification delivery remains enabled by default;
- owner-scoped notification preferences;
- preservation across later writing-preference updates;
- suppression before outbox claim;
- consent revocation after claim but before delivery;
- absence of suppressed items from the inbox;
- rejection of unreviewed preference/channel fields.

Operational staging and production activation are separate from repository
implementation and CI.
