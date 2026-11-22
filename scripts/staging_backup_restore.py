from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from scripts.staging_api_exercise import (
    ExerciseFailure, env_secret, require_https_base, verified_staging_owner,
)
from scripts.staging_day2_archive_attestation import (
    ArchiveAttestationFailure, _private_json, attest_archives,
)
from scripts.staging_day2_authorization import (
    AuthorizationEvidenceFailure, preflight_restored_destination, read_private_authorization,
)
from scripts.staging_preseed_baseline import (
    PreseedBaselineFailure, attest_preseed_baseline, require_unchanged_source,
    read_original_attestation, require_same_source_resources,
)
from scripts.staging_object_backup import ObjectArchiveError, _inventory as private_object_inventory
from scripts.staging_restored_api_access import RestoredAPIReadbackFailure, attest_restored_api_access
from scripts.staging_release_evidence import (
    StagingReleaseEvidenceError,
    passed,
    prepared_release_context,
    validate_prepared_release_context,
    write_private_json,
)
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.models import Account, Document, DocumentVersion, Task, TaskEvent, Workspace
from services.coworker.schemas import TaskCreate, UploadRequest

import httpx


class BackupRestoreFailure(RuntimeError):
    pass


def require_guard(name: str) -> None:
    if os.environ.get(name, "").lower() != "true":
        raise BackupRestoreFailure(f"Set {name}=true only in the controlled staging environment.")


def resolve_owner() -> str:
    """Require the pinned live API to bind the managed owner before restore writes."""
    try:
        return verified_staging_owner(
            env_secret("SHUDDHO_STAGING_TOKEN_A"),
            origin=env_secret("SHUDDHO_STAGING_API_BASE_URL"),
        )
    except ExerciseFailure:
        raise BackupRestoreFailure(
            "Managed staging owner cannot be verified for backup/restore."
        ) from None


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def environment_fingerprints(container: Container) -> dict[str, str]:
    engine = container.repository.sessions.kw["bind"]
    with engine.connect() as connection:
        database = connection.execute(text("select current_database()")).scalar_one()
        address = connection.execute(text("select coalesce(inet_server_addr()::text, 'local')")).scalar_one()
        port = connection.execute(text("select coalesce(inet_server_port(), 0)")).scalar_one()
    settings = container.settings
    storage_identity = "|".join([
        settings.storage_backend,
        settings.storage_endpoint or "",
        settings.storage_bucket,
        settings.storage_region,
    ])
    return {
        "database": stable_hash(f"{address}|{port}|{database}"),
        "storage": stable_hash(storage_identity),
    }


def restored_database_inventory(container: Container) -> dict:
    """Read every private table from the isolated target in one SQL snapshot."""
    from scripts.staging_postgres_backup import inventory

    engine = container.repository.sessions.kw["bind"]
    proxy = engine.raw_connection()
    dbapi = getattr(proxy, "driver_connection", None) or proxy
    try:
        # This connection is separate from the synthetic-probe ORM session and
        # cannot change the target while comparing all table digests.
        dbapi.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return inventory(dbapi)
    except Exception:
        raise BackupRestoreFailure("Isolated restored PostgreSQL inventory could not be verified.") from None
    finally:
        try:
            dbapi.rollback()
        finally:
            proxy.close()


def _preflight_private_json_destination(path: Path) -> None:
    """Validate the evidence destination before contacting or mutating staging."""
    if path.exists() or path.is_symlink():
        raise StagingReleaseEvidenceError(
            "Refusing to overwrite existing private evidence file."
        )
    if not path.parent.is_dir():
        raise StagingReleaseEvidenceError(
            "Private evidence directory does not exist."
        )

    probe_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.preflight"
    try:
        # Exercise the same private, atomic writer that will publish the final
        # manifest. A predictable local write failure must not leave staging
        # uploads, task records, or objects behind.
        write_private_json(probe_path, {"preflight": True})
    finally:
        try:
            probe_path.unlink(missing_ok=True)
        except OSError as error:
            raise StagingReleaseEvidenceError(
                f"Could not clean up private evidence preflight file: {type(error).__name__}"
            ) from None


def attest_original(
    settings: Settings, output_path: Path,
    *, original_postgres_verification: Path | None = None,
    original_postgres_archive: Path | None = None,
    original_object_archive: Path | None = None,
) -> dict:
    """Early source gate; execute at 0070, *before* migration or synthetic writes.

    Later task preparation cannot demand original row equality because an
    authorized migration and synthetic source tasks legitimately change rows.
    """
    require_guard("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE")
    _preflight_private_json_destination(output_path)
    if any(path is None for path in (
        original_postgres_verification, original_postgres_archive, original_object_archive,
    )):
        raise BackupRestoreFailure(
            "Verified original PostgreSQL archive and zero-object baseline are mandatory before attestation."
        )
    summary, archived_inventory = attest_preseed_baseline(
        original_postgres_verification, original_postgres_archive, original_object_archive,
    )
    container = Container.create(settings)
    try:
        current = environment_fingerprints(container)
        live_database = restored_database_inventory(container)
        try:
            live_objects = private_object_inventory(container.storage)
        except ObjectArchiveError:
            raise BackupRestoreFailure(
                "Original private object inventory cannot be read for attestation."
            ) from None
        require_unchanged_source(
            summary, archived_inventory, current, live_database, live_objects,
        )
        write_private_json(output_path, {
            "schema_version": 1,
            "status": "preseed_verified",
            "attested_at": datetime.now(timezone.utc).isoformat(),
            "baseline": summary,
        })
        return {"status": "preseed_verified"}
    finally:
        container.repository.sessions.kw["bind"].dispose()


def prepare(
    settings: Settings, state_path: Path, rollout_path: Path,
    *, original_postgres_verification: Path | None = None,
    original_postgres_archive: Path | None = None,
    original_object_archive: Path | None = None,
    original_baseline_attestation: Path | None = None,
) -> dict:
    require_guard("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE")
    release_context = prepared_release_context(settings, rollout_path)
    _preflight_private_json_destination(state_path)
    if any(path is None for path in (
        original_postgres_verification, original_postgres_archive, original_object_archive,
        original_baseline_attestation,
    )):
        raise BackupRestoreFailure(
            "Verified original PostgreSQL archive and zero-object baseline attestation are mandatory before any synthetic write."
        )
    original_summary, _ = attest_preseed_baseline(
        original_postgres_verification, original_postgres_archive, original_object_archive,
    )
    original_summary = read_original_attestation(
        original_baseline_attestation, original_summary,
    )
    container = Container.create(settings)
    marker = uuid.uuid4().hex
    payload = ("shuddho-backup-restore-probe-" + marker).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    try:
        source_fingerprints = environment_fingerprints(container)
        # Schema/rows may now be at 0072 with synthetic data. The earlier
        # immutable attestation proves the pre-migration original state.
        require_same_source_resources(original_summary, source_fingerprints)
        owner = resolve_owner()
        upload = container.repository.create_upload(
            owner,
            UploadRequest(
                filename="staging-backup-probe.txt",
                byte_size=len(payload),
                sha256=digest,
            ),
        )
        item = container.repository.get_upload(owner, upload["id"])
        container.storage.put(item["object_key"], payload, "text/plain")
        container.repository.finish_upload(owner, upload["id"])

        task, _ = container.repository.create_task(
            owner,
            TaskCreate(
                skill_id="report_email",
                instruction="Create a synthetic backup/restore validation record.",
                notes="Synthetic staging probe only. No customer data.",
                document_ids=[upload["id"]],
                output_language="en",
            ),
            "staging-backup-" + marker,
        )
        container.repository.cancel(owner, task["id"])

        state = {
            "release_context": release_context,
            "owner_id": owner,
            "document_id": upload["id"],
            "version_id": upload["version_id"],
            "task_id": task["id"],
            "sha256": digest,
            "byte_size": len(payload),
            "source_fingerprints": source_fingerprints,
            "preseed_baseline": original_summary,
        }
        write_private_json(state_path, state)
        return {
            "document_id": upload["id"],
            "task_id": task["id"],
            "next": "Run the real PostgreSQL and object-storage backup, restore both into an isolated staging environment, then run verify there.",
        }
    finally:
        container.repository.sessions.kw["bind"].dispose()


def verify(
    settings: Settings,
    state_path: Path,
    backup_reference: str,
    restore_reference: str,
    rollout_path: Path,
    evidence_path: Path,
    base_evidence: Path | None,
    *,
    authorization_path: Path | None = None,
    postgres_verification: Path | None = None,
    postgres_archive: Path | None = None,
    object_archive: Path | None = None,
    object_restore_receipt: Path | None = None,
    original_postgres_verification: Path | None = None,
    original_postgres_archive: Path | None = None,
    original_object_archive: Path | None = None,
    original_baseline_attestation: Path | None = None,
) -> dict:
    require_guard("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE")
    if not backup_reference.strip() or not restore_reference.strip():
        raise BackupRestoreFailure("Both backup and restore evidence references are required.")
    # Validate local inputs and a writable private output *before* opening the
    # restored database, storage, or sending the managed owner tokens.
    _preflight_private_json_destination(evidence_path)
    state = _private_json(state_path, "Prepared backup/restore state")
    base_fields = _private_json(base_evidence, "Prior staging evidence") if base_evidence else {}
    required = {"release_context", "owner_id", "document_id", "version_id", "task_id", "sha256", "byte_size", "source_fingerprints"}
    if not required.issubset(state):
        raise BackupRestoreFailure("Backup/restore state file is incomplete.")
    source = state["source_fingerprints"]
    if (
        not isinstance(source, dict)
        or set(source) != {"database", "storage"}
        or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in source.values()
        )
    ):
        raise BackupRestoreFailure(
            "Prepared source environment fingerprints must include database and storage SHA-256 digests."
        )

    context = validate_prepared_release_context(
        state["release_context"],
        settings,
        rollout_path,
    )
    container = Container.create(settings)
    try:
        target = environment_fingerprints(container)
        if target["database"] == source["database"]:
            raise BackupRestoreFailure("Restore verification must run against an isolated restored PostgreSQL target.")
        if target["storage"] == source["storage"]:
            raise BackupRestoreFailure("Restore verification must run against an isolated restored object-storage target.")

        if any(path is None for path in (
            postgres_verification, postgres_archive, object_archive, object_restore_receipt,
        )):
            raise BackupRestoreFailure(
                "Full PostgreSQL verification, dump, private object archive and restore receipt are mandatory."
            )
        if any(path is None for path in (
            original_postgres_verification, original_postgres_archive, original_object_archive,
            original_baseline_attestation,
        )):
            raise BackupRestoreFailure(
                "Verified original PostgreSQL dump and empty-object baseline attestation are mandatory for restore."
            )
        original_summary, _ = attest_preseed_baseline(
            original_postgres_verification, original_postgres_archive, original_object_archive,
        )
        original_summary = read_original_attestation(
            original_baseline_attestation, original_summary,
        )
        if (state.get("preseed_baseline") != original_summary
                or original_summary["source_database_fingerprint"] != source["database"]
                or original_summary["source_storage_fingerprint"] != source["storage"]):
            raise BackupRestoreFailure(
                "Original staging baseline is missing or differs from the prepared source receipt."
            )
        integrity, source_inventory, restored_objects = attest_archives(
            state, target, postgres_verification, postgres_archive,
            object_archive, object_restore_receipt,
        )
        if restored_database_inventory(container) != source_inventory:
            raise BackupRestoreFailure(
                "Isolated PostgreSQL target has different schema, migration ledger, rows, or table SHA-256."
            )

        owner = str(state["owner_id"])
        document_id = str(state["document_id"])
        version_id = str(state["version_id"])
        task_id = str(state["task_id"])
        expected_sha = str(state["sha256"])
        expected_size = int(state["byte_size"])

        with container.repository.sessions() as db:
            account = db.get(Account, owner)
            workspace = db.scalar(select(Workspace).where(Workspace.owner_id == owner))
            document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == owner))
            version = db.scalar(select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.owner_id == owner,
            ))
            task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner))
            events = list(db.scalars(select(TaskEvent).where(TaskEvent.task_id == task_id)).all())

            if account is None or workspace is None:
                raise BackupRestoreFailure("Restored account/workspace records are missing.")
            if document is None or version is None or version.state != "uploaded":
                raise BackupRestoreFailure("Restored source document/version is missing or not uploaded.")
            if version.sha256 != expected_sha or version.byte_size != expected_size:
                raise BackupRestoreFailure("Restored document metadata does not match the pre-backup manifest.")
            if task is None or task.state != "cancelled":
                raise BackupRestoreFailure("Restored synthetic task record is missing or changed.")
            if not events:
                raise BackupRestoreFailure("Restored task event history is missing.")
            object_key = version.object_key

        body = container.storage.get(object_key, expected_size)
        if len(body) != expected_size or hashlib.sha256(body).hexdigest() != expected_sha:
            raise BackupRestoreFailure("Restored object bytes do not match the pre-backup SHA-256 manifest.")
        if not any(
            row["key"] == object_key and row["sha256"] == expected_sha
            and row["byte_size"] == expected_size for row in restored_objects
        ):
            raise BackupRestoreFailure("Synthetic probe object is absent from the full private archive/restore ledger.")
        integrity["probe_object_verified"] = True
        integrity["probe_object_sha256"] = expected_sha
        integrity["probe_object_bytes"] = expected_size
        integrity["preseed_baseline"] = original_summary

        # Direct database/object reads are insufficient to prove user-facing
        # isolated restore access. Require a distinct, approved HTTPS API with
        # two actual managed synthetic tokens, and refuse a PASS if absent.
        required_secrets = (
            "SHUDDHO_STAGING_API_BASE_URL",
            "SHUDDHO_STAGING_RESTORED_API_BASE_URL",
            "SHUDDHO_STAGING_TOKEN_A",
            "SHUDDHO_STAGING_TOKEN_B",
        )
        if any(not os.environ.get(key) for key in required_secrets):
            raise BackupRestoreFailure(
                "Restored API readback requires approved source/isolated HTTPS origins and two managed identity tokens."
            )
        try:
            source_api_origin = require_https_base(os.environ["SHUDDHO_STAGING_API_BASE_URL"])
            restored_api_origin = require_https_base(
                os.environ["SHUDDHO_STAGING_RESTORED_API_BASE_URL"]
            )
        except ExerciseFailure:
            raise BackupRestoreFailure(
                "Source and restored API must use separate clean, approved public HTTPS origins."
            ) from None
        if source_api_origin == restored_api_origin:
            raise BackupRestoreFailure(
                "Isolated restored API must not be the live source API origin."
            )
        if authorization_path is None:
            raise BackupRestoreFailure(
                "Protected Founder/C restored API destination authorization is required before any bearer request."
            )
        try:
            # A different public HTTPS URL is not authorization to receive
            # either managed owner token. Verify the private approved origin
            # hash and both distinct DB/S3 targets BEFORE opening HTTP.
            approved_api_sha = preflight_restored_destination(
                read_private_authorization(authorization_path),
                source_revision=context["source_revision"],
                release_id=context["release_id"],
                rollout_manifest_sha256=context["rollout_manifest_sha256"],
                source_api_origin=source_api_origin,
                restored_api_origin=restored_api_origin,
                target_database_fingerprint=target["database"],
                target_storage_fingerprint=target["storage"],
            )
        except AuthorizationEvidenceFailure:
            raise BackupRestoreFailure(
                "Restored API destination does not match the protected Founder/C decision."
            ) from None
        with httpx.Client(
            base_url=restored_api_origin,
            timeout=20,
            follow_redirects=False,
            trust_env=False,
        ) as restored_api:
            integrity["restored_api_access"] = attest_restored_api_access(
                restored_api,
                os.environ["SHUDDHO_STAGING_TOKEN_A"],
                os.environ["SHUDDHO_STAGING_TOKEN_B"],
                source_origin=source_api_origin,
                restored_origin=restored_api_origin,
                approved_restored_origin_sha256=approved_api_sha,
                expected_owner_id=owner,
                document_id=document_id,
                task_id=task_id,
                document_sha256=expected_sha,
                document_size=expected_size,
                source_revision=context["source_revision"],
                expected_issuer=settings.auth_issuer,
                expected_audience=settings.auth_audience,
            )

        base = dict(base_fields)
        backup_ref = backup_reference.strip()[:200]
        restore_ref = restore_reference.strip()[:200]
        base["archive_integrity"] = integrity
        base["backup_restore"] = passed(
            f"isolated PostgreSQL + private object restore matched synthetic manifest and SHA-256; backup_ref={backup_ref}; restore_ref={restore_ref}",
            context,
        )
        write_private_json(evidence_path, base)
        return {"checks": {"backup_restore": "passed"}}
    finally:
        container.repository.sessions.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the controlled Shuddho PostgreSQL/object backup and restore drill.")
    sub = parser.add_subparsers(dest="command", required=True)

    original_parser = sub.add_parser("attest-original")
    original_parser.add_argument("--output", type=Path, required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--state", type=Path, required=True)
    prepare_parser.add_argument("--rollout", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--backup-reference", required=True)
    verify_parser.add_argument("--restore-reference", required=True)
    verify_parser.add_argument(
        "--authorization", type=Path, required=True,
        help="Protected 0600 Founder/C decision for the exact isolated DB/S3/API targets.",
    )
    verify_parser.add_argument("--postgres-verification", type=Path, required=True)
    verify_parser.add_argument("--postgres-archive", type=Path, required=True)
    verify_parser.add_argument("--object-archive-directory", type=Path, required=True)
    verify_parser.add_argument("--object-restore-receipt", type=Path, required=True)
    for command in (original_parser, prepare_parser, verify_parser):
        command.add_argument("--original-postgres-verification", type=Path, required=True)
        command.add_argument("--original-postgres-archive", type=Path, required=True)
        command.add_argument("--original-object-archive-directory", type=Path, required=True)
    for command in (prepare_parser, verify_parser):
        command.add_argument("--original-baseline-attestation", type=Path, required=True)
    verify_parser.add_argument("--rollout", type=Path, required=True)
    verify_parser.add_argument("--base-evidence", type=Path)
    verify_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "attest-original":
            result = attest_original(
                settings, args.output,
                original_postgres_verification=args.original_postgres_verification,
                original_postgres_archive=args.original_postgres_archive,
                original_object_archive=args.original_object_archive_directory,
            )
            print(json.dumps({"status": result["status"], "written": str(args.output)}, indent=2))
        elif args.command == "prepare":
            result = prepare(
                settings, args.state, args.rollout,
                original_postgres_verification=args.original_postgres_verification,
                original_postgres_archive=args.original_postgres_archive,
                original_object_archive=args.original_object_archive_directory,
                original_baseline_attestation=args.original_baseline_attestation,
            )
            print(json.dumps({"status": "prepared", **result}, indent=2))
        else:
            result = verify(
                settings,
                args.state,
                args.backup_reference,
                args.restore_reference,
                args.rollout,
                args.output,
                args.base_evidence,
                postgres_verification=args.postgres_verification,
                postgres_archive=args.postgres_archive,
                object_archive=args.object_archive_directory,
                object_restore_receipt=args.object_restore_receipt,
                authorization_path=args.authorization,
                original_postgres_verification=args.original_postgres_verification,
                original_postgres_archive=args.original_postgres_archive,
                original_object_archive=args.original_object_archive_directory,
                original_baseline_attestation=args.original_baseline_attestation,
            )
            print(json.dumps({"written": str(args.output), **result}, indent=2))
    except (
        BackupRestoreFailure,
        ArchiveAttestationFailure,
        PreseedBaselineFailure,
        RestoredAPIReadbackFailure,
        StagingReleaseEvidenceError,
        httpx.HTTPError,
        OSError,
        ValueError,
    ) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
