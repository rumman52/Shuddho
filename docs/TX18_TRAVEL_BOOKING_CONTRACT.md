# TX-18 Travel Booking Contract Foundation

TX-18 defines the provider-neutral preview and receipt rules that any future
travel booking adapter must satisfy. It grants no booking, identity or payment
authority.

## Input

TX-18 consumes only an existing TX-17 booking binding. Before it can build a
preview, it recomputes the full TX-17 approval scope and requires the SHA-256 to
match the stored binding.

The preview binds:

- TX-17 booking binding ID;
- transaction and terms revisions;
- exact terms SHA-256;
- TX-08 quote SHA-256;
- TX-09 verification ID and snapshot SHA-256;
- travel kind;
- provider and provider quote ID;
- exact currency and total;
- binding expiry.

The preview explicitly states:

- `execution_authority=not_registered`;
- `identity_authority=not_bound`;
- `payment_authority=not_authorized`.

Traveler legal identity, passport, loyalty credentials and payment instruments
are therefore outside TX-18.

## Receipt contract

A future provider adapter may only claim success when its normalized booking
receipt matches the approved preview's:

- provider;
- provider quote ID;
- travel kind;
- currency;
- exact total.

The receipt must also include a provider booking identifier, status
`confirmed`, and an offset-aware confirmation timestamp. The confirmation
must not predate the approved preview beyond the bounded clock-skew allowance
and must not occur after the binding expiry. The normalized receipt is SHA-256
hashed for later reconciliation evidence.

## Deliberately excluded

TX-18 does not:

- add `travel_booking_create` to ActionPayload;
- register a travel booking ActionSpec;
- add a transaction-operation allowlist entry;
- create an ExternalAction;
- expose a booking execution endpoint;
- select a provider;
- submit traveler identity or travel documents;
- hold inventory;
- submit payment credentials;
- book, ticket, reserve or purchase.

The next provider-specific travel slice must first define the minimum traveler
identity contract and prove provider credential scope, idempotency,
reconciliation, outcome lookup, receipt readback, privacy and payment behavior
before action registration is considered.
