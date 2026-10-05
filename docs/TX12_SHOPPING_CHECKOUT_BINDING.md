# TX-12 Shopping Checkout Approval Binding

TX-12 creates the immutable source binding required before any future
consequential shopping checkout adapter can exist. It does not execute checkout.

## Preconditions

A binding may be created only when all of the following are true:

- the owner-scoped transaction is a TX-10 shopping cart transaction;
- the transaction is already in `awaiting_approval`, meaning its exact terms
  hash completed the existing human review-confirmation flow;
- the requested transaction revision and terms SHA-256 still match;
- the selected TX-11 verification belongs to the same owner and transaction;
- it is the latest verification for that transaction;
- the verification matched the exact immutable TX-10 cart SHA-256;
- the client supplies the exact verification snapshot SHA-256;
- the provider observation is no more than five minutes old;
- both the reviewed quote and verified merchant quote are still unexpired.

## Immutable binding

The record binds:

- transaction ID and revision;
- terms revision and SHA-256;
- TX-10 cart SHA-256;
- TX-11 verification ID and snapshot SHA-256;
- provider and merchant cart reference;
- exact currency and total;
- expiry;
- canonical approval-scope SHA-256.

The binding expiry is the earliest of the reviewed quote expiry, provider quote
expiry, and five minutes after the provider observation.

Replaying the exact request returns the same binding. A conflicting attempt for
the same transaction fails closed.

## Authority boundary

TX-12 does **not**:

- create or approve an ExternalAction;
- register a shopping checkout operation;
- call a merchant/provider;
- mutate or hold inventory;
- submit shipping or billing identity;
- submit checkout;
- create a card, payment or bank mutation;
- perform browser submission;
- advance the transaction to an execution state.

A future provider-specific checkout adapter must consume this binding into a
separate immutable action preview, revalidate every source at approval and
execution, use provider idempotency/reconciliation, preserve outcome-unknown
semantics, and require a receipt that exactly matches the approved purchase.
