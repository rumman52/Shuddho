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


def test_passed_evidence_shape():
    assert backup.passed("restore drill") == {"status": "passed", "evidence": "restore drill"}


def test_verify_rejects_same_environment_fingerprints(monkeypatch, tmp_path):
    state = {
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
            SimpleNamespace(),
            state_path,
            "backup-run-1",
            "restore-run-1",
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
            tmp_path / "evidence.json",
            None,
        )
