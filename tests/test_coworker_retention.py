from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest
from sqlalchemy import select

pytest.importorskip("sqlalchemy")

from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.migrate import upgrade
from services.coworker.models import Account, Artifact, Task
from services.coworker.schemas import TaskCreate, UploadRequest


ISSUER = "https://identity.example.test/auth/v1"


@pytest.fixture
def container(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'workspace.sqlite3'}",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
    )
    upgrade(settings.database_url)
    value = Container.create(settings)
    yield value
    value.repository.sessions.kw["bind"].dispose()


def owner(container, subject="retention-user"):
    principal = Principal(ISSUER, subject, int(time.time()) + 3600)
    return container.repository.ensure_account(principal)["account_id"]


def test_task_erasure_removes_rows_and_output_objects(container):
    account_id = owner(container)
    task, _ = container.repository.create_task(
        account_id,
        TaskCreate(instruction="Create retention test output.", notes="synthetic", output_language="en"),
        "retention-task",
    )
    body = b"synthetic-output"
    key = f"{account_id}/outputs/{task['id']}/artifact.txt"
    container.storage.put(key, body, "text/plain")
    container.repository.complete(task["id"], [{
        "filename": "artifact.txt",
        "content_type": "text/plain",
        "object_key": key,
        "byte_size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }])

    result = container.retention.erase_task(account_id, task["id"])
    assert result["database_erased"] is True
    assert result["objects_deleted"] == 1
    assert result["objects_failed"] == []
    with container.repository.sessions() as db:
        assert db.get(Task, task["id"]) is None
        assert db.scalar(select(Artifact).where(Artifact.task_id == task["id"])) is None
    with pytest.raises(FileNotFoundError):
        container.storage.get(key, 1024)


def test_account_erasure_removes_owned_rows_and_source_objects(container):
    account_id = owner(container, "erase-account")
    body = b"owned-source"
    digest = hashlib.sha256(body).hexdigest()
    upload = container.repository.create_upload(
        account_id,
        UploadRequest(filename="owned.txt", byte_size=len(body), sha256=digest),
    )
    item = container.repository.get_upload(account_id, upload["id"])
    container.storage.put(item["object_key"], body, "text/plain")
    container.repository.finish_upload(account_id, upload["id"])

    task, _ = container.repository.create_task(
        account_id,
        TaskCreate(instruction="Synthetic task.", notes="erase me", output_language="en"),
        "erase-account-task",
    )
    container.repository.cancel(account_id, task["id"])

    result = container.retention.erase_account(account_id)
    assert result["database_erased"] is True
    assert result["objects_failed"] == []
    with container.repository.sessions() as db:
        assert db.get(Account, account_id) is None
        assert db.scalar(select(Task).where(Task.owner_id == account_id)) is None
    with pytest.raises(FileNotFoundError):
        container.storage.get(item["object_key"], 1024)


def test_orphan_cleanup_is_dry_run_first_and_age_bounded(container):
    account_id = owner(container, "orphan-user")
    referenced_body = b"referenced"
    digest = hashlib.sha256(referenced_body).hexdigest()
    upload = container.repository.create_upload(
        account_id,
        UploadRequest(filename="referenced.txt", byte_size=len(referenced_body), sha256=digest),
    )
    item = container.repository.get_upload(account_id, upload["id"])
    container.storage.put(item["object_key"], referenced_body, "text/plain")
    container.repository.finish_upload(account_id, upload["id"])

    orphan = f"{account_id}/outputs/orphan/old.bin"
    recent = f"{account_id}/outputs/orphan/recent.bin"
    container.storage.put(orphan, b"old", "application/octet-stream")
    container.storage.put(recent, b"recent", "application/octet-stream")
    old_time = time.time() - 7200
    os.utime(container.storage.path(orphan), (old_time, old_time))

    preview = container.retention.cleanup_orphans(prefix=account_id, min_age_seconds=3600, dry_run=True)
    keys = {item["key"] for item in preview["candidates"]}
    assert orphan in keys
    assert recent not in keys
    assert item["object_key"] not in keys
    assert preview["deleted"] == 0

    result = container.retention.cleanup_orphans(prefix=account_id, min_age_seconds=3600, dry_run=False)
    assert result["deleted"] == 1
    assert result["failed"] == []
    with pytest.raises(FileNotFoundError):
        container.storage.get(orphan, 100)
    assert container.storage.get(recent, 100) == b"recent"
    assert container.storage.get(item["object_key"], 100) == referenced_body
