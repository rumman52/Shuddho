# TX-13 Shopping Checkout Contract Foundation

TX-13 defines the provider-neutral immutable preview and receipt rules that a
future shopping checkout adapter must satisfy. It grants no external authority.

## Input

The contract consumes only an already-created TX-12 checkout binding. Before a
preview can be constructed, TX-13 recomputes the complete TX-12 approval scope
and requires its SHA-256 to match the stored binding.

The preview therefore binds:

- TX-12 checkout binding ID;
- transaction and terms revisions;
- exact terms SHA-256;
- TX-10 cart SHA-256;
- TX-11 verification ID and snapshot SHA-256;
- provider and merchant cart reference;
- currency and exact total;
- binding expiry.

The preview also explicitly states:

- `execution_authority=not_registered`;
- `payment_authority=not_authorized`;
- `identity_authority=not_bound`.

## Receipt contract

A future provider adapter may only claim success when its normalized receipt
matches the approved preview's:

- provider;
- merchant cart ID;
- currency;
- exact total.

The receipt must contain a provider order identifier, status `confirmed`, and
an offset-aware confirmation timestamp. The normalized receipt is SHA-256
hashed for later transaction reconciliation evidence.

## Deliberately excluded

TX-13 does not:

- add `shopping_checkout_create` to the ActionPayload union;
- add it to the external-action registry;
- add a transaction operation allowlist entry;
- expose a checkout execution endpoint;
- select a merchant provider;
- submit shipping/billing identity;
- authorize or transmit payment credentials;
- create an ExternalAction;
- call a provider;
- mutate inventory, cart, payment or order state.

The next consequential slice must first select a real provider and prove that
provider's API contract, credential boundary, idempotency, outcome lookup,
receipt readback, privacy posture, and payment/identity model before action
registration is considered.
