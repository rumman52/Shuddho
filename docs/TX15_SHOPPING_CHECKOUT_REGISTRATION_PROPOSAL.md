# TX-15 Shopping Checkout Registration Proposal

TX-15 closes the evidence-continuity gap between TX-14 provider qualification
and any future provider-specific checkout implementation.

It compiles an inert registration proposal only. It does not change the runtime
action registry.

## Inputs

The compiler requires:

1. the exact normalized TX-14 qualification object, including its canonical
   `qualification_sha256`;
2. a reviewed registration request that repeats the exact provider, operation,
   adapter revision, provider checkout origin and TX-14 qualification hash.

TX-15 recomputes the TX-14 qualification digest before accepting the evidence.
A copied hash attached to changed qualification data therefore fails closed.

The review must be fresh and must remain on TX-13 checkout contract version 1.

## Output

The proposal binds:

- provider and exact `provider:shopping_checkout_create` operation;
- adapter source revision;
- fixed provider origin;
- TX-14 qualification SHA-256;
- TX-13 contract kind/version;
- qualified credential scopes;
- provider idempotency and reconciliation contract;
- receipt contract;
- privacy and merchant-hosted payment boundary;
- reviewed change reference and reviewer identity;
- a canonical registration-proposal SHA-256.

A successful output has status
`eligible_for_provider_implementation_review`.

## Authority remains closed

The output explicitly keeps:

- `registration_authority=false`;
- `operation_allowlisted=false`;
- `external_action_registered=false`;
- `runtime_enabled=false`;
- `payment_authority=false`.

TX-15 does not modify `ActionPayload`, `ACTION_SPECS`, transaction-operation
configuration, credentials, deployment flags, or cohort rollout state.

The next provider-specific code slice may use this proposal as a required source
artifact. That later slice must still implement the actual adapter, source
revalidation at preview/approval/execution, provider idempotency and
reconciliation, exact TX-13 receipt validation, and independent staging/release
qualification before any checkout action can be enabled.
