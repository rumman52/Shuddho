"""Guarded private-object byte archive and isolated restore (Day 2 D02.T09).

This utility does not back up PostgreSQL, authenticate API owners, or certify
hosted acceptance. The test-callable functions operate only on supplied stores;
the CLI explicitly requires the authorized staging/S3 environment.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
import stat
from pathlib import Path
import re
import uuid

from scripts.staging_release_evidence import StagingReleaseEvidenceError, write_private_json
from services.coworker.storage import S3ObjectStore, make_storage, validate_key


SCHEMA_VERSION = 1
MAX_OBJECT_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_OBJECTS = 10_000
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ObjectArchiveError(RuntimeError):
    pass


def _sha(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def storage_fingerprint(settings) -> str:
    """Same endpoint/bucket identity used by the existing restore drill."""
    return _sha("|".join((
        settings.storage_backend,
        settings.storage_endpoint or "",
        settings.storage_bucket,
        settings.storage_region,
    )).encode("utf-8"))


def _fingerprint(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ObjectArchiveError(f"{label} requires a lowercase SHA-256 fingerprint.")
    return value


def _inventory(store) -> list[dict]:
    try:
        items = store.inventory()
    except Exception:
        raise ObjectArchiveError("Private object inventory could not be read.") from None
    if not isinstance(items, list) or len(items) > MAX_OBJECTS:
        raise ObjectArchiveError("Private object inventory exceeds the allowed count or is malformed.")
    rows = []
    seen: set[str] = set()
    total_bytes = 0
    for item in items:
        try:
            key = validate_key(item.key)
            size = item.byte_size
            modified = item.modified_at
        except (AttributeError, TypeError, ValueError):
            raise ObjectArchiveError("Private object inventory contains a malformed key or record.") from None
        if key in seen:
            raise ObjectArchiveError("Private object inventory contains duplicate keys.")
        if type(size) is not int or size < 0 or size > MAX_OBJECT_BYTES:
            raise ObjectArchiveError("Private object exceeds the allowed maximum byte size.")
        if not isinstance(modified, datetime) or modified.tzinfo is None:
            raise ObjectArchiveError("Private object inventory has no timezone-aware modification time.")
        seen.add(key)
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise ObjectArchiveError("Private object inventory total exceeds the allowed archive size.")
        rows.append({
            "key": key,
            "byte_size": size,
            "modified_at": modified.astimezone(timezone.utc).isoformat(),
        })
    return sorted(rows, key=lambda row: row["key"])


def _mime(store, key: str, expected_size: int) -> tuple[str, str | None]:
    if not isinstance(store, S3ObjectStore):
        return "application/octet-stream", None
    try:
        response = store.client.head_object(Bucket=store.bucket, Key=key)
    except Exception:
        raise ObjectArchiveError("Private S3 object metadata could not be read.") from None
    content_type = response.get("ContentType")
    content_length = response.get("ContentLength")
    metadata = response.get("Metadata") or {}
    if (not isinstance(content_type, str) or "/" not in content_type
            or len(content_type) > 200 or any(ord(ch) < 32 for ch in content_type)
            or type(content_length) is not int or content_length != expected_size
            or not isinstance(metadata, dict)):
        raise ObjectArchiveError("Private S3 object content type or size is inconsistent.")
    asserted_sha = metadata.get("sha256")
    if asserted_sha is not None and (not isinstance(asserted_sha, str)
                                     or _DIGEST.fullmatch(asserted_sha) is None):
        raise ObjectArchiveError("Private S3 SHA-256 metadata is malformed.")
    return content_type, asserted_sha


def _get(store, key: str, size: int, *, label: str) -> bytes:
    try:
        data = store.get(key, size)
    except Exception:
        raise ObjectArchiveError(f"{label} bytes could not be read.") from None
    if not isinstance(data, bytes) or len(data) != size:
        raise ObjectArchiveError(f"{label} byte size changed during readback.")
    return data


def _file_name(key: str) -> str:
    # Flat hashed filenames: source object keys can never traverse the archive.
    return _sha(key.encode("utf-8")) + ".bin"


def _private_bytes(path: Path, data: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except OSError:
        raise ObjectArchiveError("Could not cdef _read_private_bytes(
    path: Path, size: int | None, *, dir_fd: int | None = None,
    limit: int | None = None,
) -> bytes:
    """Read exactly one regular inode under its already-open archive directory.

    The supplied size is the signed manifest's byte count for object files.
    Manifests use a separate hard cap; neither read follows a symlink.
    """
    maximum = size if limit is None else limit
    if type(maximum) is not int or maximum < 0 or (size is not None and (type(size) is not int or size < 0)):
        raise ObjectArchiveError("Archived object byte size is invalid.")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ObjectArchiveError("Secure no-follow private archive reads are unavailable.")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = None
    try:
        # A dir_fd keeps the leaf bound to the same verified parent even if a
        # concurrent process replaces the pathname of that parent.
        leaf = path.name if dir_fd is not None else path
        descriptor = os.open(leaf, flags, dir_fd=dir_fd)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ObjectArchiveError("Archived object exceeds the regular-file size limit.")
        if size is not None and before.st_size != size:
            raise ObjectArchiveError("Archived object byte size differs from its manifest.")
        remaining = maximum + 1
        parts: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            parts.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(parts)
        after = os.fstat(descriptor)
        if (before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns):
            raise ObjectArchiveError("Archived object changed during readback.")
        if len(raw) != before.st_size or len(raw) > maximum:
            raise ObjectArchiveError("Archived object byte size changed during readback.")
        if size is not None and len(raw) != size:
            raise ObjectArchiveError("Archived object byte size differs from its manifest.")
        return raw
    except OSError:
        raise ObjectArchiveError("Archived object could not be read safely.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _strict_manifest_json(raw: bytes) -> dict:
    """Reject JSON ambiguity before any object bytes or target writes."""
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ObjectArchiveError("Source object manifest contains duplicate JSON keys.")
            result[key] = value
        return result

    def reject_constant(_value: str):
        raise ObjectArchiveError("Source object manifest has a nonfinite JSON number.")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ObjectArchiveError("Source object manifest has a nonfinite JSON number.")
        return number

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_fields,
                          parse_constant=reject_constant, parse_float=finite_float)
    except (UnicodeError, ValueError, TypeError, OverflowError):
        raise ObjectArchiveError("Source object manifest cannot be parsed.") from None
ject byte size differs from its manifest.")
    return result


def archive_store(store, source_fingerprint: str, directory: Path, *, allow_empty_baseline: bool = False) -> dict:
    """Take a source inventory and copy every private object's exact bytes."""
    source_fingerprint = _fingerprint(source_fingerprint, "Source storage")
    if directory.exists() or directory.is_symlink() or not directory.parent.is_dir():
        raise ObjectArchiveError("Use a fresh object archive directory inside an existing private parent.")
    try:
        directory.mkdir(mode=0o700)
        objects_dir = directory / "objects"
        objects_dir.mkdir(mode=0o700)
    except OSError:
        raise ObjectArchiveError("Could not create private object archive directory.") from None

    initial = _inventory(store)
    if not initial and not allow_empty_baseline:
        raise ObjectArchiveError("Private source bucket is empty; no object restore can be certified.")
    if initial and allow_empty_baseline:
        raise ObjectArchiveError("Empty-baseline archive mode requires exactly zero source objects.")
    entries = []
    total_bytes = 0
    for item in initial:
        key, size = item["key"], item["byte_size"]
        content_type, asserted_sha = _mime(store, key, size)
        payload = _get(store, key, size, label="Source object")
        digest = _sha(payload)
        if asserted_sha is not None and digest != asserted_sha:
            raise ObjectArchiveError("Source object SHA-256 differs from its S3 metadata.")
        file_name = _file_name(key)
        _private_bytes(objects_dir / file_name, payload)
        entries.append({**item, "file": file_name, "sha256": digest, "content_type": content_type})
        total_bytes += size

    # A changing key/size/modification listing is not a complete source snapshot.
    if _inventory(store) != initial:
        raise ObjectArchiveError("Source object inventory changed during archive; discard partial backup.")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "baseline_archived" if not initial else "archived",
        "source_storage_fingerprint": source_fingerprint,
        "object_count": len(entries),
        "total_bytes": total_bytes,
        "objects": entries,
    }
    try:
        write_private_json(directory / "manifest.json", manifest)
    except StagingReleaseEvidenceError:
        raise ObjectArchiveError("Private source manifest could not be written.") from None
    return manifest


def _manifest(directory: Path) -> tuple[dict, list[tuple[dict, bytes]], str]:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise ObjectArchiveError("Secure no-follow private archive directories are unavailable.")
    flags = os.O_RDONLY | nofollow | directory_flag | getattr(os, "O_CLOEXEC", 0)
    try:
        root_fd = os.open(directory, flags)
    except OSError:
        raise ObjectArchiveError("Source archive directory is missing or symlinked.") from None
    try:
        raw = _read_private_bytes(
            Path("manifest.json"), None, dir_fd=root_fd, limit=MAX_MANIFEST_BYTES,
        )
        manifest = _strict_manifest_json(raw)
        if (not isinstance(manifest, dict)
                or set(manifest) != {
                    "schema_version", "status", "source_storage_fingerprint",
                    "object_count", "total_bytes", "objects",
                }
                or type(manifest["schema_version"]) is not int
                or manifest["schema_version"] != SCHEMA_VERSION
                or manifest["status"] not in ("archived", "baseline_archived")):
            raise ObjectArchiveError("Source object manifest has an invalid schema.")
        _fingerprint(manifest["source_storage_fingerprint"], "Source storage")
        rows = manifest["objects"]
        if (not isinstance(rows, list) or not 0 <= len(rows) <= MAX_OBJECTS
                or type(manifest["object_count"]) is not int
                or manifest["object_count"] != len(rows)
                or type(manifest["total_bytes"]) is not int
                or not 0 <= manifest["total_bytes"] <= MAX_TOTAL_BYTES):
            raise ObjectArchiveError("Source object manifest has invalid object totals.")
        if (manifest["status"] == "baseline_archived") != (len(rows) == 0):
            raise ObjectArchiveError("Source object baseline status conflicts with the object count.")
        try:
            objects_fd = os.open("objects", flags, dir_fd=root_fd)
        except OSError:
            raise ObjectArchiveError("Archived objects directory is missing or symlinked.") from None
        try:
            return _verify_archive_objects(manifest, rows, raw, objects_fd)
        finally:
            os.close(objects_fd)
    finally:
        os.close(root_fd)


def _verify_archive_objects(
    manifest: dict, rows: list[dict], raw: bytes, objects_fd: int,
) -> tuple[dict, list[tuple[dict, bytes]], str]:
    verified = []
    seen = set()
    size_total = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "key", "byte_size", "modified_at", "file", "sha256", "content_type",
        }:
            raise ObjectArchiveError("Source object manifest contains a malformed record.")
        key, size, checksum = row["key"], row["byte_size"], row["sha256"]
        try:
            validate_key(key)
        except (ValueError, TypeError):
            raise ObjectArchiveError("Source object manifest contains an invalid key.") from None
        if key in seen or row["file"] != _file_name(key):
            raise ObjectArchiveError("Source object manifest has duplicate or mismatched keys/files.")
        if type(size) is not int or not 0 <= size <= MAX_OBJECT_BYTES:
            raise ObjectArchiveError("Source object manifest has an invalid byte size.")
        if not isinstance(checksum, str) or _DIGEST.fullmatch(checksum) is None:
            raise ObjectArchiveError("Source object manifest has an invalid SHA-256.")
        mime = row["content_type"]
        if not isinstance(mime, str) or "/" not in mime or not 0 < len(mime) <= 200 or any(ord(c) < 32 for c in mime):
            raise ObjectArchiveError("Source object manifest has an invalid content type.")
        try:
            modified = datetime.fromisoformat(row["modified_at"])
        except (TypeError, ValueError):
            raise ObjectArchiveError("Source object manifest has an invalid timestamp.") from None
        if modified.tzinfo is None:
            raise ObjectArchiveError("Source object manifest has an unqualified timestamp.")
        if size_total + size > MAX_TOTAL_BYTES:
            raise ObjectArchiveError("Source object manifest total exceeds the allowed archive size.")
        payload = _read_private_bytes(Path(row["file"]), size, dir_fd=objects_fd)
        if _sha(payload) != checksum:
            raise ObjectArchiveError("Archived object SHA-256 digest does not match the manifest.")
        seen.add(key)
        size_total += size
        verified.append((row, payload))
    if [row["key"] for row, _ in verified] != sorted(seen) or size_total != manifest["total_bytes"]:
        raise ObjectArchiveError("Source object manifest ordering or totals are inconsistent.")
    return manifest, verified, _sha(raw)


def _preflight_receipt(path: Path) -> None:
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ObjectArchiveError("Use a fresh private restore receipt path inside an existing directory.")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.preflight"
    try:
        write_private_json(temporary, {"test": True})
    except StagingReleaseEvidenceError:
        raise ObjectArchiveError("Private restore receipt destination is unwritable.") from None
    finally:
        temporary.unlink(missing_ok=True)


def restore_store(
    store, target_fingerprint: str, directory: Path, receipt_path: Path,
    *, allow_empty_baseline: bool = False,
) -> dict:
    """Preflight *all* archived bytes, then restore into an empty distinct store."""
    target_fingerprint = _fingerprint(target_fingerprint, "Target storage")
    manifest, verified, manifest_sha = _manifest(directory)
    if (manifest["status"] == "baseline_archived") != allow_empty_baseline:
        raise ObjectArchiveError(
            "Explicit empty-baseline restore mode must match the archived baseline status."
        )
    if target_fingerprint == manifest["source_storage_fingerprint"]:
        raise ObjectArchiveError("Source and target object-storage resources must be distinct.")
    _preflight_receipt(receipt_path)
    if _inventory(store):
        raise ObjectArchiveError("Isolated object restore target must be empty before any writes.")

    for row, payload in verified:
        try:
            store.put(row["key"], payload, row["content_type"])
        except Exception:
            raise ObjectArchiveError("Private object restore PUT failed; target may be partial.") from None

    actual = _inventory(store)
    expected = sorted(
        (row["key"], row["byte_size"]) for row, _ in verified
    )
    if [(row["key"], row["byte_size"]) for row in actual] != expected:
        raise ObjectArchiveError("Restored object inventory did not match the full source archive.")
    for row, _ in verified:
        payload = _get(store, row["key"], row["byte_size"], label="Restored object readback")
        if _sha(payload) != row["sha256"]:
            raise ObjectArchiveError("Restored object readback SHA-256 mismatch.")
        mime, metadata_sha = _mime(store, row["key"], row["byte_size"])
        if isinstance(store, S3ObjectStore) and (mime != row["content_type"] or metadata_sha != row["sha256"]):
            raise ObjectArchiveError("Restored S3 MIME type or SHA-256 metadata differs from archive.")

    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "baseline_verified" if allow_empty_baseline else "verified",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "source_storage_fingerprint": manifest["source_storage_fingerprint"],
        "target_storage_fingerprint": target_fingerprint,
        "source_manifest_sha256": manifest_sha,
        "object_count": len(verified),
        "total_bytes": manifest["total_bytes"],
        "objects": [{"key": row["key"], "byte_size": row["byte_size"], "sha256": row["sha256"]}
                    for row, _ in verified],
        "caveat": (
            "Empty source baseline verified; no private PDF/task restoration proven, "
            "and D02.T09/G04 remain blocked."
            if allow_empty_baseline else
            "Isolated object restore only; independent database and hosted owner/API checks remain mandatory."
        ),
    }
    try:
        write_private_json(receipt_path, result)
    except StagingReleaseEvidenceError:
        raise ObjectArchiveError("Private restore receipt could not be published.") from None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    archive = sub.add_parser("archive")
    archive.add_argument("--directory", type=Path, required=True)
    archive.add_argument("--allow-empty-baseline", action="store_true")
    restore = sub.add_parser("restore")
    restore.add_argument("--archive-directory", type=Path, required=True)
    restore.add_argument("--output", type=Path, required=True)
    restore.add_argument("--allow-empty-baseline", action="store_true")
    args = parser.parse_args(argv)

    try:
        from services.coworker.config import Settings

        # Command guard + reviewed environment are required before initializing
        # boto3/S3 or any external service.
        guard = ("SHUDDHO_STAGING_ALLOW_OBJECT_ARCHIVE" if args.command == "archive"
                 else "SHUDDHO_STAGING_ALLOW_OBJECT_RESTORE")
        if (os.environ.get(guard, "").lower() != "true"
                or (args.command == "restore" and os.environ.get(
                    "SHUDDHO_STAGING_ALLOW_BACKUP_RESTORE_EXERCISE", ""
                ).lower() != "true")):
            raise ObjectArchiveError("Explicit private object archive/restore staging guards are required.")
        settings = Settings.from_env()
        if settings.environment != "staging" or settings.storage_backend != "s3":
            raise ObjectArchiveError("Private object archive/restore requires a reviewed staging S3 environment.")
        if args.command == "archive" and settings.storage_bucket != "shuddho-coworker-staging":
            raise ObjectArchiveError("Only the named private staging bucket can be archived.")
        from urllib.parse import urlparse
        endpoint = urlparse(settings.storage_endpoint or "")
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise ObjectArchiveError("Private S3 source/target endpoint must use HTTPS.")
        store = make_storage(settings)
        fingerprint = storage_fingerprint(settings)
        if args.command == "archive":
            report = archive_store(
                store, fingerprint, args.directory, allow_empty_baseline=args.allow_empty_baseline,
            )
            print(json.dumps({"status": report["status"], "object_count": report["object_count"]}))
        else:
            report = restore_store(
                store, fingerprint, args.archive_directory, args.output,
                allow_empty_baseline=args.allow_empty_baseline,
            )
            print(json.dumps({"status": report["status"], "object_count": report["object_count"],
                              "receipt": str(args.output)}))
        return 0
    except (ObjectArchiveError, StagingReleaseEvidenceError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    except Exception:
        # Never echo provider errors that could contain object keys or secrets.
        print(json.dumps({"status": "failed", "error": "Private object backup/restore failed."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
