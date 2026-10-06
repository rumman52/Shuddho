# TX-16 Shopping Checkout Adapter Admission

TX-16 defines the structural interface and evidence admission gate for a future
real merchant checkout adapter.

It does **not** select a provider and it does **not** register checkout authority.

## Why this slice exists

TX-14 proves that one concrete provider contract is suitable for bounded
checkout. TX-15 binds that qualification into an inert human-reviewed
registration proposal. TX-16 closes the next gap: provider implementation code
must prove that its own static metadata and capabilities exactly match that
reviewed TX-15 proposal before isolated adapter tests can begin.

## Required adapter contract

A concrete adapter must expose code-owned metadata for:

- provider identifier;
- exact adapter Git revision;
- fixed HTTPS checkout origin;
- exact credential scopes;
- action kind `shopping_checkout_create`;
- TX-13 contract version 1;
- provider idempotency support;
- lookup by idempotency key;
- lookup by provider order ID;
- merchant-hosted, user-present payment;
- explicit declaration that the adapter never receives a payment instrument.

It must also implement asynchronous:

- `create_checkout_handoff(preview=..., idempotency_key=...)`;
- `lookup_checkout_receipt(idempotency_key=..., provider_order_id=...)`.

The create method returns only provider-hosted handoff metadata. It must not
return or imply a confirmed order before the user-present hosted flow completes.

TX-16 admission performs no call to either method.

## Evidence continuity

Admission revalidates the complete TX-15 proposal, including its canonical
`registration_proposal_sha256`, review freshness, provider/revision/origin,
credential scopes, idempotency/reconciliation contract, TX-13 receipt shape,
privacy boundary and payment model.

Every adapter metadata field must exactly match the proposal.

A successful result is only
`admitted_for_provider_implementation_tests` and is itself SHA-256 hashed for
later provider-specific tests.

## Authority remains closed

TX-16 does not:

- modify `ActionPayload`;
- add `shopping_checkout_create` to `ACTION_SPECS`;
- alter `SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS`;
- create an `ExternalAction`;
- create an execution grant;
- request credentials;
- call the provider;
- add a public checkout endpoint;
- transmit identity or payment data;
- enable checkout or payment in any environment.

The next slice can implement isolated contract tests for a **real selected
provider** only when reviewed provider code and credentials/testing
infrastructure actually exist. Until then, checkout remains unregistered.
