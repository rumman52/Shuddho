"""Read-only Day 2 full archive/restore evidence reconciliation.

This binds existing PostgreSQL and private-object tool receipts to a prepared
source and an isolated target. It authenticates formats, local archive bytes,
manifest hashes and source/target relationships, not cloud operator authority:
an independent reviewer must still check live service histories and receipts.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from scripts.staging_object_backup import ObjectArchiveError, _manifest


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ACCESS_KEYS = (
    "anon_schema_access", "authenticated_schema_access",
    "anon_table_privilege_count", "authenticated_table_privilege_count",
    "anon_default_table_privileges", "authenticated_default_table_privileges",
)


class ArchiveAttestationFailure(RuntimeError):
    """A source/restore receipt is absent, forged or mutually inconsistent."""


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ArchiveAttestationFailure(f"{label} requires a lowercase SHA-256 digest.")
    return value


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ArchiveAttestationFailure(f"{label} must be a JSON object.")
    return value


def _private_json(path: Path, label: str) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 2_000_000:
        raise ArchiveAttestationFailure(f"{label} is missing, linked or oversized.")
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), label)
    except (OSError, ValueError, UnicodeError) as error:
        raise ArchiveAttestationFailure(f"{label} is not readable JSON.") from None


def _file_sha(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size < 1:
        raise ArchiveAttestationFailure("PostgreSQL dump is missing or linked.")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        raise ArchiveAttestationFailure("PostgreSQL dump could not be read.") from None
    return digest.hexdigest()


def _inventory(value: object) -> dict:
    inv = _object(value, "PostgreSQL source inventory")
    revision = inv.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,128}", revision):
        raise ArchiveAttestationFailure("PostgreSQL source migration revision is invalid.")
    tables = _object(inv.get("tables"), "PostgreSQL table inventory")
    if not 84 <= len(tables) <= 512 or "cw_alembic_version" not in tables:
        raise ArchiveAttestationFailure("PostgreSQL inventory must include all 84+ private tables and migration ledger.")
    for name, value in tables.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ArchiveAttestationFailure("PostgreSQL inventory has an invalid table name.")
        row = _object(value, f"PostgreSQL inventory table {name}")
        if (set(row) != {"rows", "sha256"} or type(row["rows"]) is not int
                or row["rows"] < 0):
            raise ArchiveAttestationFailure("PostgreSQL table count/sha schema is invalid.")
        _hash(row["sha256"], "PostgreSQL table digest")
    if tables["cw_alembic_version"]["rows"] != 1:
        raise ArchiveAttestationFailure("PostgreSQL migration ledger must have exactly one row.")
    acl = _object(inv.get("access_control"), "PostgreSQL source access_control")
    if any(acl.get(key) not in (False, 0) for key in _ACCESS_KEYS):
        raise ArchiveAttestationFailure("PostgreSQL source snapshot exposes private schema grants.")
    if (type(acl.get("rls_enabled_table_count")) is not int
            or acl["rls_enabled_table_count"] < 0):
        raise ArchiveAttestationFailure("PostgreSQL RLS inventory is incomplete.")
    return inv


def attest_archives(
    state: dict,
    target_fingerprints: dict,
    postgres_verification: Path,
    postgres_archive: Path,
    object_archive: Path,
    object_restore_receipt: Path,
) -> tuple[dict, dict, list[dict]]:
    """Validate complete local archive bytes and structured source/target receipts."""
    original = _object(state.get("source_fingerprints"), "Prepared source fingerprints")
    target = _object(target_fingerprints, "Restored environment fingerprints")
    for kind in ("database", "storage"):
        source_value = _hash(original.get(kind), f"source {kind}")
        target_value = _hash(target.get(kind), f"target {kind}")
        if source_value == target_value:
            raise ArchiveAttestationFailure(f"Source and restored {kind} resources must be distinct.")

    pg = _private_json(postgres_verification, "PostgreSQL verification receipt")
    if pg.get("status") != "verified":
        raise ArchiveAttestationFailure("PostgreSQL archive was not independently verified.")
    if _hash(pg.get("source_database_fingerprint"), "PostgreSQL source identity") != original["database"]:
        raise ArchiveAttestationFailure("PostgreSQL archive belongs to a different source database.")
    if _hash(pg.get("archive_sha256"), "PostgreSQL archive sha") != _file_sha(postgres_archive):
        raise ArchiveAttestationFailure("PostgreSQL archive bytes differ from the verification receipt.")
    source_inventory = _inventory(pg.get("source"))
    alignment = _object(pg.get("schema_alignment"), "PostgreSQL schema alignment")
    if (alignment.get("source_revision") != source_inventory["revision"]
            or alignment.get("status") not in ("migration_required", "current")
            or type(alignment.get("source_is_current")) is not bool
            or alignment.get("source_is_current") is not (alignment.get("status") == "current")
            or alignment.get("release_qualified") is not False):
        raise ArchiveAttestationFailure("PostgreSQL migration-graph evidence is inconsistent.")
    if alignment.get("code_head") != "0072_merge_0071_heads":
        raise ArchiveAttestationFailure("PostgreSQL backup was not reconciled with both 0071 parents and the 0072 code head.")

    try:
        object_manifest, verified_archive, object_manifest_sha = _manifest(object_archive)
    except (ObjectArchiveError, OSError, ValueError) as error:
        raise ArchiveAttestationFailure("Private source object archive bytes or manifest are invalid.") from None
    if object_manifest["source_storage_fingerprint"] != original["storage"]:
        raise ArchiveAttestationFailure("Private object archive belongs to a different source storage.")
    restored = _private_json(object_restore_receipt, "Private object restore receipt")
    if (type(restored.get("schema_version")) is not int
            or restored["schema_version"] != 1 or restored.get("status") != "verified"
            or restored.get("source_manifest_sha256") != object_manifest_sha
            or restored.get("source_storage_fingerprint") != original["storage"]
            or restored.get("target_storage_fingerprint") != target["storage"]):
        raise ArchiveAttestationFailure("Private object restore receipt does not match the isolated archive and target.")
    objects = [{"key": row["key"], "byte_size": row["byte_size"], "sha256": row["sha256"]}
               for row, _ in verified_archive]
    if (type(restored.get("object_count")) is not int
            or restored["object_count"] != len(objects)
            or type(restored.get("total_bytes")) is not int
            or restored["total_bytes"] != object_manifest["total_bytes"]
            or restored.get("objects") != objects):
        raise ArchiveAttestationFailure("Private object restore inventory does not match every archived byte.")

    summary = {
        "status": "verified",
        "source_schema_revision": source_inventory["revision"],
        "postgres_archive_sha256": pg["archive_sha256"],
        "postgres_table_count": len(source_inventory["tables"]),
        "postgres_row_count": sum(row["rows"] for row in source_inventory["tables"].values()),
        "source_database_fingerprint": original["database"],
        "target_database_fingerprint": target["database"],
        "object_manifest_sha256": object_manifest_sha,
        "object_count": len(objects),
        "object_total_bytes": object_manifest["total_bytes"],
        "source_storage_fingerprint": original["storage"],
        "target_storage_fingerprint": target["storage"],
    }
    return summary, source_inventory, objects
