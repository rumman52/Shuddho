# Day 1 C — database continuity and release controls

**Observed:** 10 November 2026, approximately 10:35–10:50 UTC.  
**Disposition:** **BLOCKED_EXTERNAL / NOT RELEASE-QUALIFIED.** Production API automatic deployment was disabled later in this session and confirmed by API readback. Database preservation, isolated restore and native GitHub enforcement remain unverified. The initial inventory below is historical where the later checkpoint supersedes it.

## Immediate owners and blockers

| Item | Current evidence / blocker | Owner and next concrete action |
| --- | --- | --- |
| Existing staging data | Expired Free PostgreSQL 18 is suspended for billing; no successful connection or verified export | Render workspace owner: decide recovery immediately. The documented route requires a paid compute upgrade, which has not been authorized. Under the existing zero-spend limit, request a no-cost courtesy access/export exception from Render; success is unknown and no request was sent here. |
| Grace-period risk | Recorded expiry plus Render's documented 14 days gives **14 November 2026, 17:11:33.79468 UTC / 23:11:33.79468 Asia/Dhaka** | Owner: confirm the actual dashboard deadline and retained source availability. This calculated deadline is not a guarantee of recoverability. Preserve the source; do not delete or replace it. |
| Source inventory and backups | Schema, row counts, database size, object inventory, backup references and last-good restore are unknown | Owner/operator: after access is restored, inventory read-only, export immediately and retain a verified isolated copy. Empty allowlist does not mean empty database. |
| Native protected main | `protected=false`, rulesets `[]`, detail endpoint HTTP 403 | Repository administrator: apply/read back the existing reviewed policy, then operate denied/permitted controls below. The installed connector cannot write admin rules. |
| Production promotion | Production is `autoDeploy=yes`, `autoDeployTrigger=commit` from main | Render administrator: change the existing production service's Auto-Deploy setting to **Off**, read it back and record the change. Session authorization covers controlled promotion; tool capability is the blocker. No setting or deployment changed during this inspection. |
| Real staging qualification | Staging API is stale; no persistent staging worker is listed | Owner: resolve data access, worker/budget and backend secrets before API/worker parity, freeze or live restore qualification. Do not sync a Blueprint as an indirect way to provision or change billing. |

The 9 November [zero-budget recovery record](../PRIORITY4_ZERO_BUDGET_OPERATIONAL_SECURITY_2026-11-09.md) remains relevant: no paid recovery/resource choice is implied by Day 1 inventory. Current evidence supersedes the old **available / expires today** wording in the 31 October snapshot.

## Fresh evidence

The user explicitly selected Render workspace **Rumman**, `tea-d6ok4okhg0os73erkdv0`; that exact `workspaceId` was supplied on the Render reads. No workspace was selected implicitly.

### Render database and service inventory

| Resource / field | Observed value |
| --- | --- |
| Database | `shuddho-staging-db`, `dpg-dav98hfpn0mc739mndvg-a` |
| Plan / engine / region | `free` / PostgreSQL `18` / `oregon` |
| Status / suspension | `suspended` / `suspended`, suspenders `["billing"]` |
| Created | `2026-10-01T17:11:33.79468Z` |
| Expires | `2026-10-31T17:11:33.79468Z` |
| External database IP allowlist | `[]` |
| High availability / replicas | `false` / `[]` |
| Staging API | `shuddho-api-staging`, `srv-dav98otg1s2s73cod4gg`, Free web service, branch `main`, `autoDeploy=no`, trigger `off` |
| Latest staging deploy | `dep-davmrnu7bikc73emahdg`, status `live`, source `fce72760456bd8bb03524ce98127120c7ac3dfb9`, finished `2026-10-02T08:41:32.326233Z` |
| Production API | `shuddho-api`, `srv-d6oki2v5r7bs73e7isfg`, Free web service, branch `main`, `autoDeploy=yes`, trigger `commit` |
| Latest production deploy | `dep-dbp3u9142hec73d1v2ng`, status `live`, source `1f6dae72e1de6f38ec4d9cf60180d856dbecb403`, trigger `new_commit`, finished `2026-11-09T21:47:49.488305Z` |
| Staging worker | None in returned workspace service inventory; the other returned service is unrelated `OutcomeOS` |
| API health-check configuration | Both Shuddho services report an empty `healthCheckPath` |

Reads used `get_postgres`, `list_services` and `list_deploys(limit=1)` with the explicit workspace. The Day 1 inventory's hosted read-only SQL request was rejected because the database has an empty external IP allowlist; the connector does not provide a stable address that can be narrowly allowlisted. No query result establishes actual data contents. No backup-list/export/recovery action was exposed among the available Render tools. No credentials were retrieved.

Service metadata marked `live` is a deployment status, not evidence that authentication, Coworker persistence, provider calls or restore/recovery work.

### GitHub source and native controls

Read-only GitHub endpoints returned:

- [Main branch](https://api.github.com/repos/rumman52/Shuddho/branches/main): SHA `1f6dae72e1de6f38ec4d9cf60180d856dbecb403`; `protected=false`; required-status enforcement `off`, contexts/checks empty.
- [Rulesets including parents](https://api.github.com/repos/rumman52/Shuddho/rulesets?includes_parents=true&per_page=100): `[]`.
- [Main protection detail](https://api.github.com/repos/rumman52/Shuddho/branches/main/protection): **403**, `Resource not accessible by integration`.
- Open pull requests: only draft [#664](https://github.com/rumman52/Shuddho/pull/664), head `5816cdbbce340b8bd286ec8ea7ab9a57e3e9e735`, which matches this checkout's HEAD. No merge was performed.

Exact-main [CI run #42705627334](https://github.com/rumman52/Shuddho/actions/runs/42705627334) is completed with conclusion `failure`:

| Job | Conclusion |
| --- | --- |
| `test-and-build` | success |
| `PostgreSQL 18 staging compatibility` | success |
| `browser-qualification` | success |
| `Frontend tests and builds` | success |
| `coworker` | failure |
| `governance-audit` | failure |
| `ci-merge-gate` | failure |

These failures and production's matching automatically deployed SHA demonstrate why a post-merge audit is insufficient as a promotion control. The inaccessible legacy-detail endpoint is a permission limitation; do not fabricate its policy or infer administrator bypass rights from it.

## Source recovery and real restore runbook

### 1. Recover access without losing the source

Render's official [Free Postgres policy](https://render.com/docs/free) says expired Free databases are inaccessible until upgraded, have a 14-day upgrade grace period, and are deleted with their data after that period. Its [recovery documentation](https://render.com/docs/postgresql-backups) says Free instances have no managed recovery or logical backups. A newly authorized upgrade does not establish a historical backup or retroactive point-in-time recovery window.

There is no documented supported zero-cost export route for this already-expired source. A courtesy exception is an owner support action with an unknown outcome. If the owner chooses a paid recovery, obtain the concrete database compute plan/cost decision first; do not confuse a workspace plan change with upgrading this database's compute plan.

After owner-approved access recovery:

1. Confirm the exact original resource still exists. Record server version, database size, application schemas/tables, migration revision, per-table counts and any existing backup/export references using read-only access. Keep private contents and credentials out of public evidence.
2. Use the provider's supported same-region path or a trusted operator connection. An external path requires an explicitly approved narrow operator address and TLS; opening the database to all addresses is not a recovery workaround. Do not change the allowlist to accommodate the hosted connector.
3. Export the existing database promptly with PostgreSQL 18-compatible tooling; separately preserve the private object store and record a consistent database/object backup boundary. Record export time, SHA-256, size, tool version, source identity and durable private location. Do not wait for a synthetic probe before rescuing the existing data.
4. Restore into an **isolated empty PostgreSQL target** and a distinct private object target. Inspect the archive and target identity before restore. Do not restore over active staging or production, repoint services, delete the source or run migrations as a substitute for preservation.
5. Compare migration/schema, counts and representative owner/task/document relationships with the source inventory; validate stored document bytes against metadata hashes. Record any excluded roles/ownership/privileges and restore warnings. An archive listing or successful download alone is not a verified restore.

For an owner-approved custom-format export, the following is a command pattern, **not a command run in this inspection**. A trusted operator must first configure private libpq service entries `shuddho_recovery_source` and `shuddho_recovery_isolated` (including TLS) and verify that the latter selects an isolated empty target; secrets do not belong on the command line:

```bash
umask 077
PGSERVICE=shuddho_recovery_source pg_dump --format=custom --no-owner --no-privileges --file=/secure/recovery/shuddho-source.dump
sha256sum /secure/recovery/shuddho-source.dump
pg_restore --list /secure/recovery/shuddho-source.dump
pg_restore --dbname=service=shuddho_recovery_isolated --exit-on-error --single-transaction --no-owner --no-privileges /secure/recovery/shuddho-source.dump
```

The private directory and isolated target must already exist. No `--clean` or `--create` operation is prescribed. See PostgreSQL 18's [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) and [pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html) references. This rescue procedure and its owner inventory are separate from the repository's release-bound synthetic drill below.

### 2. Reuse the existing controlled drill after prerequisites are restored

The actual command is [scripts/staging_backup_restore.py](../../scripts/staging_backup_restore.py), documented in [Controlled Staging Backup and Restore](../CONTROLLED_STAGING_BACKUP_RESTORE.md). Its `prepare` and `verify` CLI arguments were checked locally using `--help`; **neither live subcommand was executed**.

Before the drill, select one reviewed full source SHA and rollout manifest, provide backend database/private storage settings securely, and provide the managed synthetic staging API identity. `SHUDDHO_SOURCE_REVISION` must be the full deployed SHA, not an invented or abbreviated revision. The current stale staging API and absent worker do not establish a matching release environment.

On the controlled **source staging** environment:

```bash
SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true uv run --extra coworker python -m scripts.staging_backup_restore prepare \
  --state /secure/recovery/backup-restore-state.json \
  --rollout /secure/release/cohort-rollout.json
```

This is a real guarded mutation: it resolves the synthetic owner via HTTPS `/api/v1/me`, uploads synthetic bytes, creates and cancels one task, then saves record IDs, hashes and environment fingerprints. It first validates the rollout and a new private evidence-file destination. The state directory must exist and the state file must not already exist or be a symlink. Keep this as a controlled staging step, after emergency preservation/access recovery.

Take a **real database backup and private object backup after prepare**, restore both into isolated targets, then run on the **restored environment**, using real durable references in place of the bracketed labels:

```bash
SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE=true uv run --extra coworker python -m scripts.staging_backup_restore verify \
  --state /secure/recovery/backup-restore-state.json \
  --backup-reference '<real-database-and-object-backup-reference>' \
  --restore-reference '<real-isolated-restore-reference>' \
  --rollout /secure/release/cohort-rollout.json \
  --output /secure/recovery/staging-evidence.restore.json
```

If combining existing evidence, add `--base-evidence /secure/recovery/staging-evidence.json`. Use a new output path. The verifier checks:

- matching release ID, full source revision, rollout SHA-256 and prepared exercise time;
- **both** database and storage fingerprints differ from the source;
- restored account/workspace, owner-scoped document/version, uploaded state, cancelled task and task-event history;
- exact metadata SHA-256/byte size and actual restored private object bytes;
- nonempty supplied backup/restore references.

Successful output records only `backup_restore=passed` with release-bound timestamps/context. The script does not perform the backup or restore and does not independently authenticate the supplied reference strings. Retain the actual provider/operator receipts and restore logs. Private output files are atomic, mode 0600 and no-overwrite. No passing live artifact exists from this session.

## Native GitHub protected-main runbook

Reuse [infra/github/main-ruleset.json](../../infra/github/main-ruleset.json) and [scripts/apply_main_ruleset.py](../../scripts/apply_main_ruleset.py), following the [existing safe operator record](V01_SAFE_RULESET_APPLY_OPERATOR_2026-10-25.md). The reviewed policy has:

- active explicit `refs/heads/main`, no exclusions or bypass actors;
- at least one independent approval, stale approval dismissal, approval of the latest push, and resolved review threads;
- strict required `test-and-build`, `coworker` and `ci-merge-gate` checks, pinned to GitHub Actions integration ID `15368`;
- force-push and deletion restrictions.

An administrator must first verify current effective repository/inherited rules and actual check publishers. Preserve stricter existing rules; do not replace ambiguous protection. In a trusted administrator terminal with a securely supplied administration-capable token, first run the default **read-only plan**:

```bash
python -m scripts.apply_main_ruleset --repository rumman52/Shuddho
```

After reviewing that concrete plan, the session-authorized administrator can apply:

```bash
python -m scripts.apply_main_ruleset \
  --repository rumman52/Shuddho \
  --apply \
  --confirm-repository rumman52/Shuddho
```

The helper refuses unsafe existing/ambiguous rules, never automatically replaces/deletes a policy, performs post-create read-back, and reconciles an uncertain POST response without blindly reposting. A successful result still states `merge_enforcement_verified=false` and `qualified=false`. Keep administrator credentials out of PR-controlled CI. No apply or live token-based operator command ran here.

### Local harness versus actual GitHub denied/permitted controls

Reuse the existing tests in `tests/test_apply_main_ruleset.py`, `tests/test_main_protection_audit.py` and `tests/test_v01_native_protection_audit.py`. They cover allowed/refused operator plans, policy acceptance/rejection, uncertain creation, source pinning and no credential redirects. Their fake local API is **not GitHub's merge authorization boundary**. No standalone real denied/permitted merge-attempt harness was found in the inspected scripts/tests/workflows; do not create evidence by relabeling these unit tests.

The native diagnostic `scripts/v01_native_protection_audit.py` always reports `enforcement_verified=false`: blocked configurations exit **2**, and configuration candidates exit **3**, never zero. `scripts/main_protection_audit.py` also describes configuration only. `scripts/v01_merge_evidence.py` classifies historical exact-head review/check chronology; a clean historical classification is not a merge lock.

After production auto-deploy is off and settings read-back is complete, the administrator should use harmless documentation-only test PRs against main and an independent reviewer. Demonstrate each case separately, recording the actor's effective permissions and testing the normal developer and routine administrator merge paths without invoking bypass:

| Actual GitHub control case | Required observed result |
| --- | --- |
| Required check pending | Normal merge denied |
| Required check failed | Normal merge denied |
| Current independent approval absent | Normal merge denied |
| Approval made stale by a new head push | Normal merge denied until a valid new approval/check run |
| Review thread unresolved | Normal merge denied |
| Latest head fully green, independently approved, threads resolved and branch current | Normal merge permitted under the recorded policy |

For each, retain repository/rule IDs, UTC time, actor/permission, test PR URL, base/head SHA, exact check-run/review IDs, GitHub denial reason or permitted merge state, and the resulting branch/PR state. If an invalid merge unexpectedly succeeds, record the control failure and stop. Do not claim a red check means denial without observing GitHub's result. The permitted control can demonstrate eligibility without actually merging; if an actual positive merge is chosen, record its merge commit and the main ref, using only the harmless reviewed PR. No actual denied/permitted GitHub control was operated here.

GitHub's [current rules documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) explains administration permissions, reviews, required checks and bypass behavior. Settings inspection and local tests alone leave V-01 [#484](https://github.com/rumman52/Shuddho/issues/484) open.

## Controlled promotion runbook

The existing production service currently promotes on commit from unprotected main. The available Render tool surface can read this configuration and trigger deployments, but does not expose a service-update action to change Auto-Deploy. A Blueprint mutation is not a narrow substitute. The administrator can make the session-authorized configuration change in the existing service's [Settings](https://dashboard.render.com/web/srv-d6oki2v5r7bs73e7isfg): **Auto-Deploy → Off**. Record before/after values, UTC time, actor, service/workspace IDs, and the unchanged current deploy identity; re-read service metadata to verify `autoDeploy=no` / trigger `off`.

Render documents the setting and manual specific-SHA deployment in [Deploying on Render](https://render.com/docs/deploys). “After CI Checks Pass” accepts some neutral/skipped conclusions and is not the exact success/review/operated-evidence contract here; use explicit promotion with Off for the requested control.

Before any later production promotion:

1. Select and record one exact reviewed commit. Require native merge controls and successful final-head CI, independent review and resolved findings. Current main fails required checks and is not a promotion candidate.
2. Match staging API/worker/configuration and schema compatibility to that candidate; collect real restore, recovery, ownership and workflow evidence. A live service label or ephemeral CI PostgreSQL job does not satisfy this.
3. Use the existing [final controlled-cohort gate](../FINAL_CONTROLLED_COHORT_GATE.md), canonical `scripts/release_contract.py`, and feature-specific activation/ledger requirements for the exact rollout. The [activation bundle](../CONTROLLED_RELEASE_ACTIVATION_BUNDLE.md) is a verifier, not a deploy command or release authorization.
4. Record the authorized promotion and rollback target before the administrator chooses **Deploy a specific commit** in the existing production service. Do not choose “latest” and allow the candidate to drift. This document does not authorize or perform that future deployment.
5. Confirm deployed SHA and liveness with the existing read-only `scripts/api_deployment_smoke.py --environment production --expected-sha <exact-deployed-sha>`, then retain the separate release-specific functional/operational evidence. A smoke pass alone sets `release_qualified=false`.

No production setting, deployment, flag, secret, IP allowlist, billing plan, database or provider action was changed during Day 1 C inspection.

## Checks actually run

| Command / check | Result and scope |
| --- | --- |
| `python -m pytest tests/test_apply_main_ruleset.py tests/test_main_protection_audit.py tests/test_v01_native_protection_audit.py -q -rs` | Default runtime lacks pytest; command exited 1 before collection. |
| `.venv/bin/python -m pytest tests/test_apply_main_ruleset.py tests/test_main_protection_audit.py tests/test_v01_native_protection_audit.py -q -rs` | **94 passed**, zero skips; local/fake-API coverage only. |
| `.venv/bin/python -m scripts.staging_backup_restore --help` and `prepare --help`, `verify --help` | Passed; verified real CLI paths/arguments, no live exercise. |
| `.venv/bin/python -m pytest tests/test_staging_backup_restore.py -q -rs` | **9 passed**, zero skips; synthetic repository checks only. |
| Existing policy functions with observed `rulesets=[]` / `protected=false` | Native diagnostic classified `blocked`, `no_active_rulesets_supplied`, enforcement false; governance audit rejected main protection. |
| Read-only GitHub and Render connector calls above | Fresh metadata collected; legacy protection read returned 403. |
| Official Render, GitHub and PostgreSQL documentation | Read 10 November 2026; URLs linked above. |

Only this operations record was authored for Day 1 C. No commit was made. Other concurrent source work is outside this record. The next evidence-bearing action is owner resolution of the database recovery deadline/cost decision and administrator execution/read-back of the already-authorized promotion and native-rule controls; until then these operational gates stay blocked.

## Later Day 1 control checkpoint

The authorized administrator browser session was available after the initial API inventory. Production service `srv-d6oki2v5r7bs73e7isfg` Auto-Deploy was changed from **On Commit** to **Off**. Render `get_service` independently read back `autoDeploy=no`, `autoDeployTrigger=off`, `updatedAt=2026-11-10T10:55:49.522248Z`. No deployment was triggered; the live commit remained `1f6dae72e1de6f38ec4d9cf60180d856dbecb403`. Staging was already off. This controls automatic API promotion; manual exact-SHA release must still satisfy the existing release contract. The production frontend has its separate Vercel integration and is not claimed controlled by a Render change.

The GitHub administrator UI was populated with the existing `infra/github/main-ruleset.json` policy: name `Shuddho main review and CI`, Active, exactly `refs/heads/main`, no bypass actors, no deletions/force pushes, PR required, one approval, stale review dismissal, most-recent-push approval, resolved conversations, up-to-date required checks `test-and-build`, `coworker`, `ci-merge-gate`, each selected from GitHub Actions rather than Any source; creation is not exempted. Saving was intercepted by GitHub **Confirm access**. GitHub Mobile verification was requested and the tab retained for the owner. The rule is **not claimed saved or active** until account verification and independent API readback succeed. Do not bypass account verification or fabricate the native denied/permitted cases.

Current unresolved operator decisions: existing zero-spend limit remains in force; no paid DB/worker upgrade or retention period is approved. The source must remain preserved. Native ruleset save/account verification, genuinely current-head human approval, real denied/permitted merge controls, recovery/resource choice and isolated restore remain owner blockers. Completion of source code and disabling production API auto-deploy do not close them.
