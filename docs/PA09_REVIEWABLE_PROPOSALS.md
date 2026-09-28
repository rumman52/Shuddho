# PA-09 Reviewable Negotiation Proposals

This increment adds model-assisted negotiation drafting on top of the durable PA-09 case ledger.

It does **not** add autonomous negotiation authority.

## Trust boundary

The lifecycle is:

```text
owned negotiation case + append-only offer history
→ bounded DeepSeek draft
→ inert NegotiationProposal
→ human review or dismissal
```

A `NegotiationProposal` cannot:

- send email or call a provider;
- choose a provider account or connection;
- accept an agreement;
- create, approve, promote, or execute an `ExternalAction`;
- write a commitment into offer history;
- mutate the negotiation case or its limits.

Binding negotiation commitments remain exclusively behind the existing
`negotiation_commitment_email` immutable preview, exact-final-terms approval,
provider-specific execution, and uncertain-outcome controls documented in
[PA-09 Negotiation Commitments](PA09_NEGOTIATION_COMMITMENTS.md).

## Activation

Proposal generation is available only when both of the existing controls are active:

- `SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=true`;
- `SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true`.

The DeepSeek backend key must also be configured. PA-09 transaction enablement by
itself therefore does not activate model-assisted drafting.

No new production send authority is introduced by this increment.

## Context sent to the model

The model receives only server-bounded negotiation context:

- case revision and current offer-history sequence;
- subject and objective;
- counterparty display name;
- explicit user limits;
- up to 40 recent append-only offer records;
- requested draft kind and output language.

Connection IDs, OAuth credentials, provider tokens, approval hashes, action IDs,
and execution receipts are excluded.

All case and offer text is explicitly treated as untrusted data rather than
instructions.

## Proposal contract

The model returns one strict typed object containing:

- summary;
- structured terms;
- editable message text;
- rationale;
- bounded risk notes.

The prompt instructs the model to preserve explicit limits as hard drafting
constraints and to omit unsupported concrete terms rather than invent them.

The server validates the returned JSON against the PA-09 proposal schema before
it can be stored.

## Revision and history binding

Every saved proposal is bound to:

- exact case ID;
- exact case revision;
- exact current offer-history sequence;
- requested kind and output language;
- exact generated draft content.

Those fields are covered by a canonical SHA-256 `proposal_hash`.

If the case revision or offer-history sequence changes after generation, the API
renders the proposal as `stale`. The UI instructs the user to generate a fresh
draft.

Proposal states are intentionally narrow:

```text
suggested → dismissed
suggested → expired
suggested → stale (derived when case/history changes)
```

There is no promotion or execution state.

## Idempotency and review

Generation uses an owner-scoped idempotency key. Replaying the same request
returns the existing proposal instead of creating another stored draft.

Dismissal requires the exact `proposal_hash`; stale UI state cannot dismiss a
changed proposal silently.

## Model capacity and cost boundary

Each model-assisted proposal acquires the existing shared provider-capacity
lease and reserves against the existing per-workspace daily token budget before
DeepSeek is called. Known usage settles the shared reservation; unknown outcomes
remain conservatively charged.

## Retention

Saved negotiation proposals are owner-scoped database records and are removed by
the existing account-erasure flow before negotiation cases are deleted.

## API

Generate a reviewable draft:

```http
POST /api/v1/negotiations/{case_id}/proposals
Idempotency-Key: <owner-scoped-key>
Content-Type: application/json

{
  "expected_revision": 3,
  "kind": "counteroffer",
  "output_language": "en"
}
```

Dismiss the exact draft:

```http
POST /api/v1/negotiations/{case_id}/proposals/{proposal_id}/dismiss
Content-Type: application/json

{
  "proposal_hash": "<exact-64-char-sha256>"
}
```

Neither endpoint prepares or executes a provider action.
