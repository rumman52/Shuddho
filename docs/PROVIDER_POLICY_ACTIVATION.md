# Provider Policy Activation Verification

The adaptive provider-policy compiler produces a bounded proposal. It does not prove that production actually uses those limits.

This verifier closes that gap before cohort expansion.

## Required order

1. Produce an `ELIGIBLE_FOR_POLICY_REVIEW` provider-policy proposal.
2. Approve and deploy the exact proposed environment values.
3. Record the deployment change with the SHA-256 of the exact policy proposal.
4. Generate a fresh clean operator status after deployment.
5. Run provider-policy activation verification.
6. Append the resulting evidence to the release ledger as schema-v5 `provider_policy_verified`.
7. Only then run bounded cohort scale activation.

## What is verified

The verifier requires:

- the exact provider policy to be eligible and failure-free;
- a deployment record bound to that exact policy SHA-256;
- deployment to occur after policy generation;
- all deployed provider concurrency, reserve, global daily-budget, workspace daily-budget and lease settings to match the reviewed proposal exactly;
- aggregate active calls, token reservations and current UTC-day allocation to remain within those deployed limits;
- a fresh `CONTINUE_COHORT` operator status generated after the policy deployment.

The output contains only policy values, aggregate runtime counters, references and SHA-256 hashes. It does not contain account IDs, provider keys or user content.

## Run

```bash
uv run --extra coworker python scripts/provider_policy_activation.py \
  --provider-policy /secure/release/provider-policy-proposal.json \
  --deployment-change /secure/release/provider-policy-deployment.json \
  --operator-status /secure/release/post-policy-operator-status.json \
  --freshness-minutes 30 \
  --output /secure/release/provider-policy-activation.json
```

Then append it to the release ledger:

```bash
uv run python scripts/cohort_release_ledger.py append-provider-policy \
  --ledger /secure/release/coworker-cohort-001.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference oncall-primary \
  --change-reference provider-policy-change-001 \
  --current-stage cohort-25 \
  --next-stage cohort-40 \
  --provider-policy /secure/release/provider-policy-proposal.json \
  --deployment-change /secure/release/provider-policy-deployment.json \
  --operator-status /secure/release/post-policy-operator-status.json \
  --policy-activation /secure/release/provider-policy-activation.json
```

Future cohort activation verifies that this exact activation artifact is already ledgered before cohort membership is expanded.
