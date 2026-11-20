"""Back up the private staging schema and verify it on a disposable PostgreSQL cluster."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import file_digest, sha256
import os
import re
from pathlib import Path
import shlex
import signal
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import unquote, urlsplit

from scripts.staging_prerequisite_preflight import PreflightFailure, _validate_postgresql_url
from scripts.staging_migration_alignment import MigrationAlignmentError, source_schema_alignment
from scripts.staging_release_evidence import write_private_json


SCHEMA = "shuddho_coworker"
SOURCE_ENV = "SHUDDHO_COWORKER_DATABASE_URL"
CERTIFICATE = Path(__file__).resolve().parents[1] / "infra/supabase-root-2021.pem"
RESTORE_USER = "shuddho_restore"
RESTORE_PORT = "55432"


class BackupError(RuntimeError):
    pass


def run_pg(pg_bin: Path | None, command: str, *args: str, db_env: dict[str, str] | None = None) -> None:
    executable = str(pg_bin / command) if pg_bin is not None else command
    env = {
        key: value for key, value in os.environ.items()
        if key in {"PATH", "LANG", "TZ", "LD_LIBRARY_PATH"} or key.startswith("LC_")
    }
    env.update(db_env or {})
    try:
        result = subprocess.run(
            [executable, *args], env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=900,
        )
    except FileNotFoundError:
        raise BackupError(f"{command} is unavailable. Install PostgreSQL client and server tools.") from None
    except subprocess.TimeoutExpired:
        raise BackupError(f"{command} timed out.") from None
    if result.returncode:
        # Connection errors and database errors can contain credentials or row values.
        raise BackupError(f"{command} failed (exit {result.returncode}).")


def private_schema_access(connection) -> dict:
    """Audit database grants for Supabase API roles against the private schema.

    RLS is defense in depth, but it is not a substitute for keeping this schema
    outside the Data API and withholding schema/table grants from anon and
    authenticated. This check is read-only and deliberately does not enable RLS.
    """
    row = connection.execute(
        """
        SELECT
            COALESCE((
                SELECT has_schema_privilege(r.oid, n.oid, 'USAGE')
                    OR has_schema_privilege(r.oid, n.oid, 'CREATE')
                FROM pg_roles AS r WHERE r.rolname = 'anon'
            ), false) AS anon_schema_access,
            COALESCE((
                SELECT has_schema_privilege(r.oid, n.oid, 'USAGE')
                    OR has_schema_privilege(r.oid, n.oid, 'CREATE')
                FROM pg_roles AS r WHERE r.rolname = 'authenticated'
            ), false) AS authenticated_schema_access,
            COALESCE((
                SELECT count(*)::int
                FROM pg_class AS c
                WHERE c.relnamespace = n.oid AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND EXISTS (
                    SELECT 1 FROM pg_roles AS r
                    WHERE r.rolname = 'anon' AND (
                        has_table_privilege(r.oid, c.oid, 'SELECT')
                        OR has_table_privilege(r.oid, c.oid, 'INSERT')
                        OR has_table_privilege(r.oid, c.oid, 'UPDATE')
                        OR has_table_privilege(r.oid, c.oid, 'DELETE')
                        OR has_table_privilege(r.oid, c.oid, 'TRUNCATE')
                        OR has_table_privilege(r.oid, c.oid, 'REFERENCES')
                        OR has_table_privilege(r.oid, c.oid, 'TRIGGER')
                    )
                  )
            ), 0) AS anon_table_privilege_count,
            COALESCE((
                SELECT count(*)::int
                FROM pg_class AS c
                WHERE c.relnamespace = n.oid AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND EXISTS (
                    SELECT 1 FROM pg_roles AS r
                    WHERE r.rolname = 'authenticated' AND (
                        has_table_privilege(r.oid, c.oid, 'SELECT')
                        OR has_table_privilege(r.oid, c.oid, 'INSERT')
                        OR has_table_privilege(r.oid, c.oid, 'UPDATE')
                        OR has_table_privilege(r.oid, c.oid, 'DELETE')
                        OR has_table_privilege(r.oid, c.oid, 'TRUNCATE')
                        OR has_table_privilege(r.oid, c.oid, 'REFERENCES')
                        OR has_table_privilege(r.oid, c.oid, 'TRIGGER')
                    )
                  )
            ), 0) AS authenticated_table_privilege_count,
            EXISTS (
                SELECT 1
                FROM pg_default_acl AS d
                CROSS JOIN LATERAL aclexplode(d.defaclacl) AS acl
                WHERE (d.defaclnamespace = 0 OR d.defaclnamespace = n.oid)
                  AND d.defaclobjtype = 'r'
                  AND (
                    acl.grantee = 0
                    OR EXISTS (
                      SELECT 1
                      FROM pg_roles AS api_role
                      WHERE api_role.rolname = 'anon'
                        AND CASE
                          WHEN acl.grantee = 0 THEN false
                          ELSE pg_has_role(api_role.oid, acl.grantee, 'USAGE')
                            OR pg_has_role(api_role.oid, acl.grantee, 'SET')
                        END
                    )
                  )
                  AND acl.privilege_type IN (
                    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
                  )
            ) AS anon_default_table_privileges,
            EXISTS (
                SELECT 1
                FROM pg_default_acl AS d
                CROSS JOIN LATERAL aclexplode(d.defaclacl) AS acl
                WHERE (d.defaclnamespace = 0 OR d.defaclnamespace = n.oid)
                  AND d.defaclobjtype = 'r'
                  AND (
                    acl.grantee = 0
                    OR EXISTS (
                      SELECT 1
                      FROM pg_roles AS api_role
                      WHERE api_role.rolname = 'authenticated'
                        AND CASE
                          WHEN acl.grantee = 0 THEN false
                          ELSE pg_has_role(api_role.oid, acl.grantee, 'USAGE')
                            OR pg_has_role(api_role.oid, acl.grantee, 'SET')
                        END
                    )
                  )
                  AND acl.privilege_type IN (
                    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
                  )
            ) AS authenticated_default_table_privileges,
            (
                SELECT count(*)::int
                FROM pg_class AS c
                WHERE c.relnamespace = n.oid AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                  AND c.relrowsecurity
            ) AS rls_enabled_table_count
        FROM pg_namespace AS n
        WHERE n.nspname = %s
        """,
        (SCHEMA,),
    ).fetchone()
    if row is None:
        raise BackupError("The private Coworker schema is missing.")

    keys = (
        "anon_schema_access",
        "authenticated_schema_access",
        "anon_table_privilege_count",
        "authenticated_table_privilege_count",
        "anon_default_table_privileges",
        "authenticated_default_table_privileges",
        "rls_enabled_table_count",
    )
    access = dict(zip(keys, row))
    exposed = any(access[key] for key in keys if key != "rls_enabled_table_count")
    if exposed:
        raise BackupError(
            "The private Coworker schema grants access to Supabase API roles; "
            "review schema, table and default privileges before backup or restore verification."
        )
    return access


def inventory(connection) -> dict:
    from psycopg import sql

    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    connection.execute("SET LOCAL DateStyle TO 'ISO, YMD'")
    connection.execute("SET LOCAL bytea_output TO 'hex'")
    connection.execute("SET LOCAL extra_float_digits TO 3")
    tables = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename", (SCHEMA,),
    ).fetchall()
    if ("cw_alembic_version",) not in tables:
        raise BackupError("The private Coworker migration ledger is missing.")
    revisions = connection.execute(
        "SELECT version_num FROM shuddho_coworker.cw_alembic_version",
    ).fetchall()
    if len(revisions) != 1 or not revisions[0][0]:
        raise BackupError("Expected one Coworker migration revision.")
    access_control = private_schema_access(connection)

    result = {}
    for (table,) in tables:
        digest = sha256()
        count = 0
        query = sql.SQL(
            'SELECT to_jsonb(t)::text COLLATE "C" AS payload FROM {} AS t ORDER BY payload',
        ).format(sql.Identifier(SCHEMA, table))
        with connection.cursor(name="backup_inventory") as cursor:
            cursor.execute(query)
            for (row,) in cursor:
                # JSON text escapes embedded newlines.
                digest.update(row.encode("utf-8") + b"\n")
                count += 1
        result[table] = {"rows": count, "sha256": digest.hexdigest()}
    return {"revision": revisions[0][0], "tables": result, "access_control": access_control}


def dump_source(url: str, archive: Path, pg_bin: Path | None) -> tuple[dict, str]:
    import psycopg

    parsed = urlsplit(url)
    username = parsed.username
    password = unquote(parsed.password or "")
    if any(char in password for char in "\r\n\x00"):
        raise BackupError("The staging database password contains an unsupported control character.")
    connection = {
        "host": parsed.hostname, "port": parsed.port, "user": username,
        "password": password, "dbname": "postgres", "sslmode": "verify-full",
        "sslrootcert": str(CERTIFICATE), "connect_timeout": 10,
    }
    db_env = {
        "PGHOST": connection["host"], "PGPORT": str(connection["port"]),
        "PGUSER": username, "PGDATABASE": "postgres",
        "PGSSLMODE": "verify-full", "PGSSLROOTCERT": str(CERTIFICATE), "PGCONNECT_TIMEOUT": "10",
    }
    escaped_password = password.replace("\\", "\\\\").replace(":", "\\:")
    with NamedTemporaryFile(mode="w", encoding="utf-8", prefix="shuddho-pgpass-") as pgpass:
        pgpass.write(f"{parsed.hostname}:{parsed.port}:postgres:{username}:{escaped_password}\n")
        pgpass.flush()
        db_env["PGPASSFILE"] = pgpass.name
        with psycopg.connect(**connection) as source:
            snapshot = dump_snapshot(source, db_env, archive, pg_bin, expected_user=username.split(".", 1)[0])
            # Bind this verified archive to the same observable database identity
            # captured by staging_backup_restore.prepare, never to a supplied label.
            database, address, port = source.execute(
                "SELECT current_database(), coalesce(inet_server_addr()::text, 'local'), "
                "coalesce(inet_server_port(), 0)"
            ).fetchone()
            fingerprint = sha256(f"{address}|{port}|{database}".encode("utf-8")).hexdigest()
            return snapshot, fingerprint


def dump_snapshot(connection, db_env: dict[str, str], archive: Path, pg_bin: Path | None, *, expected_user: str) -> dict:
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    if connection.execute("SELECT current_user").fetchone()[0] != expected_user:
        raise BackupError("PostgreSQL did not authenticate as the expected backup reader.")
    snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
    source_inventory = inventory(connection)
    run_pg(
        pg_bin, "pg_dump", "--no-password", "--format=custom", "--schema", SCHEMA,
        "--no-publications", "--no-subscriptions",
        "--snapshot", snapshot, "--file", str(archive), db_env=db_env,
    )
    return source_inventory


@contextmanager
def isolated_postgres(pg_bin: Path | None) -> Iterator[dict[str, str]]:
    # The cluster is reachable only via a new private Unix socket directory.
    with TemporaryDirectory(prefix="shuddho-restore-") as directory:
        root = Path(directory)
        data = str(root / "data")
        socket = str(root / "socket")
        Path(socket).mkdir(mode=0o700)
        run_pg(
            pg_bin, "initdb", "-D", data, "--username", RESTORE_USER,
            "--auth-local=trust", "--auth-host=reject", "--encoding=UTF8", "--locale=C",
        )
        options = f"-h '' -k {shlex.quote(socket)} -p {RESTORE_PORT}"
        try:
            run_pg(pg_bin, "pg_ctl", "-D", data, "-l", str(root / "postgres.log"), "-o", options, "-w", "start")
            yield {"PGHOST": socket, "PGPORT": RESTORE_PORT, "PGUSER": RESTORE_USER, "PGDATABASE": "postgres"}
        finally:
            if (root / "data" / "postmaster.pid").exists():
                run_pg(pg_bin, "pg_ctl", "-D", data, "-m", "immediate", "-w", "stop")


def restore_inventory(archive: Path, pg_bin: Path | None) -> dict:
    import psycopg

    with isolated_postgres(pg_bin) as db_env:
        run_pg(
            pg_bin, "pg_restore", "--no-password", "--dbname=postgres", "--single-transaction",
            "--no-owner", "--no-privileges", "--exit-on-error", str(archive), db_env=db_env,
        )
        with psycopg.connect(
            host=db_env["PGHOST"], port=db_env["PGPORT"], user=RESTORE_USER,
            dbname="postgres", sslmode="disable",
        ) as restored:
            restored.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            return inventory(restored)


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return file_digest(source, "sha256").hexdigest()


def run_backup(url: str, directory: Path, pg_bin: Path | None = None) -> dict:
    if os.environ.get("PGHOSTADDR") or os.environ.get("PGSERVICE"):
        raise BackupError("Unset PGHOSTADDR and PGSERVICE before using the staging backup command.")
    try:
        _validate_postgresql_url(url)
    except PreflightFailure as error:
        raise BackupError(str(error)) from None
    try:
        directory.mkdir(mode=0o700)
    except OSError:
        raise BackupError("Provide a new backup output directory under an existing private parent.") from None
    partial = directory / ".coworker.dump.partial"
    archive = directory / "coworker.dump"
    try:
        source, source_database_fingerprint = dump_source(url, partial, pg_bin)
        if not isinstance(source_database_fingerprint, str) or not re.fullmatch(
            r"[a-f0-9]{64}", source_database_fingerprint
        ):
            raise BackupError("The archive source database fingerprint is unavailable.")
        partial.chmod(0o600)
        partial.rename(archive)
    finally:
        partial.unlink(missing_ok=True)
    restored = restore_inventory(archive, pg_bin)
    if restored != source:
        raise BackupError("Restored migration revision or table contents differ from the source snapshot.")
    # Backup integrity and application-schema readiness are separate checks.
    # Never block preserving an older valid backup just because the current
    # source graph is newer (or unreadable); fail closed on release readiness.
    try:
        schema_alignment = source_schema_alignment(source["revision"])
    except MigrationAlignmentError:
        schema_alignment = {
            "status": "migration_graph_unverified",
            "source_revision": source["revision"], "code_head": None,
            "source_is_current": False, "pending_migrations": None,
            "release_qualified": False,
        }
    result = {
        "status": "verified", "verified_at": datetime.now(timezone.utc).isoformat(),
        "archive_sha256": file_hash(archive), "source": source,
        "source_database_fingerprint": source_database_fingerprint,
        "schema_alignment": schema_alignment,
    }
    write_private_json(directory / "verification.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="New directory under your private backup location")
    parser.add_argument("--pg-bin", type=Path, help="Directory containing the PostgreSQL executables")
    args = parser.parse_args()
    try:
        receipt = run_backup(os.environ.get(SOURCE_ENV, ""), args.directory, args.pg_bin)
    except KeyboardInterrupt:
        parser.exit(130, "Database backup interrupted.\n")
    except BackupError as error:
        parser.exit(1, f"{error}\n")
    except Exception as error:
        parser.exit(1, f"Database backup verification failed ({type(error).__name__}).\n")
    print(f"Verified {len(receipt['source']['tables'])} private tables at migration {receipt['source']['revision']}.")
    alignment = receipt["schema_alignment"]
    print(f"Source/schema alignment: {alignment['status']} (code head: {alignment['code_head'] or 'unverified'}). "
          "Backup verification is not release authorization.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    main()
