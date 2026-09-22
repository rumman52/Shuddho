# Controlled Staging Live Microsoft Approved-Action Validation

This is the Microsoft-provider release gate that must pass before Shuddho exposes Microsoft/Outlook connection controls to users.

It verifies the deployed Microsoft Graph connector with explicitly authorized staging accounts and recipients. The exercise intentionally performs **one real Microsoft Graph email send and one real calendar event creation**.

## Preconditions

Use controlled staging only.

Required backend/deployment configuration:

```bash
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true
SHUDDHO_STAGING_ALLOW_LIVE_MICROSOFT_ACTIONS=true
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<short-lived staging user token>
SHUDDHO_STAGING_MICROSOFT_TEST_RECIPIENT=<explicitly authorized test recipient>
```

The staging user must already have exactly one active Microsoft Email connection and one active Microsoft Calendar connection through Shuddho's provider-bound OAuth flow.

Use only accounts/recipients that explicitly agreed to the test. Do not use customer addresses.

## Run

```bash
uv run --extra coworker python scripts/staging_live_microsoft_actions.py \
  --base-evidence /secure/path/staging-evidence.json \
  --output /secure/path/staging-evidence.microsoft-actions.json
```

Then evaluate the independent Microsoft conditional gate:

```bash
uv run python scripts/staging_gate.py \
  --evidence /secure/path/staging-evidence.microsoft-actions.json \
  --require-actions \
  --require-microsoft-actions
```

The existing Google `actions` evidence and the Microsoft `microsoft_actions` evidence are deliberately separate. Passing Google does not approve Microsoft.

## What is proven before provider mutation

For both email and calendar, the exercise proves:

- the prepared action is `awaiting_approval`;
- no approval timestamp or provider receipt exists;
- the immutable preview hashes to the returned preview hash;
- the preview is version 2;
- provider is exactly `microsoft`;
- the backend-generated `approval_scope` is bound to Microsoft, the exact connection, and the exact payload digest;
- the preview payload exactly matches the synthetic submitted payload;
- waiting does not auto-approve or auto-execute;
- an intentionally incorrect preview hash is rejected with HTTP 409;
- rejected approval leaves the action unapproved;
- audit history contains no approval/execution event before exact approval.

Only then is the exact returned preview hash approved.

## Microsoft email validation

The synthetic email:

- sends from the connected Microsoft account;
- addresses the connected account in `To`;
- uses the explicit staging recipient in `Bcc`;
- includes Unicode/Bangla content;
- contains only synthetic plain text.

A pass requires:

- exactly one prepared/approved/execution-started/succeeded audit path;
- immutable preview/hash through completion;
- action state `succeeded`;
- receipt provider `microsoft`;
- receipt status `accepted_by_microsoft_graph`;
- valid confirmation timestamp.

The Graph response confirms API acceptance only. It is not a delivery or read receipt, and the staging validator does not invent a provider message ID.

## Microsoft calendar validation

The exercise creates one synthetic event in the connected account's default calendar with the explicit staging recipient as attendee.

A pass requires:

- the same exact-approval and single-execution audit path;
- action state `succeeded`;
- receipt provider `microsoft`;
- receipt status `event_created`;
- calendar `primary`;
- non-empty Graph event id;
- Shuddho transaction binding beginning with `shuddho-`;
- valid confirmation timestamp.

The provider adapter already checks the returned subject, location, attendees, and UTC-normalized start/end instants against the approved payload before producing this receipt.

## Evidence and cleanup

Only after both actions pass is `microsoft_actions` promoted to `passed`.

The evidence file contains only concise status text and action IDs/provider statuses. It does not contain access tokens, refresh tokens, OAuth codes, Microsoft response bodies, email/calendar bodies, or connector secrets.

After retaining staging evidence:

1. delete the synthetic calendar event;
2. delete/archive the synthetic staging email as appropriate;
3. retain the action/audit evidence under the approved staging evidence-retention policy.

## Failure policy

Any `failed`, `expired`, `cancelled`, or `outcome_unknown` result is a gate failure.

For uncertain Microsoft outcomes, do not immediately create another action. Verify the provider state manually first. This increment intentionally does not claim deterministic Graph reconciliation after a lost mutation response.

Do not manually mark `microsoft_actions` passed.

## Rollback

Set:

```text
SHUDDHO_MICROSOFT_ACTIONS_ENABLED=false
```

on API and workers and redeploy current code.

If all external actions must be disabled, also set:

```text
SHUDDHO_ACTIONS_ENABLED=false
```

Do not remove migration 0012 or action history tables as routine rollback.
