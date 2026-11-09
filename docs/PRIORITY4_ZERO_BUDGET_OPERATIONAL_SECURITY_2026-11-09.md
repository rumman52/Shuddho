# Priority 4 — Zero-Budget Operational Security Recovery

**Prepared:** 9 November 2026 (Asia/Dhaka)  
**Repository baseline:** `0e07cb1ca9bee376475baf463ce301a0312ff486`  
**Spending authorization:** USD 0. No paid resources, upgrades, overages, or usage-based services are authorized.

## Executive decision

Use GitHub Actions as the disposable qualification environment while attempting a no-cost recovery of the existing Render PostgreSQL database. Do not create a replacement database and do not point staging at another provider until the existing data has either been recovered or explicitly classified as unrecoverable.

This is a **zero-cost engineering qualification path**, not a claim that a permanently deployed staging environment has been restored.

## 1. Existing infrastructure evidence

### Render PostgreSQL

Observed resource:

- Name: `shuddho-staging-db`
- ID: `dpg-dav98hfpn0mc739mndvg-a`
- PostgreSQL: 18
- Plan: Free
- State: suspended
- Suspension reason: billing
- Recorded expiry: `2026-10-31T17:11:33Z`

Render's Free Postgres policy states that Free databases expire 30 days after creation, are inaccessible after expiry until upgraded, have a 14-day upgrade grace period, and do not support automatic backups or point-in-time recovery. The current recorded expiry implies a grace deadline of approximately `2026-11-14T17:11:33Z` (23:11:33 Asia/Dhaka).

**No export, snapshot, or successful database connection has been observed.** Therefore, the existing data is at risk and must not be described as backed up.

Zero-cost action: open a Render support request asking whether a one-time courtesy restore or export is possible without upgrading. This is an exception request, not a guaranteed recovery path. Do not delete the database. Any paid upgrade requires separate explicit authorization.

References:
- https://render.com/docs/free
- https://render.com/docs/postgresql-backups

### Supabase staging

Observed project:

- Name: `shuddho-staging`
- Project ref: `bsmbvjenpvcyfjzwtuax`
- Organization tier: Free
- Control-plane metadata: `ACTIVE_HEALTHY`
- PostgreSQL: 17.11
- Region: `us-west-1`

The connected Supabase tools could not verify schema or migrations: table inspection failed with password authentication failure for the connector's read-only database user, migration inspection failed with password authentication failure for the PostgreSQL user, and advisor calls reported hibernation. A restore request reported the project was already `ACTIVE_HEALTHY`.

This is contradictory control-plane / data-plane evidence. Do not treat the project as a verified Coworker database, reset its password, apply migrations, or change application connection strings until an operator confirms dashboard connectivity and schema state.

### GitHub Actions

The repository is public and its existing CI uses disposable PostgreSQL service containers, Temporal's test environment, and Playwright Chromium. These are suitable for repository-level qualification without a persistent cloud worker.

The latest main CI run inspected on 9 November 2026 was `42583600850` on `0e07cb1`:

- `test-and-build`: passed
- frontend: passed
- Coworker: failed during test collection because `services.coworker.time` was missing
- Chromium browser-worker network boundary: passed
- browser source-provenance test collection: failed because of the same missing module
- governance audit: failed because native main protection is absent

PR #663 restores the missing time module and adds regression tests. Its first rerun then exposed a separate Alembic graph defect: migration `0068_fly_repository_coding` referenced `0067_agent_decision_latency`, while migration 0067 declares its actual revision ID as `0067`. The PR corrects the parent reference and adds a PostgreSQL migration assertion.

The PR also adds a PostgreSQL 18 CI qualification job to the existing required merge gate. It uses an ephemeral GitHub-hosted PostgreSQL 18 service and runs database migration, trusted-skill registry, Temporal test-server, transaction fault, observability, and rollback tests without live provider mutations. This is repository-level qualification only; it does not restore a persistent staging worker or live cloud egress isolation. Its exact-head run must pass before repository-level qualification can be updated.

## 2. Zero-cost qualification topology

Use the following boundaries:

| Capability | Zero-cost environment | What it proves | What it does not prove |
|---|---|---|---|
| PostgreSQL | GitHub Actions service container | Real PostgreSQL migrations, constraints, concurrency and transaction tests | Persistent staging database availability or retention |
| Temporal | Temporal test server / test environment in CI | Workflow/activity execution, replay, cancellation and restart contracts covered by tests | A deployed Temporal cluster and real worker fleet |
| Browser | Playwright Chromium on GitHub runner | Browser-worker proxy policy, pinned CONNECT path, DNS/SSRF unit and integration regressions present in CI | Cloud egress firewall, live DNS rebinding and private-network isolation on a deployed worker |
| Trusted skills | PostgreSQL-backed registry tests in CI | Version pinning, selection, revocation and fencing logic exercised by tests | Actual old/new deployed worker inventory, drain and rollback |
| Provider actions | Synthetic provider and fault-injection tests | Ledger transitions, idempotency boundaries and unknown-outcome handling in code | Gmail/Graph provider-side acceptance and reconciliation |
| Monitoring / rollback | Exporter, health-gate and rollback tests | Schema/contract and rollback-state invariants | Live metric receiver, delivered alert, or operated rollback drill |

The current CI already runs many of these suites. Do not add a second always-on workflow that merely repeats them. Use exact-head CI evidence from PR #663 and existing CI artifacts.

## 3. Provider reconciliation safety

Real Google and Microsoft action tests are consequential external actions. They require:

- explicitly authorized staging OAuth connections;
- a test recipient/account controlled by the operator;
- secrets stored only in GitHub Environment secrets or the provider's approved secret store;
- the existing exact-preview approval gate;
- independent inspection of provider-side state after an uncertain response;
- cleanup of synthetic events/messages where supported.

No live email or calendar mutation is authorized by this zero-budget infrastructure request. Keep live provider evidence `BLOCKED_EXTERNAL` until a separate operator authorization and safe test identity are supplied. Do not mark provider reconciliation passed based on fake adapters or local tests.

## 4. Monitoring and rollback

Run repository tests for the OpenMetrics exporter, cohort health gate, rollback completion, recovery verification, and flag rollback. These remain code-level evidence.

Live qualification still requires an operated staging deployment with:

1. an identified metric receiver and successful ingestion;
2. an alert rule and a verified alert delivery path;
3. a recorded pre-rollback deployment and capability manifest;
4. a controlled stop/rollback;
5. evidence that capabilities are disabled and in-flight work is drained/reconciled;
6. a fresh post-rollback health observation tied to the exact deployment revision.

Do not use screenshots of configuration or a passing unit test as evidence that an alert was delivered or rollback was operated.

## 5. Emergency action order

1. **Render data preservation:** submit a support request immediately, asking for a no-cost courtesy restore/export before the grace deadline. Do not delete or replace the database.
2. **Supabase verification:** in the dashboard, verify the existing free project is reachable and inspect its database schema/migration history. Do not reset credentials or run migrations until the operator understands which services depend on its database password.
3. **Repository CI repair:** review PR #663; require exact-head CI and independent review. Do not merge based only on a green subset.
4. **Free staging substitute:** only after Supabase access and schema compatibility are verified, decide whether the existing free Supabase project can host a temporary Coworker test database. This requires an explicit migration plan, a separate schema/database boundary, and a verified backup first.
5. **No permanent free-worker claim:** GitHub Actions jobs are ephemeral. Neon Free (if manually created by the owner) can provide a small scale-to-zero PostgreSQL database, but it is not a persistent worker or a replacement for a durable Temporal deployment.
6. **Live evidence remains open:** use only authorized staging identities and explicit operator consent for real provider actions.

## 6. Hard prohibitions

- No Render plan upgrade, paid worker, database creation, or Key Value provisioning.
- No new Supabase project or development branch that could incur charges.
- No production deployment, capability activation, or external provider mutation.
- No migration from Render to Supabase/Neon without a verified source export, target backup, compatibility review, and cutover/rollback plan.
- No claim of database preservation until a verified export or restored copy exists.

## Completion status

This runbook establishes a safe zero-budget recovery strategy. It does **not** complete live operational qualification. Current blockers are the inaccessible Render Free database, unverified Supabase data-plane access, missing live staging workers, absent real provider observations, live alert/rollback evidence, and native GitHub main protection.
