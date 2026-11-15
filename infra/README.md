# Local deployment

Run the full MVP stack with:

```bash
docker compose -f infra/docker-compose.yml up --build
```

Services:
- Web app: http://localhost:3000
- API gateway: http://localhost:4000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

For local development without containers, copy `.env.example`, run `npm install`, then run `npm run dev`.

## Coworker staging on Supabase

The Render staging API and worker use the PostgreSQL session pooler for the
`shuddho-staging` Supabase project. Use the connection settings from that
project's Connect panel with the `shuddho_staging_runtime` login, project
reference in the username and port 5432. Set `sslmode=verify-full` and
`sslrootcert=infra/supabase-root-2021.pem` from the repository root. The
public CA is published through Supabase Database Settings and its SHA-256
certificate fingerprint is
`80:70:25:AD:50:D4:ED:21:9D:2C:9C:7D:29:9C:00:4F:82:4E:B0:0C:F7:F6:5A:FE:F6:07:D0:7B:72:E6:CA:FA`.
Refresh it from Supabase when the provider rotates its CA.

Store the runtime URL as `SHUDDHO_COWORKER_DATABASE_URL` on the Render staging
services, `PA10_STAGING_DATABASE_URL` in GitHub's `pa10-staging` environment, and
`SHUDDHO_STAGING_DATABASE_URL` in GitHub's `staging` environment for CW-11.
Keep the schema owner credential in the operator's secret store.

Before deploying a release with a new Alembic revision, run
`uv run --extra coworker python -m services.coworker.migrate` once using the
schema-owner URL. The API startup and worker pre-deploy checks use
`python -m services.coworker.migrate --check` with the runtime URL and reject an
out-of-date database. The runtime role can read and write Coworker data but
cannot change the schema or migration history. The `shuddho_coworker` schema is
private and should stay outside the Supabase Data API.

### Authorize the GitHub ruleset audit

Install a dedicated GitHub App on `rumman52/Shuddho` only. Give it repository
**Administration: Read and write** because GitHub only returns the ruleset's
`bypass_actors` field to an identity with write access to that ruleset. Keep the
app itself off the ruleset's bypass list.

The app is used in two protected GitHub Actions environments, both restricted
to the `main` branch and protected by required reviewers:

- `v01-governance`: main-push governance audit and the PA-10 preflight's
  pre-credential ruleset audit.
- `pa10-staging`: repeat the same audit after environment approval and
  immediately before staging database access or Render/provider mutations.

Configure the same app identity in **both** environments:

- Environment variable `V01_RULESET_APP_CLIENT_ID`: the app's client ID.
- Environment secret `V01_RULESET_APP_PRIVATE_KEY`: the app's private key.

The composite audit action mints a temporary installation token scoped to the
single `Shuddho` repository. It uses that token for the protected-branch
revalidation and the sensitive ruleset detail (including bypass-actor) read,
then revokes it after the job. The ordinary workflow token is used only for CI
run/job reads. The unprivileged source-gate checks the exact `main` SHA and
successful CI; the privileged audit is the authority for the native protection
state. Post-approval audits prevent a stale approval from releasing staging
credentials after the ruleset or branch state changes.

After configuring both environments, confirm `governance-audit` passes on the
current `main` push, then run **PA-10 staging prerequisite preflight**. Do not
run the worker-provision workflow without separate explicit approval for its
paid Render plan.

### Back up and verify the staging database

Run from the repository root as a non-root operator with PostgreSQL 17 or
newer client and server tools. Load the staging runtime DSN from your secret
store into `SHUDDHO_COWORKER_DATABASE_URL`.

```bash
uv run --extra coworker python -m scripts.staging_postgres_backup \
  --pg-bin /usr/lib/postgresql/17/bin \
  --directory /secure/private-backups/shuddho-staging-2026-11-15
```

The command takes a read-only, consistent snapshot of `shuddho_coworker`,
writes `coworker.dump`, and restores it into a disposable local cluster with
no TCP listener. It writes `verification.json` after checking the migration
revision, row counts and row hashes against that same snapshot. The archive
and receipt stay in the new private directory. If the restore fails, the
completed archive is retained for diagnosis.

This verifies the database archive only. Use the
[controlled staging recovery drill](../docs/CONTROLLED_STAGING_BACKUP_RESTORE.md)
to verify private object bytes and release-bound recovery. A new hosted
restore also requires provisioning its staging runtime role and grants.
The free Supabase plan does not include daily managed backups.
