from __future__ import annotations

import hashlib
import json
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


def release_context(settings, rollout_path: Path) -> dict:
    try:
        rollout = json.loads(rollout_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StagingReleaseEvidenceError(
            f"Could not read rollout manifest: {type(error).__name__}"
        ) from None
    if not isinstance(rollout, dict):
        raise StagingReleaseEvidenceError("Rollout manifest must contain a JSON object.")
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise StagingReleaseEvidenceError("Rollout manifest release_id is required.")
    source_revision = require_revision(getattr(settings, "source_revision", None))
    return {
        "release_id": release_id.strip(),
        "source_revision": source_revision,
        "rollout_manifest_sha256": sha256_file(rollout_path),
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
