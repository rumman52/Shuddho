# Day 2 dual-parent PostgreSQL migration rehearsal plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Independently execute both 0070 → 0071 Alembic parent paths into 0072 on two disposable PostgreSQL databases and verify rollback/replay preserve baseline data.

**Architecture:** The existing `services.coworker.migrate.migration_config` supplies the actual Alembic revisions. A new integration test provisions isolated databases in the CI-only PostgreSQL 18 service, seeds a non-customer account at 0070, and snapshots private-schema row counts/hashes using `scripts.staging_postgres_backup.inventory`. It exercises each parent first, both heads, head replay, full rollback to 0070, and re-upgrade to head. No remote staging database or credentials are used.

**Tech stack:** Python, pytest, psycopg 3, SQLAlchemy, Alembic, PostgreSQL 18, GitHub Actions.

**Spec:** `02_Rukh_AI_Private_Staging(1).docx`, Part 02, Day 02 / Platform Operation, D02.T01.

## Global constraints

- CI uses a disposable PostgreSQL 18 service with `SHUDDHO_TEST_POSTGRES_URL`; do not contact Supabase or production.
- Rehearse **both** `0071` and `0071_project_scoped_goals` first-parent routes.
- Require the exact merged revision `0072_merge_0071_heads`.
- No privileged staging write, paid provisioning, real model call, worker restart or hosted-acceptance claim.
- Build the test from current repository migrations; no mocked Alembic graph and no fabricated database readback.

## Review focus

- Wrong branch applied first: verify one and only one Alembic revision before merge.
- Missing column, index, or composite foreign key: inspect PostgreSQL catalogs after actual upgrade.
- Data corruption during upgrade/rollback: compare per-table row counts and SHA-256 snapshots excluding only the migration ledger.
- Revision downgrade/replay ambiguity: assert 0070 restored and second upgrade reaches the same merged head.
- CI silently skipping PostgreSQL qualification: add a required-module JUnit gate to the PostgreSQL 18 job.

### Task 1: Add real dual-parent migration integration tests

**Files:** Create `tests/test_day2_dual_0071_postgres.py`.

**Interfaces:** Use `migration_config`, `migrate.check`, `staging_postgres_backup.inventory`, and the CI-only PostgreSQL 18 URL.

- [ ] Create a failing test for each of the two first-parent sequences in a unique disposable local database.
- [ ] Execute real `upgrade("0070")`, seed one synthetic account, and record full private-schema row inventory.
- [ ] Upgrade the selected first parent, verify ledger and schema, merge to head and validate both parents' DDL.
- [ ] Replay head, downgrade to 0070, re-upgrade, and assert unchanged table data hashes/counts.
- [ ] Destroy each disposable database even on failure, and report test outcomes.

### Task 2: Make PostgreSQL 18 qualification mandatory

**Files:** Modify `.github/workflows/ci.yml`.

- [ ] Run new integration file in the PostgreSQL 18 staging compatibility job with `--junitxml`.
- [ ] Require its module through `scripts.mandatory_test_gate` so skipped tests fail the job.
- [ ] Upload a nonsecret JUnit artifact even on test failure.

### Task 3: Document evidence boundary

**Files:** Create `docs/DAY2_DUAL_0071_MIGRATION_REHEARSAL.md`.

- [ ] State the exact local test invocation, what PostgreSQL readbacks prove, and that this is not a restored copy of Supabase staging.
- [ ] List what still blocks hosted D02.T01 and Day 2 exit gate.
- [ ] Open a PR against main and record independently observed CI results and limitations.
