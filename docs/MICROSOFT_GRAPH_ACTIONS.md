# Microsoft Graph Email and Calendar Adapter

This increment adds Microsoft as the second consequential-action provider behind Shuddho's connector-neutral approval boundary.

It is **disabled by default**. The frontend provider selector/callback code is also separately gated and remains hidden unless `VITE_MICROSOFT_ACTIONS_ENABLED=true`.

## Supported provider surface

When `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true`, the backend can use delegated Microsoft Graph permissions for:

- email sending with `Mail.Send`;
- calendar event creation with `Calendars.ReadWrite`;
- identity verification with `User.Read`;
- offline refresh through `offline_access`.

The adapter uses the Microsoft identity platform authorization-code flow with PKCE and the configured tenant boundary.

The implementation calls fixed Microsoft endpoints only:

- Microsoft identity authorize/token endpoints under the configured tenant;
- `GET /v1.0/me`;
- `POST /v1.0/me/sendMail`;
- `POST /v1.0/me/events`.

No arbitrary Graph URL is accepted.

## Same Shuddho action boundary

Microsoft does not introduce a second approval system.

The sequence remains:

```
typed action
→ registered ActionSpec
→ immutable v2 preview
→ server-owned approval_scope
→ explicit user approval
→ committed execution claim
→ provider mutation
→ confirmed receipt or outcome_unknown
```

The approval scope binds the provider, connection, Microsoft account identity, payload SHA-256, recipients/destinations, policy and expiry.

A Microsoft OAuth state is also bound to provider=`microsoft`. A Google callback cannot finish a Microsoft OAuth attempt, and vice versa.

## Email behavior

`POST /me/sendMail` may return an empty successful response. A successful HTTP response is recorded only as Microsoft Graph acceptance; it is not represented as a delivery/read receipt.

If the HTTP outcome is uncertain after the execution claim is committed, Shuddho records `outcome_unknown` and does not issue another send.

## Calendar behavior

Events are created in the signed-in user's default calendar using `POST /me/events`.

The event payload includes a stable Shuddho-derived `transactionId`, no reminder, exact approved subject/content/location/times and approved attendees.

A successful response is checked against the approved subject, location, UTC-normalized start/end instants and attendee addresses before the receipt is accepted.

After a lost create response, this increment does not claim deterministic Microsoft reconciliation. The action remains `outcome_unknown`; Shuddho does not blindly repeat the mutation.

## Configuration

Backend-only configuration:

```text
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_MICROSOFT_ACTIONS_ENABLED=false
SHUDDHO_MICROSOFT_CLIENT_ID=
SHUDDHO_MICROSOFT_CLIENT_SECRET=
SHUDDHO_MICROSOFT_TENANT=organizations
SHUDDHO_MICROSOFT_REDIRECT_URI=https://YOUR-FRONTEND-DOMAIN/oauth/microsoft/callback
```

The redirect URI must be HTTPS outside local development and must use the exact `/oauth/microsoft/callback` frontend path.

Migration `0012` adds the provider identity to OAuth attempts. Existing OAuth attempts migrate as `google`.

## Release boundary

Do not enable Microsoft in production from this PR alone.

Before UI exposure or cohort use, complete the [controlled live Microsoft staging gate](CONTROLLED_STAGING_LIVE_MICROSOFT_ACTIONS.md).

1. configure a Microsoft Entra app with the required delegated permissions;
2. run an explicit staging OAuth test with authorized Microsoft test accounts;
3. verify denied/partial consent, token refresh and identity changes;
4. verify Unicode email recipients/content and Microsoft calendar invitations;
5. exercise worker loss and uncertain email/event outcomes;
6. confirm no second provider mutation occurs after an uncertain result;
7. record provider latency/failure/unknown-outcome evidence;
8. verify the frontend provider picker/callback with `VITE_MICROSOFT_ACTIONS_ENABLED=true` in the approved rollout environment.

Frontend exposure requires both backend Microsoft enablement and the frontend rollout flag. Keep `VITE_MICROSOFT_ACTIONS_ENABLED=false` until the independent `microsoft_actions` staging gate is recorded as passed. The callback validates Microsoft login origin, tenant-shaped authorize path, exact returned state, and exact current-site `/oauth/microsoft/callback` redirect before navigation. OAuth code/state are not persisted beyond the tab-scoped connection handshake.

Official Microsoft references used for this adapter:

- Microsoft identity platform authorization-code flow;
- Microsoft Graph `user: sendMail`;
- Microsoft Graph `user: post events`;
- Microsoft Graph `GET /me`;
- Microsoft Graph permissions reference for `Mail.Send`, `Calendars.ReadWrite`, and `User.Read`.
