# TX-21 Travel Booking Adapter Admission

TX-21 defines the structural code interface and evidence admission gate for a
future real travel-booking provider adapter.

It does not select a provider, call a provider, or register
`travel_booking_create`.

## Evidence continuity

Admission independently revalidates the exact TX-20 registration proposal:

- canonical proposal SHA-256;
- concrete provider and `provider:travel_booking_create` operation;
- exact adapter revision and fixed HTTPS booking origin;
- one travel kind: flight or lodging;
- TX-18 contract version 1;
- canonical credential scopes;
- exact traveler-data partition and traveler-data boundary SHA-256;
- booking-binding-scoped idempotency;
- lookup-before-retry reconciliation with no blind retry;
- exact TX-18 receipt contract;
- privacy and logging restrictions;
- provider-hosted, user-present payment;
- fresh human review;
- explicit no-runtime-authority flags.

## Required adapter metadata

A concrete adapter must expose code-owned metadata matching the proposal for:

- provider, revision, origin and travel kind;
- credential scopes;
- traveler-data boundary SHA-256;
- required traveler fields;
- Shuddho-transmitted traveler fields;
- provider-hosted traveler fields;
- action kind and TX-18 contract version;
- idempotency and both reconciliation lookup capabilities;
- provider-hosted collection support;
- provider-hosted payment mode;
- no payment instrument reception;
- no document-image reception;
- no traveler-data logging.

It must implement asynchronous:

- `create_booking(preview=..., traveler_data=..., idempotency_key=...)`;
- `lookup_booking(idempotency_key=..., provider_booking_id=...)`.

TX-21 admission does not call either method.

## Authority remains closed

A successful result means only
`admitted_for_provider_implementation_tests`.

The result explicitly keeps:

- `provider_called=false`;
- `registration_authority=false`;
- `operation_allowlisted=false`;
- `external_action_registered=false`;
- `runtime_enabled=false`;
- `identity_authority=false`;
- `payment_authority=false`.

TX-21 does not modify ActionPayload, ACTION_SPECS, transaction-operation
configuration, credentials, deployment flags, traveler storage, or rollout
state.

A later provider-specific implementation test slice may exercise a real adapter
only after reviewed provider code and controlled test infrastructure exist.
