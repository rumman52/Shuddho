# PA-10 scheduled-profile controlled-staging probe

Use `scripts/staging_pa10_scheduled_profile.py` to collect consistent release-bound evidence for one real Temporal-scheduled **Agent-backed** occurrence of the non-provider PA-10 profiles:

- `daily_coworker` → `briefing` profile on a daily schedule;
- `weekly_coworker` → `briefing` profile on a weekly schedule;
- `deadline_coworker` → `deadline` profile on a daily/weekly schedule;
- `goal_driven_proactivity` → `proactive` profile on a daily/weekly schedule.

The probe records a baseline from the owner-scoped automation history and inbox, waits for exactly one new schedule occurrence, and accepts evidence only when it links one completed Agent run plus exactly one start and one completion notice.

The PA-10 matrix's **simple scheduled reminder** remains intentionally excluded from this Agent-backed collector because it now has a dedicated notification-only path and dedicated `scripts/staging_pa10_simple_reminder.py` verifier. Do not qualify reminders through this scheduled-profile script. This script remains for Agent-backed Daily/Weekly/Deadline/goal-driven profiles.

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

## Day 7 / Day 8 — two naturally scheduled briefings with fresh source pins

This additional **operated acceptance** is not replaced by controlled timestamps in tests or
Temporal's explicit `handle.trigger()` API. It requires an approved nonproduction
synthetic account, user-approved recurring daily briefing, a linked project document,
real Temporal calendar firings on **two consecutive local dates**, and a durable
operator case linking the unmodified Temporal Schedule history. Do not use real
users, manually trigger the schedule, accelerate the clock, or call this gate passed
before the second natural day. A passing JSON comparison **alone** cannot prove
that a Temporal firing was natural instead of manually triggered.

1. Confirm the staging runtime manifest and reviewed rollout/provider-policy plan,
   then use the synthetic workspace UI to create a project, upload source version 1,
   approve a persistent goal with exactly that document read scope, and separately
   approve a **daily** briefing schedule in a named IANA timezone. Choose a local
   time a few minutes after staging preparation; document the schedule ID,
   deployment, owner approval, worker health, and quiet-hour notification rule.
   Set the staging guard variables, expected environment, nonproduction API origin,
   synthetic account label, bearer token, and deployment reference documented above;
   never place credentials in evidence artifacts.
2. **Before Day 7's scheduled time**, collect a baseline. Allow the actual Temporal
   schedule to fire while the user is absent. Record Temporal schedule/audit logs,
   run completion, history, and notifications, and verify that day. The resulting
   file now includes owner-scoped `document_ids` and immutable
   `input_version_ids` for the completed Agent run.
3. Update the **same authorized source document** to version 2 after the first
   occurrence; do not edit or recreate the automation. **Before Day 8's scheduled
   time**, prepare a new baseline. Allow the next *natural* local-calendar-day
   occurrence, then verify it using `--prior-evidence` to re-read the Day 7 run's
   original immutable version pins. A worker restart may occur between days; record
   its deployment/worker evidence rather than triggering an extra run.
4. Pause the **same synthetic automation** only after both passed day records exist.
   The guarded `pause-two-day` command validates the pair *before* issuing the
   owner-scoped, revision-checked pause request, then reads the paused state back.
   Finally run the offline two-day evidence gate and independently review the
   real Temporal natural-firing logs and absence of extra accepted runs.

```bash
# The SHUDDHO_STAGING_* gates described above must be set in a reviewed synthetic
# staging environment. Do not run these commands against production.
uv run --extra coworker python scripts/staging_pa10_scheduled_profile.py prepare \
  --scenario daily_coworker --automation-id "$SYNTHETIC_AUTOMATION_ID" \
  --rollout "$ROLLOUT" --provider-policy-plan "$PROVIDER_POLICY" \
  --state /tmp/day7-state.json

# After the first *natural* daily occurrence and its Agent run completes:
uv run --extra coworker python scripts/staging_pa10_scheduled_profile.py verify \
  --rollout "$ROLLOUT" --provider-policy-plan "$PROVIDER_POLICY" \
  --state /tmp/day7-state.json --operator-case-reference "$CASE_ID" \
  --output /tmp/day7-evidence.json

# Upload version 2 of the SAME authorized source document. Before Day 8's time:
uv run --extra coworker python scripts/staging_pa10_scheduled_profile.py prepare \
  --scenario daily_coworker --automation-id "$SYNTHETIC_AUTOMATION_ID" \
  --rollout "$ROLLOUT" --provider-policy-plan "$PROVIDER_POLICY" \
  --state /tmp/day8-state.json

# After the second *natural* daily occurrence and run completion:
uv run --extra coworker python scripts/staging_pa10_scheduled_profile.py verify \
  --rollout "$ROLLOUT" --provider-policy-plan "$PROVIDER_POLICY" \
  --state /tmp/day8-state.json --operator-case-reference "$CASE_ID" \
  --prior-evidence /tmp/day7-evidence.json --output /tmp/day8-evidence.json

# Only after two passed day records, pause and read back the synthetic schedule:
uv run --extra coworker python scripts/staging_pa10_scheduled_profile.py pause-two-day \
  --rollout "$ROLLOUT" --provider-policy-plan "$PROVIDER_POLICY" \
  --state /tmp/day8-state.json \
  --first-evidence /tmp/day7-evidence.json \
  --second-evidence /tmp/day8-evidence.json \
  --operator-case-reference "$CASE_ID" --output /tmp/day8-pause.json

uv run --extra coworker python scripts/staging_day7_two_day_gate.py \
  --first /tmp/day7-evidence.json --second /tmp/day8-evidence.json \
  --pause /tmp/day8-pause.json --output /tmp/day7-two-day-acceptance.json
```

The gate checks release/account/automation consistency; one completed run and two
unique notices each day; exact scheduled local clock time; consecutive **local**
calendar days (including DST transitions); identical authorized document IDs; a
changed immutable version pin on Day 8; the unchanged original Day 7 pin when
re-read; and the persisted pause transition. Attach the independent Temporal
schedule provenance and operational notification/worker observations to the
operator case before declaring the actual natural-firing acceptance complete.
