# Approved Gmail owned-thread follow-ups

This increment adds the smallest safe Wave D threading capability without widening Shuddho into a mailbox reader.

## Scope

`email_thread_reply` is Google-only and disabled by default:

```text
SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false
```

A reply can be prepared only from an owned `succeeded` Shuddho email action on the **same Google email connection**. The parent provider receipt must already contain a Gmail message id, Gmail thread id, and Shuddho's deterministic RFC `Message-ID`.

The reply keeps the parent's exact To/Cc lists and subject. Bcc and attachments are forbidden in v1. The user writes the new body, receives an immutable preview, explicitly approves its hash, and execution uses the existing one-attempt consequential-action workflow.

## No mailbox-read expansion

The Google email connection remains `gmail.send` only. Shuddho does not list, fetch, search, or inspect Gmail threads. Users cannot paste or invent a Gmail thread id. Thread authority is derived only from Shuddho's own confirmed provider receipt.

This means v1 supports **follow-ups inside threads created by Shuddho**, not replies to arbitrary incoming email. Supporting incoming-message replies later would require a separate privacy/security design and independently reviewed OAuth scope expansion.

## Approval boundary

The immutable preview and approval scope bind:

- parent Shuddho action id;
- root Shuddho action id;
- exact Gmail thread id;
- parent provider message id;
- deterministic RFC parent `Message-ID`;
- bounded RFC `References` chain;
- exact To/Cc destinations;
- empty Bcc;
- unchanged subject;
- new body;
- Google connection, account identity and approval expiry;
- policy declaration that mailbox read access is `none`.

Execution revalidates the ordinary approval scope before the provider mutation. The Gmail request supplies the approval-bound `threadId`, `In-Reply-To`, and `References`. The returned Gmail `threadId` must match the approved thread or the receipt is rejected.

## Excluded from v1

- Gmail mailbox read/search/list;
- arbitrary external thread ids;
- changing To/Cc or subject inside a thread;
- Bcc;
- attachments;
- Microsoft Graph threading;
- model/Agent selection of a thread;
- auto-approval or scheduled sending;
- retrying an uncertain Gmail send.

The same send-only uncertainty rule remains: a lost Gmail send response is not blindly retried because `gmail.send` does not provide a read path for safe reconciliation.

## Release status

The implementation and release-safety machinery are now complete for a **reviewed controlled cohort**, while the capability remains disabled by default.

Production enablement is allowed only when all of the following are present and mutually hash-bound:

1. guarded live Gmail evidence from `scripts/staging_live_email_threading.py`;
2. a reviewed rollout declaring `actions=true` and `action_email_threading=true`;
3. exact rollback switch `SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false`;
4. deployed source revision and rollout/staging hashes;
5. fresh clean operator health;
6. `scripts/action_email_threading_activation.py` output proving the deployed runtime manifest exactly matches the reviewed rollout;
7. schema-v13 `action_email_threading_verified` release-ledger attestation;
8. schema-v8 scale/recovery evidence consuming that exact attestation.

See [Email Threading Activation](ACTION_EMAIL_THREADING_ACTIVATION.md).

The OAuth boundary is unchanged: Gmail remains send-only. Arbitrary incoming-mail replies still require a separate future privacy/security design.
