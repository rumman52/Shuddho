# PA-10 simple scheduled reminder

The simple reminder profile is a notification-only PA-10 automation. It reuses the existing Temporal schedule reconciliation and durable occurrence ledger but **does not create an Agent run**.

## Contract

- `run_profile="reminder"`;
- daily or weekly Temporal schedule only;
- no connector-read grants;
- no Agent tool allowlist;
- bound to one active persistent-goal revision;
- one canonical occurrence key per automation revision + UTC due instant;
- one `automation_reminder` notification per admitted occurrence;
- `run_id` remains null;
- replay/restart returns the same occurrence and notification;
- pause/cancel/stale automation revision/expiry/goal pause/cancel/revision change block a new reminder;
- source authority is revalidated again when notification delivery is claimed, so revocation after enqueue suppresses the reminder before delivery;
- quiet hours delay visibility through the existing notification service;
- Browser Push, when separately enabled and consented, mirrors only generic Shuddho text.

The reminder body uses the already-reviewed bound goal objective and is capped to the existing 300-character notification limit.

## Controlled-staging evidence

Required guards:

```bash
export SHUDDHO_STAGING_ALLOW_SIMPLE_REMINDER=true
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT_LABEL="<non-sensitive synthetic account label>"
export SHUDDHO_STAGING_EXPECTED_ENVIRONMENT="<exact non-production environment>"
export SHUDDHO_STAGING_DEPLOYMENT_REFERENCE="<reviewed deployment reference>"
export SHUDDHO_STAGING_API_BASE_URL="https://<staging-api-origin>"
export SHUDDHO_STAGING_TOKEN_A="<synthetic staging token>"
```

Prepare before the due occurrence:

```bash
uv run --extra coworker python scripts/staging_pa10_simple_reminder.py prepare \
  --automation-id "<dedicated reminder automation id>" \
  --rollout "<reviewed rollout>" \
  --provider-policy-plan "<reviewed provider-policy plan>" \
  --state /tmp/pa10-reminder-state.json
```

For the app/browser-closed qualification case, close the user surface and allow exactly one normal Temporal due occurrence. Then verify:

```bash
uv run --extra coworker python scripts/staging_pa10_simple_reminder.py verify \
  --rollout "<same reviewed rollout>" \
  --provider-policy-plan "<same reviewed provider-policy plan>" \
  --state /tmp/pa10-reminder-state.json \
  --operator-case-reference "<test-run/ticket/reference>" \
  --output /tmp/pa10-reminder-evidence.json
```

A pass proves one new schedule-triggered `notified` occurrence, exactly one delivered `automation_reminder` notification and zero new Agent runs on the same reviewed release.

Repeat with fresh exercises for pause/resume/cancel, revision changes, goal revocation, quiet hours and restart/replay cases. Repository tests are not a substitute for those controlled-staging exercises.
