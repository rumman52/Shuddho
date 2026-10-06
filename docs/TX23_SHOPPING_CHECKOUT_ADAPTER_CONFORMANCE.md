# TX-23 Shopping Checkout Adapter Implementation Conformance

TX-23 adds the isolated provider-implementation conformance boundary after TX-16.

It does not select a merchant provider, register `shopping_checkout_create`,
allowlist a transaction operation, collect payment credentials, or grant runtime
checkout authority.

## Evidence chain

TX-23 requires the exact normalized TX-14 provider qualification object and the
exact TX-15 registration proposal consumed by TX-16.

Before any provider I/O it rechecks:

- the canonical TX-14 qualification SHA-256;
- exact provider, operation, adapter revision and checkout origin;
- credential-broker and least-privilege scope continuity;
- exact idempotency, reconciliation, receipt, privacy and payment contracts;
- a passed, fresh TX-14 staging live probe;
- live-probe revision and origin matching the admitted adapter;
- all zero-authority flags;
- absence of `shopping_checkout_create` from the runtime action registry and
  transaction-operation allowlist.

The adapter must additionally declare `implementation_test_only=true`,
`implementation_test_environment="staging"`, and an
`implementation_test_origin` exactly matching the reviewed origin.

## Bounded staging I/O

For one immutable TX-13 preview, the harness:

1. confirms no receipt exists for the new idempotency key;
2. requests a provider-hosted checkout handoff;
3. repeats the handoff request with the same idempotency key;
4. validates both handoffs through TX-27;
5. requires the handoff digests to be identical;
6. confirms the adapter still exposes no confirmed receipt before the user
   completes the hosted flow.

The result is schema v2 with status
`provider_handoff_conformance_passed`. It binds the exact TX-15 proposal,
adapter admission, preview, idempotency key, and TX-27 handoff digest.

A final provider receipt is deliberately **not** manufactured by this automated
adapter test. Final receipt equality and reconciliation after a real/sandbox
user-present completion remain live provider evidence required by TX-27/TX-28.

## Authority remains closed

A passing result has status
`provider_handoff_conformance_passed` and still records:

- `registration_authority=false`;
- `operation_allowlisted=false`;
- `external_action_registered=false`;
- `runtime_enabled=false`;
- `identity_authority=false`;
- `payment_authority=false`.

TX-23 is implementation evidence only. TX-24 may compile this evidence together
with the exact TX-15 proposal and a fresh human review into an inert
runtime-registration-review bundle, but neither TX-23 nor TX-24 may silently
register or activate checkout.
