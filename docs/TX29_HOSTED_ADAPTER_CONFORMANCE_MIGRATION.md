# TX-29 Hosted Adapter Conformance Migration

TX-29 makes the shopping and travel adapter interfaces consistent with the
provider-hosted, user-present transaction boundary established by TX-27.

Before TX-29, TX-22/TX-23 implementation tests expected
`create_booking`/`create_checkout` to return an immediately confirmed receipt.
That model contradicted the already-reviewed payment boundary because the user
must complete payment and, where applicable, identity steps directly with the
provider before Shuddho can observe a confirmed receipt.

## Interface

Shopping adapters now expose:

- `create_checkout_handoff(...)`;
- `lookup_checkout_receipt(...)`.

Travel adapters now expose:

- `create_booking_handoff(...)`;
- `lookup_booking_receipt(...)`.

The create call may return only:

- `handoff_id`;
- `handoff_url`.

The URL is validated by TX-27 against the exact reviewed HTTPS origin.

## Conformance

TX-22/TX-23 schema-v2 conformance proves:

- exact provider/revision/proposal continuity;
- exact immutable preview binding;
- deterministic idempotency;
- two identical hosted handoffs for the same idempotency key;
- no confirmed receipt before user-present completion;
- no payment instrument or identity-document authority;
- no runtime registration or transaction-operation allowlisting.

The passing status is `provider_handoff_conformance_passed`.

The conformance artifact binds `handoff_sha256`, not a fabricated
`receipt_sha256`. Final confirmed receipt evidence is collected only after a
real provider-hosted completion and is separately required by TX-27/TX-28
staging/activation controls.

## Downstream continuity

TX-24, TX-25 and TX-26 now carry the hosted handoff digest forward into
runtime-registration review and change planning. A future concrete provider
runtime implementation must implement both phases:

1. create/return the hosted handoff;
2. reconcile the later provider-confirmed receipt.

TX-29 grants no production authority and selects no provider.
