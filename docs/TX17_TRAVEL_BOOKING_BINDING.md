# TX-17 Travel Booking Approval Binding

TX-17 adds the immutable source binding required before any future travel
booking action can exist. It does not book travel.

## Preconditions

A binding may be created only when:

- the owner-scoped transaction is a TX-08 travel flight or lodging quote;
- exact transaction terms have completed the existing review-confirmation flow;
- the transaction is in `awaiting_approval`;
- the caller presents the current transaction revision and exact terms SHA-256;
- the selected TX-09 verification belongs to the same owner and transaction;
- it is the latest verification;
- the provider observation matched the immutable TX-08 quote SHA-256;
- the stored verification snapshot still matches its SHA-256;
- the client presents the exact verification snapshot SHA-256;
- the provider observation is no more than five minutes old;
- the reviewed quote and provider quote are both still unexpired;
- provider quote ID, travel kind, currency and exact total still match reviewed terms.

## Immutable binding

The durable record binds:

- transaction ID and revision;
- terms revision and SHA-256;
- TX-08 quote SHA-256;
- TX-09 verification ID and snapshot SHA-256;
- travel kind;
- provider and provider quote ID;
- exact currency and total;
- expiry;
- canonical approval-scope SHA-256.

The binding expiry is the earliest of the reviewed quote expiry, provider quote
expiry and five minutes after the provider observation.

Exact replay returns the same immutable binding. A conflicting attempt for the
same transaction fails closed.

## Privacy and authority boundary

TX-17 does **not**:

- register a travel booking action;
- create or approve an ExternalAction;
- select a travel provider;
- call a provider;
- hold inventory;
- submit traveler legal identity, passport or loyalty details;
- submit payment credentials;
- book, ticket, reserve or purchase;
- advance the transaction into an execution state.

A later provider-specific booking contract must separately define the minimum
traveler/identity fields, exact booking preview, provider idempotency,
reconciliation, outcome-unknown handling and receipt validation before action
registration is considered.
