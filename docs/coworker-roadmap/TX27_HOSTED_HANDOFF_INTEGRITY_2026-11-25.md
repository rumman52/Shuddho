# TX-27 hosted handoff integrity — Prompt 04 source slice

## Task contract

- Objective: prevent ambiguous hosted HTTPS URL syntax and receipt timestamps outside the handoff lifetime from entering the TX-27 completion path.
- Baseline: main `67d187f972c8069e4369ebc9fdb28dae55c40e3f`; [issue #378](https://github.com/rumman52/Shuddho/issues/378).
- Branch: `fix/tx27-handoff-origin-chronology-20261125`.
- Reuse: existing TX-13/TX-18 receipt contracts, TX-27 evidence schema/digest, TX-29 adapter interface. No new authority or ledger.
- Source: `services/coworker/hosted_transaction_handoff.py`; regression tests: `tests/test_hosted_transaction_handoff.py`.
- Baseline root causes: urllib URL normalization strips control characters; it does not reject malformed ports until parsed.port is accessed; empty userinfo can evade truthiness checks. Completion revalidated preview fields and a digest but did not validate creation time, stored URL/ID or schema version and allowed receipt confirmation predating handoff.
- Acceptance: reject ambiguous authority and URL syntax; validate stored origin, URL, handoff ID and exact integer schema version; enforce creation <= confirmation < expiry; allow a later read of an already timely receipt. A digest is integrity evidence, not proof of provider authenticity. Provider adapters still must authenticate and bind the final receipt to the actual handoff identity.
- Compatibility: no schema or interface changes. Deliberate fail-closed rejection of malformed or ambiguous legacy evidence and confirmation exactly at expiry. Origin must be ASCII (use reviewed IDNA A-label), with at most one trailing slash.
- Boundaries: no network calls in this slice, no provider registration, flag changes, credentials, payments, migration or production deployment. No changes to ExternalAction or governance controls.
- Regression tests were authored in commit `21704b5159b789b70d23009e6eaf8459827dd0a8`, followed by implementation `e3dc2cf871abb53f5bdcdda8b5c94dd461cec5dc`. Local full checkout failed DNS resolution; red/green pytest and exact-head CI are not yet attested.

## Verification

Run in a checked-out authorized environment:
```sh
uv run --extra coworker pytest tests/test_hosted_transaction_handoff.py tests/test_shopping_checkout_adapter_conformance.py tests/test_travel_booking_adapter_conformance.py tests/test_shopping_checkout_contract.py tests/test_travel_booking_contract.py -q -rs
```
Then run all existing mandatory CI checks, inspect exact-head JUnit artifacts and obtain independent security review. Baseline [CI #45351544500](https://github.com/rumman52/Shuddho/actions/runs/45351544500) reports coworker/application/frontend/browser/PostgreSQL compatibility success; governance and merge gate failed (app token client-id missing). Do not bypass this gate.

## Provider decision package (not activation authorization)

| Capability | Source registration | External decision required |
| --- | --- | --- |
| Negotiation | google/microsoft:negotiation_commitment_email | Controlled synthetic recipient, exact approved content, provider audit/receipt evidence, reviewer; no real commitment |
| Restaurant | opentable:restaurant_reservation_create | Authorized sandbox account and documented availability/create/lookup contract, test restaurant/slot, no-payment scope, exact owner approval, independent mutation counts |
| Shopping | Not registered | Owner selects named merchant/provider, supported cart/checkout product and jurisdictions, legal/commercial API access, documented sandbox and production origins, credential broker least-privilege scopes, supported cart freshness/expiry, idempotency and receipt lookup semantics |
| Travel | Not registered | Owner selects named provider and flight or lodging scope, jurisdictions, documented quote and hosted booking APIs, legal/commercial access, sandbox, credential broker scopes, permitted traveler fields, provider-hosted identity/payment, cancellation and receipt lookup contract |

For each selected shopping/travel provider require TX-14/19 qualification, TX-15/20 reviewed registration proposal, TX-16/21 admission, TX-23/22 conformance, TX-24/25 runtime registration review, TX-26 code-change plan, TX-27 authenticated receipt evidence and TX-28 exact-revision activation gate, kill switch and rollback proof. No real purchases, reservations, commitments or paid provisioning are authorized by this record.

## Completion evidence

| Level | Status |
| --- | --- |
| Implemented | Proposed source patch committed on review branch |
| Repository-verified | Pending exact-head mandatory CI and independent review |
| Staging-verified | Not established; zero operated fault receipts supplied by this slice |
| Production-qualified | NO-GO |
| Activated | No |

The 16-scenario validator is a structural evidence gate, not an execution harness. Do not substitute simulated-provider integration results for independent staging provider observations. Supabase staging was listed ACTIVE_HEALTHY; Render workspace confirmation is required by the connector before service inspection. No isolated fault target identity or provider authorization established. Next: verify exact PR head, resolve governance credential through authorized repository owner, acquire selected provider scope and staging authorization, then operate canonical fault matrix and attach real receipts. Prompt 05 must not treat this source patch as release qualification.
