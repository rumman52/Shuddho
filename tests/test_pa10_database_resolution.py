"""Exercise the database admission check at the staging workflow entry point."""

import subprocess
import sys

import pytest

from scripts.staging_prerequisite_preflight import PreflightFailure, _validate_postgresql_url
from services.coworker.migrate import upgrade


STAGING_URL = (
    "postgresql+psycopg://shuddho_staging_runtime.bsmbvjenpvcyfjzwtuax:fixture-secret"
    "@aws-0-us-west-1.pooler.supabase.com:5432/postgres"
    "?sslmode=verify-full&sslrootcert=system"
)


def test_staging_database_accepts_bound_runtime_session():
    _validate_postgresql_url(STAGING_URL)


@pytest.mark.parametrize("url", [
    "",
    STAGING_URL.replace("bsmbvjenpvcyfjzwtuax", "wrong_project"),
    STAGING_URL.replace("shuddho_staging_runtime.", "postgres."),
    STAGING_URL.replace("aws-0-us-west-1.pooler.supabase.com", "wrong.example"),
    STAGING_URL.replace(":5432", ":6543"),
    STAGING_URL.replace("verify-full", "require"),
    STAGING_URL + "&host=wrong.example",
    STAGING_URL + "&sslmode=disable",
])
def test_staging_database_rejects_wrong_project_role_or_connection_mode(url):
    with pytest.raises(PreflightFailure, match="SHUDDHO_COWORKER_DATABASE_URL") as error:
        _validate_postgresql_url(url)
    assert "fixture-secret" not in str(error.value)


def test_readiness_requires_migration_head_and_can_repeat_without_writing(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'runtime.sqlite3'}"
    monkeypatch.setenv("SHUDDHO_COWORKER_DATABASE_URL", url)
    command = [sys.executable, "-m", "services.coworker.migrate", "--check"]
    stale = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert stale.returncode == 1
    assert "not at the required migration revision" in stale.stderr

    upgrade(url)
    current = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert current.returncode == 0, current.stderr
    assert "migration revision verified" in current.stdout
    repeated = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert repeated.returncode == 0, repeated.stderr
