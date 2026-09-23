# Document Sharing Production Activation

This runbook governs controlled production activation of Google Drive document sharing.

## Invariants

The action remains intentionally narrow:

- one existing owner-scoped Shuddho artifact;
- one exact recipient;
- Google Drive only;
- reader role only;
- OAuth scope `drive.file`;
- no public links, writer grants, folder browsing, contact lookup, or Agent authority.

Production activation must never widen those boundaries.

## Preconditions

- PR implementing document sharing and its release qualification is merged.
- CI is green.
- The rollout is a bounded production cohort.
- `actions=true`, `artifact_services=true`, and `action_document_sharing=true`.
- Exact kill switch: `SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false`.
- A dedicated staging Google Drive connection exists.
- Staging uses only synthetic, non-customer data.
- Operator health is `CONTINUE_COHORT` with zero breaches.

## Evidence chain

`live staging -> reviewed rollout -> deployment change -> fresh operator status -> runtime manifest -> action_document_sharing_verified activation -> schema-v12 ledger event`

Every artifact is SHA-256 bound. The runtime manifest must exactly equal the reviewed capability set and deployed revision.

## Rollback

Set:

```text
SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false
```

New Drive OAuth starts and new document-share execution are blocked by the feature boundary. Existing history remains readable.

After a **global** Coworker rollback, do not reuse the previous document-sharing activation. Recovery must deploy the reviewed state, run a fresh activation after rollback completion, append a new schema-v12 ledger event, and only then emit schema-v7 recovery evidence.

## Expansion

A cohort expansion with document sharing enabled must provide `--action-document-sharing-activation` to `cohort_scale_activation.py`. The file hash must match exactly one schema-v12 ledger event for the current stage. Scale evidence is schema v7 while this capability is enabled.

## Exit criteria

Document sharing is eligible for controlled activation only when:

- guarded live Drive evidence passed;
- the exact deployment revision and runtime capability set were verified;
- cohort enforcement is active and inside the reviewed ceiling;
- operator status is fresh and clean;
- the activation hashes all reviewed inputs;
- schema-v12 ledger verification passes;
- scale and recovery checks fail closed when the attestation is absent or tampered.
