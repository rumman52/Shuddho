"""Read-only Day 2 full archive/restore evidence reconciliation.

This binds existing PostgreSQL and private-object tool receipts to a prepared
source and an isolated target. It authenticates formats, local archive bytes,
manifest hashes and source/target relationships, not cloud operator authority:
an independent reviewer must still check live service histories and receipts.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
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


MAX_PRIVATE_JSON_BYTES = 2_000_000


def _private_json(path: Path, label: str) -> dict:
    """Read one bounded regular inode once; never reopen a prechecked pathname."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ArchiveAttestationFailure(f"{label} requires secure no-follow file reads.")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= MAX_PRIVATE_JSON_BYTES:
                raise ArchiveAttestationFailure(f"{label} is missing, non-regular or oversized.")
            # Files can grow after fstat. Read no more than the hard cap + 1.
            remaining = MAX_PRIVATE_JSON_BYTES + 1
            pieces: list[bytes] = []
            while remaining:
                piece = os.read(descriptor, min(65536, remaining))
                if not piece:
                    break
                pieces.append(piece)
                remaining -= len(piece)
        finally:
            os.close(descriptor)
    except OSError:
        raise ArchiveAttestationFailure(f"{label} is missing, linked or unreadable.") from None
    raw = b"".join(pieces)
    if not 0 < len(raw) <= MAX_PRIVATE_JSON_BYTES:
        raise ArchiveAttestationFailure(f"{label} is empty or exceeds its byte limit.")

    def unique_fields(pairs: list[tuple[str, object]]) -> dict:
        out = {}
        for key, value in pairs:
            if key in out:
                raise ArchiveAttestationFailure(f"{label} contains duplicate JSON keys.")
            out[key] = value
        return out

    def reject_constant(_value: str) -> None:
        raise ArchiveAttestationFailure(f"{label} contains non-finite JSON.")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ArchiveAttestationFailure(f"{label} contains non-finite JSON.")
        return number

    try:
        parsed = json.loads(
            raw.decode("utf-8"), object_pairs_hook=unique_fields,
            parse_constant=reject_constant, parse_float=finite_float,
        )
    except (UnicodeError, ValueError, TypeError, OverflowError):
        raise ArchiveAttestationFailure(f"{label} is not readable JSON.") from None
    return _object(parsed, label)


def _file_sha(path: Path) -> str:
    """Hash a stable PostgreSQL archive inode without trusting a prechecked path.

    Dumps can be large, so digest in chunks. A changed inode during hashing
    cannot attest to one immutable source archive; reject it rather than
    returning a checksum from a mixed or substituted read.
    """
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ArchiveAttestationFailure("Secure no-follow PostgreSQL archive reads are unavailable.")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 1:
            raise ArchiveAttestationFailure("PostgreSQL dump must be a nonempty regular file.")

        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > before.st_size:
                raise ArchiveAttestationFailure("PostgreSQL dump changed while hashing.")
            digest.update(chunk)

        after = os.fstat(descriptor)
        if (total != before.st_size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ArchiveAttestationFailure("PostgreSQL dump changed while hashing.")
        return digest.hexdigest()
    except OSError:
        raise ArchiveAttestationFailure("PostgreSQL dump could not be opened or read safely.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _inventory(value: object) -> dict:
    inv = _object(value, "PostgreSQL source inventory")
    revision = inv.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,128}", revision):
        raise ArchiveAttestationFailure("PostgreSQL source migration revision is invalid.")
    _hash(inv.get("schema_sha256"), "PostgreSQL structural schema SHA-256")
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
    if object_manifest["status"] == "baseline_archived" or not verified_archive:
        raise ArchiveAttestationFailure(
            "An empty pre-seeding baseline does not prove a private PDF/task object restore."
        )
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
        "postgres_schema_sha256": source_inventory["schema_sha256"],
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
