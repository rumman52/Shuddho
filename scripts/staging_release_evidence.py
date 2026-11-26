from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


class StagingReleaseEvidenceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_revision(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise StagingReleaseEvidenceError(
            "Staging recovery evidence requires a full lowercase source revision."
        )
    return value


MAX_ROLLOUT_MANIFEST_BYTES = 1_048_576


def _read_rollout_manifest(
    path: Path, *, max_bytes: int = MAX_ROLLOUT_MANIFEST_BYTES,
) -> tuple[object, str]:
    """Parse and hash the same bounded regular file bytes; never reopen the path."""
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise StagingReleaseEvidenceError("Secure no-follow rollout reading is unavailable")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
                raise StagingReleaseEvidenceError("Rollout manifest must be a bounded regular file")
            remaining = max_bytes + 1
            parts: list[bytes] = []
            while remaining:
                part = os.read(descriptor, min(65536, remaining))
                if not part:
                    break
                parts.append(part)
                remaining -= len(part)
            final_metadata = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise StagingReleaseEvidenceError(
            f"Could not read rollout manifest: {type(error).__name__}"
        ) from None
    raw = b"".join(parts)
    if len(raw) > max_bytes:
        raise StagingReleaseEvidenceError("Rollout manifest exceeds byte bound")
    # One no-follow descriptor prevents a path-swap. This fence also rejects
    # concurrent in-place rewrites, truncation and growth, including a change
    # after the final EOF read but before the descriptor is closed. The hash
    # below must describe one complete, stable regular-file snapshot.
    if (
        not stat.S_ISREG(final_metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != (final_metadata.st_dev, final_metadata.st_ino)
        or metadata.st_size != final_metadata.st_size
        or len(raw) != metadata.st_size
        or metadata.st_mtime_ns != final_metadata.st_mtime_ns
        or metadata.st_ctime_ns != final_metadata.st_ctime_ns
    ):
        raise StagingReleaseEvidenceError("Rollout manifest changed during bounded read")

    return parse_evidence_json(raw), hashlib.sha256(raw).hexdigest()


def parse_evidence_json(raw: bytes) -> object:
    """Parse one UTF-8 evidence snapshot without ambiguous or non-finite values."""
    def unique_fields(pairs: list[tuple[str, object]]) -> dict:
        out = {}
        for key, value in pairs:
            if key in out:
                raise StagingReleaseEvidenceError("Duplicate rollout manifest JSON field")
            out[key] = value
        return out

    def reject_constant(_value: str) -> None:
        raise StagingReleaseEvidenceError("Rollout manifest has non-finite JSON value")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise StagingReleaseEvidenceError("Rollout manifest has non-finite JSON number")
        return number

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=unique_fields,
            parse_constant=reject_constant, parse_float=finite_float,
        )
        # JSON escapes can produce unpaired surrogates even when the input
        # bytes are valid UTF-8. Require scalar text in every key and value
        # before callers canonicalize, hash, or publish the evidence.
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, str):
                item.encode("utf-8")
            elif isinstance(item, dict):
                pending.extend(item)
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        return value
    except (UnicodeError, ValueError, TypeError, RecursionError) as error:
        raise StagingReleaseEvidenceError(
            f"Invalid rollout manifest: {type(error).__name__}"
        ) from None


def release_context(settings, rollout_path: Path) -> dict:
    rollout, rollout_digest = _read_rollout_manifest(rollout_path)
    if not isinstance(rollout, dict):
        raise StagingReleaseEvidenceError("Rollout manifest must contain a JSON object.")
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise StagingReleaseEvidenceError("Rollout manifest release_id is required.")
    source_revision = require_revision(getattr(settings, "source_revision", None))
    return {
        "release_id": release_id.strip(),
        "source_revision": source_revision,
        "rollout_manifest_sha256": rollout_digest,
    }


PREPARED_CONTEXT_KEYS = {
    "release_id",
    "source_revision",
    "rollout_manifest_sha256",
    "exercise_started_at",
}
MAX_CLOCK_SKEW = timedelta(minutes=5)


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise StagingReleaseEvidenceError(f"{label} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise StagingReleaseEvidenceError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None:
        raise StagingReleaseEvidenceError(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def prepared_release_context(
    settings,
    rollout_path: Path,
    *,
    now: datetime | None = None,
) -> dict:
    current = release_context(settings, rollout_path)
    started = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        **current,
        "exercise_started_at": started.isoformat(),
    }


def validate_prepared_release_context(
    value: object,
    settings,
    rollout_path: Path,
    *,
    now: datetime | None = None,
) -> dict:
    if not isinstance(value, dict) or set(value) != PREPARED_CONTEXT_KEYS:
        raise StagingReleaseEvidenceError(
            "Prepared staging release context has an unexpected schema."
        )
    current = release_context(settings, rollout_path)
    for key in ("release_id", "source_revision", "rollout_manifest_sha256"):
        if value.get(key) != current[key]:
            raise StagingReleaseEvidenceError(
                f"Prepared staging release context {key} does not match verification."
            )
    started = parse_time(value.get("exercise_started_at"), "exercise_started_at")
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if started - checked_at > MAX_CLOCK_SKEW:
        raise StagingReleaseEvidenceError(
            "Prepared staging exercise start is from the future."
        )
    return {
        **current,
        "exercise_started_at": started.isoformat(),
    }


def passed(evidence: str, context: dict, *, now: datetime | None = None) -> dict:
    if not isinstance(evidence, str) or not evidence.strip():
        raise StagingReleaseEvidenceError("Staging evidence reference is required.")
    if not isinstance(context.get("exercise_started_at"), str):
        raise StagingReleaseEvidenceError(
            "Prepared exercise_started_at is required for staging recovery evidence."
        )
    verified_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    started = parse_time(context["exercise_started_at"], "exercise_started_at")
    if verified_at < started:
        raise StagingReleaseEvidenceError(
            "Staging recovery verification cannot precede exercise start."
        )
    return {
        "status": "passed",
        "evidence": evidence.strip(),
        "exercise_started_at": started.isoformat(),
        "verified_at": verified_at.isoformat(),
        "release_id": context["release_id"],
        "source_revision": context["source_revision"],
        "rollout_manifest_sha256": context["rollout_manifest_sha256"],
    }

def write_private_bytes(path: Path, payload: bytes) -> None:
    """Publish complete private bytes once, without replacing any existing path.

    The caller must provide a trusted, existing parent directory. Native
    OSError (including FileExistsError) is preserved for the calling CLI.
    """
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    descriptor_open = True
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "wb")
        descriptor_open = False
        with handle:
            if handle.write(payload) != len(payload):
                raise OSError("incomplete private evidence write")
            handle.flush()
            os.fsync(handle.fileno())

        # Same-directory hard-link publication is exclusive and atomic.
        # If directory sync fails after this point, retain the complete
        # destination but report failure; never retry over the same name.
        os.link(temporary_path, path)
        if os.name == "posix":
            directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if descriptor_open:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def write_private_json(path: Path, value: dict) -> None:
    """Atomically create a private JSON evidence file without overwriting existing data."""
    try:
        payload = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")
        # Validate the actual serialized bytes before creating any file.
        # This also catches duplicate keys introduced by JSON key coercion.
        parse_evidence_json(payload)
    except (TypeError, ValueError, RecursionError, StagingReleaseEvidenceError):
        raise StagingReleaseEvidenceError(
            "Private evidence must be JSON-serializable as unambiguous, finite UTF-8 JSON."
        ) from None

    try:
        write_private_bytes(path, payload)
    except FileExistsError:
        raise StagingReleaseEvidenceError(
            "Refusing to overwrite existing private evidence file."
        ) from None
    except OSError as error:
        raise StagingReleaseEvidenceError(
            f"Could not write private evidence file: {type(error).__name__}"
        ) from None
