# Shuddho — live release-readiness refresh

**Inspection time:** 31 October 2026, 00:50 Asia/Dhaka (30 October 2026, 18:50 UTC)  
**Repository:** https://github.com/rumman52/Shuddho  
**Current main:** 38c5b8d0d3eafa5692f848a5e664897a500fcfe2  
**Disposition:** **NOT RELEASE-QUALIFIED.** This is a dated evidence snapshot, not production approval.

This refresh supersedes older operational claims where they conflict. Historical source work logs remain preserved. Do not interpret merged code, green application tests, or a Render deployment marked LIVE as proof of end-to-end production readiness.

## 1. GitHub source, CI and governance

- Current main is 38c5b8d0d3eafa5692f848a5e664897a500fcfe2, the merge commit for PR #596. PR #597 is also merged. The open-pulls endpoint currently returns no open pull requests.
- Exact-main Actions run [#41098651428](https://github.com/rumman52/Shuddho/actions/runs/41098651428) completed:
  - test-and-build: **SUCCESS**
  - coworker: **SUCCESS**
  - governance-audit: **FAILURE**
  - ci-merge-gate: **FAILURE**
- The coworker job completed its mandatory transaction safety regressions, PostgreSQL transaction fault-boundary tests, transaction HTTP and hard-worker recovery, CW-02 to CW-04 gate tests, CW-11 registry checks, browser isolation, routing, and evaluation steps without reported skips in those named steps. This is repository/CI evidence, not live operated acceptance.
- GitHub branch metadata reports main protected=false; the active repository rulesets endpoint returns an empty list. The legacy branch-protection detail endpoint returns 403 Resource not accessible by integration. The governance log says main branch protection is not confirmed.
- The repository contains the reviewed policy at infra/github/main-ruleset.json and operator script scripts/apply_main_ruleset.py. The connected GitHub integration does not expose an administrative ruleset-write action. A repository administrator must apply/read back the no-bypass ruleset with a secured admin token and prove both negative and positive merge cases.
- Production Render auto-deploys every commit to main. This allows an unqualified commit to reach production before post-merge governance and CI finish; a reviewed production-promotion path remains necessary.

Related tracking: [V-01 #484](https://github.com/rumman52/Shuddho/issues/484) and [release-control #339](https://github.com/rumman52/Shuddho/issues/339).

## 2. Render — confirmed live state

Workspace: **Rumman**.

### Staging PostgreSQL — urgent continuity decision

| Field | Observed value |
|---|---|
| Resource | shuddho-staging-db |
| Resource ID | dpg-dav98hfpn0mc739mndvg-a |
| PostgreSQL | 18 |
| Plan / status | Free / available |
| Created | 1 October 2026, 17:11:33.79468 UTC |
| Expiry | **31 October 2026, 17:11:33.79468 UTC / 23:11:33.79468 Asia/Dhaka** |
| External IP allowlist | Empty |
| High availability | Disabled |

Render's official policy states that Free Postgres expires after 30 days, becomes inaccessible at expiry, has a 14-day grace period to upgrade before deletion, and does not support backups, PITR, or managed logical exports:
- https://render.com/docs/free
- https://render.com/docs/postgresql-backups

The hosted Render read-only SQL query was rejected because the database's empty external IP allowlist blocks the hosted query connection. Therefore table count, data size, schema and row inventory remain **unknown**. Do not assume the database is empty or backed up. No allowlist, credential, plan or database change was made.

A preservation path must be explicitly chosen before expiry: a narrowly scoped trusted /32 plus TLS-protected pg_dump and a verified restore, or an owner-authorized paid upgrade / approved same-region export process. Never use 0.0.0.0/0. Do not migrate or delete the source until a restore has been verified.

### Staging API and worker

- shuddho-api-staging (srv-dav98otg1s2s73cod4gg) is a Free web service, branch main, auto-deploy off, health-check path blank.
- Its live build command is pip install uv && uv sync --extra coworker; its start command omits the Blueprint's explicit --extra coworker. The reviewed Blueprint expects frozen locked dependencies, the explicit coworker extra, and health path /health.
- Its latest live deployment is 2 October 2026 on source SHA fce72760456bd8bb03524ce98127120c7ac3dfb9.
- No shuddho-worker-staging service exists in the current Render inventory.
- The reviewed infra/render.staging.yaml specifies a real persistent worker, type worker, plan 0.5c-512mb, pre-deploy migrations, Temporal task-queue polling, auto-deploy off, and 120-second shutdown allowance.
- The prior owner approval for the worker's $7/month plan is recorded in issue #291. The connected Render actions do not expose worker creation or Blueprint sync; no web-service or cron substitute was created. This approval does not authorize a database upgrade or other spend.

The staging API/worker, Temporal, private S3 credentials, managed synthetic identity, and provider/device prerequisites remain BLOCKED_EXTERNAL.

### Production API

- Service: shuddho-api (srv-d6oki2v5r7bs73e7isfg), Free web service, auto-deploy yes from main.
- Health-check path is blank.
- Latest live deployment: dep-dbid5ta9lscs73fsq33g, source SHA 38c5b8d0d3eafa5692f848a5e664897a500fcfe2.
- Startup logs on 30 October 17:26 UTC explicitly report SHUDDHO_DETECTOR_ENABLED=false, SHUDDHO_CORRECTOR_ENABLED=false, and degraded local analysis mode with reasons detector_disabled and corrector_disabled.
- From 17:25 to 18:50 UTC, no application error or HTTP 5xx log records were returned. CPU/memory samples exist, but HTTP request-count and latency metrics returned empty series. Empty error/5xx logs and empty HTTP metrics do not prove successful user requests.
- Direct GET retrieval of /health and /version through the connected web path was unavailable. No successful live HTTP smoke result is claimed.

Production is deployed but not analysis-ready or release-qualified. Do not enable detector/corrector checkpoints or change health settings without reviewed artifacts, agreed liveness/readiness semantics, and explicit release approval.

Related tracking: [staging #291](https://github.com/rumman52/Shuddho/issues/291) and [production readiness #583](https://github.com/rumman52/Shuddho/issues/583).

## 3. Supabase

- Project shuddho-staging (bsmbvjenpvcyfjzwtuax) reports ACTIVE_HEALTHY.
- Database version is PostgreSQL 17.11.
- The public schema has zero tables and the migration list has zero entries.
- Security and performance advisors returned no lints; with no application tables this is not evidence of a migrated or qualified application database.

This project is not a verified replacement for the Render PostgreSQL 18 source. Do not change the staging API connection string to Supabase based only on project health.

## 4. PostHog

- Connected project: Default project, ID 675660.
- project-get reports ingested_event=false; read-data-schema confirms the project has not received events.
- No SDK, event, dashboard, alert, or wizard PR was created, and no telemetry was sent.
- Telemetry remains blocked pending explicit approval of event scope, region, retention, consent/privacy disclosure, opt-out/kill-switch behavior, and data exclusions.

The proposed safe scope remains operational-only, coarse events. Do not send raw prompts/text, document contents, tokens, OAuth secrets, raw account identifiers, or connector payloads. See https://posthog.com/docs/privacy/data-collection and issue [#584](https://github.com/rumman52/Shuddho/issues/584).

## 5. Vercel, Linear and ProductOS

- Vercel project shuddho-web-editor is listed under the connected account. Deployment listing returned 403 and project detail returned 404 in the current connector scope. No current frontend deployment SHA or route health is independently verified.
- Linear search returned no Shuddho issue or project.
- ProductOS returned no accessible project for this organization.

Do not claim frontend release readiness from a historical preview status.

## 6. Transactions and architecture/core acceptance

The exact-main coworker CI job passed the named mandatory transaction safety, PostgreSQL fault-boundary, transaction HTTP/hard-worker recovery, and CW-02 to CW-04 gate steps. This supports source-level regression coverage.

Issue [#378](https://github.com/rumman52/Shuddho/issues/378) remains open because real provider sandbox receipts, independent provider-side applied-mutation counts, frozen exact API/worker/Temporal identity, accepted-but-lost provider response reconciliation, and rollback/kill-switch operation are not verified. Keep payment-bearing and provider mutation capabilities disabled.

All **17 A/C/P/V architecture-core acceptance rows remain NOT FULLY QUALIFIED**. Repository CI does not substitute for operated staging, independent review, provider evidence, security isolation, quality/economics measurements, restore/rollback evidence, or explicit release authorization.

## 7. Ordered remaining work

1. **Database continuity before expiry:** owner chooses and executes a controlled preservation path; verify the export by restoring it. Keep source intact until restore proof exists.
2. **GitHub governance:** administrator applies and reads back the existing no-bypass main ruleset, requires exact final-head test-and-build, coworker, ci-merge-gate and independent approval, then proves denied and allowed merge cases.
3. **Staging worker and credentials:** create the reviewed persistent worker through the Render Dashboard/Blueprint flow; securely enter Temporal, S3, auth and provider secrets. Do not place secrets in GitHub/chat.
4. **Staging parity and freeze:** align API/worker to the same reviewed SHA and configuration, verify migrations, PostgreSQL, Temporal, private S3, managed identity and owner isolation, then execute the reviewed PA-10 freeze and synthetic reminder scenario.
5. **Production readiness:** decide detector/corrector intent, validate model/checkpoint artifacts, define liveness versus analysis readiness, set health checks only after tests, and establish reviewed promotion instead of unqualified auto-deploy.
6. **Telemetry:** obtain explicit privacy/scope approval, implement through a reviewed PR, then verify actual ingestion and useful alerts.
7. **Transactions:** qualify each provider separately with real sandbox evidence, independent mutation counts, reconciliation and rollback drills.
8. **Final acceptance:** close all applicable 17 rows with exact source, CI, operated environment, security and human-review evidence.

## 8. Changes and evidence boundary

During this inspection, GitHub status comments were added to issues #291, #339, #378, #484, #583 and #584. No source code, database data, network allowlist, Render service, billing, secrets, branch rules, production flag, deployment, provider mutation, or telemetry configuration was changed.

The documentation refresh is not a release approval. No production activation is authorized by this report.
