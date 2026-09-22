from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path

from sqlalchemy import select, text

from scripts.staging_api_exercise import staging_owner if False else None
from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.models import Account, Document, DocumentVersion, Task, TaskEvent, Workspace
from services.coworker.schemas import TaskCreate, UploadRequest

import httpx


class BackupRestoreFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def require_guard(name: str) -> None:
    if os.environ.get(name, "").lower() != "true":
        raise BackupRestoreFailure(f"Set {name}=true only in the controlled staging environment.")


def resolve_owner() -> str:
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    try:
        response = httpx.get(
            base_url + "/api/v1/me",
            headers={"Authorization": "Bearer " + token},
            timeout=20,
            follow_redirects=False,
        )
    except httpx.HTTPError as error:
        raise BackupRestoreFailure(f"Staging /me request failed: {type(error).__name__}") from None
    if response.status_code != 200:
        raise BackupRestoreFailure(f"Staging /me returned HTTP {response.status_code}.")
    try:
        value = response.json()
    except ValueError:
        raise BackupRestoreFailure("Staging /me did not return JSON.") from None
    owner = value.get("account_id") if isinstance(value, dict) else None
    if not isinstance(owner, str) or not owner:
        raise BackupRestoreFailure("Staging /me did not return an account id.")
    return owner


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def environment_fingerprints(container: Container) -> dict:
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


def prepare(settings: Settings, state_path: Path) -> dict:
    require_guard("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE")
    owner = resolve_owner()
    container = Container.create(settings)
    marker = uuid.uuid4().hex
    payload = ("shuddho-backup-restore-probe-" + marker).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    try:
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
            "owner_id": owner,
            "document_id": upload["id"],
            "version_id": upload["version_id"],
            "task_id": task["id"],
            "sha256": digest,
            "byte_size": len(payload),
            "source_fingerprints": environment_fingerprints(container),
        }
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
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
    evidence_path: Path,
    base_evidence: Path | None,
) -> dict:
    require_guard("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE")
    if not backup_reference.strip() or not restore_reference.strip():
        raise BackupRestoreFailure("Both backup and restore evidence references are required.")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise BackupRestoreFailure("Backup/restore state file must be a JSON object.")
    required = {"owner_id", "document_id", "version_id", "task_id", "sha256", "byte_size", "source_fingerprints"}
    if not required.issubset(state):
        raise BackupRestoreFailure("Backup/restore state file is incomplete.")

    container = Container.create(settings)
    try:
        target = environment_fingerprints(container)
        source = state["source_fingerprints"]
        if target["database"] == source.get("database"):
            raise BackupRestoreFailure("Restore verification must run against an isolated restored PostgreSQL target.")
        if target["storage"] == source.get("storage"):
            raise BackupRestoreFailure("Restore verification must run against an isolated restored object-storage target.")

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

        base = {}
        if base_evidence:
            value = json.loads(base_evidence.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise BackupRestoreFailure("Base staging evidence must be a JSON object.")
            base.update(value)
        backup_ref = backup_reference.strip()[:200]
        restore_ref = restore_reference.strip()[:200]
        base["backup_restore"] = passed(
            f"isolated PostgreSQL + private object restore matched synthetic manifest and SHA-256; backup_ref={backup_ref}; restore_ref={restore_ref}"
        )
        evidence_path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        return {"checks": {"backup_restore": "passed"}}
    finally:
        container.repository.sessions.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the controlled Shuddho PostgreSQL/object backup and restore drill.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--backup-reference", required=True)
    verify_parser.add_argument("--restore-reference", required=True)
    verify_parser.add_argument("--base-evidence", type=Path)
    verify_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "prepare":
            result = prepare(settings, args.state)
            print(json.dumps({"status": "prepared", **result}, indent=2))
        else:
            result = verify(
                settings,
                args.state,
                args.backup_reference,
                args.restore_reference,
                args.output,
                args.base_evidence,
            )
            print(json.dumps({"written": str(args.output), **result}, indent=2))
    except (BackupRestoreFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
