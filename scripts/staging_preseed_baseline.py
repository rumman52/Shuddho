"""Fail-closed, read-only attestation of the original pre-seeding staging state.

This receipt is deliberately separate from the post-synthetic private-task
archive. An empty private bucket is valid for the *original* snapshot only;
it can never demonstrate PDF recovery, owner access or hosted D02.T09 PASS.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from scripts.staging_day2_archive_attestation import (
    ArchiveAttestationFailure,
    _file_sha,
    _hash,
    _inventory,
    _object,
    _private_json,
)
from scripts.staging_object_backup import ObjectArchiveError, _manifest


EXPECTED_SOURCE_REVISION = "0070"
EXPECTED_CODE_HEAD = "0072_merge_0071_heads"


class PreseedBaselineFailure(RuntimeError):
    """Original source archive cannot be matched to a zero-object source."""


def attest_preseed_baseline(
    postgres_verification: Path,
    postgres_archive: Path,
    object_archive: Path,
) -> tuple[dict, dict]:
    """Verify protected original DB/object bytes without contacting any cloud resource."""
    try:
        pg = _private_json(postgres_verification, "Original PostgreSQL backup receipt")
        if pg.get("status") != "verified":
            raise PreseedBaselineFailure("Original PostgreSQL snapshot is not verified.")
        database = _hash(pg.get("source_database_fingerprint"), "Original PostgreSQL identity")
        digest = _hash(pg.get("archive_sha256"), "Original PostgreSQL dump SHA")
        if digest != _file_sha(postgres_archive):
            raise PreseedBaselineFailure("Original PostgreSQL archive bytes do not match receipt.")
        inv = _inventory(pg.get("source"))
        if inv["revision"] != EXPECTED_SOURCE_REVISION:
            raise PreseedBaselineFailure("Original source was not captured at migration 0070.")
        alignment = _object(pg.get("schema_alignment"), "Original migration alignment")
        if (alignment.get("source_revision") != EXPECTED_SOURCE_REVISION
                or alignment.get("code_head") != EXPECTED_CODE_HEAD
                or alignment.get("status") != "migration_required"
                or alignment.get("source_is_current") is not False
                or alignment.get("release_qualified") is not False):
            raise PreseedBaselineFailure("Original PostgreSQL source migration graph is not verified.")
        manifest, archived_objects, manifest_digest = _manifest(object_archive)
        if (manifest["status"] != "baseline_archived"
                or manifest["object_count"] != 0
                or manifest["total_bytes"] != 0
                or archived_objects):
            raise PreseedBaselineFailure(
                "Original object store must be an explicit zero-object pre-seeding baseline."
            )
        storage = _hash(manifest["source_storage_fingerprint"], "Original storage identity")
    except (ArchiveAttestationFailure, ObjectArchiveError, OSError, ValueError, TypeError):
        raise PreseedBaselineFailure("Original PostgreSQL/object baseline evidence is invalid.") from None

    return {
        "status": "preseed_verified",
        "source_schema_revision": inv["revision"],
        "postgres_schema_sha256": inv["schema_sha256"],
        "postgres_archive_sha256": digest,
        "postgres_table_count": len(inv["tables"]),
        "postgres_row_count": sum(row["rows"] for row in inv["tables"].values()),
        "source_database_fingerprint": database,
        "source_storage_fingerprint": storage,
        "object_manifest_sha256": manifest_digest,
        "object_count": 0,
        "object_total_bytes": 0,
    }, inv


def require_unchanged_source(
    summary: dict,
    archived_inventory: dict,
    live_fingerprints: dict,
    live_inventory: dict,
    live_object_inventory: list,
) -> None:
    """Check archive was made before any source mutation, prior to synthetic writes.

    Call with read-only source database inventory obtained under repeatable-read
    and a complete current private object listing. Quiesce writers or take an
    approved cross-system snapshot to avoid concurrent source races.
    """
    if (not isinstance(live_fingerprints, dict)
            or live_fingerprints.get("database") != summary["source_database_fingerprint"]
            or live_fingerprints.get("storage") != summary["source_storage_fingerprint"]):
        raise PreseedBaselineFailure("Original baseline belongs to different source resources.")
    if live_inventory != archived_inventory:
        raise PreseedBaselineFailure(
            "Original source PostgreSQL schema, revision, ACL, table rows or digests changed after snapshot."
        )
    if type(live_object_inventory) is not list or live_object_inventory:
        raise PreseedBaselineFailure(
            "Original private bucket is not empty before synthetic seeding."
        )


def read_original_attestation(path: Path, baseline_summary: dict) -> dict:
    """Rebind an immutable earlier observation to the three original archives.

    The attestation must have been written while the source still equaled the
    archived 0070 schema and empty bucket. Later schema upgrades/rows are
    expected, so the operator must *not* rerun live row equality at task time.
    """
    try:
        receipt = _private_json(path, "Original pre-seeding attestation")
        if (set(receipt) != {"schema_version", "status", "attested_at", "baseline"}
                or type(receipt["schema_version"]) is not int
                or receipt["schema_version"] != 1
                or receipt["status"] != "preseed_verified"
                or receipt["baseline"] != baseline_summary):
            raise PreseedBaselineFailure(
                "Original pre-seeding attestation does not match protected archive bytes."
            )
        timestamp = receipt["attested_at"]
        if not isinstance(timestamp, str):
            raise PreseedBaselineFailure("Original pre-seeding time is missing.")
        observed_at = datetime.fromisoformat(timestamp)
        if observed_at.tzinfo is None or observed_at > datetime.now(timezone.utc):
            raise PreseedBaselineFailure("Original pre-seeding time is invalid or in the future.")
    except (ArchiveAttestationFailure, OSError, ValueError, TypeError):
        raise PreseedBaselineFailure("Original pre-seeding attestation is invalid.") from None
    return {**baseline_summary, "attested_at":timestamp}


def require_same_source_resources(summary: dict, current_fingerprints: dict) -> None:
    """The DB/bucket identities must remain the same even after schema migration."""
    if (not isinstance(current_fingerprints, dict)
            or current_fingerprints.get("database") != summary["source_database_fingerprint"]
            or current_fingerprints.get("storage") != summary["source_storage_fingerprint"]):
        raise PreseedBaselineFailure(
            "Original pre-seeding attestation belongs to different database/storage resources."
        )
