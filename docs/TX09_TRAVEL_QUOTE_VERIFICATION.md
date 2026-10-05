# TX-09 Travel Quote Verification Evidence

TX-09 adds the trusted read-only boundary between the TX-08 travel quote ledger
and a future selected travel inventory provider.

## What this slice does

A code-owned provider adapter may retrieve an existing quote using only:

- the opaque provider quote identifier; and
- the travel kind.

The adapter returns a normalized provider observation containing public
itinerary/stay details, exact price components, cancellation/change terms,
provider quote expiry and observation time.

Shuddho compares that observation with the immutable TX-08 quote and stores
append-only owner-scoped verification evidence. Verification evidence is bound
to the exact TX-08 quote SHA-256 so later quote replacement cannot inherit an
older verification.

Traveler names, email, phone, passport data, payment data and other private
booking details are never included in the verification adapter request.

## Explicitly out of scope

TX-09 grants no consequential authority. It does not:

- book or reserve flights/hotels;
- hold inventory;
- create a remote cart;
- submit traveler identity;
- create an ExternalAction;
- register a transaction operation;
- authorize checkout;
- create a payment intent or card/bank mutation;
- perform browser submission;
- convert a mismatch into a silently updated quote.

A mismatch is evidence that the user must review fresh terms. It is not an
authorization to rewrite the reviewed transaction.

## Next gate

A later provider-specific slice must separately choose a provider, implement
real read-only retrieval, add live staging evidence and qualify its security,
quota and data-egress behavior. Booking remains a separate later action contract
with exact approval and provider-confirmed receipt requirements.
