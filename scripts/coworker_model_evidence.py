from __future__ import annotations

import math
from datetime import datetime, timezone


class ModelEvidenceError(RuntimeError):
    pass


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ModelEvidenceError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None:
        raise ModelEvidenceError(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _sha256(value, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ModelEvidenceError(f"{label} must be a lowercase SHA-256.")
    return value


def _source_revision(value, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ModelEvidenceError(
            f"{label} must be a full lowercase 40-character Git SHA-1."
        )
    return value


def _ratio(value, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise ModelEvidenceError(f"{label} must be a finite number.")
    number = float(value)
    if number < 0 or number > 1:
        raise ModelEvidenceError(f"{label} must be between 0 and 1.")
    return number


def validate_live_model_evidence(
    value: dict,
    *,
    release_id: str,
    rollout_sha256: str,
    expected_provider_model: str,
    min_pass_rate: float = 1.0,
) -> datetime:
    if not isinstance(value, dict):
        raise ModelEvidenceError(
            "Planner evaluation must contain a JSON object."
        )
    if value.get("mode") != "live":
        raise ModelEvidenceError(
            "Planner evaluation must be a live-provider run."
        )
    if value.get("release_id") != release_id:
        raise ModelEvidenceError(
            "Planner evaluation release_id does not match."
        )
    _sha256(rollout_sha256, "Expected rollout manifest SHA-256")
    if value.get("rollout_manifest_sha256") != rollout_sha256:
        raise ModelEvidenceError(
            "Planner evaluation does not bind the current rollout manifest."
        )
    if (
        value.get("gate_decision") != "PASS"
        or value.get("failures") != []
        or value.get("gate_failures") != []
    ):
        raise ModelEvidenceError(
            "Live planner evaluation did not pass cleanly."
        )
    pass_rate = _ratio(
        value.get("pass_rate"),
        "planner.pass_rate",
    )
    if pass_rate < min_pass_rate:
        raise ModelEvidenceError(
            "Live planner pass rate is below the required threshold."
        )
    _sha256(value.get("fixture_sha256"), "planner.fixture_sha256")
    provider_model = value.get("provider_model")
    if (
        not isinstance(provider_model, str)
        or not provider_model.strip()
        or len(provider_model) > 500
    ):
        raise ModelEvidenceError(
            "planner.provider_model must be a non-empty string."
        )
    if provider_model != expected_provider_model:
        raise ModelEvidenceError(
            "Planner evaluation provider model does not match the reviewed rollout."
        )
    _source_revision(
        value.get("source_revision"),
        "planner.source_revision",
    )
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ModelEvidenceError(
            "Planner evaluation has no generated_at timestamp."
        )
    return _parse_time(generated_at, "planner.generated_at")
