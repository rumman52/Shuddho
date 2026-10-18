from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for retention tests")
from sqlalchemy import select

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


def _crash_test_renderer(_draft, _sources, **_options):
    return [("crash-boundary.txt", "text/plain", b"written before hard worker loss")]


def _export_worker_blocked_after_put(settings, task_id, put_ready, release):
    """Child-process target: persist one blob, then wait to be SIGKILLed."""
    import asyncio

    from services.coworker.container import Container
    from services.coworker.runner import DocumentRunner

    value = Container.create(settings)
    wrapped = value.storage

    class BlockingStore:
        def put(self, key, data, content_type):
            result = wrapped.put(key, data, content_type)
            put_ready.set()
            release.wait(60)
            return result

        def __getattr__(self, name):
            return getattr(wrapped, name)

    value.storage = BlockingStore()
    try:
        asyncio.run(DocumentRunner(value, renderer=_crash_test_renderer).phase(task_id, "export"))
    finally:
        value.repository.sessions.kw["bind"].dispose()


def test_hard_worker_loss_after_object_put_is_reconciled_without_deleting_checkpointed_outputs(container):
    """A SIGKILL after PUT leaves an orphan; age-bounded cleanup deletes only unreferenced bytes."""
    import asyncio
    import multiprocessing
    import signal

    from test_coworker import FakeModel
    from services.coworker.runner import DocumentRunner

    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("Hard worker-loss test requires POSIX fork semantics")

    account_id = owner(container, "orphan-after-worker-loss")
    task, _ = container.repository.create_task(
        account_id,
        TaskCreate(
            instruction="Create a crash-recovery report.",
            notes="This export is synthetic test data.",
            output_language="en",
        ),
        "orphan-after-worker-loss-task",
    )

    # A second, already-checkpointed object under the same owner prefix must
    # survive the sweep even when it is old enough to be an orphan candidate.
    checkpoint_task, _ = container.repository.create_task(
        account_id,
        TaskCreate(
            instruction="Preserve the durable export checkpoint.",
            notes="This object is referenced by a saved export step.",
            output_language="en",
        ),
        "checkpointed-output-preservation-task",
    )
    checkpoint_body = b"durable checkpoint output"
    checkpoint_digest = hashlib.sha256(checkpoint_body).hexdigest()
    checkpoint_key = (
        f"{account_id}/outputs/{checkpoint_task['id']}/"
        f"{checkpoint_digest}/checkpoint.txt"
    )
    container.storage.put(checkpoint_key, checkpoint_body, "text/plain")
    container.repository.save_step(checkpoint_task["id"], "export", {
        "artifacts": [{
            "filename": "checkpoint.txt",
            "content_type": "text/plain",
            "object_key": checkpoint_key,
            "byte_size": len(checkpoint_body),
            "sha256": checkpoint_digest,
        }],
    })

    runner = DocumentRunner(container, FakeModel())
    asyncio.run(runner.phase(task["id"], "extract"))
    asyncio.run(runner.phase(task["id"], "draft"))

    context = multiprocessing.get_context("fork")
    put_ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_export_worker_blocked_after_put,
        args=(container.settings, task["id"], put_ready, release),
    )
    process.start()
    try:
        assert put_ready.wait(20), "Export worker did not persist an object before the crash boundary"
        prefix = f"{account_id}/outputs/{task['id']}/"
        stored = container.storage.inventory(prefix=prefix)
        assert len(stored) == 1
        orphan_key = stored[0].key
        assert container.repository.step(task["id"], "export") is None

        # SIGKILL bypasses the export exception handler and its best-effort cleanup.
        os.kill(process.pid, signal.SIGKILL)
        process.join(10)
        assert not process.is_alive()
        assert process.exitcode == -signal.SIGKILL
        assert container.storage.get(orphan_key, 1024) == b"written before hard worker loss"

        # Simulate the object becoming eligible for the existing age-bounded sweep.
        old_time = time.time() - 7200
        os.utime(container.storage.path(orphan_key), (old_time, old_time))
        os.utime(container.storage.path(checkpoint_key), (old_time, old_time))
        preview = container.retention.cleanup_orphans(
            prefix=account_id, min_age_seconds=3600, dry_run=True,
        )
        assert {item["key"] for item in preview["candidates"]} == {orphan_key}
        assert checkpoint_key not in {item["key"] for item in preview["candidates"]}
        assert preview["deleted"] == 0

        result = container.retention.cleanup_orphans(
            prefix=account_id, min_age_seconds=3600, dry_run=False,
        )
        assert result["deleted"] == 1
        assert result["failed"] == []
        with pytest.raises(FileNotFoundError):
            container.storage.get(orphan_key, 1024)
        assert container.storage.get(checkpoint_key, 1024) == checkpoint_body
    finally:
        if process.is_alive():
            os.kill(process.pid, signal.SIGKILL)
            process.join(10)
