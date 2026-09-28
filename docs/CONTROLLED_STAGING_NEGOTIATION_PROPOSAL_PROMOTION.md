# Controlled Live PA-09 Negotiation Proposal Promotion

This gate verifies the deployed `negotiation_proposal_promotion` trust boundary through the public staging API. It is intentionally **non-destructive**: it prepares one immutable commitment preview but never successfully approves or executes that preview.

## Preconditions

Controlled staging must explicitly enable the existing prerequisites:

```text
SHUDDHO_ACTIONS_ENABLED=true
SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=true
SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=true
SHUDDHO_AGENT_RUNTIME_ENABLED=true
SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true
SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=true
SHUDDHO_NEGOTIATION_PROPOSAL_PROMOTION_ENABLED=true
```

The selected provider's exact `provider:negotiation_commitment_email` operation must also appear in `SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS`. Microsoft additionally requires its existing Microsoft-actions gate.

A backend-only DeepSeek key is required because this exercise validates a real model-generated negotiation proposal before promotion.

The operator must opt in explicitly:

```bash
export SHUDDHO_STAGING_ALLOW_LIVE_NEGOTIATION_PROPOSAL_PROMOTION=true
```

Required staging environment also includes:

- `SHUDDHO_STAGING_API_BASE_URL`
- `SHUDDHO_STAGING_TOKEN_A`
- `SHUDDHO_STAGING_TRANSACTION_COUNTERPARTY_EMAIL`

Use only a controlled test mailbox. Do not point this exercise at a real commercial counterparty.

## Run

Google:

```bash
uv run --extra coworker python scripts/staging_live_negotiation_proposal_promotion.py \
  --provider google \
  --base-evidence /secure/release/staging-evidence.json \
  --output /secure/release/staging-evidence.negotiation-promotion.json
```

Microsoft uses `--provider microsoft`.

## Proof sequence

The verifier:

1. checks the deployed transaction-authority manifest for the exact provider operation;
2. selects exactly one active owned staging email connection;
3. verifies the deployed negotiation, proposal and promotion capabilities are enabled;
4. creates a synthetic owner-scoped negotiation case with explicit zero-value staging terms;
5. calls the live DeepSeek-backed proposal generator;
6. independently recomputes the canonical proposal hash;
7. proves proposal generation created no `ExternalAction`;
8. changes offer history and proves the old proposal becomes stale and cannot be promoted;
9. generates a fresh history-bound proposal;
10. proves wrong-hash promotion fails without changing proposal state;
11. promotes the exact hash and verifies one server-built contract-v6 immutable preview;
12. verifies provider, connection, counterparty, message, summary, terms, proposal hash, case revision and offer-history sequence are source-bound;
13. proves exact promotion replay converges on the same preview/action;
14. changes the case revision after promotion;
15. proves approval of the now-stale preview is rejected;
16. verifies the action remains unapproved with no execution/provider-success audit or receipt.

The exercise never reaches a successful approval. Cleanup cancels the synthetic preview and negotiation case.

## Evidence

A passing run adds a `negotiation_proposal_promotion` record with timestamped `operation_evidence` for the exact provider operation. Multiple provider runs may accumulate in the same evidence file.

This staging result proves the deployed promotion boundary only. It does not enable production, qualify a different transaction operation, prove counterparty delivery/agreement, or authorize autonomous negotiation.

## Rollback

Keep or restore:

```text
SHUDDHO_NEGOTIATION_PROPOSAL_PROMOTION_ENABLED=false
```

The broader safety controls remain independently available:

```text
SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false
SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=false
SHUDDHO_ACTIONS_ENABLED=false
```

## Activation handoff

After a reviewed deployment of the exact tested revision/configuration, run [PA-09 Negotiation Proposal Promotion Activation](NEGOTIATION_PROPOSAL_PROMOTION_ACTIVATION.md). A live staging file alone is not production qualification.
