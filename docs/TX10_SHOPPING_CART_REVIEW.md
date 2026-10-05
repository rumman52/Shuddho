# TX-10 Shopping Cart Review Domain

TX-10 adds an exact, durable shopping-cart review surface on top of the generic
transaction ledger.

## Scope

The slice stores user-supplied review evidence for:

- merchant identity and opaque merchant cart/quote reference;
- exact product ID, title, variant, quantity and unit/line prices;
- subtotal, tax, fees, shipping, discount and total in integer minor units;
- fulfillment mode and visible fulfillment terms;
- return terms;
- quote observation and expiry.

The cart is hashed and owner-scoped. Exact cart terms are written into the
existing immutable transaction terms lifecycle and can be reviewed using the
existing revision/hash/freshness controls.

## Authority boundary

TX-10 is intentionally non-consequential.

It does **not**:

- create or modify a merchant cart;
- call a merchant/provider;
- verify merchant inventory or price;
- submit shipping or billing identity;
- register a checkout action;
- create an ExternalAction;
- submit a browser form;
- authorize a payment, card hold, bank transfer or purchase;
- treat transaction review confirmation as checkout approval.

The transaction provider remains `internal`, `connection_id` remains null,
and `execution.available=false`.

## Next gate

A later slice may add trusted read-only merchant/cart verification. Checkout
must remain a separate provider-specific action contract with exact final terms,
fresh price validation, explicit approval, provider idempotency/reconciliation
and a validated receipt.
