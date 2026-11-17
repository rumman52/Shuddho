import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import staging_postgres_backup as backup


SOURCE = (
    "postgresql+psycopg://shuddho_staging_runtime.bsmbvjenpvcyfjzwtuax:fixture-password"
    "@aws-0-us-west-1.pooler.supabase.com:5432/postgres"
    "?sslmode=verify-full&sslrootcert=infra/supabase-root-2021.pem"
)


def test_invalid_host_or_existing_archive_directory_stops_before_postgres(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    with patch.object(backup, "dump_source") as dump:
        with pytest.raises(backup.BackupError, match="staging Supabase"):
            backup.run_backup(SOURCE.replace("bsmbvjenpvcyfjzwtuax", "other"), tmp_path / "output")
        with pytest.raises(backup.BackupError, match="output directory"):
            backup.run_backup(SOURCE, existing)
        dump.assert_not_called()
    assert not (tmp_path / "output").exists()


def test_verification_receipt_requires_identical_row_inventory(tmp_path):
    source = {"revision": "0070", "tables": {"cw_accounts": {"rows": 1, "sha256": "first"}}}
    restored = {"revision": "0070", "tables": {"cw_accounts": {"rows": 1, "sha256": "different"}}}

    def dump(_url, path, _pg_bin):
        path.write_bytes(b"PGDMP-test")
        return source

    destination = tmp_path / "mismatch"
    with patch.object(backup, "dump_source", side_effect=dump):
        with patch.object(backup, "restore_inventory", return_value=restored):
            with pytest.raises(backup.BackupError, match="differ"):
                backup.run_backup(SOURCE, destination)
    assert (destination / "coworker.dump").is_file()
    assert not (destination / "verification.json").exists()

    destination = tmp_path / "passed"
    with patch.object(backup, "dump_source", side_effect=dump):
        with patch.object(backup, "restore_inventory", return_value=source):
            receipt = backup.run_backup(SOURCE, destination)
    assert receipt["status"] == "verified"
    assert receipt["source"] == source
    alignment = receipt["schema_alignment"]
    assert alignment["status"] == "migration_required"
    assert alignment["source_revision"] == "0070"
    assert alignment["code_head"] == "0072_merge_0071_heads"
    assert alignment["pending_migrations"] == [
        "0071", "0071_project_scoped_goals", "0072_merge_0071_heads",
    ]
    assert alignment["source_is_current"] is False
    assert alignment["release_qualified"] is False
    assert receipt["archive_sha256"] == backup.file_hash(destination / "coworker.dump")
    assert (destination / "verification.json").stat().st_mode & 0o777 == 0o600
    assert (destination / "coworker.dump").stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_mode & 0o777 == 0o700



def test_broken_checked_in_migration_graph_never_converts_backup_into_release_evidence(tmp_path):
    source = {"revision": "0070", "tables": {"cw_accounts": {"rows": 0, "sha256": "fixture"}}}

    def dump(_url, path, _pg_bin):
        path.write_bytes(b"PGDMP-synthetic")
        return source

    output = tmp_path / "verified-older-schema"
    with patch.object(backup, "dump_source", side_effect=dump), \
         patch.object(backup, "restore_inventory", return_value=source), \
         patch.object(backup, "source_schema_alignment", side_effect=backup.MigrationAlignmentError("untrusted graph")):
        receipt = backup.run_backup(SOURCE, output)

    assert receipt["status"] == "verified"
    assert receipt["source"] == source
    assert receipt["schema_alignment"] == {
        "status": "migration_graph_unverified",
        "source_revision": "0070",
        "code_head": None,
        "source_is_current": False,
        "pending_migrations": None,
        "release_qualified": False,
    }
    assert (output / "coworker.dump").exists()
    assert (output / "verification.json").exists()

def test_postgres_subprocess_hides_connection_secrets_and_output(monkeypatch, tmp_path):
    monkeypatch.setenv("PGHOST", "unrelated.example")
    monkeypatch.setenv("PGPASSWORD", "unrelated-password")
    monkeypatch.setenv("SHUDDHO_COWORKER_DATABASE_URL", SOURCE)
    with patch.object(backup.subprocess, "run") as run:
        run.return_value.returncode = 1
        run.return_value.stderr = SOURCE
        with pytest.raises(backup.BackupError, match="pg_dump failed") as error:
            backup.run_pg(None, "pg_dump", "--file", str(tmp_path / "backup.dump"), db_env={"PGHOST": "staging"})
    argv = run.call_args.args[0]
    env = run.call_args.kwargs["env"]
    assert "fixture-password" not in " ".join(argv)
    assert "fixture-password" not in str(error.value)
    assert env["PGHOST"] == "staging"
    assert "PGPASSWORD" not in env and "SHUDDHO_COWORKER_DATABASE_URL" not in env


def test_custom_archive_restores_the_same_rows_on_a_disposable_postgres(tmp_path):
    pg_bin = os.getenv("SHUDDHO_TEST_PG_BIN")
    if not pg_bin:
        pytest.skip("Set SHUDDHO_TEST_PG_BIN to a PostgreSQL bin directory")
    import psycopg

    archive = tmp_path / "sample.dump"
    with backup.isolated_postgres(Path(pg_bin)) as db_env:
        connect = dict(
            host=db_env["PGHOST"], port=db_env["PGPORT"], user=db_env["PGUSER"],
            dbname=db_env["PGDATABASE"], sslmode="disable",
        )
        with psycopg.connect(**connect) as fixture:
            fixture.execute("CREATE SCHEMA shuddho_coworker")
            fixture.execute("CREATE SCHEMA unrelated")
            fixture.execute("CREATE TABLE unrelated.other_account (id integer)")
            fixture.execute("CREATE TABLE shuddho_coworker.cw_alembic_version (version_num text)")
            fixture.execute("INSERT INTO shuddho_coworker.cw_alembic_version VALUES ('0070')")
            fixture.execute("CREATE TABLE shuddho_coworker.cw_accounts (id int primary key, label text)")
            fixture.execute("INSERT INTO shuddho_coworker.cw_accounts VALUES (2, 'বাংলা'), (1, E'with\\nnew line')")
            fixture.execute(
                "CREATE TABLE shuddho_coworker.cw_conversations "
                "(id int PRIMARY KEY, owner_id int REFERENCES shuddho_coworker.cw_accounts)"
            )
            fixture.execute("INSERT INTO shuddho_coworker.cw_conversations VALUES (1, 2)")
        run_pg = backup.run_pg

        def update_before_dump(pg_tools, command, *args, **kwargs):
            if command == "pg_dump":
                with psycopg.connect(**connect) as concurrent:
                    concurrent.execute("UPDATE shuddho_coworker.cw_accounts SET label = 'replacement'")
            return run_pg(pg_tools, command, *args, **kwargs)

        with psycopg.connect(**connect) as source, patch.object(backup, "run_pg", side_effect=update_before_dump):
            expected = backup.dump_snapshot(source, db_env, archive, Path(pg_bin), expected_user=db_env["PGUSER"])
        assert backup.restore_inventory(archive, Path(pg_bin)) == expected
    archive_objects = subprocess.check_output([str(Path(pg_bin) / "pg_restore"), "--list", str(archive)], text=True)
    assert "other_account" not in archive_objects and "unrelated" not in archive_objects
    assert "TABLE shuddho_coworker cw_accounts" in archive_objects
    assert expected["tables"]["cw_accounts"]["rows"] == 2
    assert expected["tables"]["cw_conversations"]["rows"] == 1


def test_private_schema_access_rejects_supabase_api_role_grants():
    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self, row):
            self.row = row

        def execute(self, statement, params):
            assert "pg_default_acl" in statement
            assert "pg_has_role" in statement
            assert params == (backup.SCHEMA,)
            return Result(self.row)

    safe = backup.private_schema_access(Connection((False, False, 0, 0, False, False, 84)))
    assert safe["anon_schema_access"] is False
    assert safe["authenticated_schema_access"] is False
    assert safe["anon_table_privilege_count"] == 0
    assert safe["authenticated_table_privilege_count"] == 0
    assert safe["anon_default_table_privileges"] is False
    assert safe["authenticated_default_table_privileges"] is False
    # Private-schema access is the security boundary; RLS is reported, not
    # blindly enabled or required for this private, ungranted schema.
    assert safe["rls_enabled_table_count"] == 84


@pytest.mark.parametrize("row", [
    (True, False, 0, 0, False, False, 0),
    (False, True, 0, 0, False, False, 0),
    (False, False, 1, 0, False, False, 0),
    (False, False, 0, 1, False, False, 0),
    (False, False, 0, 0, True, False, 0),
    (False, False, 0, 0, False, True, 0),
])
def test_private_schema_access_fails_closed_on_any_api_role_grant(row):
    class Result:
        def fetchone(self):
            return row

    class Connection:
        def execute(self, statement, params):
            return Result()

    with pytest.raises(backup.BackupError, match="Supabase API roles"):
        backup.private_schema_access(Connection())


def test_inventory_detects_real_schema_table_and_default_grants():
    pg_bin = os.getenv("SHUDDHO_TEST_PG_BIN")
    if not pg_bin:
        pytest.skip("Set SHUDDHO_TEST_PG_BIN to a PostgreSQL bin directory")
    import psycopg

    with backup.isolated_postgres(Path(pg_bin)) as db_env:
        connect = dict(
            host=db_env["PGHOST"], port=db_env["PGPORT"], user=db_env["PGUSER"],
            dbname=db_env["PGDATABASE"], sslmode="disable",
        )
        with psycopg.connect(**connect) as fixture:
            fixture.execute("CREATE ROLE anon NOLOGIN")
            fixture.execute("CREATE ROLE authenticated NOLOGIN")
            fixture.execute("CREATE SCHEMA shuddho_coworker")
            fixture.execute(
                "CREATE TABLE shuddho_coworker.cw_alembic_version (version_num text)"
            )
            fixture.execute("INSERT INTO shuddho_coworker.cw_alembic_version VALUES ('0070')")
            fixture.execute("GRANT USAGE ON SCHEMA shuddho_coworker TO anon")
            fixture.execute(
                "GRANT SELECT ON shuddho_coworker.cw_alembic_version TO authenticated"
            )
            fixture.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA shuddho_coworker "
                "GRANT SELECT ON TABLES TO anon"
            )
            fixture.execute(
                "ALTER DEFAULT PRIVILEGES GRANT INSERT ON TABLES TO authenticated"
            )
            with pytest.raises(backup.BackupError, match="Supabase API roles"):
                backup.inventory(fixture)

@pytest.mark.parametrize(
    ("api_role", "membership_options"),
    [
        ("anon", "INHERIT TRUE, SET TRUE"),
        ("authenticated", "INHERIT FALSE, SET TRUE"),
    ],
)
def test_inventory_detects_inherited_default_privileges(api_role, membership_options):
    pg_bin = os.getenv("SHUDDHO_TEST_PG_BIN")
    if not pg_bin:
        pytest.skip("Set SHUDDHO_TEST_PG_BIN to a PostgreSQL bin directory")
    import psycopg

    grant_role = f"{api_role}_table_reader"
    with backup.isolated_postgres(Path(pg_bin)) as db_env:
        connect = dict(
            host=db_env["PGHOST"], port=db_env["PGPORT"], user=db_env["PGUSER"],
            dbname=db_env["PGDATABASE"], sslmode="disable",
        )
        with psycopg.connect(**connect) as fixture:
            fixture.execute("CREATE ROLE anon NOLOGIN")
            fixture.execute("CREATE ROLE authenticated NOLOGIN")
            fixture.execute(f"CREATE ROLE {grant_role} NOLOGIN")
            fixture.execute(
                f"GRANT {grant_role} TO {api_role} WITH {membership_options}"
            )
            fixture.execute("CREATE SCHEMA shuddho_coworker")
            fixture.execute(
                "CREATE TABLE shuddho_coworker.cw_alembic_version (version_num text)"
            )
            fixture.execute("INSERT INTO shuddho_coworker.cw_alembic_version VALUES ('0070')")
            fixture.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA shuddho_coworker "
                f"GRANT SELECT ON TABLES TO {grant_role}"
            )
            with pytest.raises(backup.BackupError, match="Supabase API roles"):
                backup.inventory(fixture)

def test_inventory_detects_public_default_privileges():
    pg_bin = os.getenv("SHUDDHO_TEST_PG_BIN")
    if not pg_bin:
        pytest.skip("Set SHUDDHO_TEST_PG_BIN to a PostgreSQL bin directory")
    import psycopg

    with backup.isolated_postgres(Path(pg_bin)) as db_env:
        connect = dict(
            host=db_env["PGHOST"], port=db_env["PGPORT"], user=db_env["PGUSER"],
            dbname=db_env["PGDATABASE"], sslmode="disable",
        )
        with psycopg.connect(**connect) as fixture:
            fixture.execute("CREATE ROLE anon NOLOGIN")
            fixture.execute("CREATE ROLE authenticated NOLOGIN")
            fixture.execute("CREATE SCHEMA shuddho_coworker")
            fixture.execute(
                "CREATE TABLE shuddho_coworker.cw_alembic_version (version_num text)"
            )
            fixture.execute("INSERT INTO shuddho_coworker.cw_alembic_version VALUES ('0070')")
            # PUBLIC receives the privilege on future tables; no current table
            # grant exists for the API roles to reveal this through has_table_privilege.
            fixture.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA shuddho_coworker "
                "GRANT SELECT ON TABLES TO PUBLIC"
            )
            with pytest.raises(backup.BackupError, match="Supabase API roles"):
                backup.inventory(fixture)
