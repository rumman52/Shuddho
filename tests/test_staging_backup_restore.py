from __future__ import annotations

import json
import stat
from pathlib import Path
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


@pytest.fixture
def restore_state(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(
        json.dumps({"release_id": "backup-restore-test-release"}),
        encoding="utf-8",
    )
    database = backup.stable_hash("source-db")
    storage = backup.stable_hash("source-storage")
    state = {
        "release_context": backup.prepared_release_context(settings, rollout_path),
        "owner_id": "owner",
        "document_id": "doc",
        "version_id": "ver",
        "task_id": "task",
        "sha256": "a" * 64,
        "byte_size": 10,
        "source_fingerprints": {"database": database, "storage": storage},
    }
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")
    return settings, rollout_path, state


@pytest.mark.parametrize(
    "fingerprints",
    [
        None,
        {},
        {"database": "1" * 64},
        {"storage": "2" * 64},
        {"database": "1" * 63, "storage": "2" * 64},
        {"database": "1" * 64, "storage": "G" * 64},
        {"database": "1" * 64, "storage": "A" * 64},
        {"database": 1, "storage": "2" * 64},
    ],
)
def test_verify_rejects_invalid_source_fingerprints_before_target_access(
    monkeypatch, tmp_path, restore_state, fingerprints,
):
    settings, rollout_path, state = restore_state
    state["source_fingerprints"] = fingerprints
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    evidence_path = tmp_path / "evidence.json"
    monkeypatch.setattr(
        backup.Container, "create", lambda _settings: pytest.fail("restore target opened")
    )

    with pytest.raises(backup.BackupRestoreFailure, match="source environment fingerprints"):
        backup.verify(
            settings, state_path, "backup-run-1", "restore-run-1", rollout_path, evidence_path, None
        )

    assert not evidence_path.exists()


@pytest.mark.parametrize(
    ("same_resource", "error"),
    [
        ("database", "isolated restored PostgreSQL"),
        ("storage", "isolated restored object-storage"),
    ],
)
def test_verify_rejects_each_original_resource(
    monkeypatch, tmp_path, restore_state, same_resource, error,
):
    settings, rollout_path, state = restore_state
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    evidence_path = tmp_path / "evidence.json"
    target = {"database": backup.stable_hash("target-db"), "storage": backup.stable_hash("target-storage")}
    target[same_resource] = state["source_fingerprints"][same_resource]
    monkeypatch.setattr(backup, "environment_fingerprints", lambda _container: target)
    disposed = []

    class Sessions:
        kw = {"bind": SimpleNamespace(dispose=lambda: disposed.append(True))}

    fake = SimpleNamespace(repository=SimpleNamespace(sessions=Sessions()), storage=SimpleNamespace())
    monkeypatch.setattr(backup.Container, "create", lambda _settings: fake)

    with pytest.raises(backup.BackupRestoreFailure, match=error):
        backup.verify(
            settings,
            state_path,
            "backup-run-1",
            "restore-run-1",
            rollout_path,
            evidence_path,
            None,
        )

    assert disposed == [True]
    assert not evidence_path.exists()


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

def test_prepare_requires_original_snapshot_before_opening_staging_or_seeding(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout = tmp_path / "rollout.json"
    rollout.write_text(json.dumps({"release_id": "baseline-required-release"}))
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")
    monkeypatch.setattr(
        backup.Container, "create",
        lambda _: pytest.fail("Must validate original-state backup before opening staging"),
    )
    with pytest.raises(backup.BackupRestoreFailure, match="original.*baseline"):
        backup.prepare(settings, state_path, rollout)
    assert not state_path.exists()


def _install_prepare_fakes(monkeypatch, calls):
    class Sessions:
        kw = {"bind": SimpleNamespace(dispose=lambda: calls.append("dispose"))}

    class Repository:
        sessions = Sessions()

        def create_upload(self, owner, request):
            calls.append("create_upload")
            return {"id": "00000000-0000-4000-8000-000000000001", "version_id": "00000000-0000-4000-8000-000000000002"}

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
        lambda _container: {
            "database": backup.stable_hash("source-db"),
            "storage": backup.stable_hash("source-storage"),
        },
    )


def _install_original_baseline_fakes(monkeypatch, *, changed_source=False):
    source = {
        "revision": "0070", "schema_sha256": "c" * 64,
        "tables": {"cw_alembic_version": {"rows": 1, "sha256": "d" * 64}},
    }
    summary = {
        "status": "preseed_verified", "source_schema_revision": "0070",
        "postgres_archive_sha256": "a" * 64,
        "postgres_schema_sha256": "c" * 64,
        "object_manifest_sha256": "b" * 64,
        "postgres_table_count": 84, "postgres_row_count": 1,
        "source_database_fingerprint": backup.stable_hash("source-db"),
        "source_storage_fingerprint": backup.stable_hash("source-storage"),
        "object_count": 0, "object_total_bytes": 0,
    }
    monkeypatch.setattr(backup, "attest_preseed_baseline", lambda *_: (summary, source))
    monkeypatch.setattr(
        backup, "restored_database_inventory",
        lambda _: {**source, "schema_sha256": "changed"} if changed_source else source,
    )
    monkeypatch.setattr(backup, "private_object_inventory", lambda _: [])
    return {
        "original_postgres_verification": Path("fake-original-verification.json"),
        "original_postgres_archive": Path("fake-original.dump"),
        "original_object_archive": Path("fake-empty-baseline"),
    }


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


def test_prepare_does_not_seed_records_if_source_identity_read_fails(
    monkeypatch, tmp_path, restore_state,
):
    settings, rollout_path, _state = restore_state
    state_path = tmp_path / "state.json"
    calls = []
    _install_prepare_fakes(monkeypatch, calls)

    def fail_identity_read(_container):
        raise backup.BackupRestoreFailure("source identity unavailable")

    monkeypatch.setattr(backup, "environment_fingerprints", fail_identity_read)
    baseline_paths = _install_original_baseline_fakes(monkeypatch)

    with pytest.raises(backup.BackupRestoreFailure, match="source identity unavailable"):
        backup.prepare(settings, state_path, rollout_path, **baseline_paths)

    assert calls == ["container_create", "dispose"]
    assert not state_path.exists()


def test_prepare_preflights_state_destination_before_staging_mutations(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(
        json.dumps({"release_id": "backup-restore-test-release"}),
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    calls = []
    _install_prepare_fakes(monkeypatch, calls)
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")

    baseline_paths = _install_original_baseline_fakes(monkeypatch)
    original_writer = backup.write_private_json
    write_phases = []

    def record_write(path, value):
        write_phases.append(("preflight" if not calls else "after_remote", path))
        original_writer(path, value)

    monkeypatch.setattr(backup, "write_private_json", record_write)

    result = backup.prepare(settings, state_path, rollout_path, **baseline_paths)

    assert write_phases[0][0] == "preflight"
    assert write_phases[0][1] != state_path
    assert write_phases[-1] == ("after_remote", state_path)
    assert result["document_id"] == "00000000-0000-4000-8000-000000000001"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["release_context"]["release_id"] == "backup-restore-test-release"
    assert state["preseed_baseline"]["status"] == "preseed_verified"
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".state.json.*.preflight"))


def test_prepare_refuses_stale_original_snapshot_before_owner_api_or_object_write(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps({"release_id": "baseline-test"}))
    state_path = tmp_path / "state.json"
    calls = []
    _install_prepare_fakes(monkeypatch, calls)
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")
    paths = _install_original_baseline_fakes(monkeypatch, changed_source=True)

    with pytest.raises(backup.PreseedBaselineFailure, match="changed"):
        backup.prepare(settings, state_path, rollout_path, **paths)
    assert calls == ["container_create", "dispose"]
    assert not state_path.exists()


def test_verify_demands_original_baseline_before_reading_task_rows(monkeypatch, tmp_path, restore_state):
    settings, rollout_path, state = restore_state
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    target = {
        "database": backup.stable_hash("other-db"),
        "storage": backup.stable_hash("other-storage"),
    }
    monkeypatch.setattr(backup, "environment_fingerprints", lambda _: target)
    disposed = []
    fake = SimpleNamespace(
        repository=SimpleNamespace(sessions=SimpleNamespace(
            kw={"bind": SimpleNamespace(dispose=lambda: disposed.append(True))},
        )),
    )
    monkeypatch.setattr(backup.Container, "create", lambda _: fake)
    monkeypatch.setattr(
        backup, "restored_database_inventory",
        lambda _: pytest.fail("Target SQL rows must not be read without original baseline"),
    )
    with pytest.raises(backup.BackupRestoreFailure, match="original.*baseline"):
        backup.verify(
            settings, state_path, "backup-ref", "restore-ref",
            rollout_path, tmp_path / "receipt.json", None,
            postgres_verification=tmp_path / "task-verification.json",
            postgres_archive=tmp_path / "task.dump",
            object_archive=tmp_path / "task-objects",
            object_restore_receipt=tmp_path / "task-restore.json",
        )
    assert disposed == [True]
    assert not (tmp_path / "receipt.json").exists()


def test_prepare_rejects_symlink_state_path_before_staging_mutations(monkeypatch, tmp_path):
    settings = SimpleNamespace(source_revision="a" * 40)
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(
        json.dumps({"release_id": "backup-restore-test-release"}),
        encoding="utf-8",
    )
    target_path = tmp_path / "existing.json"
    target_path.write_text('{"existing":true}', encoding="utf-8")
    state_path = tmp_path / "state.json"
    state_path.symlink_to(target_path)
    calls = []
    _install_prepare_fakes(monkeypatch, calls)
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", "true")

    with pytest.raises(backup.StagingReleaseEvidenceError, match="Refusing to overwrite"):
        backup.prepare(settings, state_path, rollout_path)

    assert calls == []
    assert target_path.read_text(encoding="utf-8") == '{"existing":true}'




def test_full_archive_receipts_are_mandatory_before_restored_sql_reads(monkeypatch, tmp_path, restore_state):
    settings, rollout_path, state = restore_state
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    target = {"database": backup.stable_hash("different-db"),
              "storage": backup.stable_hash("different-storage")}
    monkeypatch.setattr(backup, "environment_fingerprints", lambda _container: target)

    disposed = []
    class Sessions:
        kw = {"bind": SimpleNamespace(dispose=lambda: disposed.append(True))}

    fake = SimpleNamespace(repository=SimpleNamespace(sessions=Sessions()), storage=SimpleNamespace())
    monkeypatch.setattr(backup.Container, "create", lambda _: fake)
    monkeypatch.setattr(
        backup, "restored_database_inventory",
        lambda _: pytest.fail("Unqualified restore may not inspect database rows"),
    )

    with pytest.raises(backup.BackupRestoreFailure, match="mandatory"):
        backup.verify(
            settings, state_path, "reference", "reference", rollout_path,
            tmp_path / "receipt.json", None,
        )
    assert disposed == [True]
    assert not (tmp_path / "receipt.json").exists()


def test_restored_database_readback_is_repeatable_read_and_read_only(monkeypatch):
    from scripts import staging_postgres_backup as postgres

    operations = []
    class Database:
        def execute(self, command):
            operations.append(command)
        def rollback(self):
            operations.append("rollback")

    dbapi = Database()
    class Proxy:
        driver_connection = dbapi
        def close(self):
            operations.append("close")

    class Engine:
        def raw_connection(self):
            return Proxy()

    fake = SimpleNamespace(repository=SimpleNamespace(
        sessions=SimpleNamespace(kw={"bind": Engine()}),
    ))
    expected = {"revision": "0070", "tables": {"cw_alembic_version": {"rows": 1}}}
    monkeypatch.setattr(postgres, "inventory", lambda connection:
                        operations.append("inventory") or expected
                        if connection is dbapi else pytest.fail("unrelated connection"))
    assert backup.restored_database_inventory(fake) == expected
    assert operations == [
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
        "inventory", "rollback", "close",
    ]
