"""Exercise real EXPLAIN on a fresh migrated disposable database.

The small synthetic seed is a collector smoke test, not a representative load.
"""
import json
import os
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("psycopg")
pytest.importorskip("alembic")
pytestmark = [
    pytest.mark.coworker_integration,
    pytest.mark.skipif(
        not os.getenv("SHUDDHO_TEST_POSTGRES_URL"),
        reason="Requires disposable PostgreSQL CI service",
    ),
]

from sqlalchemy import text

from scripts.day8_fk_plan_evidence import FINDINGS, collect, connection_parameters
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.migrate import upgrade
from services.coworker.repository import Repository
from services.coworker.schemas import TaskCreate
from test_day2_dual_0071_postgres import _disposable_database


def test_fk_plans_use_real_explain_and_preserve_unmeasured_findings(record_property):
    # Reject a remote or non-test database before invoking the existing
    # isolated database fixture (which creates/drops only a random child DB).
    connection_parameters(os.environ["SHUDDHO_TEST_POSTGRES_URL"])
    with _disposable_database() as url:
        upgrade(url)
        settings = Settings(
            database_url=url,
            auth_issuer="https://identity.example.test/auth/v1",
            environment="development",
            storage_backend="local",
        )
        repository = Repository(session_factory(url), settings)
        synthetic_values = []
        try:
            for _ in range(2):
                subject = "day8-fk-synthetic-" + uuid4().hex
                owner = repository.ensure_account(
                    Principal(settings.auth_issuer, subject, 9999999999)
                )["account_id"]
                synthetic_values.extend((subject, owner))
                for _ in range(2):
                    task, _created = repository.create_task(
                        owner, TaskCreate(instruction="Synthetic FK smoke fixture", notes="No real data"),
                        str(uuid4()),
                    )
                    synthetic_values.append(task["id"])
            with repository.sessions.begin() as db:
                synthetic_values.extend(db.scalars(text("SELECT id FROM cw_workspaces")).all())
                db.execute(text("ANALYZE shuddho_coworker.cw_tasks"))
        finally:
            repository.sessions.kw["bind"].dispose()

        report = collect(url)
        encoded = json.dumps(report, sort_keys=True, allow_nan=False)
        record_property("day8_fk_plan_evidence", encoded)
        assert report["finding_count"] == 32
        assert {(row["table"], row["constraint"]) for row in report["findings"]} == set(FINDINGS)
        assert report["index_changes_authorized"] is False
        assert not any(value in encoded for value in synthetic_values)
        assert not any(row["status"] in {"unavailable_query_error", "unavailable_invalid_plan"} for row in report["findings"])
        tasks = next(row for row in report["findings"] if row["table"] == "cw_tasks")
        assert tasks["status"] == "measured"
        assert tasks["columns"] == ["workspace_id"]
        assert tasks["measurement"]["actual_rows"] == 2
        assert report["measured_count"] >= 1
        unavailable = [row for row in report["findings"] if row["status"] != "measured"]
        assert unavailable  # Most fixture tables intentionally contain no rows.
        assert all("measurement" not in row for row in unavailable)
