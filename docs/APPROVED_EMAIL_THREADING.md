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

Implementation is not production qualification. Keep the flag off in production until a separate release increment provides:

1. CI coverage for parent ownership, recipient/subject invariants, approval tampering and kill-switch behavior;
2. guarded live Gmail evidence proving the returned thread id remains stable across an approved follow-up;
3. exact deployed-revision/runtime activation evidence;
4. a dedicated release-ledger attestation and rollback switch;
5. bounded scale/recovery consumption of that attestation;
6. monitoring for provider rejection, uncertain outcomes and thread-receipt mismatch.

Exact rollback switch:

```text
SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false
```

Turning this switch off must cancel an unclaimed threaded reply at execution revalidation and must not disable history/receipt visibility for already completed actions.
