# Day 2 — prove the real staging execution loop (12 November 2026)

**Disposition: SOURCE WORK IN REVIEW; LIVE ACCEPTANCE BLOCKED.** This is a
controlled nonproduction operator contract, not evidence that model execution,
backup/restore, Temporal recovery or owner isolation has already succeeded.

## Scope and invariants

Reuse the existing Coworker API, PostgreSQL repository/migrations, S3 object
storage, managed Auth identity, ReportEmailWorkflow, Temporal dispatcher and
worker registry. Do not build a second runner or depend on Day 4 briefing,
conversations or the multi-turn golden path. Keep production actions,
browser/agent actions and unrelated privileges disabled. Keep source SHA,
release, task, artifact, worker and restore identities in private evidence.

This patch includes:

- `scripts/staging_day2_execution.py`: one selected **synthetic private TXT
  document** is uploaded through the real authenticated API, read back by the
  owner, denied to a second owner, used by the existing `report_email`
  workflow with `output_language=en`, and must reach `completed` with
  positive persisted model attempts/tokens.
- The resulting `report.pdf` is read through the authorized artifact endpoint
  and a private S3 presigned URL. Both byte streams must match the
  repository-reported size and SHA-256. Cross-owner artifact download and
  content requests must return 404.
- `staging_release_freeze.py` now compares the **actual v2 runtime manifest**
  against the exact reviewed declaration; newly exposed capabilities must be
  explicitly declared and cannot be silently added. The existing full PA-10
  provider/cohort freeze contract remains strict.
- The operator script reads a **fresh, running worker on the same SHA and task
  queue**, requires a progressing database heartbeat, and directly describes
  `shuddho-task-<task_id>` in Temporal as `completed`.
- The output contains only nonsecret release/worker/document/task/artifact IDs,
  hashes, sizes, model accounting and pass labels. It does not log tokens,
  user text, signed URLs, passwords, or the synthetic source contents.

## Current external blockers (read-only inventory, 12 November)

| Resource | Observed | Consequence |
| --- | --- | --- |
| Render `shuddho-staging-db` | Free PostgreSQL 18, suspended for billing; expiry recorded 2026-10-31 | No durable DB, migration readback or isolated restore proof. Existing contents are unknown. Do not delete or replace the source. |
| Render `shuddho-api-staging` | Free web service, no auto-deploy; existing build/start differ from Blueprint; deployed 2 October source SHA | Cannot attest the candidate API SHA or runtime contract. |
| Render `shuddho-worker-staging` | Absent from the approved Rumman workspace inventory | No persistent Temporal poller, heartbeat or active restart evidence. |
| Supabase `shuddho-staging` | Project returned a hibernation response to a security-advisors read | Private bucket and synthetic identity must be revalidated live; no credential/test claim. |

The release must **remain blocked** under the Day 2 and Day 10 rules. Existing
Day 1 zero-spend restrictions are not superseded by this patch. Obtain
separate authorization for database recovery/retention, provisioned compute,
provider-model calls and approved nonproduction credentials, where required.
Do not widen database public access or activate production flags.

## Controlled operator sequence

Execute only inside the approved nonproduction environment, with protected
credentials injected through its secret manager and a fresh, empty, mode-0700
directory for private evidence. Use one independently reviewed **full 40-char
candidate SHA** for both API and worker. The Blueprint
`infra/render.staging.yaml` has auto-deploy off; the operator must manually
deploy the **exact same reviewed commit** to both, not unqualified moving
`main`. Verify actual Render deployment commit IDs and commands, run the
existing `services.coworker.migrate` pre-deploy, and inspect nonsecret worker
polling and migration output. Render deployment metadata alone does not prove
that the worker can execute work.

Before provider/model/storage calls:

```bash
uv run --extra coworker python scripts/staging_prerequisite_preflight.py \
  --output /secure/day2/prerequisite.json

export SHUDDHO_STAGING_ALLOW_RELEASE_FREEZE=true
export SHUDDHO_STAGING_SYNTHETIC_ACCOUNT=true
uv run --extra coworker python scripts/staging_release_freeze.py prepare \
  --rollout /secure/day2/pa10-staging-rollout.json \
  --provider-policy-plan /secure/day2/provider-policy-plan.json \
  --expected-source-revision "<reviewed-40-character-SHA>" \
  --build-reference "<reviewed-immutable-build-reference>" \
  --deployment-reference "<approved-API-and-worker-change-reference>" \
  --synthetic-account-reference "<approved-synthetic-cohort-reference>" \
  --state /secure/day2/release-prepare.json
```

The full PA-10 freeze requires its documented provider/cohort declarations.
If these are not approved, **stop at the freeze blocker**; do not fabricate
provider availability or weaken the contract to make Day 2 appear to pass.
After the actual reviewed API+worker deployment, inspect nonsecret Render
service/deploy readback and execute:

```bash
export SHUDDHO_STAGING_API_BASE_URL="https://<approved-staging-api-origin>"
export SHUDDHO_STAGING_TOKEN_A="<approved-owner-A-token>"
export SHUDDHO_STAGING_TOKEN_B="<approved-owner-B-token>"

uv run --extra coworker python scripts/staging_release_freeze.py verify \
  --state /secure/day2/release-prepare.json \
  --output /secure/day2/release-frozen.json

export SHUDDHO_STAGING_ALLOW_DAY2_EXECUTION=true
# Run where the reviewed staging Settings have the same attested source SHA,
# private S3, durable PostgreSQL, configured model and Temporal TLS credentials.
uv run --extra coworker python scripts/staging_day2_execution.py \
  --freeze-evidence /secure/day2/release-frozen.json \
  --output /secure/day2/document-execution.json --timeout 180
```

The script refuses to publish a pass artifact until it has verified the model
usage, correct owner, source/artifact bytes, real Temporal workflow and live
worker heartbeat. If it fails, inspect the error and persistent task/worker
state; do not edit or merge a pass result. The source document and artifact
remain available for the operator's separately approved retention/deletion
checks. Existing `scripts/staging_api_exercise.py --artifact` additionally
checks guessed artifact IDs and expiring signed URLs, when approved.

## Separate restart and backup/restore gates

These are **not** satisfied by the single document test.

```bash
export SHUDDHO_STAGING_ALLOW_RECOVERY_EXERCISE=true
uv run --extra coworker python scripts/staging_temporal_recovery.py prepare \
  --state /secure/day2/recovery-state.json \
  --rollout /secure/day2/pa10-staging-rollout.json
# Restart the active staging worker deliberately, record the actual platform
# timestamp and event/deploy reference, and let the same run finish.
uv run --extra coworker python scripts/staging_temporal_recovery.py verify \
  --state /secure/day2/recovery-state.json \
  --restart-at "<UTC-ISO-8601-platform-event-time>" \
  --restart-reference "<real-worker-restart-event-reference>" \
  --rollout /secure/day2/pa10-staging-rollout.json \
  --base-evidence /secure/day2/document-execution.json \
  --output /secure/day2/temporal-recovery.json

export SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true
uv run --extra coworker python scripts/staging_backup_restore.py prepare \
  --state /secure/day2/backup-state.json \
  --rollout /secure/day2/pa10-staging-rollout.json
# Perform an independently verified real PostgreSQL + private object backup,
# then restore both to distinct empty isolated targets, not live staging.
uv run --extra coworker python scripts/staging_backup_restore.py verify \
  --state /secure/day2/backup-state.json \
  --backup-reference "<actual-private-backup-manifest-reference>" \
  --restore-reference "<actual-isolated-restore-event-reference>" \
  --rollout /secure/day2/pa10-staging-rollout.json \
  --base-evidence /secure/day2/temporal-recovery.json \
  --output /secure/day2/restore-evidence.json
```

The existing recovery script has stronger agent-v2 configuration requirements
than the one-document Day 2 smoke. If those are not present on the approved
release, report the restart drill **blocked**, do not silently call it a
document-only test. For backup, recover/export any retained original DB
**before** adding a probe. The restore script rejects the original source
database or original object storage as its target. It needs both actual
backup and restore references; merely running commands does not count.

## Acceptance

Pass requires an identical reviewed source SHA in the release freeze,
running staging API, worker registry and Temporal execution; a real model-backed
completed task on the selected private synthetic document; a retrievable
SHA-verified private artifact; owner B's denied upload/download/list/task/
artifact access; a live worker restart with persistent run identity; and
PostgreSQL+object-storage restoration on separate identities. Inspect
**nonsecret outputs**, record CI/review results separately, and do not infer
success from process exit alone.

**If the database or persistent worker remains unavailable at day's end,
Day 10 live-pilot readiness is blocked.** Independent source/grounding work
may continue, but the milestone is not relabeled complete.
