# TX-26 Transaction Runtime Registration Change Plan

TX-26 is the next inert gate after TX-24 and TX-25.

It accepts one exact, fresh runtime-registration review artifact for either:

- `shopping_checkout_create`; or
- `travel_booking_create`.

It then compiles a deterministic code-change plan. It does **not** apply that
plan.

## Fail-closed checks

TX-26 recomputes the runtime-registration review SHA-256, validates provider and
operation identity, adapter revision, evidence hashes, origin, review chronology,
freshness, privacy boundaries and every zero-authority flag.

It also inspects the current code-owned action registry and refuses to compile a
plan if the action kind or provider operation is already registered. This keeps
TX-26 useful only while runtime authority is still closed.

## Output

The only successful status is:

`eligible_for_runtime_registration_code_change_review`

The output records the exact reviewed provider operation and the code surfaces a
future registration PR must change:

- ActionPayload schema;
- ActionSpec registry entry;
- concrete provider hosted-handoff runtime binding;
- post-user-completion receipt lookup/reconciliation path;
- owner-scoped audit and receipt persistence;
- frontend payload type.

It also records that the provider operation may be added to
`SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS` only **after** the reviewed code
change exists and later activation evidence passes.

TX-26 never:

- edits `ACTION_SPECS`;
- edits `ActionPayload`;
- modifies deployment configuration;
- changes transaction allowlists;
- enables feature flags;
- stores credentials;
- calls a provider;
- creates an ExternalAction;
- grants identity or payment authority;
- appends release-ledger evidence.

The next slice must be a separately reviewed implementation PR for one provider
and one action kind. That PR must remain default-off until controlled staging,
rollback, production activation verification and release-ledger attestation are
complete.
