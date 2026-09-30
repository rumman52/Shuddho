# PA-10 bounded Browser Push

**Status: implementation slice; default-off and not production-qualified.**

This slice adds the first external PA-10 notification channel without creating another scheduler, notification ledger, model trigger or action authority. Browser Push is a projection of an already-authorized notice after the shared `NotificationRepository` has delivered that notice to the in-app inbox. PostgreSQL remains the durable notification and channel-receipt authority; Temporal remains the only due-time scheduler.

## User outcome

A user who explicitly enables Browser Push for the account and grants browser notification permission can receive a generic device/browser alert after an eligible Shuddho in-app notice becomes visible. The alert opens Shuddho so the actual notice can be reviewed inside the authenticated workspace.

The push payload intentionally does not copy the notice title/message or connected-provider content. It contains generic Shuddho text, an owned notification identifier and a same-origin review path.

## Authority and consent

Browser Push requires all of the following:

- the default-off deployment gate `SHUDDHO_BROWSER_PUSH_ENABLED=true`;
- the existing PA-02 automation/in-app notification boundary;
- `in_app_enabled=true`;
- the separate account preference `browser_push_enabled=true`;
- browser notification permission; and
- an active owner-scoped browser Push subscription registered through the authenticated Shuddho API.

Enabling personal suggestions, event notices, model relevance or in-app delivery does not enable Browser Push. Turning Browser Push off suppresses pending channel receipts without pausing goals, automations or the in-app inbox. Turning the in-app inbox off also requires Browser Push off.

Browser Push does not create an Agent run, automation, ExternalAction, provider mutation, model call or new notification candidate.

## Durable state

Migration 0037 adds:

- `cw_browser_push_subscriptions`: owner, stable endpoint hash, encrypted subscription material, optional browser expiry, active state and timestamps;
- `cw_browser_push_deliveries`: owner, notification, subscription, delivery state, lease, bounded attempts, push-service HTTP status, error code and provider-acceptance time.

Subscription endpoint, `p256dh` and authentication secret are encrypted at rest with a dedicated backend key. The endpoint hash supports idempotent owner-scoped updates without exposing the endpoint as ordinary metadata.

A unique `notification_id + subscription_id` constraint makes channel projection durable and deduplicated.

## Delivery state machine

1. The normal notification outbox applies current in-app consent, quiet hours, expiry and registered source validation.
2. Only an in-app notice that reaches `delivered` may create browser-push receipt rows for currently active subscriptions.
3. The worker claims pending push receipts with a bounded lease and rechecks:
   - owner/account preferences;
   - deployment gate;
   - subscription activity/expiry;
   - notification delivery/read state and expiry; and
   - the registered source validator, including goal revision/dismissal or connector-read revocation where applicable.
4. The sender uses Web Push message encryption and VAPID authentication. Egress is restricted to reviewed HTTPS push-service hosts; redirects are disabled.
5. HTTP 2xx is recorded only as `provider_accepted`. It does not prove device display, user reading or task completion.
6. 404/410 retires the subscription. 429/503 is retried with a bounded attempt count. A transport exception after dispatch becomes `outcome_unknown` and is not blindly resent.
7. Opt-out or source revocation before send suppresses the pending receipt.

A notice marked `read` in the Shuddho inbox is still an already-delivered notice; read state does not by itself revoke a separately consented pending push.

## Web client

The Automations/Notifications workspace exposes a separate **Browser notifications on this account and device** control. Enabling it:

- checks deployment availability;
- requests browser permission;
- registers the same-origin `/push-sw.js` service worker;
- creates or reuses one Push API subscription using the server-provided public VAPID key;
- registers that subscription with the authenticated API; and
- then persists the separate account opt-in.

The service worker accepts only the generic encrypted payload and constrains notification-click navigation to the Shuddho origin.

## Release and rollback

`browser_push` is a separate controlled-release capability with:

- kill switch: `SHUDDHO_BROWSER_PUSH_ENABLED=false`;
- dependency: `automations`;
- independent staging evidence;
- production activation/ledger identity schema 29.

Repository implementation and CI are not live qualification. Controlled staging must prove real browser permission/subscription creation, approved push-service egress, owner isolation, encrypted subscription storage, generic payloads, duplicate suppression, opt-out/source-revocation races, restart recovery, 404/410 retirement, bounded 429/503 recovery and rollback. No live push is performed by repository CI.

## Non-goals

This slice does not add:

- email notifications;
- Slack/Teams/WhatsApp or other collaboration/messaging delivery;
- native mobile-app push providers;
- provider-content text in push payloads;
- model-generated push messages;
- event-triggered Agent execution;
- autonomous actions;
- a second scheduler or notification ledger.

Those remain separate PA-10 work and require their own consent, privacy, provider and release contracts.
