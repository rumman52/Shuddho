# PA-10 controlled staging completion runbook

This runbook is for the remaining Automation / Proactive Coworker qualification after repository implementation is green. It does not turn repository tests into live evidence.

## Prerequisites

Use an approved non-production staging environment with:

- the exact reviewed source revision deployed;
- the reviewed rollout manifest and provider-policy plan;
- isolated synthetic test accounts;
- PostgreSQL and Temporal staging services;
- controlled Google and Microsoft OAuth credentials/accounts;
- Browser Push VAPID configuration and an approved real browser/device;
- DeepSeek staging credentials only when live Runtime-v3 evaluation is explicitly authorized;
- production flags still unchanged.

Retain timestamps, deployment/platform references and provider receipts. Never use customer messages, calendars or credentials as test fixtures.

## Existing guarded approval-boundary probes

These scripts validate live **approved write actions** and the immutable-preview/explicit-approval boundary. They do not qualify proactive read-event intake.

Google:

```bash
SHUDDHO_STAGING_ALLOW_LIVE_GOOGLE_ACTIONS=true \
uv run --extra coworker python scripts/staging_live_google_actions.py \
  --output /tmp/google-action-evidence.json
```

The script additionally requires its documented staging API/token/recipient environment values and exactly one active Google email/calendar action connection.

Microsoft:

```bash
SHUDDHO_STAGING_ALLOW_LIVE_MICROSOFT_ACTIONS=true \
uv run --extra coworker python scripts/staging_live_microsoft_actions.py \
  --output /tmp/microsoft-action-evidence.json
```

The script additionally requires its documented staging API/token/recipient environment values, Microsoft actions enabled in staging and exactly one active Microsoft email/calendar action connection.

Passing either command proves only the action approval/receipt checks implemented by that script. It does not prove Gmail/Outlook read-event dedupe, Meeting Coworker, Email Coworker or Browser Push.

## Temporal worker-restart qualification

Prepare the existing controlled recovery workflow:

```bash
uv run --extra coworker python scripts/staging_temporal_recovery.py prepare \
  --state /tmp/temporal-recovery-state.json \
  --rollout docs/cohort-rollout.template.json
```

Restart or replace the staging Coworker worker while the run is active and retain the real platform restart timestamp/reference. Then verify:

```bash
uv run --extra coworker python scripts/staging_temporal_recovery.py verify \
  --state /tmp/temporal-recovery-state.json \
  --restart-at "<ISO-8601 timestamp>" \
  --restart-reference "<deployment/pod/platform reference>" \
  --rollout docs/cohort-rollout.template.json \
  --output /tmp/temporal-recovery-evidence.json
```

Use a reviewed deployed rollout file for real qualification; the repository template above shows the command shape and must not be substituted for an unreviewed deployment manifest.

## Flag rollback qualification

Prepare:

```bash
uv run --extra coworker python scripts/staging_flag_rollback.py prepare \
  --state /tmp/flag-rollback-state.json \
  --rollout docs/cohort-rollout.template.json
```

Apply the controlled flag rollback required by the script, retain the real rollout/deployment reference, then verify:

```bash
uv run --extra coworker python scripts/staging_flag_rollback.py verify \
  --state /tmp/flag-rollback-state.json \
  --rollout-reference "<deployment/rollout reference>" \
  --rollout docs/cohort-rollout.template.json \
  --output /tmp/flag-rollback-evidence.json
```

## Runtime-v3 live quality evaluation

When DeepSeek staging access and a reviewed rollout are explicitly authorized:

```bash
uv run --extra coworker python scripts/agent_eval.py \
  --live --runtime-v3 \
  --release-id "<reviewed release id>" \
  --rollout "<reviewed rollout manifest>" \
  --min-pass-rate 1.0 \
  --output /tmp/agent-runtime-v3-eval.json
```

This is a model-routing/typed-decision evaluation. The PA-10 evidence matrix still requires human review of proactive relevance, timing, grounding, actionability, noise and safety for representative Bangla and English scenarios.

## Task economics

Collect measured completed proactive-task usage into the existing PA-11 sample schema. Compile it only with the reviewed rollout, provider policy and reviewed pricing plan:

```bash
uv run --extra coworker python scripts/task_economics_evidence.py \
  --rollout "<reviewed rollout manifest>" \
  --provider-policy-plan "<reviewed provider policy plan>" \
  --pricing-plan "<reviewed pricing plan>" \
  --samples "<measured proactive task samples>" \
  --output /tmp/proactive-task-economics.json
```

Do not fabricate sample rows. The completed-task cohort must contain real staging measurements.

## Expanded proactive scenarios

For the same reviewed release, collect evidence for:

1. Daily and Weekly schedules across timezone/DST, edit, pause/resume and app/worker restart.
2. Meeting Coworker: upcoming event, recurring occurrence, reschedule, cancel, calendar-grant revocation, exact one preparation.
3. Email Coworker: authenticated Gmail and Outlook read events, duplicate/delayed/out-of-order delivery, deleted message, token expiry/refresh, disconnect/reconnect, malicious content, exact draft-only boundary.
4. Deadline Coworker: 7d/72h/24h/overdue threshold transitions, unchanged-state suppression, edited deadline and paused/completed goal.
5. Goal-driven proactivity: useful-action and no-action outcomes, exact reviewed tool scope, selected-context revocation and finite stop.
6. Browser Push: explicit opt-in, real delivery with browser closed, reopen, multiple devices, endpoint retirement, retry, quiet hours, disable and cross-owner rejection.
7. API/worker/Temporal failure injection with one logical recovered outcome and no duplicate notice.
8. Consequential action approval: automation may prepare the exact action but must not execute until immutable preview, explicit approval and fresh authorization.
9. Prompt-injection content in email/calendar/web context with no authority expansion or secret disclosure.
10. Multilingual proactive samples including Bangla and English.
11. Economics evidence reporting cost per completed useful proactive task.

## Missing live proactive-read probe

The repository currently contains guarded live Google/Microsoft **action** scripts, but no dedicated operator script that automatically drives and validates the complete proactive Gmail/Outlook/Calendar read-event scenarios above. Until an approved staging environment performs those scenarios and evidence is reviewed, mark provider/proactive live qualification **NOT VERIFIED**.

## Completion rule

Repository-green plus this runbook is not staging qualification. Sign the expanded `automations` release gate only after the evidence matrix has fresh passing evidence from the same reviewed release. Production activation remains a separate decision.
