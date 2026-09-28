# PA-09: Binding Negotiation Commitments

This is the first bounded PA-09 transaction slice. It adds one qualified action contract, `negotiation_commitment_email`, on top of the existing consequential-action ledger and the already-qualified Google/Microsoft email connectors.

## Scope

The user prepares one exact external commitment with:

- one primary counterparty email;
- optional Cc recipients;
- no Bcc;
- no attachments;
- an exact subject and plain-text message;
- a human-readable counterparty identity;
- an explicit commitment summary;
- one or more named final terms.

The server stores those values in the immutable preview and binds them into approval-scope contract v6. Any change to destination, message, summary or any final term invalidates the old approval and requires a new preview.

## Authority boundary

The feature is disabled by default:

```text
SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=false
```

Enabling it also requires:

```text
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=true
```

This flag does not grant generic transaction authority. The code-owned action registry remains authoritative and only individually registered action kinds may cross the mutation boundary.

The current PA-09 slice is not registered as an Agent planner proposal or direct Agent tool. Browser and sandbox capabilities cannot create, approve or execute this action.

## Execution and uncertainty

Execution reuses the existing fixed-provider Gmail or Microsoft Mail adapter. There are no arbitrary endpoints, provider selection by the model, or new credentials.

The existing action claim is committed before provider mutation. A claimed action that becomes `outcome_unknown` is never returned to `queued` and is not blindly resent. The user sees the uncertain result and must inspect the connected provider or create a separately reviewed fresh action if appropriate.

Provider acceptance is recorded as a receipt. Acceptance is not represented as delivery, reading, agreement by the counterparty or payment settlement.

## Release controls

The capability has a separate release-contract entry:

- capability: `personal_transactions`
- kill switch: `SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=false`
- dependencies: `actions`, `connector_trust_boundary`
- staging gate: `personal_transactions`
- release-ledger schema: v26
- ledger event: `personal_transactions_verified`
- activation artifact key: `personal_transactions_activation`

Code completion does not qualify production activation. Controlled staging still has to prove exact-term invalidation, owner/connection enforcement, fixed provider egress, provider acceptance receipts, uncertain-outcome behavior, rollback and recovery.

## Out of scope

This slice does not implement or authorize:

- airline/hotel booking;
- restaurant reservations;
- shopping checkout;
- card or bank payments;
- fee-bearing cancellation;
- browser-based purchasing;
- autonomous negotiation messages generated and sent by the planner;
- accepting agreements without an exact user-reviewed preview.

Those remain separate PA-09 increments with provider-specific schemas, idempotency/reconciliation and live qualification.
