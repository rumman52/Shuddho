# PA-09 Negotiation Proposal Promotion Activation

This verifier converts no flag and performs no provider mutation. It proves that a reviewed production deployment is running the exact `negotiation_proposal_promotion` configuration that passed controlled staging.

## Required evidence

Activation requires:

1. fresh passed [controlled live promotion staging](CONTROLLED_STAGING_NEGOTIATION_PROPOSAL_PROMOTION.md);
2. the exact reviewed production rollout manifest;
3. a deployment record binding both files by SHA-256 and naming the full deployed Git revision;
4. an authenticated HTTPS runtime manifest from the deployed backend;
5. an authenticated transaction-authority manifest whose operation list exactly equals the reviewed allowlist;
6. fresh `CONTINUE_COHORT` operator status with zero breaches.

The reviewed rollout must enable all promotion prerequisites and include the exact rollback control:

```text
SHUDDHO_NEGOTIATION_PROPOSAL_PROMOTION_ENABLED=false
```

## Deployment record

Start from `docs/negotiation-proposal-promotion-deployment.template.json`. The record contains exactly:

- release ID;
- reviewed change reference;
- current stage;
- deployment timestamp;
- full lowercase 40-character Git revision;
- SHA-256 of the exact staging-evidence file;
- SHA-256 of the exact rollout manifest.

Deployment must be later than the newest required staging proof.

## Run

Keep the short-lived production verification token out of process arguments:

```bash
export SHUDDHO_PRODUCTION_VERIFICATION_TOKEN='<short-lived-admitted-token>'
```

Then:

```bash
uv run --extra coworker python scripts/negotiation_proposal_promotion_activation.py \
  --staging-evidence /secure/release/staging-evidence.negotiation-promotion.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/negotiation-promotion-deployment.json \
  --operator-status /secure/release/post-negotiation-promotion-status.json \
  --api-base-url https://api.example.com \
  --output /secure/release/negotiation-proposal-promotion-activation.json
```

The verifier fails closed on stale evidence, rollout/deployment hash drift, source-revision mismatch, capability/provider drift, operation-allowlist drift, cohort overflow, non-HTTPS runtime access, stale health or a missing prerequisite.

A passing artifact has:

```text
status = negotiation_proposal_promotion_verified
```

and SHA-binds the exact staging, rollout, deployment, operator status, runtime snapshot and transaction-authority snapshot.

## Release-ledger attestation

A passing activation artifact must then be recorded through schema v27:

```bash
SHUDDHO_RELEASE_LEDGER_HMAC_KEY='<operations-key>' \
uv run python scripts/cohort_release_ledger.py append-negotiation-proposal-promotion \
  --ledger /secure/release/release-ledger.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference security-review \
  --change-reference change-negotiation-promotion-001 \
  --current-stage canary-5 \
  --staging-evidence /secure/release/staging-evidence.negotiation-promotion.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/negotiation-promotion-deployment.json \
  --operator-status /secure/release/post-negotiation-promotion-status.json \
  --negotiation-proposal-promotion-activation /secure/release/negotiation-proposal-promotion-activation.json
```

Schema v27 requires current-stage schema-v8 `action_proposals_verified` and schema-v26 `personal_transactions_verified` attestations. It rejects duplicate activation recording and revalidates the exact runtime, operation authority and artifact hashes before writing the HMAC-protected hash chain.

Only after the feature-specific activation and schema-v27 attestation exist can the generic release-activation bundle satisfy a reviewed rollout with `negotiation_proposal_promotion=true`.

## Rollback

If any check fails, keep or restore:

```text
SHUDDHO_NEGOTIATION_PROPOSAL_PROMOTION_ENABLED=false
```

This does not delete historical proposals/actions/receipts and does not enable or disable unrelated user-prepared action paths.
