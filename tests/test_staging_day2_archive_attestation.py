"""Offline tests for the Day 2 full archive/restore receipt binding.

Uses only disposable LocalObjectStore bytes and synthetic PostgreSQL receipts.
No hosted Supabase, model, Temporal or Render operation occurs here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy", reason="Install coworker extra for staging archive tests")

from scripts import staging_backup_restore as backup
from scripts import staging_day2_archive_attestation as attest
from scripts import staging_object_backup as objects
from services.coworker.storage import LocalObjectStore


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fixtures(tmp_path: Path) -> tuple[dict, dict, tuple[Path, Path, Path, Path], dict]:
    source_database = _sha(b"source-database")
    source_storage = _sha(b"source-storage")
    target_database = _sha(b"target-database")
    target_storage = _sha(b"target-storage")
    state = {"source_fingerprints": {"database": source_database, "storage": source_storage}}
    target = {"database": target_database, "storage": target_storage}

    archive = tmp_path / "postgres.dump"
    archive.write_bytes(b"PGDMP synthetic private schema snapshot\n")
    tables = {f"cw_table_{n:03d}": {"rows": 0, "sha256": _sha(b"")}
              for n in range(83)}
    tables["cw_alembic_version"] = {"rows": 1, "sha256": _sha(b'{"version_num": "0070"}\n')}
    source = {
        "revision": "0070", "tables": tables, "schema_sha256": _sha(b"catalog schema"),
        "access_control": {
            "anon_schema_access": False, "authenticated_schema_access": False,
            "anon_table_privilege_count": 0, "authenticated_table_privilege_count": 0,
            "anon_default_table_privileges": False,
            "authenticated_default_table_privileges": False,
            "rls_enabled_table_count": 0,
        },
    }
    pg = {
        "status": "verified",
        "archive_sha256": _sha(archive.read_bytes()),
        "source_database_fingerprint": source_database,
        "source": source,
        "schema_alignment": {
            "status": "migration_required", "source_revision": "0070",
            "code_head": "0072_merge_0071_heads", "source_is_current": False,
            "release_qualified": False,
        },
    }
    postgres_receipt = tmp_path / "verification.json"
    postgres_receipt.write_text(json.dumps(pg), encoding="utf-8")

    storage_source = LocalObjectStore(tmp_path / "source-store")
    payload = b"%PDF-1.4\nsynthetic private source\n%%EOF\n"
    key = "owner-a/documents/example/source.pdf"
    storage_source.put(key, payload, "application/pdf")
    object_archive = tmp_path / "object-archive"
    objects.archive_store(storage_source, source_storage, object_archive)
    storage_target = LocalObjectStore(tmp_path / "target-store")
    object_receipt = tmp_path / "object-restore.json"
    objects.restore_store(storage_target, target_storage, object_archive, object_receipt)
    return state, target, (postgres_receipt, archive, object_archive, object_receipt), {
        "source": source, "key": key, "sha256": _sha(payload), "byte_size": len(payload),
    }


def _check(state, target, paths):
    return attest.attest_archives(state, target, *paths)


def test_source_snapshot_and_all_object_bytes_are_bound_to_isolated_targets(tmp_path):
    state, target, paths, expected = _fixtures(tmp_path)
    summary, inventory, restored_objects = _check(state, target, paths)
    assert inventory == expected["source"]
    assert summary["status"] == "verified"
    assert summary["postgres_table_count"] == 84
    assert summary["postgres_row_count"] == 1
    assert summary["source_schema_revision"] == "0070"
    assert summary["postgres_archive_sha256"] == _sha(paths[1].read_bytes())
    assert summary["postgres_schema_sha256"] == expected["source"]["schema_sha256"]
    assert summary["object_count"] == 1
    assert summary["object_total_bytes"] == expected["byte_size"]
    assert restored_objects == [{"key": expected["key"], "byte_size": expected["byte_size"],
                                 "sha256": expected["sha256"]}]


@pytest.mark.parametrize("changed", [
    "missing_pg_receipt", "changed_pg_archive", "wrong_source_database",
    "wrong_pg_inventory", "wrong_schema_alignment", "missing_pg_table",
    "wrong_object_manifest", "wrong_source_storage", "wrong_target_storage",
    "missing_restored_object", "changed_object_archive",
])
def test_corrupt_or_unrelated_backup_evidence_fails_closed(tmp_path, changed):
    state, target, paths, expected = _fixtures(tmp_path)
    pg_path, pg_archive, object_archive, object_receipt = paths
    if changed == "missing_pg_receipt":
        pg_path.unlink()
    elif changed == "changed_pg_archive":
        pg_archive.write_bytes(b"PGDMP modified\n")
    elif changed in {"wrong_source_database", "wrong_pg_inventory", "wrong_schema_alignment",
                     "missing_pg_table"}:
        pg = json.loads(pg_path.read_text())
        if changed == "wrong_source_database":
            pg["source_database_fingerprint"] = _sha(b"different-database")
        elif changed == "wrong_pg_inventory":
            pg["source"]["tables"]["cw_table_001"]["sha256"] = "not-a-digest"
        elif changed == "wrong_schema_alignment":
            pg["schema_alignment"]["source_revision"] = "0072_merge_0071_heads"
        else:
            del pg["source"]["tables"]["cw_alembic_version"]
        pg_path.write_text(json.dumps(pg))
    elif changed in {"wrong_object_manifest", "wrong_source_storage", "wrong_target_storage", "missing_restored_object"}:
        value = json.loads(object_receipt.read_text())
        if changed == "wrong_object_manifest":
            value["source_manifest_sha256"] = _sha(b"other-manifest")
        elif changed == "wrong_source_storage":
            value["source_storage_fingerprint"] = _sha(b"other-source")
        elif changed == "wrong_target_storage":
            value["target_storage_fingerprint"] = state["source_fingerprints"]["storage"]
        else:
            value["objects"] = []
        object_receipt.write_text(json.dumps(value))
    else:
        manifest = json.loads((object_archive / "manifest.json").read_text())
        (object_archive / "objects" / manifest["objects"][0]["file"]).write_bytes(b"corrupted")

    with pytest.raises(attest.ArchiveAttestationFailure):
        _check(state, target, paths)


@pytest.mark.parametrize("reused", ["database", "storage"])
def test_same_source_and_target_never_qualify_as_isolated_restore(tmp_path, reused):
    state, target, paths, _ = _fixtures(tmp_path)
    target[reused] = state["source_fingerprints"][reused]
    with pytest.raises(attest.ArchiveAttestationFailure, match="distinct"):
        _check(state, target, paths)


@pytest.mark.parametrize("broken_schema", [None, "", "not-a-digest", 17])
def test_postgres_archive_rejects_missing_or_forged_schema_digest(tmp_path, broken_schema):
    state, target, paths, _ = _fixtures(tmp_path)
    verification = json.loads(paths[0].read_text())
    if broken_schema is None:
        del verification["source"]["schema_sha256"]
    else:
        verification["source"]["schema_sha256"] = broken_schema
    paths[0].write_text(json.dumps(verification))
    with pytest.raises(attest.ArchiveAttestationFailure, match="schema"):
        _check(state, target, paths)


def test_symlink_receipt_rejected(tmp_path):
    state, target, paths, _ = _fixtures(tmp_path)
    link = tmp_path / "linked-receipt.json"
    link.symlink_to(paths[0])
    with pytest.raises(attest.ArchiveAttestationFailure):
        _check(state, target, (link, *paths[1:]))


def test_preseed_zero_object_baseline_is_never_private_task_restore_proof(tmp_path):
    state, target, paths, _ = _fixtures(tmp_path)
    empty_source = LocalObjectStore(tmp_path / "preseed-source")
    baseline = tmp_path / "preseed-empty-archive"
    objects.archive_store(
        empty_source, state["source_fingerprints"]["storage"],
        baseline, allow_empty_baseline=True,
    )
    empty_target = LocalObjectStore(tmp_path / "preseed-target")
    receipt = tmp_path / "preseed-restore-receipt.json"
    objects.restore_store(
        empty_target, target["storage"], baseline, receipt,
        allow_empty_baseline=True,
    )
    with pytest.raises(attest.ArchiveAttestationFailure, match="baseline"):
        _check(state, target, (paths[0], paths[1], baseline, receipt))

# These tests guard the common private-receipt reader used by both source
# pre-seeding and the archive/isolated-restore qualification gate.
def test_private_receipt_reader_rejects_symlink_substitution_at_open(tmp_path, monkeypatch):
    submitted = tmp_path / "submitted.json"
    target = tmp_path / "other.json"
    submitted.write_text('{"status":"reviewed"}', encoding="utf-8")
    target.write_text('{"status":"substituted"}', encoding="utf-8")
    actual_open = os.open
    swapped = False

    def swap_at_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == submitted and not swapped:
            swapped = True
            submitted.unlink()
            submitted.symlink_to(target)
        return actual_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_at_open)
    with pytest.raises(attest.ArchiveAttestationFailure):
        attest._private_json(submitted, "Private archive evidence")
    assert swapped


def test_private_receipt_reader_rejects_same_inode_growth_after_size_check(tmp_path, monkeypatch):
    receipt = tmp_path / "receipt.json"
    original = b'{"status":"verified"}'
    receipt.write_bytes(original)
    actual_read = os.read
    grew = False

    def expand_before_read(fd, size):
        nonlocal grew
        if not grew:
            grew = True
            receipt.write_bytes(original + b" " * 2_000_001)
        return actual_read(fd, size)

    monkeypatch.setattr(os, "read", expand_before_read)
    with pytest.raises(attest.ArchiveAttestationFailure):
        attest._private_json(receipt, "Private archive evidence")
    assert grew


@pytest.mark.parametrize("payload", [
    '{"status":"wrong","status":"verified"}',
    '{"status":"verified","nested":{"owner":"a","owner":"b"}}',
    '{"status":"verified","distance":NaN}',
    '{"status":"verified","distance":1e999}',
])
def test_private_receipt_reader_rejects_ambiguous_or_nonfinite_json(tmp_path, payload):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(payload, encoding="utf-8")
    with pytest.raises(attest.ArchiveAttestationFailure):
        attest._private_json(receipt, "Private archive evidence")



# The PostgreSQL binary dump (unlike bounded JSON receipts) can be large.
# Its identity must be bound to a regular, stable inode, not prechecked path.
def test_postgres_dump_hash_refuses_symlink_swap_at_descriptor_open(tmp_path, monkeypatch):
    submitted = tmp_path / "source.dump"
    replacement = tmp_path / "replacement.dump"
    submitted.write_bytes(b"PGDMP original verified contents")
    replacement.write_bytes(b"PGDMP unrelated contents")
    original_open = os.open
    swapped = False

    def change_path_at_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == submitted and not swapped:
            swapped = True
            submitted.unlink()
            submitted.symlink_to(replacement)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", change_path_at_open)
    with pytest.raises(attest.ArchiveAttestationFailure):
        attest._file_sha(submitted)
    assert swapped


@pytest.mark.parametrize("mutation", ["append", "overwrite_same_length"])
def test_postgres_dump_hash_rejects_mutation_during_stream(
    tmp_path, monkeypatch, mutation,
):
    archive = tmp_path / "source.dump"
    original = b"PGDMP original contents"
    archive.write_bytes(original)
    real_read = os.read
    mutated = False

    def change_bytes_at_first_read(fd, size):
        nonlocal mutated
        if not mutated:
            mutated = True
            if mutation == "append":
                with archive.open("ab") as handle:
                    handle.write(b" extra")
            else:
                archive.write_bytes(b"PGDMP updated!!contents")
                assert archive.stat().st_size == len(original)
        return real_read(fd, size)

    monkeypatch.setattr(os, "read", change_bytes_at_first_read)
    with pytest.raises(attest.ArchiveAttestationFailure, match="changed"):
        attest._file_sha(archive)
    assert mutated


def test_postgres_dump_hash_does_not_reopen_prechecked_path(tmp_path, monkeypatch):
    archive = tmp_path / "source.dump"
    unrelated = tmp_path / "other.dump"
    original = b"PGDMP identity-bound bytes"
    archive.write_bytes(original)
    unrelated.write_bytes(b"PGDMP unrelated bytes")
    actual_path_open = Path.open

    def swap_before_legacy_read(path, mode="r", *args, **kwargs):
        if path == archive and mode == "rb":
            archive.unlink()
            archive.symlink_to(unrelated)
        return actual_path_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swap_before_legacy_read)
    assert attest._file_sha(archive) == _sha(original)
