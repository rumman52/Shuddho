# TX-08 Travel Quote Domain

TX-08 adds a durable, review-only travel quote domain on top of the generic
transaction ledger.

## Scope

The slice records exact user-supplied flight or lodging quote details:

- traveler identities and traveler type;
- exact flight segments or one exact lodging property/stay;
- local times plus IANA time zones;
- provider label and quote reference;
- subtotal, tax, fees, discount and total in integer minor units;
- cancellation and change terms;
- quote observation and expiry.

The quote is hashed and stored owner-scoped. The same quote is converted into
immutable transaction terms and uses the existing revision, exact-hash review
and freshness checks.

## Authority boundary

TX-08 is intentionally inert.

It does **not**:

- call a travel provider;
- claim the user-supplied quote is provider verified;
- register a new provider/action operation;
- create or bind an `ExternalAction`;
- book a flight or lodging stay;
- submit a browser form;
- create a payment intent, card hold, deposit or purchase;
- retry or reconcile a provider mutation.

The transaction provider remains `internal`, `connection_id` remains null,
and the review surface reports `execution.available=false`.

A later travel provider adapter must be separately selected, implemented,
allowlisted, staged and qualified before any booking authority exists.

## Data and retention

Migration `0048` adds `cw_travel_quote_intents`. The row is keyed by the
owning transaction and carries the exact quote JSON plus its SHA-256 digest.
Account erasure deletes the quote intent before the parent transaction rows.

## Acceptance

TX-08 passes only when:

1. flight and lodging schemas reject mixed/invalid itineraries;
2. quote timestamps are timezone-aware and unexpired;
3. money totals reuse the exact transaction price invariant;
4. quote creation is owner-scoped and idempotent;
5. replay cannot change quote details under the same idempotency key;
6. exact terms can be reviewed with the existing transaction hash binding;
7. no booking/execute endpoint or ExternalAction is introduced;
8. account erasure removes the travel quote intent;
9. repository CI remains green.
