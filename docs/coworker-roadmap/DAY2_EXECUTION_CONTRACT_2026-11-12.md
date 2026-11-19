# Day 2 — prove the real staging execution loop (12 November 2026)

**Disposition: PR #670 MERGED; LIVE ACCEPTANCE BLOCKED.** This is a
controlled nonproduction operator contract, not evidence that model execution,
backup/restore, Temporal recovery or owner isolation has already succeeded.

## Scope and invariants

Reuse the existing Coworker API, PostgreSQL repository/migrations, S3 object
storage, managed Auth identity, ReportEmailWorkflow, Temporal dispatcher and
worker registry. Do not build a second runner or depend on Day 4 briefing,
conversations or the multi-turn golden path. Keep production actions,
browser/agent actions and unrelated privileges disabled. Keep source SHA,
release, task, artifact, worker and restore identities in private evidence.

The merged Day 2 source includes:

- `scripts/staging_day2_execution.py`: one operator-selected **synthetic private, text-based PDF
  document** is uploaded as owner A through the normal authenticated API and
  used by the existing `report_email` workflow with `output_language=en`.
  The task must reach `completed` with positive persisted model attempts/tokens.
  A synthetic owner-B TXT control document is also uploaded through the normal
  private path. Each owner must read its own document; the opposite owner must
  receive 404 for document read/write, and each owner's document listing must
  exclude the foreign document. The extracted A DocumentVersion must appear in
  the persisted source manifest with matching document ID and SHA-256, and a
  report section must cite that version ID.
- The resulting `report.pdf` is read through the authorized artifact endpoint
  and a private S3 presigned URL. Both byte streams must match the
  repository-reported size and SHA-256. The signed URL must resolve to the
  configured HTTPS S3 endpoint host, not an arbitrary third-party origin.
  The artifact checks are bidirectional: B must be denied A's report artifact,
  and A must be denied B's separate synthetic task-output control artifact.
  Both owners must positively retrieve their own artifact content and private
  download URL, and each owner's artifact list must exclude the foreign artifact.
- `staging_release_freeze.py` now compares the **actual v2 runtime manifest**
  against the exact reviewed declaration; newly exposed capabilities must be
  explicitly declared and cannot be silently added. The existing full PA-10
  provider/cohort freeze contract remains strict.
- The operator script reads a **fresh, running worker on the same SHA and task
  queue**, requires a progressing database heartbeat, and directly describes
  `shuddho-task-<task_id>` in Temporal as `completed`.
- After Temporal confirms the private `report_email` workflow completed, the Day 2 operator reads the actual `cw_outbox` row keyed by that **same PDF task ID**. Exactly one row, `delivered=true` and positive dispatch attempts are required; `document_outbox` travels unchanged with the task identity through recovery and isolated restore acceptance. This proves one logical task-dispatch ledger effect, not provider-side exactly-once execution.
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

## Refreshed Day 2 staging readback (19 November 2026, read-only)

This section refreshes the historical 12 November inventory above. It records
only nonsecret metadata; it is not a deployment, migration, restore or identity
authorization.

| System | Fresh observation | Consequence |
| --- | --- | --- |
| Render workspace | Rumman, `tea-d6ok4okhg0os73erkdv0` | Exact requested workspace was selected for read-only inspection. |
| Render API | `shuddho-api-staging`, `srv-dav98otg1s2s73cod4gg`; latest live deploy source SHA `0e0b662fad0a02817a79a4514abba8f94e0ad022` | Deployed API is behind inspected repository `main` `8afcfccf409c5a01fd70a7966fb4b538575f502f`; no same-SHA API/worker release is proven. |
| Render service settings | Auto-deploy disabled; build `pip install uv && uv sync --extra coworker`; start `uv run --extra coworker python -m services.coworker.migrate --check && uv run --extra coworker uvicorn services.coworker.api:app --host 0.0.0.0 --port $PORT`; Render health-check path empty | No configured Render health check; no deployment or command change was made. |
| Render worker inventory | No dedicated persistent staging worker service | No authenticated Temporal poller, same-SHA worker heartbeat or restart proof. |
| Supabase `shuddho-staging` (`bsmbvjenpvcyfjzwtuax`) | Private migration ledger `0070`; source expects `0072_merge_0071_heads`; 84 private-schema relations; zero Auth users and zero bucket objects; application tables/outboxes/worker-instance tables read as zero rows | Migration alignment, synthetic identities and real private task remain blocked. |
| Supabase access posture | Bucket `shuddho-coworker-staging` has `public=false`; `anon` and `authenticated` have no private-schema USAGE or default table grants; no RLS-enabled relations among the 84 private relations; inspection SQL role was `postgres` with RLS bypass | The private-schema grant boundary is present, but row-level security is not enabled. The privileged read-only SQL role is not the app runtime role and must not be used for application migrations or seeding. |
| Restore | No approved distinct empty database/object-store restore targets were supplied or verified | Do not back up, restore or overwrite the live source. |
| Browser / Vercel / identity | Connected Vercel project inventory did not establish a Shuddho frontend repository/deployment/origin/API destination; no two approved managed synthetic identity tokens were available for issuer/audience/expiry/subject verification | Browser origin and hosted identity acceptance remain unverified. |

The canonical `scripts/release_contract.py` and the PA-10 freeze contract
remain authoritative and unchanged. Their CI, identity, database, storage,
Temporal, model, quality, backup/restore, deletion, restart, fan-in and rollback
requirements are not satisfied by this read-only inventory or by this source
patch. Do not provision a paid worker, create identities, issue provider calls,
apply migrations, seed data, or deploy until the Founder/operator supplies the
required dated approvals, cost ceiling, duration, restore targets and rollback
owner.

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
uv run --locked --extra coworker python scripts/staging_day2_execution.py \
  --freeze-evidence /secure/day2/release-frozen.json \
  --source-pdf /secure/day2/approved-synthetic-source.pdf \
  --owner-b-artifact-id "$DAY2_OWNER_B_ARTIFACT_ID" \
  --output /secure/day2/document-execution.json --timeout 180
```

Place an owner-approved **synthetic**, text-based, unencrypted PDF (1–40 pages,
at most 8 MiB, extractable text) in the operator's protected evidence location.
Set its permissions to 0600, prohibit symlinks, and never commit, print or
attach the private source to GitHub/Linear or shared logs. The operator script
validates the PDF before uploading it and retains only redacted IDs and hashes
in its private result receipt. The prior bounded TXT API-probe helper remains
available for source-only regression tests; live CLI execution now requires the
selected PDF.

The script refuses to publish a pass artifact until it has verified the model
usage, correct owner, source/artifact bytes, real Temporal workflow and live
worker heartbeat. If it fails, inspect the error and persistent task/worker
state; do not edit or merge a pass result. The source document and artifact
remain available for the operator's separately approved retention/deletion
checks. Existing `scripts/staging_api_exercise.py --artifact` additionally
checks guessed artifact IDs and expiring signed URLs, when approved.

## Owner-B artifact control precondition

The reverse artifact check needs an actual synthetic task-output artifact owned
by B. The Day 2 execution command does not create a second provider-backed task.
If a suitable B-owned artifact does not already exist, it may be prepared with
the existing `scripts/staging_api_exercise.py --artifact` operator, binding
owner B as `SHUDDHO_STAGING_TOKEN_A` and owner A as
`SHUDDHO_STAGING_TOKEN_B` in the protected environment. This is a separate
model/provider task and requires separate explicit cost authorization; it is
not implicitly authorized by the one owner-A PDF task.

Only after separate approval for the B-owned synthetic control task, run in the
protected operator environment:

    export SHUDDHO_STAGING_TOKEN_A="<approved-owner-B-token>"
    export SHUDDHO_STAGING_TOKEN_B="<approved-owner-A-token>"
    uv run --locked --extra coworker python scripts/staging_api_exercise.py --artifact --output /secure/day2/owner-b-control.json

Read `storage.artifact_id` from the private receipt and supply only that UUID
as `DAY2_OWNER_B_ARTIFACT_ID`. The artifact exercise receipt also retains
`storage.task_id`. Tokens, signed URLs and source content remain outside the
receipt. The Day 2 execution operator verifies that the ID exists in B's
artifact catalog, is absent from A's catalog, is retrievable by B and is denied
to A before creating either document or the owner-A task. If the control
artifact is absent, invalid, foreign-visible or unreadable, the operator fails
closed before any private write. Do not manufacture a pass or run a second
model task without separate approval.

For both managed owner tokens, the operator also checks the configured issuer,
audience, expiry window, authenticated role and distinct subject. The same
tokens must be accepted by the API's issuer-pinned asymmetric JWT verifier;
the operator binds each decoded subject to the authenticated `/api/v1/me`
account ID. Only per-owner boolean claim evidence is retained, never tokens
or raw subjects.

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

## Required same-run restart and outbox evidence

The recovery gate is **not** satisfied by an arbitrary restart reference, a completed but unrelated task, or an agent workflow with matching child-task IDs alone. The operator now snapshots one fresh, reviewed-SHA running worker at prepare time, then requires a *different* fresh worker registration on that queue during the same active Agent run. The replacement start must correlate with the real Render restart event (within five minutes), and its heartbeat must advance after registration. The persisted run requires exactly one delivered `cw_agent_outbox` row and **zero** `cw_outbox` rows for its three completed child tasks: the AgentRuntime uses `create_task(..., enqueue=False)` and dispatches them directly through Temporal, so child outbox rows would indicate a duplicate dispatch path. Three distinct idempotency-bound, completed child tasks and one durable parent AgentRun dispatch effect do not by themselves prove exactly-once external-provider side effects. The redacted `recovery_outbox` receipt is copied unchanged into the isolated restore evidence and is mandatory in `staging_day2_acceptance.py`.

**Scope limitation:** the restarted synthetic Agent run is separate from the owner-A document/report task. The document run is linked to its own Temporal workflow, source and artifact; the recovery gate establishes same-run worker takeover for its Agent run. Do not report that the PDF task itself was restarted unless a separate, directly observed PDF-task restart was also performed.

## Evidence-chain reconciliation (after the real drills)

Only after the real document task, active-worker restart and isolated
PostgreSQL/object-storage restore have generated private receipt files,
run the fail-closed source/identity gate:

```bash
uv run --extra coworker python scripts/staging_day2_acceptance.py \
  --freeze /secure/day2/release-frozen.json \
  --execution /secure/day2/document-execution.json \
  --recovery /secure/day2/temporal-recovery.json \
  --restored /secure/day2/restore-evidence.json \
  --expected-revision "<reviewed-40-character-SHA>" \
  --output /secure/day2/identity-consistency.json
```

This reconciles the same frozen release, runtime-manifest digest, rollout
digest, document/version/task/workflow/artifact IDs and hashes, worker source
and heartbeat, and nested restart/restore receipts. An absent, altered,
out-of-order or different-release proof **fails closed**. Its result is only
`evidence_consistent`, not an independent attestation of live platform
events. An operator must still verify the real Render restart reference,
model-usage records, source and target database/storage identities, backup
artifacts and authorization checks. No CI mock or merged source changes that.

## Acceptance

Pass requires an identical reviewed source SHA in the release freeze,
running staging API, worker registry and Temporal execution; a real model-backed
completed task on the selected private synthetic document; a retrievable
SHA-verified private artifact; positive own-resource access and separate 404
cross-owner document/artifact read/write/download denials in both A-to-B and
B-to-A directions, with foreign resources absent from both owner-scoped lists;
a live worker restart with persistent run identity; and PostgreSQL+object-storage
restoration on separate identities. Inspect **nonsecret outputs**, record
CI/review results separately, and do not infer success from process exit alone.

**If the database or persistent worker remains unavailable at day's end,
Day 10 live-pilot readiness is blocked.** Independent source/grounding work
may continue, but the milestone is not relabeled complete.
