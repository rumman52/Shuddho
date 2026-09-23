# Approved Attachment Production Activation

This verifier proves that the reviewed production deployment is the exact deployment that passed the approved-email-attachment release gate.

It does not trust shell flags as production proof. It binds:

1. fresh timestamped live `action_attachments` staging evidence;
2. the exact reviewed controlled-cohort rollout manifest;
3. a reviewed deployment record with exact source revision and SHA-256 bindings;
4. the authenticated deployed `/api/v1/runtime-manifest`;
5. fresh post-deploy `CONTINUE_COHORT` health with zero breaches.

Only then does it emit `action_attachments_verified`.

## Reviewed rollout requirements

The rollout must declare:

```json
"action_attachments": true
```

and the exact rollback switch:

```text
SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false
```

The controlled-cohort release gate also requires `actions=true`, `artifact_services=true`, and independent live attachment evidence.

## Required order

1. Run [Controlled Staging Live Approved Email Attachments](CONTROLLED_STAGING_ACTION_ATTACHMENTS.md).
2. Retain the exact resulting staging evidence.
3. Review the exact rollout manifest with `action_attachments=true`.
4. Fill `docs/action-attachments-deployment.template.json` with the exact release/stage/change reference, full 40-character source revision, deployment timestamp, and SHA-256 values of the staging evidence and rollout manifest.
5. Deploy that exact revision/configuration.
6. Generate fresh post-deploy operator status.
7. Export a short-lived admitted verification token as `SHUDDHO_PRODUCTION_VERIFICATION_TOKEN`.
8. Run the activation verifier.

## Run

```bash
export SHUDDHO_PRODUCTION_VERIFICATION_TOKEN='<short-lived-token>'

uv run --extra coworker python scripts/action_attachments_activation.py \
  --staging-evidence /secure/release/staging-evidence.action-attachments.json \
  --rollout /secure/release/cohort-rollout.json \
  --deployment-change /secure/release/action-attachments-deployment.json \
  --operator-status /secure/release/post-attachment-status.json \
  --api-base-url https://api.example.com \
  --max-cohort-users 25 \
  --max-staging-age-minutes 1440 \
  --freshness-minutes 30 \
  --output /secure/release/action-attachments-activation.json
```

## Remote proof

The authenticated runtime manifest must exactly match the reviewed deployment:

- full source revision;
- production environment;
- exact normalized capability map, including `action_attachments=true`;
- exact action-provider set;
- controlled-cohort enforcement on;
- configured membership within the reviewed cohort ceiling.

The verifier fails closed on redirects, non-HTTPS origins, stale staging evidence, artifact-hash drift, revision/config drift, cohort overflow or breached/stale operator health.

## Activation boundary

This increment creates production activation evidence but does **not** automatically flip the feature flag and does not silently authorize broader cohort expansion. Operators must keep the flag off until the reviewed deployment sequence is complete.

After this activation verifier is green, record the exact proof through release-ledger schema v9 `action_attachments_verified`.

Schema v9 independently re-verifies the exact staging proof, reviewed rollout, deployment record, runtime capability/provider snapshot, cohort enforcement, operator status and activation artifact before appending to the HMAC-protected release chain. Use `append-action-attachments` as documented in [Controlled Cohort Release Ledger](CONTROLLED_COHORT_RELEASE_LEDGER.md).

Attachment-enabled bounded scale and post-rollback recovery now consume that ledgered proof. Scale/recovery evidence upgrades to schema v4 only when `SHUDDHO_ACTION_ATTACHMENTS_ENABLED=true`; when the flag is off, existing schema-v3 evidence remains unchanged. Recovery additionally requires the schema-v9 event to occur after the exact rollback-completion event.

## Rollback

Set:

```text
SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false
```

and redeploy API/workers. Do not delete action history, approval records, or artifact rows as routine rollback.
