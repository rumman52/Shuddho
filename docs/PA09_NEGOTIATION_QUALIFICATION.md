# PA-09 Negotiation Commitment Qualification

This runbook qualifies only the first bounded PA-09 transaction adapter: `negotiation_commitment_email`.

It does **not** qualify shopping checkout, payment, travel booking, restaurant reservation, fee-bearing cancellation, browser purchase, or autonomous negotiation. Browser and sandbox capabilities do not inherit this authority.

## Runtime boundary

The feature remains disabled by default:

```text
SHUDDHO_ACTIONS_ENABLED=false
SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=false
SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=false
SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS=
```

When reviewed for a controlled cohort, the three capability prerequisites must be enabled together **and** the exact provider/action pair must appear in `SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS`. For the Google negotiation slice that value is `google:negotiation_commitment_email`; Microsoft requires its own separately reviewed `microsoft:negotiation_commitment_email` entry. The broad PA-09 flag does not grant authority by itself. The transaction action still requires a human-created immutable preview and a separate explicit approval. The Agent planner cannot create, promote, approve, or execute it.

## Controlled staging

Use only a dedicated synthetic staging mailbox and a dedicated counterparty test mailbox. Do not use customer data or real commercial terms.

Required guard:

```text
SHUDDHO_STAGING_ALLOW_LIVE_PERSONAL_TRANSACTIONS=true
SHUDDHO_STAGING_TRANSACTION_COUNTERPARTY_EMAIL=<dedicated-test-mailbox>
SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS=google:negotiation_commitment_email
```

The staging probe first reads the authenticated `/api/v1/transaction-authority-manifest` and refuses to contact the provider unless that deployed manifest contains the exact requested `provider:action_kind`.

Run the Google baseline probe:

```bash
uv run python -m scripts.staging_live_personal_transactions \
  --provider google \
  --base-evidence /secure/release/staging-evidence.json \
  --output /secure/release/staging-evidence-pa09.json
```

If Microsoft Mail is part of the reviewed provider set, run the same guarded probe with `--provider microsoft` using the dedicated Microsoft staging connection before approving that provider for PA-09.

The probe proves:

- exactly one active owned email connection is selected for the provider;
- the prepared action is still `awaiting_approval` and has no receipt;
- preview version 6 and transaction policy are present;
- exact primary counterparty, message, summary and final terms are approval-bound;
- a wrong preview hash is rejected;
- no provider mutation occurs before explicit approval;
- one approved execution produces one provider-acceptance receipt;
- Gmail acceptance is not represented as delivery/read/agreement;
- Microsoft Graph acceptance is not represented as delivery/read/agreement.

The live probe intentionally does not inject a provider timeout after mutation. PA-09 CI fault-injection tests prove that an uncertain mutation is not reclaimed for blind resend. Do not add a production/staging backdoor solely to force provider uncertainty.

## Production activation evidence

After the reviewed deployment, generate fresh PA-09 activation evidence:

```bash
SHUDDHO_PRODUCTION_VERIFICATION_TOKEN=<short-lived-admitted-token> \
uv run python -m scripts.personal_transactions_activation \
  --staging-evidence /secure/release/staging-evidence-pa09.json \
  --rollout /secure/release/reviewed-rollout.json \
  --deployment-change /secure/release/deployment-change.json \
  --operator-status /secure/release/operator-status.json \
  --api-base-url https://YOUR-COWORKER-API \
  --output /secure/release/personal-transactions-activation.json
```

The verifier requires:

- fresh passed `personal_transactions` staging evidence;
- a valid production rollout with `actions=true`, `connector_trust_boundary=true`, and `personal_transactions=true`;
- the exact kill switch `SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=false`;
- the Google action-provider baseline;
- deployment SHA/time bindings to the exact staging and rollout files;
- fresh clean `CONTINUE_COHORT` operator status;
- an authenticated deployed runtime manifest whose normalized capabilities and action-provider set exactly match the reviewed rollout;
- an authenticated transaction-authority manifest whose source revision and exact operation allowlist match the reviewed rollout;
- enforced cohort admission with the reviewed ceiling.

It emits `personal_transactions_verified`.

## Tamper-evident ledger

Record the exact activation artifact as schema v26:

```bash
SHUDDHO_RELEASE_LEDGER_HMAC_KEY=<operations-key> \
uv run python scripts/cohort_release_ledger.py append-personal-transactions \
  --ledger /secure/release/release-ledger.jsonl \
  --release-id coworker-cohort-001 \
  --actor-reference security-review \
  --change-reference CHANGE-TICKET \
  --current-stage canary-5 \
  --staging-evidence /secure/release/staging-evidence-pa09.json \
  --rollout /secure/release/reviewed-rollout.json \
  --deployment-change /secure/release/deployment-change.json \
  --operator-status /secure/release/operator-status.json \
  --personal-transactions-activation /secure/release/personal-transactions-activation.json
```

The ledger writer verifies the activation again and refuses duplicate attestation.

## Release bundle, scale and recovery

Add the exact artifact to the controlled release activation manifest when `personal_transactions=true`:

```json
{
  "personal_transactions": "/secure/release/personal-transactions-activation.json"
}
```

`scripts.release_activation_bundle` derives this requirement from `scripts/release_contract.py` and requires exactly one matching schema-v26 ledger event. Scale and recovery continue to require the exact reviewed activation bundle, so a post-rollback or changed rollout cannot reuse stale PA-09 proof.

## Rollback

The PA-09 broad kill switch is:

```text
SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED=false
```

Disabling it blocks new previews and cancels an approved-but-unclaimed PA-09 action before provider mutation. Removing a single operation from `SHUDDHO_PERSONAL_TRANSACTION_OPERATIONS` also blocks that operation at preview time and is rechecked at the final execution claim before provider mutation. It does not claim that an already executing or uncertain provider mutation was undone. Preserve receipts and uncertain outcomes for operator/user review.

## Qualification status

Code completion, CI success, live staging qualification and production activation are separate states. This runbook authorizes no production transaction by itself.
