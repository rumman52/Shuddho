# PA-10 scheduled-profile controlled-staging probe

Use `scripts/staging_pa10_scheduled_profile.py` to collect consistent release-bound evidence for one real Temporal-scheduled **Agent-backed** occurrence of the non-provider PA-10 profiles:

- `daily_coworker` → `briefing` profile on a daily schedule;
- `weekly_coworker` → `briefing` profile on a weekly schedule;
- `deadline_coworker` → `deadline` profile on a daily/weekly schedule;
- `goal_driven_proactivity` → `proactive` profile on a daily/weekly schedule.

The probe records a baseline from owner-scoped automation history and inbox and waits for one new occurrence with a completed Agent run. **Briefings have exactly one completion notice per occurrence** (no start notice); deadline/proactive profiles retain one start and one completion notice.

The PA-10 matrix's **simple scheduled reminder** remains intentionally excluded from this Agent-backed collector because it now has a dedicated notification-only path and dedicated `scripts/staging_pa10_simple_reminder.py` verifier. Do not qualify reminders through this scheduled-profile script. This script remains for Agent-backed Daily/Weekly/Deadline/goal-driven profiles.

This does **not** turn one happy-path run into complete qualification. Repeat with fresh artifacts for each applicable matrix case: timezone/DST, edit, pause/resume, restart, quiet hours, deadline thresholds/unchanged suppression, useful-action/no-action and scope/revocation cases.

Required guards are `SHUDDHO_STAGING_ALLOW_SCHEDULED_PROFILES=true`, `SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true`, the standard staging API/token/account label, exact expected environment and deployment reference.

**Credentialed API-origin boundary:** `SHUDDHO_STAGING_API_BASE_URL` must be a single public HTTPS origin (one optional trailing slash, optional valid port). The scheduled-profile probe rejects local/IP destinations, whitespace or control characters, path suffixes, query/fragment markers and malformed ports before using the synthetic bearer token. This is only a static URL-shape gate; it does **not** prove DNS control, TLS identity, ownership or permission to send a token. Keep the token in approved secret storage and the staging execution guards disabled until the owner authorizes the exercise.

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

The controlled Day 7 probe now fetches the synthetic account's **live, owner-scoped
persistent goal** and its **owner-owned project** at prepare, verify, and before
pausing. The goal must be active, its revision must match the automation's pinned
`goal_revision`, its explicit `project_id` must resolve to a live project owned
by the same account, and every selected document must remain linked to that
project. Its approved resources must consist of **one to five distinct documents
only**, with no connected read grants or memory namespaces. The automation must
have an explicit future `expires_at`, and the API must report
`schedule_applied_revision == revision`, `schedule_applied_enabled == true`,
and no schedule error before the probe proceeds. The `goal_id`,
`goal_revision`, `project_id`, `authorized_document_ids`, expiry, and applied
schedule revision are captured in the evidence and checked against the Agent
run's actual `document_ids` on both days. The pause gate then requires the
Temporal worker to apply the new paused revision with
`schedule_applied_enabled == false`; the approved expiry must remain after the
Day 8 pause. Any change of goal revision,
approved read scope, or run document set fails closed; uploading a new version
of the **same** approved document does not change that scope. The offline gate
checks evidence consistency, but the operator must still authenticate the live
API observations and independent Temporal schedule logs.

1. Confirm the staging runtime manifest and reviewed rollout/provider-policy plan,
   then use the synthetic workspace UI to create a project, upload source version 1,
   approve a persistent goal with exactly that document read scope, and separately
   approve a **daily** briefing schedule in a named IANA timezone. Choose a local
   time a few minutes after staging preparation; document the schedule ID,
   deployment, owner approval, worker health, and quiet-hour notification rule.
   Set the staging guard variables, expected environment, nonproduction API origin,
   synthetic account label, bearer token, and deployment reference documented above;
   never place credentials in evidence artifacts. **Choose an unambiguous local time
   across the staging validity period.** If the next due time lands in the autumn
   repeated hour (for example, 01:30 occurs twice), the offline gate now blocks:
   selecting Python's default DST fold is not independent proof of which UTC
   instant Temporal scheduled. Re-approve an unambiguous time and recapture
   new natural-day evidence instead of manually editing a UTC timestamp.
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
   owner-scoped, revision-checked pause request, then reads the paused state back
   and captures the owner's exact occurrence/run/notification baseline. **This
   immediate pause receipt is preliminary and cannot pass the final two-day gate.**
5. Leave that synthetic schedule paused through its *next* approved local daily
   opportunity, including the full configured catch-up window (60–86,400 seconds).
   The approved expiry must be later than the opportunity. Only then run the
   **read-only**, owner-authenticated `staging_day7_paused_opportunity` observer;
   it rejects release/owner/goal drift, resumed state, missing baseline rows and
   any new stored occurrence, run or notification. It writes a new pause receipt
   with an explicit due timestamp and observation timestamp. No automated wait,
   shortened time window, manual Temporal trigger or fabricated timestamp qualifies.
6. Run the offline gate with the **observed** pause receipt. Independently review
   both days' natural Temporal schedule histories, server/worker recovery, and
   actual notification transport logs (the owner inbox only proves persistence,
   not downstream physical delivery). Complete the other controlled Day 7 edge
   cases separately; no JSON file substitutes for those operational receipts.

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

# At the following approved local scheduled time PLUS the complete catch-up
# window, use the SAME synthetic token/release; this command only performs GETs.
uv run --locked --extra coworker python -m scripts.staging_day7_paused_opportunity \
  --rollout "$ROLLOUT" --provider-policy-plan "$PROVIDER_POLICY" \
  --first-evidence /tmp/day7-evidence.json \
  --second-evidence /tmp/day8-evidence.json \
  --pause-evidence /tmp/day8-pause.json \
  --operator-case-reference "$CASE_ID" \
  --output /tmp/day8-paused-opportunity.json

uv run --locked --extra coworker python -m scripts.staging_day7_two_day_gate \
  --first /tmp/day7-evidence.json --second /tmp/day8-evidence.json \
  --pause /tmp/day8-paused-opportunity.json \
  --output /tmp/day7-two-day-acceptance.json
```

The pause collector also rejects *any extra stored occurrence, run or
briefing notification* in the two-date synthetic automation's baseline. It
must contain exactly the two independently observed natural occurrences,
their two runs and their two completion-notice IDs; an extra pre-baseline
admission or notice cannot be silently relabeled as authorized history.
Use **separate** controlled automations for replay, restart, quiet-hours and
other edge cases rather than contaminating this clean two-date ledger.

The gate checks release/account/automation consistency; one completed run and
**exactly one unique completion notice per briefing occurrence**; exact scheduled
local clock time; consecutive **local** calendar days (including DST transitions);
identical authorized document IDs; a changed immutable version pin on Day 8;
the unchanged original Day 7 pin when re-read; the persisted pause transition;
and **zero** new owner-scoped stored occurrences, runs and notifications after
the following scheduled local time and catch-up window. The pause-only artifact
is intentionally insufficient.

The generated report includes `owner_local_receipts`: the owner-IANA-zone
`day7_due_at`, `day7_verified_at`, `day8_due_at`, `day8_verified_at`,
`paused_at`, `post_pause_due_at` and the actual
`post_pause_observed_at`. Each present ISO 8601 timestamp records **both the
local calendar date/time and the UTC offset**, including differing offsets on
successive DST dates. During the preliminary `preflight_only` receipt,
`post_pause_observed_at` is explicitly `null`, not synthesized. A non-existent
spring-forward scheduled time and an ambiguous fall-back next due time both
fail closed. The report uses UTC instants to calculate ordering and retains
owner-local timestamps solely for independent audit.

Attach the independent Temporal
schedule provenance and operational notification/worker observations to the
operator case before declaring the actual natural-firing acceptance complete.
