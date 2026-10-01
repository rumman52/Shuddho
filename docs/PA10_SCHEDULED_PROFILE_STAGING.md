# PA-10 scheduled-profile controlled-staging probe

Use `scripts/staging_pa10_scheduled_profile.py` to collect consistent release-bound evidence for one real Temporal-scheduled occurrence of the non-provider PA-10 profiles:

- `scheduled_reminder` → ordinary `goal` profile on a daily/weekly schedule;
- `daily_coworker` → `briefing` profile on a daily schedule;
- `weekly_coworker` → `briefing` profile on a weekly schedule;
- `deadline_coworker` → `deadline` profile on a daily/weekly schedule;
- `goal_driven_proactivity` → `proactive` profile on a daily/weekly schedule.

The probe records a baseline from the owner-scoped automation history and inbox, waits for exactly one new schedule occurrence, and accepts evidence only when it links one completed Agent run plus exactly one start and one completion notice. It binds the artifact to the deployed source revision, release ID, rollout hash, provider-policy hash and deployment reference.

This does **not** turn one happy-path run into complete qualification. Repeat with fresh artifacts for each applicable matrix case: timezone/DST, edit, pause/resume, restart, quiet hours, deadline thresholds/unchanged suppression, useful-action/no-action and scope/revocation cases.

Required guards are `SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES=true`, `SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true`, the standard staging API/token/account label, exact expected environment and deployment reference.

Example:

```bash
uv run --extra coworker python scripts/staging_pa10_scheduled_profile.py prepare \
  --scenario daily_coworker \
  --automation-id "<dedicated synthetic automation>" \
  --rollout "<reviewed rollout>" \
  --provider-policy-plan "<reviewed provider policy>" \
  --state /tmp/pa10-daily-state.json

uv run --extra coworker python scripts/staging_pa10_scheduled_profile.py verify \
  --rollout "<same reviewed rollout>" \
  --provider-policy-plan "<same reviewed provider policy>" \
  --state /tmp/pa10-daily-state.json \
  --operator-case-reference "<test-run/ticket/reference>" \
  --output /tmp/pa10-daily-evidence.json
```
