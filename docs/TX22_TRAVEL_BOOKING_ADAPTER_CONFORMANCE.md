# TX-22 Travel Booking Adapter Implementation Conformance

TX-22 adds the isolated implementation-test boundary that follows TX-21.

It does not select a provider, register `travel_booking_create`, enable a
transaction operation, collect payment credentials, or grant runtime booking
authority.

## Purpose

TX-21 proves that adapter metadata and method signatures match an exact reviewed
TX-20 registration proposal without making provider calls.

TX-22 is the next bounded step: once a real provider adapter and controlled
sandbox credentials exist, the adapter can be exercised against its sandbox
while the Shuddho runtime remains unable to execute travel bookings.

## Preconditions

The harness requires all of the following:

- an exact TX-20 registration proposal;
- a TX-21-compatible adapter;
- `implementation_test_only=true` on the adapter;
- `implementation_test_environment="sandbox"`;
- an `implementation_test_origin` exactly matching the reviewed TX-20 booking origin;
- an explicit caller opt-in with `allow_provider_test_io=True`;
- a fresh TX-18 travel booking preview;
- only the reviewed `shuddho_transmitted_fields` traveler data;
- no `travel_booking_create` entry in `ACTION_SPECS`;
- no allowlisted `provider:travel_booking_create` transaction operation.

The harness fails closed if any of these conditions are absent. The adapter cannot
switch its implementation test to an unreviewed host merely by labeling that host
as a sandbox; the exact test origin remains bound to the reviewed TX-20 origin.

## Bounded provider I/O

For one immutable booking preview, TX-22:

1. performs a pre-create lookup by the binding-scoped idempotency key;
2. performs a sandbox create;
3. performs the same sandbox create again with the same idempotency key;
4. reads the booking back by idempotency key;
5. reads the booking back by provider booking ID;
6. validates every returned receipt against the exact TX-18 receipt contract;
7. requires all observed receipt hashes to be identical.

The deterministic idempotency key is derived from the TX-21 adapter admission,
booking binding, immutable booking scope and preview digest. No traveler data,
secret or payment value is embedded in the key or emitted in the result.

## Privacy boundary

Only the exact reviewed `shuddho_transmitted_fields` may be passed to the
adapter. Provider-hosted traveler fields remain outside the Shuddho payload.
The conformance evidence records only field names, not traveler values. It also
binds the exact TX-19 qualification SHA-256, TX-20 registration-proposal
SHA-256, and conformance evaluation timestamp for downstream review continuity.

## Authority remains closed

A successful TX-22 result has status:

`provider_implementation_conformance_passed`

The evidence still requires:

- `registration_authority=false`;
- `operation_allowlisted=false`;
- `external_action_registered=false`;
- `runtime_enabled=false`;
- `identity_authority=false`;
- `payment_authority=false`.

TX-22 intentionally performs sandbox provider I/O, so
`sandbox_provider_io=true` and `provider_called=true` are evidence that the
isolated implementation test actually exercised the adapter. They are not
runtime authority.

## What TX-22 does not do

TX-22 does not:

- choose a travel provider;
- add provider credentials to the repository;
- call a production travel endpoint;
- add `travel_booking_create` to the action registry;
- add a transaction-operation allowlist entry;
- create an ExternalAction;
- expose traveler document images to Shuddho;
- receive or store a payment instrument;
- qualify production activation.

A later provider-specific slice must supply reviewed concrete provider code and
sandbox configuration, then run this harness and retain the resulting evidence.
TX-25 may compile that exact evidence together with the TX-20 proposal and a
fresh human review into an inert runtime-registration-review bundle, but it must
not silently register or activate travel booking.
