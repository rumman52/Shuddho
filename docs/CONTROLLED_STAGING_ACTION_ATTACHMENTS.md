# Controlled Staging Live Approved Email Attachments

This is the independent live gate for `SHUDDHO_ACTION_ATTACHMENTS_ENABLED`.

It intentionally sends **one synthetic email with one existing synthetic Shuddho artifact** through an explicitly authorized staging account. The script never chooses an arbitrary recent artifact: the operator must supply the exact artifact UUID through an environment variable.

## Preconditions

Use controlled staging only. The selected artifact must contain synthetic, non-confidential test data.

```bash
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_ACTION_ATTACHMENTS_ENABLED=true
SHUDDHO_STAGING_ALLOW_LIVE_ACTION_ATTACHMENTS=true
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com
SHUDDHO_STAGING_TOKEN_A=<short-lived admitted staging token>
SHUDDHO_STAGING_ACTION_ATTACHMENT_ARTIFACT_ID=<exact synthetic artifact UUID>
SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT=<explicitly authorized test recipient>
```

For Microsoft also enable `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true` and configure `SHUDDHO_STAGING_MICROSOFT_TEST_RECIPIENT`.

The staging account must already have exactly one active email connection for the selected provider.

## Run

Google:

```bash
uv run --extra coworker python scripts/staging_live_action_attachments.py \
  --provider google \
  --base-evidence /secure/release/staging-evidence.json \
  --output /secure/release/staging-evidence.action-attachments.json
```

Microsoft:

```bash
uv run --extra coworker python scripts/staging_live_action_attachments.py \
  --provider microsoft \
  --base-evidence /secure/release/staging-evidence.json \
  --output /secure/release/staging-evidence.action-attachments.json
```

Then evaluate:

```bash
uv run python scripts/staging_gate.py \
  --evidence /secure/release/staging-evidence.action-attachments.json \
  --require-actions \
  --require-action-attachments
```

## What the live gate proves

Before provider mutation it requires:

- the deployment reports attachments enabled;
- the exact operator-selected artifact exists in the authenticated owner workspace;
- the artifact uses an allowlisted type and is within the attachment byte ceiling;
- the prepared action is `email_send_with_attachments`;
- preview schema is v3 and provider-bound;
- preview SHA-256 matches the returned immutable preview;
- the exact artifact id, filename, MIME type, byte size and SHA-256 are present in the preview;
- approval scope contract v2 binds the exact connection and attachment manifest;
- attachment policy is `owned_artifacts`;
- the action remains `awaiting_approval` while unapproved;
- an intentionally wrong preview hash is rejected with HTTP 409.

The script then approves only the exact returned preview hash. A pass requires a single prepared → approved → execution-started → succeeded audit path and a provider acceptance receipt.

Provider acceptance is not a delivery/read receipt. The byte re-hash and immutable-object checks remain enforced by the worker and covered by repository tests.

## Evidence

A pass adds a timestamped `action_attachments` record. It contains no bearer token, artifact bytes, recipient content, OAuth secrets or provider response bodies.

A passing staging file is necessary but not sufficient for production activation. Run [Approved Attachment Production Activation](ACTION_ATTACHMENTS_ACTIVATION.md) after the reviewed deployment.

## Failure and rollback

Any non-success terminal state is a failed gate. For an uncertain provider outcome, inspect the provider before retrying.

Disable immediately with:

```text
SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false
```

This leaves ordinary plain-text approved actions available.
