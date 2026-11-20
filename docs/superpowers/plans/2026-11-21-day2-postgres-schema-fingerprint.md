# Day 2 restored PostgreSQL schema fingerprint

**Source requirement:** `02_Rukh_AI_Private_Staging.docx`, Part 02 page 2, "Back up then align staging", and exit D02.T09 on page 4. Back up private schema, count rows and hash bytes; restore to an isolated database and compare **schema as well as table counts and digests**.

**Observed gap:** `staging_postgres_backup.inventory()` records migration revision, table names, per-table counts/row SHA and Supabase API-role ACL posture. Both its source/local restoration check and `staging_backup_restore.restored_database_inventory()` compare those fields only. A restored table can have a different column default, missing index, changed constraint or RLS policy while retaining the same rows and revision, yet pass current comparison. This is a structural verification gap, not evidence of a staging restore.

**Design:** Produce a separate `schema_sha256` from canonical read-only `pg_catalog` records in the same REPEATABLE READ snapshot as the row digests. Include relation/partition/RLS metadata, column types/defaults, constraints, indexes, triggers, policies, sequence parameters, routine definitions, and enum/domain metadata. Exclude database-specific object OIDs, owner labels, and inherited ACLs that a deliberately isolated `pg_restore --no-owner --no-privileges` cannot preserve. Hash sorted category + canonical jsonb records to avoid enumeration order variability. Emit only digest in receipts. Treat malformed or missing digest as a failure and require it in downstream Day 2 archive and acceptance receipts. The snapshot cannot prove live cloud authorization, restore ownership, or third-party objects.

## Implementation checklist

- [ ] RED: add disposable-PG fixture test that changes a column default and index while row hashes and Alembic revision remain equal; assert `schema_sha256` changes.
- [ ] RED: reject a PostgreSQL verification receipt with missing/malformed `source.schema_sha256` and a downstream Day 2 acceptance receipt lacking the digest.
- [ ] Verify expected RED CI before implementing code.
- [ ] GREEN: new `scripts/staging_postgres_schema_digest.py` with bounded, sorted, read-only canonical catalog signatures.
- [ ] Extend `staging_postgres_backup.inventory()` to return `schema_sha256`, and `staging_day2_archive_attestation` to validate/report it.
- [ ] Extend `staging_day2_acceptance` to validate the digest without elevating source checks to hosted acceptance.
- [ ] Update fixtures and docs describing column/index/constraint/RLS/trigger/sequence and function coverage; source and restored comparison in the same respective snapshots.
- [ ] Run mandatory no-skips Day 2 tests, PostgreSQL 18 compatibility, Coworker tests, and report exact-head CI results.
- [ ] Open a draft GitHub PR, record source-only result in issue #728 and Linear MD-6, and leave hosted gates blocked absent Founder+C approval for cost/host/credentials/restore targets and independent D evidence.

**Safety/verification:** No production/staging DDL, credential inspection, synthetic account seeding, service deployment, operator restore, model call or paid worker. This is source-only; local disposable PostgreSQL tests are not hosted acceptance.
