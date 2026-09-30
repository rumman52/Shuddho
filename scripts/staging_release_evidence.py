from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
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


def passed(evidence: str, context: dict, *, now: datetime | None = None) -> dict:
    if not isinstance(evidence, str) or not evidence.strip():
        raise StagingReleaseEvidenceError("Staging evidence reference is required.")
    verified_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "status": "passed",
        "evidence": evidence.strip(),
        "verified_at": verified_at.isoformat(),
        "release_id": context["release_id"],
        "source_revision": context["source_revision"],
        "rollout_manifest_sha256": context["rollout_manifest_sha256"],
    }
