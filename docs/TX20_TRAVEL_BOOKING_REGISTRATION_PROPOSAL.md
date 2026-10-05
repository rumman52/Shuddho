# TX-20 Travel Booking Registration Proposal

TX-20 closes the evidence-continuity gap between TX-19 provider qualification
and any future provider-specific travel booking implementation.

It compiles an inert, human-reviewed registration proposal only. It does not
register `travel_booking_create`.

## Inputs

The compiler requires:

1. the exact normalized TX-19 qualification object, including its canonical
   `qualification_sha256`;
2. a reviewed registration request that repeats the exact provider, operation,
   adapter revision, booking origin, travel kind, traveler-data boundary hash,
   and TX-19 qualification hash.

TX-20 recomputes the full TX-19 qualification digest and separately recomputes
the normalized traveler-data boundary digest. The live staging probe must still
be bound to that exact travel kind and traveler boundary.

TX-19 qualification evidence must also remain fresh when the proposal is
compiled. A stale provider probe cannot be promoted into implementation review.

## Output

The proposal binds:

- provider and exact `provider:travel_booking_create` operation;
- exact adapter revision and booking origin;
- one travel kind: flight or lodging;
- TX-19 qualification SHA-256;
- TX-18 action-contract version;
- exact credential scopes;
- exact traveler-data partition and its SHA-256;
- idempotency and reconciliation rules;
- TX-18 receipt contract;
- privacy and provider-hosted payment boundary;
- reviewed change reference and reviewer reference;
- canonical `registration_proposal_sha256`.

A successful result has status
`eligible_for_provider_implementation_review`.

## Authority remains closed

Every proposal explicitly keeps:

- `registration_authority=false`;
- `operation_allowlisted=false`;
- `external_action_registered=false`;
- `runtime_enabled=false`;
- `identity_authority=false`;
- `payment_authority=false`.

TX-20 does not modify `ActionPayload`, `ACTION_SPECS`, transaction-operation
configuration, credentials, deployment flags, traveler storage, or rollout
state.

A future provider-specific adapter must consume this exact proposal and still
pass separate code, staging, identity-minimization, reconciliation, and release
qualification before any travel booking mutation can be registered.
