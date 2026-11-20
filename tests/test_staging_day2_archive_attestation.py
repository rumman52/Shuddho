"""Offline tests for the Day 2 full archive/restore receipt binding.

Uses only disposable LocalObjectStore bytes and synthetic PostgreSQL receipts.
No hosted Supabase, model, Temporal or Render operation occurs here.
"""
from __future__ import annotations

import hashlib
import json
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
        "revision": "0070", "tables": tables,
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


def test_symlink_receipt_rejected(tmp_path):
    state, target, paths, _ = _fixtures(tmp_path)
    link = tmp_path / "linked-receipt.json"
    link.symlink_to(paths[0])
    with pytest.raises(attest.ArchiveAttestationFailure):
        _check(state, target, (link, *paths[1:]))
