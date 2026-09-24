from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path


class QualityEvidenceError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: str, label: str = "generated_at") -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise QualityEvidenceError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None:
        raise QualityEvidenceError(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _ratio(value, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise QualityEvidenceError(f"{label} must be a finite number.")
    number = float(value)
    if number < 0 or number > 1:
        raise QualityEvidenceError(f"{label} must be between 0 and 1.")
    return number


def _sha256(value, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise QualityEvidenceError(f"{label} must be a lowercase SHA-256.")
    return value


def validate_live_quality_evidence(
    value: dict,
    *,
    release_id: str,
    rollout_sha256: str,
    min_pass_rate: float,
    min_fact_recall: float,
) -> datetime:
    if not isinstance(value, dict):
        raise QualityEvidenceError(
            "Quality evaluation must contain a JSON object."
        )
    if value.get("mode") != "live":
        raise QualityEvidenceError(
            "Quality evaluation must be a live-provider run."
        )
    if value.get("release_id") != release_id:
        raise QualityEvidenceError(
            "Quality evaluation release_id does not match."
        )
    _sha256(rollout_sha256, "Expected rollout manifest SHA-256")
    if value.get("rollout_manifest_sha256") != rollout_sha256:
        raise QualityEvidenceError(
            "Quality evaluation does not bind the current rollout manifest."
        )
    if (
        value.get("gate_decision") != "PASS"
        or value.get("failures") != []
        or value.get("gate_failures") != []
    ):
        raise QualityEvidenceError(
            "Live quality evaluation did not pass cleanly."
        )
    pass_rate = _ratio(value.get("pass_rate"), "quality.pass_rate")
    fact_recall = _ratio(
        value.get("required_fact_recall"),
        "quality.required_fact_recall",
    )
    if pass_rate < min_pass_rate:
        raise QualityEvidenceError(
            "Live quality pass rate is below the required threshold."
        )
    if fact_recall < min_fact_recall:
        raise QualityEvidenceError(
            "Live quality fact recall is below the required threshold."
        )
    _sha256(value.get("fixture_sha256"), "quality.fixture_sha256")
    provider_model = value.get("provider_model")
    if (
        not isinstance(provider_model, str)
        or not provider_model.strip()
        or len(provider_model) > 500
    ):
        raise QualityEvidenceError(
            "quality.provider_model must be a non-empty string."
        )
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise QualityEvidenceError(
            "Quality evaluation has no generated_at timestamp."
        )
    return parse_time(generated_at, "quality.generated_at")
