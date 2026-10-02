# PA-10 Controlled-Staging Canonical Checkpoint

**Inspected:** 2 October 2026  
**Program result:** **BLOCKED_EXTERNAL**  
**Scope:** Automation / Proactive Coworker controlled-staging qualification only. Production activation remains unauthorized and unchanged.

## Release identity

- Repository: `rumman52/Shuddho`
- Current `main`: `1a6debbcb3cbd3b7407083eed10f0d2eb0e38251`
- Merge: PR #289, **Prepare Render controlled-staging deployment**
- Required merged-main CI: #1094 / run `36904018888`
- CI result: **SUCCESS**
  - `test-and-build`: SUCCESS
  - `coworker`: SUCCESS
- Relevant open PA-10 PRs: none. The remaining open PRs are older unrelated work and are not PA-10 staging blockers.

## Operated non-production state

### Render

- Staging API service exists: `shuddho-api-staging`
- Latest staging API deploy: `dep-dava5hjtqb8s73d1plmg`
- Deployed source SHA: `1a6debbcb3cbd3b7407083eed10f0d2eb0e38251`
- Deploy status observed: `live`
- Staging PostgreSQL exists: `shuddho-staging-db`; status observed: `available`
- **No `shuddho-worker-staging` service exists.**
- The existing API is a free Render web service. Logs show normal startup and later shutdown after the free-service idle window; this is not evidence of a persistent background worker.
- The live API service does not exactly match the reviewed `infra/render.staging.yaml`: its configured health-check path is empty, and its build/start commands are looser than the reviewed Blueprint contract.
- External read-only SQL through the hosted Render connector is unavailable because the database has an empty external IP allowlist. Do not weaken the allowlist merely to collect evidence.

### Supabase staging

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
3. deploy the exact candidate;
4. run `scripts/staging_release_freeze.py prepare` before deployment;
5. verify the authenticated `/api/v1/runtime-manifest`;
6. require `status=frozen`;
7. collect every PA-10 scenario against that same frozen release.

## External blockers

| Blocker | Classification | Owner / required input | Prevents |
| --- | --- | --- | --- |
| Persistent `shuddho-worker-staging` missing | paid resource / operator setup | Render account owner must approve and provision the reviewed `0.5c-512mb` background worker | Temporal polling, durable schedules, reminders, Daily/Weekly/Deadline/Meeting/Email executions, restart recovery |
| Temporal Cloud namespace/auth not available in operated staging | provider setup / secret reference | Temporal namespace endpoint, namespace, API key/TLS auth entered securely into Render | scheduler reconciliation, due occurrences, restart/replay evidence, release readiness |
| Supabase S3 access credentials not available to the application | provider setup / secret reference | reviewed S3 endpoint/region/access-key secret references for the private bucket | app upload/read/delete, storage isolation, full staging readiness |
| Synthetic auth token / operated managed identity exercise not available | human/access | approved synthetic account and token generated through the staging auth flow | authenticated runtime-manifest verification and all owner-scoped collectors |
| Google Gmail/Calendar synthetic OAuth + subscriptions | provider setup / authorization | approved synthetic Google account/app credentials, grants/subscriptions/callbacks | Email/Meeting live qualification and duplicate/revocation exercises |
| Microsoft Outlook/Calendar synthetic OAuth + subscriptions | provider setup / authorization | approved synthetic Microsoft tenant/account/app credentials, grants/subscriptions/callbacks | Email/Meeting live qualification and duplicate/revocation exercises |
| Browser Push VAPID + approved real device confirmation | human/device/provider setup | VAPID config, explicit consent, approved browser/device | Browser Push live scenario |
| Human Bangla/English review | human action | reviewers and retained non-sensitive review references | multilingual_human_review |
| Measured task economics | dependent evidence | actual completed staging runs plus reviewed pricing inputs | task_economics |

## Non-billing prerequisite preflight

Before requesting paid Render worker authorization, run the GitHub Actions workflow:

`PA-10 staging prerequisite preflight`

It performs no provider calls and creates no infrastructure. It verifies only the presence of the required GitHub Actions secrets and the reviewed non-secret configuration shape for:

- Temporal host/port, namespace presence, TLS and task queue;
- S3 backend, reviewed staging bucket, HTTPS endpoint and region;
- Render API credential presence;
- staging S3 credential presence;
- optional DeepSeek credential presence reporting.

The same validator is reused by the paid worker provisioner immediately before any Render mutation, preventing drift between preflight and provisioning checks. Secret values are never emitted.

## Paid worker approval boundary

The reviewed Blueprint requests Render background-worker plan `0.5c-512mb` (0.5 CPU, 512 MB). Do **not** purchase or provision it without account-owner authorization. After approval, provision the worker from the reviewed `infra/render.staging.yaml` contract rather than substituting a web service or cron job.

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

Restored the actual current repository and operated staging state; verified current main and CI; verified PR #289 has no unresolved review thread; inspected the live Render API/deployment/database inventory and logs; confirmed the missing worker; inspected the reviewed Render Blueprint; verified the healthy Supabase staging project/private bucket/security-advisor state; and identified the exact external prerequisites blocking freeze.

## Next exact action

**Account owner / staging operator:**

1. Approve the Render `0.5c-512mb` background-worker spend.
2. Provision `shuddho-worker-staging` from `infra/render.staging.yaml`.
3. Enter the already-reviewed Temporal, auth, Supabase S3 and model secret values through secure provider/Render secret entry; do not place them in chat or Git.
4. Align `shuddho-api-staging` with the reviewed Blueprint health/build/start contract.
5. Verify the worker starts, polls the expected Temporal task queue, can reach PostgreSQL and private storage, and runs migrations.
6. Then create the reviewed rollout/provider-policy artifacts and run the exact release-freeze prepare/deploy/verify cycle.

After those external steps, resume with the scheduled-reminder collector first. Do not launch an Agent for the simple reminder; require one `automation_reminder`, zero Agent runs and `run_id=null`.

## Production boundary

No production flag, cohort, provider authority, Browser Push activation, LinkedIn proposal capability, transaction capability, or production rollout is authorized by this checkpoint.
