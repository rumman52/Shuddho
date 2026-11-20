"""Offline Day 2: exercise both 0071 parents on separate disposable PostgreSQL databases.

These are *not* restored Supabase staging copies and do not authorize live DDL.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest

pytest.importorskip("sqlalchemy", reason="Install coworker extra for PostgreSQL migration rehearsal")
pytest.importorskip("alembic", reason="Install coworker extra for PostgreSQL migration rehearsal")
pytest.importorskip("psycopg", reason="Install coworker extra for PostgreSQL migration rehearsal")

import psycopg
from psycopg import sql
from alembic import command
from sqlalchemy.engine import make_url

from scripts.staging_postgres_backup import inventory
from services.coworker.migrate import (
    DatabaseReadinessError,
    check as check_current_revision,
    migration_config,
)

pytestmark = [
    pytest.mark.coworker_integration,
    pytest.mark.skipif(
        not os.getenv("SHUDDHO_TEST_POSTGRES_URL"),
        reason="Requires the disposable PostgreSQL 18 CI service",
    ),
]

MERGE = "0072_merge_0071_heads"
PARENTS = ("0071", "0071_project_scoped_goals")
NEW_COLUMNS = {
    ("cw_agent_runs", "planner_input_tokens"),
    ("cw_agent_runs", "planner_output_tokens"),
    ("cw_model_attempts", "input_tokens"),
    ("cw_model_attempts", "output_tokens"),
    ("cw_personal_goals", "project_id"),
}
INDEX = "cw_personal_goals_owner_project_state"
FK = "fk_cw_personal_goals_project_owner"


def _psycopg_url(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextmanager
def _disposable_database():
    """Each branch gets its own database, never an existing schema in place."""
    root_url = make_url(os.environ["SHUDDHO_TEST_POSTGRES_URL"])
    db_name = "day2_dual_0071_" + uuid.uuid4().hex[:20]
    admin_dsn = _psycopg_url(root_url.render_as_string(hide_password=False))
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    try:
        yield root_url.set(database=db_name).render_as_string(hide_password=False)
    finally:
        # CI's disposable PostgreSQL user is the docker service's administrator.
        # FORCE releases any accidentally retained pooled test connections.
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name))
            )


def _readback(url: str) -> tuple[dict, set[tuple[str, str]], set[str], set[str]]:
    with psycopg.connect(_psycopg_url(url)) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        manifest = inventory(db)
        cols = {
            (table, column)
            for table, column in db.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'shuddho_coworker'"
            ).fetchall()
        }
        indexes = {
            name for (name,) in db.execute(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'shuddho_coworker'"
            ).fetchall()
        }
        constraints = {
            name for (name,) in db.execute(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace = 'shuddho_coworker'::regnamespace"
            ).fetchall()
        }
        return manifest, cols, indexes, constraints


def _data_only(snapshot: dict) -> dict:
    """Only the Alembic revision row is expected to change across DDL."""
    return {
        name: summary for name, summary in snapshot["tables"].items()
        if name != "cw_alembic_version"
    }


def _seed_synthetic_account(url: str) -> tuple[str, str, str]:
    sample = (
        "day2-test-" + uuid.uuid4().hex,
        "https://synthetic.identity.example.test/auth/v1",
        "day2-local-only",
    )
    with psycopg.connect(_psycopg_url(url)) as db:
        db.execute(
            "INSERT INTO shuddho_coworker.cw_accounts "
            "(id, issuer, subject, storage_bytes, preferences, created_at) "
            "VALUES (%s, %s, %s, 0, '{}'::json, now())",
            sample,
        )
    return sample


def _old_reader(url: str, expected_account: tuple[str, str, str]) -> None:
    with psycopg.connect(_psycopg_url(url)) as db:
        rows = db.execute(
            "SELECT id, issuer, subject FROM shuddho_coworker.cw_accounts"
        ).fetchall()
        assert rows == [expected_account], "Legacy account reader changed across migration"


@pytest.mark.parametrize("first_parent", PARENTS)
def test_dual_0071_first_parent_upgrade_merge_rollback_and_replay(first_parent):
    with _disposable_database() as url:
        config = migration_config(url)
        command.upgrade(config, "0070")
        sample = _seed_synthetic_account(url)
        baseline, initial_columns, initial_indexes, initial_constraints = _readback(url)
        assert baseline["revision"] == "0070"
        assert baseline["tables"]["cw_accounts"]["rows"] == 1
        assert not (NEW_COLUMNS & initial_columns)
        assert INDEX not in initial_indexes and FK not in initial_constraints

        # Both migrations really execute, starting from *different* parents.
        command.upgrade(config, first_parent)
        single, columns, indexes, constraints = _readback(url)
        assert single["revision"] == first_parent
        assert _data_only(single) == _data_only(baseline)
        if first_parent == "0071":
            assert NEW_COLUMNS - {("cw_personal_goals", "project_id")} <= columns
            assert ("cw_personal_goals", "project_id") not in columns
            assert INDEX not in indexes and FK not in constraints
        else:
            assert ("cw_personal_goals", "project_id") in columns
            assert INDEX in indexes and FK in constraints
            assert ("cw_agent_runs", "planner_input_tokens") not in columns
        _old_reader(url, sample)

        command.upgrade(config, "head")
        merged, columns, indexes, constraints = _readback(url)
        assert merged["revision"] == MERGE
        assert NEW_COLUMNS <= columns
        assert INDEX in indexes and FK in constraints
        assert _data_only(merged) == _data_only(baseline)
        check_current_revision(url)
        _old_reader(url, sample)

        # Idempotent replay must not duplicate data or change the ledger.
        command.upgrade(config, "head")
        assert _readback(url)[0] == merged

        command.downgrade(config, "0070")
        rolled_back, columns, indexes, constraints = _readback(url)
        assert rolled_back["revision"] == "0070"
        assert _data_only(rolled_back) == _data_only(baseline)
        assert not (NEW_COLUMNS & columns)
        assert INDEX not in indexes and FK not in constraints
        with pytest.raises(DatabaseReadinessError, match="migration revision"):
            check_current_revision(url)
        _old_reader(url, sample)

        command.upgrade(config, "head")
        replayed, columns, indexes, constraints = _readback(url)
        assert replayed == merged
        assert NEW_COLUMNS <= columns
        assert INDEX in indexes and FK in constraints
        check_current_revision(url)
        _old_reader(url, sample)


@pytest.mark.parametrize("unsafe_url", [
    "postgresql+psycopg://example:pw@aws-0-us-west-1.pooler.supabase.com:5432/shuddho_coworker_test",
    "postgresql+psycopg://example:pw@localhost:5432/postgres",
    "postgresql+psycopg://example:pw@127.0.0.2:5432/shuddho_coworker_test",
    "postgresql+psycopg://example:pw@localhost:5432/shuddho_coworker_prod",
    "sqlite:////tmp/shuddho_coworker_test",
])
def test_rehearsal_rejects_nonlocal_or_non_test_urls_before_opening_database(monkeypatch, unsafe_url):
    monkeypatch.setenv("SHUDDHO_TEST_POSTGRES_URL", unsafe_url)
    monkeypatch.setattr(
        psycopg, "connect",
        lambda *_args, **_kwargs: pytest.fail("A database connection was attempted"),
    )
    with pytest.raises(RuntimeError, match="disposable loopback"):
        with _disposable_database():
            pytest.fail("Unsafe database URL was accepted")
