# Email Threading Production Activation

This runbook governs controlled production activation of Gmail email threading.

## Invariants

The action remains intentionally narrow:

- one existing owner-scoped Shuddho artifact;
- one exact recipient;
- Gmail only;
- reader role only;
- OAuth scope `drive.file`;
- no public links, writer grants, folder browsing, contact lookup, or Agent authority.

Production activation must never widen those boundaries.

## Preconditions

- PR implementing email threading and its release qualification is merged.
- CI is green.
- The rollout is a bounded production cohort.
- `actions=true`, `artifact_services=true`, and `action_email_threading=true`.
- Exact kill switch: `SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false`.
- A dedicated staging Gmail connection exists.
- Staging uses only synthetic, non-customer data.
- Operator health is `CONTINUE_COHORT` with zero breaches.

## Evidence chain

`live staging -> reviewed rollout -> deployment change -> fresh operator status -> runtime manifest -> action_email_threading_verified activation -> schema-v12 ledger event`

Every artifact is SHA-256 bound. The runtime manifest must exactly equal the reviewed capability set and deployed revision.

## Rollback

Set:

```text
SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false
```

New Gmail OAuth starts and new document-share execution are blocked by the feature boundary. Existing history remains readable.

After a **global** Coworker rollback, do not reuse the previous email-threading activation. Recovery must deploy the reviewed state, run a fresh activation after rollback completion, append a new schema-v12 ledger event, and only then emit schema-v7 recovery evidence.

## Expansion

A cohort expansion with email threading enabled must provide `--action-email-threading-activation` to `cohort_scale_activation.py`. The file hash must match exactly one schema-v12 ledger event for the current stage. Scale evidence is schema v7 while this capability is enabled.

## Exit criteria

Email threading is eligible for controlled activation only when:

- guarded live Gmail evidence passed;
- the exact deployment revision and runtime capability set were verified;
- cohort enforcement is active and inside the reviewed ceiling;
- operator status is fresh and clean;
- the activation hashes all reviewed inputs;
- schema-v12 ledger verification passes;
- scale and recovery checks fail closed when the attestation is absent or tampered.


## Threading-specific safety invariant

This qualification does **not** widen Gmail OAuth scope. The live exercise must use the existing send-only Google email connection. Evidence is valid only when the reply is derived from a confirmed Shuddho-sent parent on the same connection, preserves exact To/Cc and subject, has no Bcc or attachment, and Gmail returns the same provider thread id for the approved follow-up.

This gate does not qualify reading, searching, listing, or replying to arbitrary incoming mailbox messages.
