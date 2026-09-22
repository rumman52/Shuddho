from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from sqlalchemy import select

from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.models import Account, Document, Task
from services.coworker.schemas import TaskCreate, UploadRequest


class DeletionFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_DELETION_EXERCISE", "").lower() != "true":
        raise DeletionFailure(
            "Set SHUDDHO_STAGING_ALLOW_DELETION_EXERCISE=true only in the controlled staging environment."
        )


def synthetic_owner(container: Container, subject: str) -> str:
    principal = Principal(
        container.settings.auth_issuer,
        subject,
        int(time.time()) + 3600,
    )
    return container.repository.ensure_account(principal)["account_id"]


def prepare(settings: Settings, state_path: Path) -> dict:
    require_guard()
    container = Container.create(settings)
    subject = "retention-probe-" + uuid.uuid4().hex
    owner = synthetic_owner(container, subject)
    source_body = ("shuddho-retention-source-" + uuid.uuid4().hex).encode()
    source_sha = hashlib.sha256(source_body).hexdigest()
    try:
        upload = container.repository.create_upload(
            owner,
            UploadRequest(
                filename="retention-probe.txt",
                byte_size=len(source_body),
                sha256=source_sha,
            ),
        )
        source = container.repository.get_upload(owner, upload["id"])
        container.storage.put(source["object_key"], source_body, "text/plain")
        container.repository.finish_upload(owner, upload["id"])

        task, _ = container.repository.create_task(
            owner,
            TaskCreate(
                instruction="Create a synthetic retention validation output.",
                notes="Synthetic staging probe only. No customer data.",
                output_language="en",
            ),
            "retention-task-" + uuid.uuid4().hex,
        )
        artifact_body = ("shuddho-retention-artifact-" + uuid.uuid4().hex).encode()
        artifact_key = f"{owner}/outputs/{task['id']}/retention-artifact.txt"
        container.storage.put(artifact_key, artifact_body, "text/plain")
        container.repository.complete(task["id"], [{
            "filename": "retention-artifact.txt",
            "content_type": "text/plain",
            "object_key": artifact_key,
            "byte_size": len(artifact_body),
            "sha256": hashlib.sha256(artifact_body).hexdigest(),
        }])

        orphan_key = f"{owner}/outputs/orphan/{uuid.uuid4().hex}.bin"
        container.storage.put(orphan_key, b"synthetic-orphan", "application/octet-stream")

        state = {
            "owner_id": owner,
            "subject": subject,
            "document_id": upload["id"],
            "task_id": task["id"],
            "source_key": source["object_key"],
            "artifact_key": artifact_key,
            "orphan_key": orphan_key,
            "prepared_at": time.time(),
        }
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return {
            "owner_id": owner,
            "task_id": task["id"],
            "document_id": upload["id"],
            "next": "Wait until the orphan object is older than the configured minimum age, then run verify.",
        }
    finally:
        container.repository.sessions.kw["bind"].dispose()


def verify(
    settings: Settings,
    state_path: Path,
    evidence_path: Path,
    base_evidence: Path | None,
    min_orphan_age_seconds: int,
) -> dict:
    require_guard()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise DeletionFailure("Deletion state file must be a JSON object.")
    required = {
        "owner_id", "document_id", "task_id", "source_key",
        "artifact_key", "orphan_key", "prepared_at",
    }
    if not required.issubset(state):
        raise DeletionFailure("Deletion state file is incomplete.")
    if time.time() - float(state["prepared_at"]) < max(300, min_orphan_age_seconds):
        raise DeletionFailure("The synthetic orphan is not old enough for age-bounded cleanup yet.")

    container = Container.create(settings)
    owner = str(state["owner_id"])
    try:
        task_result = container.retention.erase_task(owner, str(state["task_id"]))
        if not task_result["database_erased"] or task_result["objects_failed"]:
            raise DeletionFailure("Task erasure did not complete cleanly.")
        try:
            container.storage.get(str(state["artifact_key"]), 1024)
            raise DeletionFailure("Task artifact still exists after task erasure.")
        except FileNotFoundError:
            pass

        with container.repository.sessions() as db:
            if db.get(Task, str(state["task_id"])) is not None:
                raise DeletionFailure("Task row still exists after task erasure.")

        preview = container.retention.cleanup_orphans(
            prefix=owner,
            min_age_seconds=min_orphan_age_seconds,
            dry_run=True,
        )
        candidates = {item["key"] for item in preview["candidates"]}
        orphan_key = str(state["orphan_key"])
        source_key = str(state["source_key"])
        if orphan_key not in candidates:
            raise DeletionFailure("Synthetic orphan was not detected by inventory cleanup.")
        if source_key in candidates:
            raise DeletionFailure("Referenced source object was incorrectly classified as an orphan.")

        cleanup = container.retention.cleanup_orphans(
            prefix=owner,
            min_age_seconds=min_orphan_age_seconds,
            dry_run=False,
        )
        if cleanup["failed"] or orphan_key not in {item["key"] for item in cleanup["candidates"]}:
            raise DeletionFailure("Orphan cleanup did not complete cleanly.")
        try:
            container.storage.get(orphan_key, 1024)
            raise DeletionFailure("Synthetic orphan still exists after cleanup.")
        except FileNotFoundError:
            pass

        account_result = container.retention.erase_account(owner)
        if not account_result["database_erased"] or account_result["objects_failed"]:
            raise DeletionFailure("Account erasure did not complete cleanly.")
        try:
            container.storage.get(source_key, 1024)
            raise DeletionFailure("Owned source object still exists after account erasure.")
        except FileNotFoundError:
            pass

        with container.repository.sessions() as db:
            if db.get(Account, owner) is not None:
                raise DeletionFailure("Account row still exists after account erasure.")
            if db.scalar(select(Document).where(Document.owner_id == owner)) is not None:
                raise DeletionFailure("Owned document row still exists after account erasure.")
            if db.scalar(select(Task).where(Task.owner_id == owner)) is not None:
                raise DeletionFailure("Owned task row still exists after account erasure.")

        base = {}
        if base_evidence:
            value = json.loads(base_evidence.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise DeletionFailure("Base staging evidence must be a JSON object.")
            base.update(value)
        base["deletion"] = passed(
            "synthetic task erasure, account erasure, referenced-object protection and age-bounded orphan cleanup all passed"
        )
        evidence_path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        return {"checks": {"deletion": "passed"}}
    finally:
        container.repository.sessions.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run controlled Shuddho retention/deletion and orphan cleanup validation."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--base-evidence", type=Path)
    verify_parser.add_argument("--output", type=Path, required=True)
    verify_parser.add_argument("--min-orphan-age-seconds", type=int, default=3600)

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
                args.output,
                args.base_evidence,
                max(300, args.min_orphan_age_seconds),
            )
            print(json.dumps({"written": str(args.output), **result}, indent=2))
    except (DeletionFailure, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
