# Day 1 — staging migration identity readback (source-only safety gate)

Issue: [#727](https://github.com/rumman52/Shuddho/issues/727), Task 6. This check is an **additional read-only diagnostic**, not a migration runner, backup, restore receipt or staging qualification. It does not replace `scripts/staging_postgres_backup.py`, the private-schema privilege audit or `scripts/staging_day2_acceptance.py`.

## Observed blocker, 18 November 2026

Read-only Supabase SQL returned a private schema with **84 tables** and staging Alembic revision **0070** on PostgreSQL **17.11**. At the time of the inspection, checked-in migration history had a single head, **0072_merge_0071_heads**, combining both distinct branches **0071** and **0071_project_scoped_goals**.

This is a **schema identity mismatch**, not authorization to execute either migration. No DDL, credentials, real customer data, paid resources or environment settings were changed by the readback. Never mark the Day 1 or Day 2 milestone complete from this status.

## Produce an independently authenticated readback

The staging operator uses the **approved read-only Supabase SQL interface**, on the exact authorized staging project. Verify the project ref, authenticated account, origin and query execution time separately. Do not run this through production, use an arbitrary connection URL, include credentials in a receipt, or publish sensitive table contents.

The following query is **SELECT only**. Substitute the approved non-secret project ref *in the query or local envelope* only after checking it against the connected project inventory:

```sql
SELECT
  version_num AS revision,
  current_setting('server_version') AS postgres_version,
  (SELECT count(*)::int FROM pg_catalog.pg_tables
    WHERE schemaname = 'shuddho_coworker') AS private_table_count,
  to_char(clock_timestamp() AT TIME ZONE 'UTC',
    'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS observed_at
FROM shuddho_coworker.cw_alembic_version;
```

The query must return **one** row. In an independently permissioned location **outside the repository**, prepare a JSON envelope with *exactly* these six non-secret fields, taking values directly from that one SQL readback: `project_ref`, `schema` (exactly `shuddho_coworker`), `revision`, `private_table_count`, `postgres_version`, and `observed_at`. The last value must be a timezone-aware ISO-8601 string not older than 24 hours. Do not construct values from source defaults.

Run the diagnostic on the exact intended Git commit:

```bash
uv run python -m scripts.day1_staging_migration_drift \
  --readback /secure/operator/day1/staging-schema-readback.json \
  --project-ref <approved-staging-project-ref> \
  --source-revision "$(git rev-parse HEAD)"
```

Exit **2** means malformed/ambiguous evidence, wrong identity, unknown revision, or pending migrations. Exit **0** means only that the **reported** staging revision equals the checked-out source head. In both cases `staging_qualified=false`, `deployment_authorized=false`, and `migration_authorized=false` by design. Readback authenticity must be independently checked; locally supplied JSON is not a cryptographic or administrative attestation.

The `pending_revisions` array is a **source DAG difference**, not an executable migration plan. From revision `0070` it must account for **both** distinct `0071` branches and then the merge revision `0072_merge_0071_heads`. Alembic must choose an authorized dependency-correct sequence; this script never invokes `alembic upgrade`.

## Blockers before attempting a staging migration

An authorized staging owner and independent reviewer must approve the exact candidate and maintenance boundary; perform and independently verify a **private-schema backup and isolated restore** with `scripts/staging_postgres_backup.py`; reconcile the current staging API/worker image SHAs and rollout manifest; then run the reviewed Alembic migration procedure under an approved database identity. Recheck source/readback alignment, cross-owner isolation, worker restart, and artifact retrieval afterward. Keep production and high-authority capability flags disabled throughout.

Regression coverage: `uv run pytest -q tests/test_day1_staging_migration_drift.py tests/test_coworker_migration_graph.py`. The tests use synthetic envelopes and do not read or modify the connected staging database.
