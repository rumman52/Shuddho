# TX-14 Shopping Checkout Provider Qualification Gate

TX-14 defines the release evidence a real shopping checkout provider must prove
before Shuddho can even consider registering `shopping_checkout_create`.

It does not select or activate a provider by itself.

## Required evidence

The validator requires one concrete production provider and binds:

- exact provider identifier;
- exact adapter source revision;
- fixed HTTPS checkout origin;
- brokered, server-side, least-privilege credential scope;
- no raw payment credentials held by Shuddho;
- checkout-binding-scoped provider idempotency;
- deterministic duplicate result or lookup behavior;
- outcome lookup by both idempotency key and provider order ID;
- no blind retry after an uncertain mutation;
- provider receipt readback satisfying the exact TX-13 receipt fields;
- data-minimized checkout requests with no secrets in logs;
- merchant-hosted, user-present payment;
- a fresh staging live probe bound to the exact adapter revision and origin.

The output is canonicalized and SHA-256 hashed for later action-registration and
release-ledger binding.

## Passing TX-14 still grants zero checkout authority

Even a passing evidence file returns:

- `registration_authority=false`;
- `operation_allowlisted=false`;
- `external_action_registered=false`;
- `payment_authority=false`.

TX-14 does not modify `ActionPayload`, `ACTION_SPECS`,
`SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS`, provider credentials, runtime
configuration, or cohort rollout state.

## Next gate

After a real provider passes TX-14, a separate provider-specific implementation
may be reviewed. That slice must bind TX-13 preview hashes and TX-12 checkout
bindings into the normal immutable ExternalAction approval path, revalidate all
sources at approval and execution, use the qualified provider's idempotency and
reconciliation APIs, and accept success only from an exact TX-13 receipt.

Payment remains merchant-hosted and user-present unless a separately designed,
reviewed and qualified payment boundary is introduced.
