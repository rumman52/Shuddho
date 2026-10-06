# TX-28 Transactions Repository Completion

TX-28 closes the remaining provider-neutral release-engineering gaps in Shuddho's
Transactions program. It does not claim live production qualification for a
provider that has not supplied credentials, staging evidence, and reviewed
runtime code.

## Completed transaction families

The repository now has bounded foundations for:

- negotiation commitments through the existing PA-09 transaction authority;
- OpenTable no-payment restaurant reservations;
- shopping cart review, immutable checkout binding, provider qualification,
  adapter admission, implementation conformance, hosted user-present handoff,
  runtime-registration review and code-change planning;
- travel quote review, immutable booking binding, provider qualification,
  adapter admission, implementation conformance, hosted user-present handoff,
  runtime-registration review and code-change planning.

TX-27 established the correct two-phase model for payment-bearing shopping and
travel flows: the first provider result is a user-present hosted handoff, never
a confirmed purchase/booking. Confirmation requires a later exact provider
receipt before approval expiry.

## Release controls completed by TX-28

TX-28 adds explicit default-off runtime kill switches:

- `SHUDDHO_SHOPPING_CHECKOUT_ENABLED=false`;
- `SHUDDHO_TRAVEL_BOOKING_ENABLED=false`.

The transaction-authority manifest advances to schema v2 and exposes restaurant,
shopping and travel sub-capability authority independently. Existing PA-09
activation and staging readers remain compatible with historical schema-v1
evidence.

The canonical release contract now has separately gated capabilities for
`shopping_checkout` and `travel_booking`. Their provider operations still
must be registered in `ACTION_SPECS`; merely setting a flag or allowlist value
cannot make an unregistered provider executable.

A shared transaction capability activation verifier binds:

- the reviewed rollout and exact provider/action operation;
- a fresh provider-bound staging evidence SHA-256;
- exact deployed source revision;
- controlled-cohort enforcement;
- runtime capability manifest;
- transaction-authority manifest;
- clean post-deploy operator status;
- the individual capability kill switch.

The tamper-evident release ledger now supports:

- schema v30 — `restaurant_reservations_verified`;
- schema v31 — `shopping_checkout_verified`;
- schema v32 — `travel_booking_verified`.

Each nested transaction capability must chain after a
`personal_transactions_verified` ledger event at the same rollout stage.

## Restaurant live qualification

A guarded OpenTable sandbox probe now produces the missing restaurant staging
evidence. It requires an explicit staging-only guard and refuses non-sandbox
OpenTable. It exercises the public API through:

1. transaction-authority verification;
2. exact availability-backed no-payment review;
3. explicit transaction review and confirmation;
4. provider action preparation;
5. wrong-preview-hash rejection;
6. separate correct approval;
7. one provider reservation attempt;
8. exact no-payment confirmation receipt evidence.

No credit-card or payment escalation is permitted.

## What is still external

Repository completion is not the same as production provider qualification.

Shopping checkout and travel booking remain disabled until a real provider is
selected and all of the following exist for that exact provider:

- production API contract and legal/commercial access;
- brokered credentials and least-privilege scopes;
- provider-specific ActionSpec and runtime adapter;
- registered `provider:action_kind` operation;
- controlled-staging TX-14/TX-19 qualification;
- TX-23/TX-22 adapter conformance;
- TX-27 hosted user-present handoff/completion evidence;
- TX-24/TX-25 runtime-registration review;
- TX-26 code-change plan;
- TX-28 production activation verification and v31/v32 ledger attestation.

Those cannot be fabricated by repository code.

## Authority state

All newly added shopping and travel runtime authority remains default-off.
TX-28 does not add a fake provider, fake credentials, fake live evidence, or
automatic payment authority.
