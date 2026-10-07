# CORE-05 — Approval Boundary Finalization

CORE-05 finalizes the Core Agent rule that model output can never become a
provider mutation by itself.

The required path for every consequential operation is:

```
Agent
  -> Prepared Action / inert proposal
  -> Immutable Preview
  -> Human Approval
  -> Execution Gateway
  -> Provider
```

The forbidden path is:

```
Agent -> provider mutation
```

## Model authority

The Agent model may:

- research;
- read authorized context;
- draft;
- prepare;
- summarize;
- recommend;
- suggest an inert email/calendar/qualified LinkedIn proposal.

It may not receive a direct consequential tool such as email send, calendar
creation, social publishing, document sharing, transaction execution, or an
arbitrary provider mutation.

The server validates the model-visible tool list before every planner call.
Only non-consequential registered tools and opaque handles for already-prepared
email/calendar actions may be exposed.

Opaque handles do not contain provider credentials, mutable payloads, approval
data, or execution authority.

## Inert proposals

Model-created action proposals are limited by a server-owned whitelist:

- `email_send`;
- `calendar_create`;
- `social_publish_linkedin` only when its separate feature gate is enabled.

A model cannot propose document sharing, restaurant reservation, shopping
checkout, travel booking, negotiation commitments, arbitrary provider writes,
attachments, reminders, or other mutation variants.

The model proposal is stored as `suggested` only. It has no connection or
provider execution identity.

Promotion is a user/API operation that converts the exact proposal hash into a
new server-owned `ActionPrepare` request. That produces a distinct immutable
preview in `awaiting_approval`; promotion does not approve it.

## Human approval and execution

Only the authenticated action approval endpoint can move an immutable preview
from `awaiting_approval` to `queued`.

Approval revalidates:

- preview hash;
- provider/connection identity;
- action policy;
- transaction/source bindings;
- freshness and expiry;
- optional capability gates.

The execution gateway performs another verification before provider mutation.
No model method has access to the provider adapter or execution grant.

Uncertain provider outcomes remain `outcome_unknown` and are reconciled rather
than blindly repeated.

## Transactions

Transaction intents are routed to the Transactions domain before general Agent
planning.

The model cannot directly select or persist:

- `restaurant_reservation_create`;
- `shopping_checkout_create`;
- `travel_booking_create`;
- negotiation commitment mutations;
- arbitrary provider transaction operations.

Existing transaction controls remain mandatory: exact reviewed terms,
transaction bindings, provider-specific idempotency, reconciliation policy,
capability activation, kill switches, staging evidence, and release-ledger
qualification.

Shopping checkout and travel booking remain provider-dependent and production
authority stays closed until a real provider is selected and qualified.

## Regression coverage

CORE-05 adversarial tests attempt to make the model:

- send email directly;
- create calendar events directly;
- publish social content directly;
- share documents directly;
- execute restaurant/shopping/travel transactions directly;
- select arbitrary provider mutation tools;
- smuggle LinkedIn publish proposals while the LinkedIn proposal gate is off.

All paths fail closed or are routed to the separate approved domain. Safe
research/draft/prepare/summarize work remains available to the Agent.
