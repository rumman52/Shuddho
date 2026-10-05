# TX-19 Travel Booking Provider Qualification Gate

TX-19 defines the evidence a concrete travel provider must prove before Shuddho
can even consider registering `travel_booking_create`.

It does not select or activate a provider by itself.

## Traveler-data minimization

Each TX-19 qualification covers exactly one travel kind (`flight` or
`lodging`). A provider supporting both requires separate evidence for each,
so flight-only identity requirements cannot leak into lodging collection.

Every provider must declare the exact traveler fields required for that travel
kind and partition them into:

- fields Shuddho must transmit; and
- fields collected directly by the provider in a user-present hosted flow.

Every required field must appear exactly once in that partition. `legal_name`
is always required, but it may be collected directly by the provider rather
than transmitted by Shuddho.

The gate only permits a bounded field vocabulary. Optional fields are default
off. Passport/identity/visa document images and payment instruments may not be
sent to or stored by Shuddho through this contract.

Examples of fields that may be declared when the provider truly requires them
include legal name, date of birth, nationality, passport metadata, contact
details, known-traveler/redress identifiers, and loyalty identifiers. The
provider must prove necessity; the qualification artifact is not permission to
collect every allowed field.

## Provider guarantees

The qualification requires:

- exact provider identity;
- exact adapter source revision;
- fixed HTTPS booking origin;
- brokered, server-side, least-privilege credentials;
- no raw payment credentials;
- explicit supported travel kinds;
- booking-binding-scoped idempotency;
- duplicate handling by same booking or lookup;
- lookup by idempotency key and provider booking ID;
- no blind retry after uncertain mutation;
- exact TX-18 receipt readback;
- required-field-only disclosure;
- no secret or traveler-data logging;
- provider-hosted traveler collection support;
- provider-hosted, user-present payment;
- fresh staging probe bound to exact revision and origin.

## Passing TX-19 still grants zero runtime authority

A passing artifact returns:

- `registration_authority=false`;
- `operation_allowlisted=false`;
- `external_action_registered=false`;
- `identity_authority=false`;
- `payment_authority=false`.

TX-19 does not modify the action registry, transaction allowlist, credentials,
deployment flags or rollout state.

A later provider-specific implementation must bind this qualification evidence
to exact code and continue to revalidate TX-17/TX-18 approval evidence before
any booking mutation.
