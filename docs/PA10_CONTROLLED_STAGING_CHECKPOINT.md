# PA-10 Controlled-Staging Canonical Checkpoint

**Inspected:** 3 October 2026 (UTC; Asia/Dhaka UTC+06:00)
**Program result:** **BLOCKED_EXTERNAL**  
**Scope:** Automation / Proactive Coworker controlled-staging qualification only. Production activation remains unauthorized and unchanged.

## Release identity

- Repository: `rumman52/Shuddho`
- Inspected implementation `main`: `ab44ea1afd56cbddd1b0c8668cc6b1a41d64eca5`.
- PR #300, **Fix PA-10 preflight summary command substitution**, is merged.
- Exact-head CI #1116 / run `37090826309`: **SUCCESS** on `538b84805e08a4cb72292c434e1a2f09dfca5086`.
- Merged-main CI #1117 / run `37093700328`: **SUCCESS** on `ab44ea1afd56cbddd1b0c8668cc6b1a41d64eca5`, including `test-and-build` and `coworker`.
- PRs #292–#299 supplied worker provisioning, poller verification, owner-isolation collectors, prerequisite preflight and S3 privacy/cleanup hardening. PR #300 fixes summary output only; it does not supply live qualification evidence.
- This checkpoint is a dated observation, not a claim that the implementation revision remains the latest main after subsequent commits.

## Operated non-production state

### Render

- Staging API service exists: `shuddho-api-staging`
- Confirmed workspace: Rumman, `tea-d6ok4okhg0os73erkdv0`
- Staging API service ID: `srv-dav98otg1s2s73cod4gg`
- Latest staging API deploy: `dep-davmrnu7bikc73emahdg`
- Deployed source SHA: `fce72760456bd8bb03524ce98127120c7ac3dfb9`
- Deploy status observed: `live`
- Staging PostgreSQL exists: `shuddho-staging-db`, `dpg-dav98hfpn0mc739mndvg-a`; status observed: `available`
- **No `shuddho-worker-staging` service exists.**
- The existing API is a free Render web service. Earlier logs showed normal startup and shutdown after the idle window; current service inventory still reports the free plan. This is not evidence of a persistent background worker or uninterrupted callback availability.
- The live API service does not exactly match the reviewed `infra/render.staging.yaml`: its configured health-check path is empty, and its build/start commands are looser than the reviewed Blueprint contract.
- External read-only SQL through the hosted Render connector is unavailable because the database has an empty external IP allowlist. Do not weaken the allowlist merely to collect evidence.

### Supabase staging

The following project/bucket observations are retained from 2 October and were not rechecked during this execution:

- Project `shuddho-staging`: `ACTIVE_HEALTHY`
- Private bucket `shuddho-coworker-staging`: exists, `public=false`
- Supabase security advisor observed: no current findings
- This proves project/bucket presence only. **Application S3 compatibility is NOT VERIFIED** because no authenticated app-level upload/read/delete/cross-owner-denial exercise has run with staging S3 credentials.

## Release-freeze state

**NOT FROZEN.**

The repository has the dedicated freeze tooling, but the controlled-staging candidate cannot be frozen yet because the operated environment does not satisfy the reviewed prerequisite set.

Do not create a prepare-only freeze artifact and call it complete. The valid sequence remains:

1. review exact staging rollout and provider-policy plan;
2. provision the reviewed worker and required secret references;
3. run `scripts/staging_release_freeze.py prepare` for the exact candidate;
4. deploy that exact source revision and reviewed configuration to both API and worker;
5. run freeze `verify` against the authenticated `/api/v1/runtime-manifest` and separately retain the worker's exact deployment identity;
6. require `status=frozen`;
7. collect every PA-10 scenario against that same frozen release.

## External blockers

| Blocker | Classification | Owner / required input | Prevents |
| --- | --- | --- | --- |
| Persistent `shuddho-worker-staging` missing | paid resource / operator setup | Render account owner must approve and provision the reviewed `0.5c-512mb` background worker | Temporal polling, durable schedules, reminders, Daily/Weekly/Deadline/Meeting/Email executions, restart recovery |
| All six required GitHub Actions staging secrets absent | credential/configuration input | account owner must add the six exact repository secret names listed below, then rerun preflight | worker provisioning |
| Temporal Cloud namespace/auth not verified in operated staging | provider setup / secret reference | verify endpoint, namespace and API key/TLS through preflight, then authenticate from the worker | scheduler reconciliation, due occurrences, restart/replay evidence, release readiness |
| Supabase S3 access credentials absent from GitHub Actions; application access unverified | provider setup / secret reference | verify reviewed endpoint/region/access-key secret references, then run authenticated probes | app upload/read/delete, storage isolation, full staging readiness |
| Synthetic auth token / operated managed identity exercise not available | human/access | approved synthetic account and token generated through the staging auth flow | authenticated runtime-manifest verification and all owner-scoped collectors |
| Google Gmail/Calendar synthetic OAuth + subscriptions | provider setup / authorization | approved synthetic Google account/app credentials, grants/subscriptions/callbacks | Email/Meeting live qualification and duplicate/revocation exercises |
| Microsoft Outlook/Calendar synthetic OAuth + subscriptions | provider setup / authorization | approved synthetic Microsoft tenant/account/app credentials, grants/subscriptions/callbacks | Email/Meeting live qualification and duplicate/revocation exercises |
| Browser Push VAPID + approved real device confirmation | human/device/provider setup | VAPID config, explicit consent, approved browser/device | Browser Push live scenario |
| Human Bangla/English review | human action | reviewers and retained non-sensitive review references | multilingual_human_review |
| Measured task economics | dependent evidence | actual completed staging runs plus reviewed pricing inputs | task_economics |

## Non-billing prerequisite preflight

Executed prerequisite workflow:

`PA-10 staging prerequisite preflight`

GitHub browser authentication was verified as `rumman52` on 3 October at approximately 04:00 UTC. Preflight run #1 (`37095132480`, job `111123403817`) executed on `ab44ea1afd56cbddd1b0c8668cc6b1a41d64eca5` and **FAILED** with `BLOCKED_EXTERNAL — RENDER_API_KEY REQUIRED`. Run: https://github.com/rumman52/Shuddho/actions/runs/37095132480.

The authenticated Actions secrets settings page then showed only `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` as repository secrets and no environment secrets. All six required staging secret names below are absent. This is now observed configuration evidence, not an inference from absent local credentials. Secret values were not accessed. No provisioning was attempted after this failure.

Required Actions secret names:

- `RENDER_API_KEY`
- `SHUDDHO_TEMPORAL_ADDRESS`
- `SHUDDHO_TEMPORAL_NAMESPACE`
- `SHUDDHO_TEMPORAL_API_KEY`
- `SHUDDHO_STAGING_S3_ACCESS_KEY_ID`
- `SHUDDHO_STAGING_S3_SECRET_ACCESS_KEY`

`DEEPSEEK_API_KEY` is also absent from the observed repository secret inventory. It remains optional for infrastructure preflight but must be present when an authorized later scenario requires the live model.

It performs no provider calls and creates no infrastructure. It verifies only the presence of the required GitHub Actions secrets and the reviewed non-secret configuration shape for:

- Temporal host/port, namespace presence, TLS and task queue;
- S3 backend, reviewed staging bucket, HTTPS endpoint and region;
- Render API credential presence;
- staging S3 credential presence;
- optional DeepSeek credential presence reporting.

The same validator is reused by the paid worker provisioner immediately before any Render mutation, preventing drift between preflight and provisioning checks. Secret values are never emitted.

PR #300 replaces command-substituting summary strings with literal-safe `printf`. Its regression executes the real shell step with sentinel commands and fails on the old workflow. The fixed regression and all 10 existing worker-provisioning shell tests passed locally. Preflight only checks presence/configuration shape; it does not authenticate against Temporal or S3.

## Paid worker approval boundary

The reviewed Blueprint requests Render background-worker plan `0.5c-512mb` (0.5 CPU, 512 MB). Use existing account-owner authorization when it covers the exact resource and spending scope; do not repeatedly request the confirmed workspace. If a spending boundary remains unapproved, prepare the exact action and resolve only that boundary. Provision from `infra/render.staging.yaml`, without substituting a web service or cron job.

## Scenario status

All 15 PA-10 scenarios remain **NOT STAGING QUALIFIED** until genuine evidence is collected on one frozen release:

- scheduled_reminder
- daily_coworker
- weekly_coworker
- meeting_coworker
- email_coworker
- deadline_coworker
- goal_driven_proactivity
- managed_recovery
- revocation
- duplicate_event
- approval_boundary
- prompt_injection
- browser_push
- multilingual_human_review
- task_economics

Repository implementation/tooling remains verified; live-provider/staging evidence is not inferred from green CI.

## Last completed action

Verified GitHub sign-in, dispatched preflight #1, inspected its failure and confirmed all six required staging secret names are absent. PR #301's earlier checkpoint revision passed CI run `37094490620`; this follow-up records the live failure. No provisioning workflow, migration, live provider collector or release-freeze operation was executed.

## Next exact action

**Account owner / staging operator:**

1. Add all six exact repository secret names listed above through **Settings → Secrets and variables → Actions → New repository secret**. Supply actual reviewed Render, Temporal and staging S3 values directly in GitHub; do not paste them into chat or source files.
2. Rerun **Actions → PA-10 staging prerequisite preflight → Run workflow → main** and inspect the actual result. Resolve any configuration-shape error before provisioning.
3. With preflight passed and the reviewed worker spending scope authorized, run **Provision PA-10 staging worker** from main with `confirm=PROVISION`. Capture its actual service/deploy IDs and source SHA.
4. Verify migrations and both workflow/activity pollers on `shuddho-documents-v1`. Align staging API build/start/health settings with the Blueprint; verify API/worker database, Temporal and storage settings match.
5. Run storage, managed identity, artifact and owner-isolation exercises. Use `--personal-agent`; run `--owned-resource-manifest` only after real synthetic scenarios have produced the six required User A IDs. Poller and bucket probes remain `partial` until their higher-level checks pass.
6. Complete readiness recovery/backup/retention checks; then select an exact reviewed candidate, PREPARE, deploy identical API/worker source, VERIFY, and require `status=frozen`.
7. Collect all final release-bound scenarios and compile `scripts/pa10_staging_evidence.py`. Recollect checks that require the final release; do not promote preliminary diagnostics into frozen-release evidence.

Resume source implementation from PR #300 / merge `ab44ea1afd56cbddd1b0c8668cc6b1a41d64eca5`; do not recreate the summary fix. No active provisioning/deploy job or frozen evidence bundle is available to resume from this checkpoint. Production settings were not modified by this execution; the existing production service retains its own auto-deploy behavior.

After those external steps, resume with the scheduled-reminder collector first. Do not launch an Agent for the simple reminder; require one `automation_reminder`, zero Agent runs and `run_id=null`.

## Production boundary

No production flag, cohort, provider authority, Browser Push activation, LinkedIn proposal capability, transaction capability, or production rollout is authorized by this checkpoint.
