"""Offline Day 2 original-state baseline gate tests.

Synthetic dump/receipts and LocalObjectStore only; no hosted accounts,
data, database server, provider calls or Render deployments.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import staging_preseed_baseline as baseline
from scripts import staging_object_backup as objects
from services.coworker.storage import LocalObjectStore


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(tmp_path: Path):
    db = sha(b"source-database")
    storage = sha(b"source-storage")
    archive = tmp_path / "original.dump"
    archive.write_bytes(b"PGDMP-test-original-staging-schema")
    tables = {f"cw_table_{i:03d}": {"rows": 0, "sha256": sha(b"")} for i in range(83)}
    tables["cw_alembic_version"] = {
        "rows": 1, "sha256": sha(b'{"version_num":"0070"}\n'),
    }
    source = {
        "revision": "0070",
        "schema_sha256": sha(b"source catalog schema"),
        "tables": tables,
        "access_control": {
            "anon_schema_access": False,
            "authenticated_schema_access": False,
            "anon_table_privilege_count": 0,
            "authenticated_table_privilege_count": 0,
            "anon_default_table_privileges": False,
            "authenticated_default_table_privileges": False,
            "rls_enabled_table_count": 0,
        },
    }
    pg = {
        "status": "verified",
        "archive_sha256": sha(archive.read_bytes()),
        "source_database_fingerprint": db,
        "source": source,
        "schema_alignment": {
            "status": "migration_required",
            "source_revision": "0070",
            "code_head": "0073_worker_runtime_identity",
            "source_is_current": False,
            "release_qualified": False,
        },
    }
    receipt = tmp_path / "verification.json"
    receipt.write_text(json.dumps(pg), encoding="utf-8")
    empty_source = LocalObjectStore(tmp_path / "empty-source")
    object_dir = tmp_path / "preseed-object-archive"
    objects.archive_store(empty_source, storage, object_dir, allow_empty_baseline=True)
    return (receipt, archive, object_dir), source, {"database": db, "storage": storage}


def test_preseed_verifier_proves_entire_empty_baseline_and_matches_source(tmp_path):
    paths, source, fingerprints = fixture(tmp_path)
    summary, archived_inventory = baseline.attest_preseed_baseline(*paths)
    assert archived_inventory == source
    assert summary["status"] == "preseed_verified"
    assert summary["source_schema_revision"] == "0070"
    assert summary["postgres_schema_sha256"] == source["schema_sha256"]
    assert summary["postgres_table_count"] == 84
    assert summary["object_count"] == 0
    assert summary["object_total_bytes"] == 0
    assert summary["source_database_fingerprint"] == fingerprints["database"]
    assert summary["source_storage_fingerprint"] == fingerprints["storage"]
    assert len(summary["postgres_archive_sha256"]) == 64
    assert len(summary["object_manifest_sha256"]) == 64
    baseline.require_unchanged_source(
        summary, source, fingerprints, source, [],
    )


@pytest.mark.parametrize("corruption", [
    "postgres_archive", "postgres_fingerprint", "postgres_schema",
    "schema_revision", "missing_table", "postgres_status", "migration_head",
    "nonempty_object_archive", "symlinked_postgres_receipt",
])
def test_preseed_rejects_incomplete_forged_or_nonempty_original(tmp_path, corruption):
    paths, source, fingerprints = fixture(tmp_path)
    receipt, pg_dump, object_dir = paths
    if corruption == "postgres_archive":
        pg_dump.write_bytes(b"changed dump")
    elif corruption == "symlinked_postgres_receipt":
        copy = tmp_path / "receipt-copy.json"
        receipt.rename(copy)
        receipt.symlink_to(copy)
    elif corruption == "nonempty_object_archive":
        source_store = LocalObjectStore(tmp_path / "nonempty-source")
        source_store.put("owner-a/inputs/v1/probe.pdf", b"PDF", "application/pdf")
        nonempty = tmp_path / "nonempty-archive"
        objects.archive_store(source_store, fingerprints["storage"], nonempty)
        paths = (receipt, pg_dump, nonempty)
    else:
        pg = json.loads(receipt.read_text())
        if corruption == "postgres_fingerprint":
            pg["source_database_fingerprint"] = "bad"
        elif corruption == "postgres_schema":
            pg["source"]["schema_sha256"] = "not-sha256"
        elif corruption == "schema_revision":
            pg["source"]["revision"] = "0072_merge_0071_heads"
        elif corruption == "missing_table":
            del pg["source"]["tables"]["cw_table_010"]
        elif corruption == "postgres_status":
            pg["status"] = "prepared"
        else:
            pg["schema_alignment"]["code_head"] = "0071"
        receipt.write_text(json.dumps(pg))
    with pytest.raises(baseline.PreseedBaselineFailure):
        baseline.attest_preseed_baseline(*paths)


@pytest.mark.parametrize("mismatch", [
    "database_resource", "storage_resource", "database_rows", "database_schema",
    "nonempty_live_storage",
])
def test_preseed_refuses_any_changed_live_source(mismatch, tmp_path):
    paths, source, fingerprints = fixture(tmp_path)
    summary, archived = baseline.attest_preseed_baseline(*paths)
    actual_fp = dict(fingerprints)
    actual_inventory = json.loads(json.dumps(source))
    actual_objects = []
    if mismatch == "database_resource":
        actual_fp["database"] = sha(b"wrong database")
    elif mismatch == "storage_resource":
        actual_fp["storage"] = sha(b"wrong bucket")
    elif mismatch == "database_rows":
        actual_inventory["tables"]["cw_table_030"]["rows"] = 1
    elif mismatch == "database_schema":
        actual_inventory["schema_sha256"] = sha(b"tampered catalog")
    else:
        actual_objects = [{"key": "owner-a/private.pdf"}]
    with pytest.raises(baseline.PreseedBaselineFailure):
        baseline.require_unchanged_source(
            summary, archived, actual_fp, actual_inventory, actual_objects,
        )


def test_original_attestation_binds_pre_migration_snapshot_to_later_same_resources(tmp_path):
    paths, _source, resources = fixture(tmp_path)
    summary, _ = baseline.attest_preseed_baseline(*paths)
    receipt = tmp_path / "original-attested.json"
    receipt.write_text(json.dumps({
        "schema_version": 1, "status": "preseed_verified",
        "attested_at": "2026-11-21T08:00:00+00:00",
        "baseline": summary,
    }))
    persisted = baseline.read_original_attestation(receipt, summary)
    assert persisted["attested_at"] == "2026-11-21T08:00:00+00:00"
    baseline.require_same_source_resources(persisted, resources)
    with pytest.raises(baseline.PreseedBaselineFailure, match="different"):
        baseline.require_same_source_resources(
            persisted, {**resources, "database": sha(b"other-host")},
        )


@pytest.mark.parametrize("mutated", ["missing", "incorrect_baseline", "future_time", "no_timezone", "symlink"])
def test_original_attestation_rejects_forged_or_unqualified_receipt(tmp_path, mutated):
    paths, _source, _resources = fixture(tmp_path)
    summary, _ = baseline.attest_preseed_baseline(*paths)
    receipt = tmp_path / "original-attested.json"
    data = {
        "schema_version": 1, "status": "preseed_verified",
        "attested_at": "2026-11-21T08:00:00+00:00", "baseline": summary,
    }
    if mutated == "incorrect_baseline":
        data["baseline"] = {**summary, "postgres_archive_sha256": "0" * 64}
    elif mutated == "future_time":
        data["attested_at"] = "2099-01-01T00:00:00+00:00"
    elif mutated == "no_timezone":
        data["attested_at"] = "2026-11-21T08:00:00"
    if mutated != "missing":
        receipt.write_text(json.dumps(data))
    if mutated == "symlink":
        copy = tmp_path / "real.json"
        receipt.rename(copy)
        receipt.symlink_to(copy)
    with pytest.raises(baseline.PreseedBaselineFailure):
        baseline.read_original_attestation(receipt, summary)
