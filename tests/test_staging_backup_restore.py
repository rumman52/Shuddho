from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for backup/restore tests")

from scripts import staging_backup_restore as backup


def test_stable_hash_is_deterministic_and_non_plaintext():
    first = backup.stable_hash("db-host|5432|coworker")
    second = backup.stable_hash("db-host|5432|coworker")
    assert first == second
    assert "db-host" not in first
    assert len(first) == 64


def test_require_guard_is_fail_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", raising=False)
    with pytest.raises(backup.BackupRestoreFailure, match="SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE"):
        backup.require_guard("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE")
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")
    backup.require_guard("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE")


def test_verify_rejects_same_environment_fingerprints(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(
        __import__("json").dumps({"release_id": "backup-restore-test-release"}),
        encoding="utf-8",
    )
    state = {
        "release_context": backup.prepared_release_context(settings, rollout_path),
        "owner_id": "owner",
        "document_id": "doc",
        "version_id": "ver",
        "task_id": "task",
        "sha256": "a" * 64,
        "byte_size": 10,
        "source_fingerprints": {"database": "same-db", "storage": "same-storage"},
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(__import__("json").dumps(state), encoding="utf-8")
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")
    monkeypatch.setattr(backup, "environment_fingerprints", lambda _container: {"database": "same-db", "storage": "new-storage"})

    class Sessions:
        kw = {"bind": SimpleNamespace(dispose=lambda: None)}

    fake = SimpleNamespace(repository=SimpleNamespace(sessions=Sessions()), storage=SimpleNamespace())
    monkeypatch.setattr(backup.Container, "create", lambda _settings: fake)

    with pytest.raises(backup.BackupRestoreFailure, match="isolated restored PostgreSQL"):
        backup.verify(
            settings,
            state_path,
            "backup-run-1",
            "restore-run-1",
            rollout_path,
            tmp_path / "evidence.json",
            None,
        )


def test_verify_requires_non_empty_backup_and_restore_references(monkeypatch, tmp_path):
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")
    with pytest.raises(backup.BackupRestoreFailure, match="Both backup and restore"):
        backup.verify(
            SimpleNamespace(),
            tmp_path / "unused.json",
            "",
            "restore-run-1",
            tmp_path / "rollout.json",
            tmp_path / "evidence.json",
            None,
        )

def _install_prepare_fakes(monkeypatch, calls):
    class Sessions:
        kw = {"bind": SimpleNamespace(dispose=lambda: calls.append("dispose"))}

    class Repository:
        sessions = Sessions()

        def create_upload(self, owner, request):
            calls.append("create_upload")
            return {"id": "upload-id", "version_id": "version-id"}

        def get_upload(self, owner, upload_id):
            calls.append("get_upload")
            return {"object_key": "private-object"}

        def finish_upload(self, owner, upload_id):
            calls.append("finish_upload")

        def create_task(self, owner, request, request_key):
            calls.append("create_task")
            return {"id": "task-id"}, None

        def cancel(self, owner, task_id):
            calls.append("cancel")

    class Storage:
        def put(self, object_key, payload, content_type):
            calls.append("storage_put")

    fake = SimpleNamespace(repository=Repository(), storage=Storage())
    monkeypatch.setattr(
        backup,
        "resolve_owner",
        lambda: calls.append("resolve_owner") or "synthetic-owner",
    )
    monkeypatch.setattr(
        backup.Container,
        "create",
        lambda _settings: calls.append("container_create") or fake,
    )
    monkeypatch.setattr(
        backup,
        "environment_fingerprints",
        lambda _container: {"database": "source-db", "storage": "source-storage"},
    )


def test_prepare_rejects_existing_state_before_staging_mutations(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(
        __import__("json").dumps({"release_id": "backup-restore-test-release"}),
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    state_path.write_text('{"existing":true}', encoding="utf-8")
    calls = []
    _install_prepare_fakes(monkeypatch, calls)
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")

    with pytest.raises(backup.StagingReleaseEvidenceError, match="Refusing to overwrite"):
        backup.prepare(settings, state_path, rollout_path)

    assert calls == []


def test_prepare_rejects_invalid_rollout_before_staging_mutations(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "missing-rollout.json"
    state_path = tmp_path / "state.json"
    calls = []
    _install_prepare_fakes(monkeypatch, calls)
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")

    with pytest.raises(backup.StagingReleaseEvidenceError, match="Could not read rollout manifest"):
        backup.prepare(settings, state_path, rollout_path)

    assert calls == []


def test_prepare_rejects_missing_state_directory_before_staging_mutations(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(
        __import__("json").dumps({"release_id": "backup-restore-test-release"}),
        encoding="utf-8",
    )
    state_path = tmp_path / "missing" / "state.json"
    calls = []
    _install_prepare_fakes(monkeypatch, calls)
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")

    with pytest.raises(backup.StagingReleaseEvidenceError):
        backup.prepare(settings, state_path, rollout_path)

    assert calls == []

