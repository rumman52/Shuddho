# PA-10 bounded in-app notification digests

## User outcome and scope

The Notifications inbox offers an optional grouped view of already-delivered notices. Goal suggestions and connected-source update notices from the same workspace, kind and six-hour UTC window appear in groups of at most ten. Each group preserves every member's title, message, delivery time and read state. Automation updates and other notice kinds remain individual entries.

This is an inbox presentation and read-state slice. It does not generate a daily briefing, merge delivery receipts, delay notification delivery, inspect provider message/calendar bodies, or add a scheduler, model call, external channel, Agent run or ExternalAction. It does not complete PA-10. Broader relevance, push/messaging channels and event-triggered execution require separate implementation and qualification.

## Contract and ownership

- `GET /api/v1/notification-digests` returns `enabled` and `digests`. The existing PA-02 automations gate controls availability; disabled returns an empty list.
- Consider at most the newest 100 delivered/read, visible, unexpired owner notices. Sort deterministically by visibility, creation and ID; never cross owner/workspace/kind/window boundaries. Split large groups into ten-member chunks without duplication.
- Recheck current in-app/type consent and the registered source validator for each member. Goal revisions, dismissal, deleted/revoked resources, expired connector grants and event consent use the existing PA-10 validators. Unknown source kinds fail closed. Filtering precedes serialization and group identity.
- Digest IDs are SHA-256 over the version tag, server-held owner, workspace/kind/window key and sorted exact member IDs. Read state does not change identity. New membership produces a different identity; these IDs are scope fingerprints, not authorization tokens.
- Six-hour boundaries use UTC delivery visibility, independent of display timezone/DST. The UI shows local dates. Existing quiet-hour admission and source expiry remain authoritative; this view only uses delivered notices.
- `POST /api/v1/notification-digests/{digest_id}/read` accepts only `notification_ids`: one to ten unique UUIDs. The server derives the owner, locks its account and member rows in one transaction, and rechecks delivered/read state, visibility, expiry, consent and source validity. The exact members must reproduce one digest and its supplied ID.
- A missing/unowned member returns 404. Changed identity, withdrawn consent/source, expiry, pending/suppressed state or incompatible grouping returns `notification_digest_changed` (409), with no partial writes. Malformed IDs, duplicates, excessive members and unknown payload fields return 422.
- Successful reads change only delivered members to read. Prior read timestamps survive replay. No pending notice is delivered or resurrected, and no notification/outbox/automation/goal is created or cancelled.

## UI, compatibility and recovery

The grouped view is off by default and is a local display choice, not a delivery-consent setting. Expand a digest to inspect original notices; mark the displayed group as read or read individual members. Successful reads reload server state. A conflicted group refreshes and shows the error without claiming a partial success. Concurrent new notices are not silently included in an earlier read request.

The existing flat inbox endpoint and individual-read API remain compatible. No migration, new provider scope, release flag or worker path is needed: durable source records and delivery remain in `NotificationRepository`, `cw_notifications` and `cw_notification_outbox`. Restart reconstructs the view from these records. Roll back the API/UI slice to remove grouping while retaining all original notices and read receipts. Production gate values are not changed by this implementation.

## Acceptance evidence

Pure grouping tests cover stable identity/order, Unicode preservation, owner/workspace/kind/window separation, bounded chunks, exact membership and equivalent timezone instants. Existing automation integration tests cover real suggestion creation/delivery, restart, owner isolation, strict API payloads, exact-member atomic reads, replay, expiry, pending state, revision invalidation, dismissal, opt-out, unknown sources and the PA-02 gate. Connector tests cover a verified event notice becoming unavailable after real read-grant revocation. Client tests verify authenticated routes and exact-member bodies. Browser UI fixtures cover optional grouping, expansion, Bangla content, desktop/mobile layout, read-state refresh and stale-source conflict recovery; these mocked HTTP fixtures are not live-provider evidence.

Repository CI must pass on the final implementation/checkpoint revision. Controlled staging, live providers, production qualification and activation remain separate and unverified by this slice.
