# PA-10 managed API/worker recovery evidence

This controlled-staging probe complements the existing Temporal workflow-recovery exercise. It does not replace Temporal replay/fan-in evidence.

Use one dedicated synthetic active automation and one reviewed deployed release. The operator performs real platform restarts; the collector never restarts infrastructure itself.

Required guards:

```bash
export SHUDDHO_STAGING_ALLOW_MANAGED_RECOVERY=true
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL="<non-sensitive synthetic account label>"
export SHUDDHO_STAGING_EXPECTED_ENVIRONMENT="<exact non-production environment>"
export SHUDDHO_STAGING_DEPLOYMENT_REFERENCE="<reviewed deployment reference>"
export SHUDDHO_STAGING_API_BASE_URL="https://<staging-api-origin>"
export SHUDDHO_STAGING_TOKEN_A="<synthetic staging token>"
```

Prepare before the occurrence:

```bash
uv run --extra coworker python scripts/staging_pa10_managed_recovery.py prepare \
  --automation-id "<dedicated synthetic automation id>" \
  --rollout "<reviewed rollout manifest>" \
  --provider-policy-plan "<reviewed provider-policy plan>" \
  --state /tmp/pa10-managed-recovery-state.json
```

Allow exactly one approved synthetic occurrence during the drill. Restart or replace the staging API and Coworker worker through the real deployment platform. Retain real timestamps and durable platform references. Then verify:

```bash
uv run --extra coworker python scripts/staging_pa10_managed_recovery.py verify \
  --rollout "<same rollout manifest>" \
  --provider-policy-plan "<same provider-policy plan>" \
  --state /tmp/pa10-managed-recovery-state.json \
  --api-restart-at "<ISO-8601>" \
  --api-restart-reference "<platform reference>" \
  --worker-restart-at "<ISO-8601>" \
  --worker-restart-reference "<platform reference>" \
  --exercise-reference "<incident/drill reference>" \
  --output /tmp/pa10-managed-recovery-evidence.json
```

A pass requires the exact deployed release to remain unchanged, the automation revision to remain unchanged, exactly one new logical occurrence, a completed linked Agent run and exactly one matching `automation_completed` notice. The restart timestamps must be inside the prepared exercise window and supported by non-empty platform references.

This proves the observed PA-10 automation outcome across the recorded API/worker replacement exercise. It does not by itself prove a Temporal namespace outage, database restore, provider outage, or notification-device delivery; retain those separate evidence artifacts.
