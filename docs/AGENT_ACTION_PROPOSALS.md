# Non-Executable Agent Action Proposals

This increment allows Shuddho's bounded intelligent planner to suggest a typed email or calendar action without granting the model an executable action capability.

The feature is disabled by default:

```text
SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false
```

## Trust boundary

The lifecycle is:

```text
model suggestion
→ inert ActionProposal
→ user reviews exact proposal hash
→ user selects a connected account
→ server prepares a separate immutable ExternalAction preview
→ user reviews preview
→ explicit approval
→ durable provider execution
```

An `ActionProposal` is not an `ExternalAction`.

It has:

- no provider or connection chosen by the model;
- no outbox row;
- no approval state;
- no execution claim;
- no provider receipt;
- no Temporal action workflow;
- no route that can approve or execute it.

The database lifecycle is bounded to `suggested → promoting → promoted`, `dismissed`, or `expired`.

## Planner contract

Only the initial intelligent planning pass may produce proposals. Deterministic fallback and replanning cannot generate new proposals.

The planner may return at most two proposals, and each payload must validate against the same strict `EmailSend` or `CalendarCreate` Pydantic schema used by real actions.

The planner is instructed not to invent missing recipients, times, time zones or content. A proposal remains untrusted model output even after schema validation; it becomes actionable only after explicit user promotion.

The proposal carries a canonical SHA-256 over:

- proposal schema version;
- Agent run ID;
- exact typed payload;
- rationale.

Promotion requires the exact hash so stale UI state cannot silently promote changed content.

## Promotion

Promotion requires the authenticated user to select a concrete owned connection. The model never selects provider or account identity.

The backend reserves the proposal in a short `promoting` state and uses a deterministic idempotency key derived from the proposal ID. A retry with the same connection returns the same action preview; a conflicting connection is rejected.

The promotion path calls the existing `ActionRepository.prepare` implementation. That means it reuses:

- owner-scoped connection lookup;
- provider/capability matching;
- connector kill switches;
- preview quotas;
- future-calendar checks;
- v2 approval-scope generation;
- immutable preview hashing.

If preparation fails, the proposal returns to `suggested`. A process crash during promotion can be retried with the same connection without creating a second action.

Promotion creates a **standalone** `ExternalAction`. It does not mutate the saved Agent plan or insert a consequential Agent step after planning.

## Approval remains separate

Successful promotion returns an action in `awaiting_approval`.

It does not:

- approve the action;
- queue execution;
- call Google or Microsoft;
- create an event;
- send an email.

The existing `POST /api/v1/actions/{id}/approve` endpoint remains the only user approval path, and it requires the immutable preview hash.

## API

The Agent run response includes owned `action_proposals`.

Promotion:

```http
POST /api/v1/agent-runs/{run_id}/action-proposals/{proposal_id}/promote
```

Body:

```json
{
  "connection_id": "<user-selected-connection-uuid>",
  "proposal_hash": "<exact-64-char-sha256>"
}
```

Dismissal:

```http
POST /api/v1/agent-runs/{run_id}/action-proposals/{proposal_id}/dismiss
```

Body:

```json
{
  "proposal_hash": "<exact-64-char-sha256>"
}
```

Both routes are owner-scoped. Another account receives not-found semantics.

## Retention

Proposal rows are included in account erasure and contain no OAuth credentials or provider receipts.

Suggested proposals expire after 24 hours. Expired or dismissed proposals cannot be promoted.

## Production controls

Production rollout requires:

- `actions=true`;
- `agent_runtime=true`;
- `intelligent_planner=true`;
- `action_proposals=true`;
- `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=true`;
- passed independent `action_proposals` staging evidence;
- exact rollback switch `SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false`.

The feature can be disabled without disabling existing action history or the ordinary user-prepared action flow.

## Security rationale

The design follows least-agency principles: model output may recommend a future operation, but cannot acquire the identity, provider binding, approval, or execution authority needed to perform it.

The controlled live proof is implemented in [Controlled Live Agent Action-Proposal Staging](CONTROLLED_STAGING_ACTION_PROPOSALS.md). It verifies through deployed public APIs that a real intelligent-planner proposal remains outside `ExternalAction`, wrong-hash promotion fails, exact promotion creates one standalone immutable preview, the saved Agent plan is not retrofitted with a consequential step, and no approval/provider mutation occurs.

Production activation is separately verified by [Agent Action-Proposal Production Activation](ACTION_PROPOSALS_ACTIVATION.md). That verifier SHA-binds the live staging proof and reviewed rollout to a deployment record, verifies the deployed backend's exact source revision and sanitized runtime capability/provider state over authenticated HTTPS, and requires fresh clean cohort health before emitting `action_proposals_verified`.
