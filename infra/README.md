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

For staging continuity, take a regular private logical dump of
`shuddho_coworker` with PostgreSQL 17+ tooling. Record the archive checksum
and migration revision, and verify a restore into an isolated database
before relying on it. Store the archive in your existing private backup
location. The free Supabase plan does not include daily managed backups.
