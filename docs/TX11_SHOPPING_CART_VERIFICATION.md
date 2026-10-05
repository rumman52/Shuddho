# TX-11 Shopping Cart Verification Evidence

TX-11 adds a trusted read-only verification boundary between the TX-10 shopping
cart review ledger and a future selected merchant/provider adapter.

## Scope

A code-owned verifier may retrieve an already-existing merchant cart using only
its opaque merchant cart identifier. The provider observation can contain:

- merchant label;
- exact product ID, title, variant, quantity, unit price and line total;
- subtotal, tax, fees, shipping, discount, total and currency;
- fulfillment mode and visible fulfillment terms;
- return terms;
- provider quote expiry and observation time.

Shuddho compares that observation with the immutable TX-10 cart and appends
owner-scoped verification evidence bound to the exact TX-10 cart SHA-256.

Price or terms drift is recorded as a mismatch. TX-11 never silently replaces
the user's reviewed terms.

## Privacy and authority boundary

The verification adapter request contains only the opaque merchant cart ID. It
does not receive shipping name/address, billing identity, account credentials,
payment instruments, phone, email, or other checkout identity.

TX-11 does **not**:

- create or modify a merchant cart;
- reserve or hold inventory;
- register a shopping/checkout transaction operation;
- create an ExternalAction;
- expose a public verification endpoint;
- submit checkout;
- send shipping or billing identity;
- create a payment/card/bank mutation;
- perform browser submission;
- treat a successful verification as checkout approval.

A later provider-specific checkout slice must separately bind a fresh verified
cart snapshot to explicit final approval and provider-specific idempotency,
reconciliation, outcome-unknown handling and receipt validation.
