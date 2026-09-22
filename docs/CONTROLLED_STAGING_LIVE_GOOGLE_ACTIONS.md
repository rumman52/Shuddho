# Controlled Staging Live Google Approved-Action Validation

This is the final external-provider gate before the Shuddho Coworker staging GO/NO-GO review.

It verifies the deployed Google connector with explicitly authorized staging accounts and recipients. The exercise intentionally performs **one real Gmail send and one real primary-calendar event creation**.

## Preconditions

Use controlled staging only.

Required backend/deployment configuration:

```bash
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_STAGING_ALLOW_LIVE_GOOGLE_ACTIONS=true
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<short-lived staging user token>
SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT=<explicitly authorized test recipient>
```

The staging user must already have exactly one active Google Email connection and one active Google Calendar connection through Shuddho's normal OAuth flow.

Use only accounts/recipients that have explicitly agreed to the test. Do not use customer addresses.

## Run

```bash
uv run --extra coworker python scripts/staging_live_google_actions.py \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.actions.json
```

## What is proven before any provider mutation

For both email and calendar, the exercise first proves:

- the action is created in `awaiting_approval`;
- there is no approval timestamp or provider receipt;
- the returned immutable preview hashes to the returned `preview_hash`;
- the preview payload exactly matches the synthetic submitted payload;
- waiting does not auto-approve or auto-execute the action;
- approving with an intentionally wrong preview hash is rejected with HTTP 409;
- the rejected approval leaves the action unapproved;
- audit history contains no approval/execution event before exact approval.

Only then does the exercise submit the exact returned preview hash.

## Gmail validation

The synthetic email:

- sends from the connected Google account;
- addresses the connected account in `To`;
- uses the explicit staging recipient in `Bcc`;
- contains Unicode/Bangla in the subject;
- contains a plain-text synthetic body.

A pass requires:

- exact approval is recorded;
- preview/hash remain unchanged after approval and completion;
- exactly one `action.prepared`, `action.approved`, `action.execution_started`, and `action.succeeded` audit event exists;
- action state is `succeeded`;
- receipt provider is `google`;
- receipt status is `accepted_by_gmail`;
- provider message id is present;
- Shuddho's deterministic Message-ID matches the action UUID;
- receipt confirmation timestamp is valid.

The Gmail receipt confirms provider acceptance, not delivery or reading.

## Calendar validation

The exercise creates one synthetic event 15 minutes in the future on the connected account's primary calendar, with the explicit staging recipient as attendee.

A pass requires:

- the same exact-approval and single-execution audit sequence;
- action state is `succeeded`;
- receipt provider is `google`;
- receipt status is `event_created`;
- calendar is `primary`;
- provider event id is exactly Shuddho's stable event ID derived from the action UUID;
- receipt confirmation timestamp is valid.

The implementation already verifies returned Google event fields, extended private approval markers, attendees, content and times before generating this receipt.

## Evidence and cleanup

Only after both actions pass is the conditional `actions` staging evidence promoted to `passed`.

The evidence file does not contain OAuth tokens, refresh tokens, email/calendar payload bodies, Google response bodies or secrets.

After retaining action IDs, receipts, audit evidence and deployment references:

1. delete the synthetic calendar event from the staging account;
2. delete/archive the synthetic test email as appropriate;
3. keep the action ledger evidence according to the approved staging evidence-retention policy.

## Failure policy

Any `failed`, `expired`, `cancelled`, or `outcome_unknown` result is a staging-gate failure. Do not manually mark the gate passed.

An uncertain Gmail result must be inspected in the connected account's Sent folder before another test send is attempted. Calendar uncertainty may use the existing read-only reconciliation path.

## Rollback

Set `SHUDDHO_ACTIONS_ENABLED=false` on API and workers and redeploy current code.

Do not remove action tables or old workflow definitions as part of routine rollback. Already issued Google requests cannot be recalled.
