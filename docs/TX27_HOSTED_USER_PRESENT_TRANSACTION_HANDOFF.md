# TX-27 Hosted User-Present Transaction Handoff

TX-27 closes a provider-model gap in the shopping and travel transaction
foundations.

TX-14 and TX-19 require payment to remain merchant/provider-hosted and
user-present. A genuine hosted flow is therefore two-phase:

1. Shuddho creates or receives a bounded provider handoff URL.
2. The user leaves Shuddho and completes identity/payment steps directly with
   the provider.
3. Shuddho later reads a provider-confirmed receipt and reconciles it against
   the exact immutable preview.

A handoff is **not** a successful purchase or booking.

## Handoff evidence

`build_hosted_transaction_handoff` consumes an existing TX-13 or TX-18 preview
and records:

- action kind and provider;
- transaction and binding identity;
- immutable binding-scope and preview SHA-256;
- exact currency and total;
- provider handoff ID;
- full HTTPS handoff URL;
- reviewed HTTPS handoff origin;
- creation and approval-expiry times;
- explicit user-present and final-receipt requirements;
- zero payment, identity, registration and runtime authority.

The handoff URL may contain a provider path/query token, but it may not contain
credentials or a fragment, and its origin must exactly match the reviewed
provider origin.

The only handoff status is:

`awaiting_user_completion`

## Completion evidence

`validate_hosted_transaction_completion` accepts a later provider receipt,
revalidates the handoff digest and immutable preview, then delegates to the
existing TX-13/TX-18 receipt contracts.

It accepts completion only when the provider confirms the exact approved terms
before approval expiry.

The output status is:

`confirmed`

and is bound by a canonical `completion_sha256`.

## Shopping expiry repair

TX-27 also repairs TX-13 receipt validation so a shopping order confirmed after
the approved checkout preview expires is rejected. Travel already enforced this
rule.

## Authority remains closed

TX-27 does not:

- register `shopping_checkout_create` or `travel_booking_create`;
- add a transaction-operation allowlist entry;
- create an ExternalAction;
- expose a browser/navigation endpoint;
- call a provider;
- receive payment credentials;
- collect identity documents;
- grant payment, identity or runtime authority.

A later provider-specific adapter slice must use this two-phase handoff instead
of pretending a hosted user-present checkout is synchronously confirmed.
