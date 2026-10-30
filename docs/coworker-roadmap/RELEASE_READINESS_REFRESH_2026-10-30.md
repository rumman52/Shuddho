# Shuddho — current release-readiness refresh

**Inspection date:** 30 October 2026 (Asia/Dhaka)  
**Repository:** [rumman52/Shuddho](https://github.com/rumman52/Shuddho)  
**Current `main`:** `5ebe86d4119bc7222c08270b7e93e106d6f3a3cc`  
**Disposition:** **NOT RELEASE-QUALIFIED**. This is a fresh evidence snapshot, not production approval.

This refresh supersedes older status statements where they conflict. It does not replace the detailed historical work log in [PROGRESS.md](PROGRESS.md). The file is intentionally separate because that historical log is very large; do not infer that older checkpoints describe today's live services.

## 1. GitHub source and CI

### Current main

[Main CI run #40896814667](https://github.com/rumman52/Shuddho/actions/runs/40896814667) on `5ebe86d4119bc7222c08270b7e93e106d6f3a3cc` reports:

| Job | Result | Interpretation |
|---|---|---|
| `test-and-build` | **SUCCESS** | Application tests/build passed |
| `coworker` | **SUCCESS** | Mandatory coworker suite passed |
| `governance-audit` | **FAILURE** | Main protection could not be confirmed |
| `ci-merge-gate` | **FAILURE** | Upstream governance audit failed |

The governance log says `main branch protection is not confirmed`. The connected rulesets listing returned an empty array; the legacy branch-protection detail endpoint was not accessible to this integration. Therefore native pre-merge protection is **not proven**. A post-merge audit is not a pre-merge control.

[PR #593](https://github.com/rumman52/Shuddho/pull/593) merged as `5ebe86d4119bc7222c08270b7e93e106d6f3a3cc` despite its exact-head CI [#40767073310](https://github.com/rumman52/Shuddho/actions/runs/40767073310) failing the merge gate and having no submitted independent review. Its code jobs passed, but this does not establish release governance.

[V-01 issue #484](https://github.com/rumman52/Shuddho/issues/484) was closed at the time PR #593 merged, although its acceptance criteria remained unmet. It has now been **reopened** with the current evidence. No repository-admin ruleset change was attempted.

### Open PR #596

[PR #596](https://github.com/rumman52/Shuddho/pull/596) contains the Node API smoke-probe correction: only explicit `full_local` with no degradation reasons is classified ready; partial profiles are degraded; missing/unknown/malformed profiles are unverified.

- Head: `4f725b5558769a2072782be4cb069e3a5c7b8394`.
- Recorded base SHA: `93ff94f0e60723652d2a1b523bf91198ebe3bd74`; current main is newer.
- GitHub reports `mergeable=false`.
- Submitted reviews: none.
- Exact-head [CI #40861018712](https://github.com/rumman52/Shuddho/actions/runs/40861018712): `test-and-build=success`, `coworker=success`, `governance-audit=skipped`, `ci-merge-gate=failure`.
- The review-gate log rejected the draft revision. The PR is now **draft** again, matching its release-limit text.
- The PR's GET-only live health probe could not reach `/health`; no live health or readiness result is claimed.

Next: refresh the branch against current main, rerun all required checks on the exact final head, and obtain independent human review after native governance is enforced. Do not merge it.

## 2. Render — confirmed live state

The inspected workspace is **Rumman**.

### Staging database

| Field | Live value |
|---|---|
| Resource | `shuddho-staging-db` |
| ID | `dpg-dav98hfpn0mc739mndvg-a` |
| Plan / status | `free` / `available` |
| Created | 1 October 2026, 17:11:33 UTC |
| Expiry | **31 October 2026, 17:11:33.79468 UTC (23:11:33.79468 Asia/Dhaka)** |
| IP allowlist | `[]` (external access disabled) |
| High availability | Disabled |

Render's current official policy states that Free Postgres instances do **not** support backups, point-in-time recovery or managed logical exports. After expiry, the database becomes inaccessible; the owner has a 14-day grace period to upgrade before deletion. See [Free instance limitations](https://render.com/docs/free) and [Postgres backup/recovery](https://render.com/articles/how-to-backup-and-restore-postgresql-databases).

Because external access is disabled, an external `pg_dump` requires an explicitly approved narrow IP allowlist or an approved same-region export process. Do not open `0.0.0.0/0`. A backup is not verified until a restore has been tested.

### Staging API and worker

- `shuddho-api-staging` (`srv-dav98otg1s2s73cod4gg`) is a Free `web_service`, branch `main`, auto-deploy off.
- Its health-check path is blank.
- Live build command: `pip install uv && uv sync --extra coworker`.
- Live start command: `uv run uvicorn services.api.shuddho_api.app:app --host 0.0.0.0 --port $PORT`.
- Latest live staging deployment: 2 October 2026, SHA `fce72760456bd8bb03524ce98127120c7ac3dfb9`.
- No `shuddho-worker-staging` service exists in the current workspace inventory.

The reviewed [staging Blueprint](../../infra/render.staging.yaml) expects the API health path `/health`, locked dependencies, the explicit coworker extra, and a persistent `type: worker` service with pre-deploy migrations and the Temporal worker start command. The worker plan is `0.5c-512mb`; this refresh did not provision it or incur charges.

### Production API

- `shuddho-api` (`srv-d6oki2v5r7bs73e7isfg`) is a Free `web_service`.
- Auto-deploy is **yes**, triggered by commits to `main`.
- Health-check path is blank.
- Latest live deployment: `dep-dbhlu47b9u1s73a2pv4g`, source SHA `5ebe86d4119bc7222c08270b7e93e106d6f3a3cc`.
- Startup logs on 28 October explicitly report detector and corrector disabled and degraded local analysis mode (`detector_disabled`, `corrector_disabled`).

The main commit is therefore live in production, but no production analysis-readiness qualification is established. A live deployment is not evidence that detector/corrector-backed analysis is ready.

## 3. Supabase, PostHog, Vercel, Linear and ProductOS

- **Supabase:** project `shuddho-staging` (`bsmbvjenpvcyfjzwtuax`) reports `ACTIVE_HEALTHY`. This does not establish Render database continuity or a live Temporal worker.
- **PostHog:** project `Default project` (ID `675660`) reports `ingested_event=false`; its data-schema tool confirms no events have been received. No instrumentation or telemetry was enabled. Privacy scope, consent, retention and region approval remain prerequisites.
- **Vercel:** `shuddho-web-editor` is connected. A Vercel GitHub bot comment reported the PR #596 preview as Ready, but deployment-list access returned 403 and direct deployment retrieval returned 404 through the connected integration. No independent route-health check is claimed.
- **Linear:** no matching Shuddho project or issue was found in the connected workspace.
- **ProductOS:** no Shuddho project was found in the connected workspace.
- **Temporal Cloud:** no direct connected service access was available for live namespace/worker verification.

## 4. Evidence-based completion status

The status labels below describe acceptance evidence, not percentages of code written.

| Workstream | Current status | Remaining acceptance |
|---|---|---|
| Architecture and core foundations | **CODE_COMPLETE_UNQUALIFIED** | Full frozen staging, security and operated acceptance |
| Automation / proactive work | **CODE_COMPLETE_UNQUALIFIED** | Real scheduled/event runs, recovery, consent, usefulness and cost proof |
| Transactions | **CODE_COMPLETE_UNQUALIFIED** | Distinct operated evidence for all 16 fault scenarios and provider-specific reconciliation |
| GitHub governance | **OWNER_ACTION_REQUIRED** | Native no-bypass ruleset, independent current-head review, denied/allowed merge tests |
| Staging DB continuity | **OWNER_ACTION_REQUIRED — URGENT** | Export/restore proof and retention decision before expiry |
| Persistent staging worker | **BLOCKED_EXTERNAL** | Approved worker provisioning, secrets, Temporal polling and restart proof |
| API/worker release consistency | **BLOCKED_EXTERNAL** | Same exact reviewed SHA, health semantics and frozen rollout |
| Identity, storage, Temporal and model runtime | **CODE_COMPLETE_UNQUALIFIED** | Real synthetic-user, private S3, worker, inference and recovery acceptance |
| Quality and observability | **INCOMPLETE** | English/Bangla evaluation, SLOs, telemetry approval, alarms and restore/rollback evidence |
| Production qualification | **NOT RELEASE-QUALIFIED** | All applicable P0/P1 evidence and separately authorized rollout |

The existing ledger identifies 17 architecture/core acceptance rows that are not fully qualified. No current overall completion percentage is asserted.

## 5. GitHub bookkeeping performed in this refresh

- Reopened [#484](https://github.com/rumman52/Shuddho/issues/484), because its closure did not match the live governance evidence.
- Added current read-only evidence and owner actions to [#484](https://github.com/rumman52/Shuddho/issues/484), [#291](https://github.com/rumman52/Shuddho/issues/291), [#583](https://github.com/rumman52/Shuddho/issues/583) and [#584](https://github.com/rumman52/Shuddho/issues/584).
- Updated [PR #596](https://github.com/rumman52/Shuddho/pull/596) with its final CI status and returned it to draft.
- Prepared this documentation-only refresh and updated the completion ledger. No source code was changed.

## 6. Owner actions in priority order

1. **Render owner — before 31 October 23:11:33 Asia/Dhaka:** choose and execute an approved database preservation path. Free Postgres has no Render-managed backups. If using external `pg_dump`, allow only a trusted operator `/32`, require TLS, keep credentials private, download the dump to durable storage and restore-test it. Then decide retention/upgrade/migration. Do not perform a destructive migration without a verified restore.
2. **GitHub repository administrator:** apply the existing [main ruleset](../../infra/github/main-ruleset.json) using [`scripts/apply_main_ruleset.py`](../../scripts/apply_main_ruleset.py) from a secured admin environment. Require independent approval and exact-final-head `test-and-build`, `coworker`, `ci-merge-gate`; prohibit ordinary bypass and stale approvals; prove denied and allowed merge cases.
3. **Render production owner:** stop automatic promotion of unqualified `main` commits or replace it with explicit reviewed promotion. Define liveness versus analysis readiness before configuring the production health-check path.
4. **Staging operator:** provision the reviewed persistent worker only with current spending approval; enter secrets through the secure dashboard; align API/worker and database to one exact SHA; verify Temporal, private storage, identity and recovery.
5. **Independent reviewer:** review PR #596 only after it is refreshed to current main and its final-head checks complete.
6. **Privacy/product owner:** approve PostHog event scope, retention, region and consent before instrumentation is added.

## 7. Execution limits and evidence quality

This refresh used read-only GitHub, Render, Supabase, Vercel and PostHog inspection, plus Linear/ProductOS discovery and current official Render documentation. The repository's `shuddho-engineering` skill and Superpowers implementation plan were read.

No Render service, database, IP allowlist, billing plan, secret, GitHub branch rule, deployment, telemetry, provider action or production flag was changed. No database credentials were accessed. No backup, migration, model inference or live Temporal run was performed. No local test process was run during this refresh; the CI results above are existing remote runs on the stated SHAs.

The uploaded skill ZIP archives named in earlier prompts were not present in the accessible Library index. The repository skill and plan were available and used. Context7 was not needed because this refresh made no package/API implementation change.

**Release decision: NOT RELEASE-QUALIFIED. Keep high-authority capabilities disabled until the required exact-SHA staging, security, provider, review and production evidence exists.**
