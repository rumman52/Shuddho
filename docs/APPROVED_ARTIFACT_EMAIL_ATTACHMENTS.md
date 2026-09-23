# Approved Shuddho Artifact Email Attachments

This increment adds a disabled-by-default consequential action for sending an email with attachments that already exist as immutable Shuddho task artifacts.

## Boundary

The attachment path is intentionally separate from model-generated action proposals.

```text
owned Shuddho artifact
→ user explicitly selects artifact in Email & Calendar
→ server resolves owner-scoped artifact metadata
→ immutable preview binds attachment id/name/type/size/SHA-256
→ explicit approval binds that exact preview hash
→ worker re-resolves metadata
→ worker reads private object-store bytes
→ worker rechecks byte length + SHA-256
→ provider adapter encodes those verified bytes
→ one committed provider mutation attempt
```

The browser never supplies attachment bytes to the action endpoint. The model cannot select artifact IDs and the Agent proposal schema remains limited to plain email/calendar proposals.

## Action contract

A new registered consequential action kind is used:

`email_send_with_attachments`

Legacy `email_send` and `calendar_create` contracts are unchanged.

`ActionPrepare` carries attachment IDs separately from the typed action payload. This is deliberate: model-produced content may never smuggle an artifact reference into the proposal payload.

The backend allows at most:

- 3 unique artifacts;
- 2 MiB total;
- PDF;
- DOCX;
- PPTX;
- XLSX;
- TXT.

Only rows owned by the signed-in Shuddho account can enter the manifest. User source uploads are not directly attachable; the files must already exist as generated Shuddho artifacts.

## Immutable approval

The prepared preview is schema version 3 and includes the exact attachment manifest:

- artifact ID;
- filename;
- normalized content type;
- byte size;
- SHA-256.

The consequential-action approval scope binds both the complete manifest and its stable digest. Changing an attachment, replacing its hash, removing it, or adding another artifact invalidates the approval.

## Execution re-verification

Before any provider access or mutation, the action worker:

1. revalidates the saved approval scope;
2. re-resolves the exact artifact IDs under the action owner;
3. compares current database metadata with the approved manifest;
4. reads the private object-store bytes;
5. verifies exact byte length;
6. verifies SHA-256.

Any failure marks the queued action failed before execution is claimed. No Gmail or Microsoft Graph mutation is attempted.

Once verified, the exact in-memory bytes are used for the provider request. A later object-store change cannot alter the already verified outgoing attachment.

## Provider encoding

Google uses the existing RFC 5322 MIME message path and adds verified attachments with explicit MIME type and filename.

Microsoft Graph uses `microsoft.graph.fileAttachment` with base64-encoded verified bytes.

Ordinary emails retain their existing provider request shape.

## Kill switch

```dotenv
SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false
```

The flag requires `SHUDDHO_ACTIONS_ENABLED=true`.

Production activation is guarded by [Controlled Staging Live Approved Email Attachments](CONTROLLED_STAGING_ACTION_ATTACHMENTS.md) and [Approved Attachment Production Activation](ACTION_ATTACHMENTS_ACTIVATION.md). The feature remains disabled by default. When enabled for a reviewed cohort, its exact activation must be recorded as schema-v9 `action_attachments_verified` in the release ledger; bounded scale and post-rollback recovery fail closed without that attestation.
