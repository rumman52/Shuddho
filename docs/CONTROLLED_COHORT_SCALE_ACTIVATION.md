# Controlled Cohort Scale Activation Verification

The bounded scale-review gate authorizes only a reviewed **proposal**. It does not prove that the production deployment actually applied the reviewed cohort ceiling or that server-side admission still works afterward.

This increment closes that gap.

## What is verified

After a human-approved deployment change, the verifier requires:

- the exact scale-review artifact to say `ELIGIBLE_FOR_BOUNDED_EXPANSION`;
- the exact provider-policy activation for this current → proposed stage to already be recorded as schema-v5 `provider_policy_verified` in the release ledger;
- when deployed Microsoft actions are enabled, the exact `microsoft_rollout_verified` activation artifact to already be recorded as one matching schema-v6 event for the current stage;
- a deployment-change record for the same release, stage, reviewed max users, and change reference;
- the deployment timestamp to be after the scale-review decision;
- backend cohort enforcement to remain enabled;
- the deployed `SHUDDHO_COWORKER_COHORT_MAX_USERS` to equal the reviewed proposed maximum exactly;
- configured membership to be larger than the previous cohort but no larger than the reviewed maximum;
- one allowed verification identity to succeed through the deployed API;
- one fresh non-member identity to receive `403 cohort_not_enabled` before provisioning;
- a fresh `CONTINUE_COHORT` operator status with zero breaches generated after the deployment change.

No account identifiers are written to the evidence artifact.

## Run

Provide a short-lived allowed verification token and a fresh denied identity:

```bash
export SHUDDHO_SCALE_VERIFY_TOKEN_ALLOWED=...
export SHUDDHO_SCALE_VERIFY_TOKEN_DENIED=...

uv run --extra coworker python scripts/cohort_scale_activation.py \
  --scale-decision /secure/release/bounded-scale-decision.json \
  --deployment-change /secure/release/cohort-scale-deployment.json \
  --operator-status /secure/release/post-scale-operator-status.json \
  --provider-policy-activation /secure/release/provider-policy-activation.json \
  --microsoft-rollout-activation /secure/release/microsoft-rollout-activation.json \
  --release-ledger /secure/release/coworker-cohort-001.jsonl \
  --freshness-minutes 30 \
  --output /secure/release/bounded-scale-activation.json
```

The verifier reads the real deployed Coworker settings, verifies the tamper-evident release ledger, and checks the deployed HTTPS API. It does not update the allowlist, provider policy, or any feature flag.

## Release ledger

After successful verification, append a schema-v4 `bounded_expansion_verified` event to the existing release ledger. The event binds the exact scale decision, deployment record, post-deploy operator status, and activation-verification artifact by SHA-256.

That event is evidence that the reviewed stage was actually activated and verified. It still does not authorize another expansion. The newly activated stage must accumulate fresh health and demand evidence before another scale review.


## Post-scale observation

After the schema-v4 activation event is committed, begin a fresh observation epoch using [post-scale cohort observation](POST_SCALE_COHORT_OBSERVATION.md).

Only health generated after the ledgered activation may count. The new stage must earn sustained healthy windows and real usage samples before it can re-enter capacity qualification for any later scale review.


## Microsoft-enabled expansion

Google-only releases remain backward-compatible: if `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=false`, no Microsoft rollout artifact is required.

If the deployed backend has `SHUDDHO_MICROSOFT_ACTIONS_ENABLED=true`, bounded scale activation fails closed unless all of the following are true:

- `--microsoft-rollout-activation` is supplied;
- the artifact status is `microsoft_rollout_verified`;
- its release ID matches the scale decision;
- it proves backend global actions and backend Microsoft actions are enabled;
- it proves Coworker frontend and Microsoft provider UI are enabled;
- the tamper-evident ledger verifies successfully;
- exactly one schema-v6 `microsoft_rollout_verified` event for the current stage binds the exact activation artifact SHA-256.

The bounded scale activation evidence also records the Microsoft rollout activation SHA-256 when Microsoft is enabled. This makes later scale evidence cryptographically dependent on the exact rollout proof rather than only on the current runtime flag.
