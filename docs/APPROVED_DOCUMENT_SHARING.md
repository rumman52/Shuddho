# Approved Google Drive Document Sharing

Status: **implemented behind a disabled-by-default feature flag; not production-release-qualified yet**.

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

## Production release status

This implementation does **not** authorize production enablement.

The controlled-cohort rollout validator intentionally rejects an `action_document_sharing` capability today. A follow-up release-qualification increment must add:

- guarded live Google Drive staging evidence;
- exact production activation/runtime proof;
- document-sharing kill-switch declaration;
- release-ledger attestation;
- bounded scale/recovery consumption;
- operational rollback/runbook evidence.

Until that increment passes, keep `SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false` in production.
