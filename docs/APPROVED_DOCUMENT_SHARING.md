# Approved Google Drive Document Sharing

Status: **implemented and production-release-qualified for a reviewed controlled cohort; disabled by default**.

This Wave D increment adds one deliberately narrow consequential action: an authenticated user may share **one existing immutable Shuddho artifact** with **one exact email address** as a Google Drive **reader**.

## Authority boundary

The registered action is `document_share`.

It is intentionally narrower than a general Drive integration:

- Google only in v1;
- OAuth scope is exactly `https://www.googleapis.com/auth/drive.file`;
- no broad `drive`, `drive.readonly`, or metadata-wide scope;
- no Drive folder browsing or remote-file picker;
- no public/anyone links;
- no writer/commenter/owner grants;
- no domain/group sharing;
- no contact or directory lookup;
- no recipient-name resolution;
- no Agent tool or Agent action proposal for document sharing.

The source must already be an owner-scoped Shuddho artifact. The immutable action preview binds its artifact ID, filename, content type, byte size and SHA-256 together with the exact recipient and reader-only policy. Immediately before execution the worker reads the private object and re-checks size and SHA-256.

## Provider sequence

After explicit approval, the Google adapter:

1. uploads the exact artifact as a new Drive file;
2. writes app-private `appProperties` containing the Shuddho action ID, approval hash, artifact ID and artifact SHA-256;
3. creates one `user` permission with role `reader` and recipient notification enabled;
4. accepts success only when the returned permission matches the exact approved recipient and role.

A provider failure after upload is treated as an uncertain external mutation, never a clean failure. Shuddho does not blindly repeat it.

Read-only reconciliation searches for the app-created file using the code-owned `shuddhoAction` app property and then lists that file's permissions. It confirms success only when exactly one matching reader permission for the approved recipient exists. Reconciliation never creates another file or permission.

## Limits

- exactly one artifact;
- exactly one recipient;
- maximum artifact size: 8 MiB;
- allowed artifact formats: PDF, DOCX, PPTX, XLSX, TXT;
- execution remains subject to the existing daily action quota and approval/execution TTLs.

## Configuration

```text
SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false
```

The flag requires both `SHUDDHO_ACTIONS_ENABLED=true` and `SHUDDHO_ARTIFACT_SERVICES_ENABLED=true`.

When the flag is false, Drive OAuth cannot be started and queued document-share actions cancel before provider mutation. Existing action history remains readable.

## Production qualification

Implementation alone still does not authorize global enablement. A production rollout may declare `action_document_sharing=true` only when all of the following are true:

1. the rollout also enables `actions` and `artifact_services`;
2. the exact rollback switch is `SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false`;
3. guarded live Google Drive evidence has passed through `scripts/staging_live_document_sharing.py`;
4. `scripts/action_document_sharing_activation.py` binds that evidence to the reviewed rollout, deployed source revision, fresh operator health, exact runtime manifest, and cohort ceiling;
5. the activation is appended to the HMAC-protected release ledger as schema-v12 `action_document_sharing_verified`;
6. any later cohort expansion emits schema-v7 scale evidence referencing that exact ledger-attested activation;
7. any recovery after a global rollback runs a **fresh post-rollback** document-sharing activation and records a new schema-v12 attestation before schema-v7 recovery evidence may pass.

The feature remains disabled by default. Qualification makes it eligible for controlled activation; it does not bypass change review, cohort admission, or operator health gates.

### Controlled staging

Use a dedicated staging Google account, a synthetic Shuddho artifact, and a synthetic test recipient. Never use customer data.

```bash
SHUDDHO_STAGING_ALLOW_LIVE_DOCUMENT_SHARING=true \
SHUDDHO_STAGING_API_BASE_URL=https://staging-api.example.com \
SHUDDHO_STAGING_TOKEN_A=<short-lived-staging-token> \
SHUDDHO_STAGING_DOCUMENT_SHARE_ARTIFACT_ID=<synthetic-owned-artifact-id> \
SHUDDHO_STAGING_GOOGLE_TEST_RECIPIENT=<synthetic-recipient@example.test> \
uv run --extra coworker python scripts/staging_live_document_sharing.py \
  --base-evidence staging-evidence.json \
  --output staging-evidence-with-document-sharing.json
```

The live probe verifies immutable artifact hash binding, no auto-approval, rejection of the wrong preview hash, explicit approval, exactly one execution audit, the exact Google recipient, reader-only access, and the provider receipt.

### Production activation

```bash
SHUDDHO_PRODUCTION_VERIFICATION_TOKEN=<short-lived-cohort-token> \
uv run --extra coworker python scripts/action_document_sharing_activation.py \
  --staging-evidence staging-evidence-with-document-sharing.json \
  --rollout docs/cohort-rollout.production.json \
  --deployment-change document-sharing-deployment.json \
  --operator-status operator-status.json \
  --api-base-url https://api.example.com \
  --output action-document-sharing-activation.json
```

### Release-ledger attestation

```bash
uv run --extra coworker python scripts/cohort_release_ledger.py append-action-document-sharing \
  --ledger release-ledger.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference <oncall-or-change-actor> \
  --change-reference <approved-change-reference> \
  --current-stage <current-cohort-stage> \
  --staging-evidence staging-evidence-with-document-sharing.json \
  --rollout docs/cohort-rollout.production.json \
  --deployment-change document-sharing-deployment.json \
  --operator-status operator-status.json \
  --action-document-sharing-activation action-document-sharing-activation.json
```

Keep the generated activation and ledger entry with the release evidence. Scale and recovery tooling will fail closed if document sharing is enabled but the attestation is missing or altered.
