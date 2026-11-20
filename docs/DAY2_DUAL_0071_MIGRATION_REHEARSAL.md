# Day 2: local PostgreSQL dual-0071 migration rehearsal

The Part 02 Day 2 execution prompt requires C to rehearse **both** paths
`0070 → 0071 → 0072_merge_0071_heads` and
`0070 → 0071_project_scoped_goals → 0072_merge_0071_heads`
on **separate disposable copies**, with old-reader compatibility, row
counts/digests, rollback and replay. The new tests are a **local synthetic
PostgreSQL 18 compatibility rehearsal only**. They are not a migrated,
restored, or authenticated copy of `shuddho-staging` and do not change the
D02.T01 hosted task's acceptance state.

## Run locally

Start a **disposable local PostgreSQL service** whose test administrator
can create and drop temporary databases. Do not point
`SHUDDHO_TEST_POSTGRES_URL` at Supabase or any customer database.
Provisioning such a local test service is separate from Render or Supabase
staging and does not authorize remote access.

```bash
SHUDDHO_TEST_POSTGRES_URL='postgresql+psycopg://LOCAL_TEST_USER:LOCAL_TEST_PASSWORD@127.0.0.1:5432/LOCAL_TEST_DATABASE' \
  uv run --locked --extra coworker pytest tests/test_day2_dual_0071_postgres.py -q -rs
```

The tests generate unique disposable database names, use the real checked-in
Alembic revisions, and drop each database after its rehearsal. Each branch
must prove all of the following before the test passes:

1. The database is genuinely at `0070`, with a synthetic account inserted.
2. Applying *only* the selected parent records exactly that parent and keeps
   every pre-existing table's row count and SHA-256 inventory unchanged,
   excluding the expected `cw_alembic_version` change.
3. Merging reaches `0072_merge_0071_heads`, with both sets of new columns,
   the project/owner composite foreign key and index, the unchanged legacy
   account-reader result and a passing restricted-readiness revision check.
4. Repeating `upgrade head` is idempotent and does not change the inventory.
5. Downgrading to `0070` removes both branches' DDL, preserves seeded data,
   and fails the current-release readiness check as expected.
6. Re-upgrading reaches the identical merged revision and table inventory.

The PostgreSQL 18 CI job runs both parametrized cases and rejects skipped
qualification using a required-module JUnit gate. A test failure is a real
migration-rehearsal failure, not evidence of staging DDL or a deployment.

## What remains before D02.T01 may pass

- Obtain a **read-only original PostgreSQL archive** of the authorized
  Supabase staging `0070` schema and a private object-storage snapshot.
- Restore original data to separate disposable PostgreSQL instances, run
  both migration parents independently on those restored copies, compare
  **actual** source/target per-table inventories and object SHA-256
  manifests, including the migration ledger and post-rollback data.
- Verify runtime `migrate --check` with the actual restricted staging
  identity and independently read the DB revision through the allowed SQL
  channel. Do not run DDL on live staging until backup/restore and
  dated deployment authority are verified.

No paid worker, model call, private test user, infrastructure deployment,
staging mutation or release acceptance is created by this change. The
project still needs the current Founder/C cost-ceiling and authority
decision described in GitHub issue #291 and the Day 2 tracker #728.
