from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


class IncidentRestoreEvidenceError(RuntimeError):
    pass


MAX_CLOCK_SKEW = timedelta(minutes=5)
REQUIRED_STAGING_CHECKS = (
    "backup_restore",
    "temporal",
    "parallel_restart",
    "fan_in",
    "flag_rollback",
)
REVIEW_KEYS = {
    "schema_version",
    "release_id",
    "source_revision",
    "exercise_started_at",
    "exercise_completed_at",
    "rto_target_minutes",
    "max_data_loss_seconds",
    "observed_data_loss_seconds",
    "incident_reference",
    "backup_reference",
    "restore_reference",
    "temporal_restart_reference",
    "rollback_reference",
    "reviewer_reference",
    "failures",
}
EVIDENCE_KEYS = {
    "schema_version",
    "mode",
    "release_id",
    "generated_at",
    "exercise_started_at",
    "exercise_completed_at",
    "source_revision",
    "rollout_manifest_sha256",
    "staging_evidence_sha256",
    "review_sha256",
    "checks",
    "rto_target_minutes",
    "observed_restore_minutes",
    "max_data_loss_seconds",
    "observed_data_loss_seconds",
    "references",
    "gate_decision",
    "failures",
}
REFERENCE_KEYS = {
    "incident",
    "backup",
    "restore",
    "temporal_restart",
    "rollback",
    "reviewer",
}


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise IncidentRestoreEvidenceError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise IncidentRestoreEvidenceError(f"{label} must contain a JSON object.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise IncidentRestoreEvidenceError(f"{label} must be an ISO-8601 timestamp.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise IncidentRestoreEvidenceError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if result.tzinfo is None:
        raise IncidentRestoreEvidenceError(f"{label} must include a timezone.")
    return result.astimezone(timezone.utc)


def reject_future(value: datetime, label: str, *, now: datetime) -> None:
    if value - now > MAX_CLOCK_SKEW:
        raise IncidentRestoreEvidenceError(f"{label} is from the future.")


def text_ref(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise IncidentRestoreEvidenceError(
            f"{label} must be a non-empty reference up to 500 characters."
        )
    return value.strip()


def require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise IncidentRestoreEvidenceError(f"{label} must be a lowercase SHA-256.")
    return value


def require_revision(value: object, label: str = "source_revision") -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise IncidentRestoreEvidenceError(
            f"{label} must be a full lowercase 40-character Git SHA-1."
        )
    return value


def positive_number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise IncidentRestoreEvidenceError(
            f"{label} must be a positive finite number."
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise IncidentRestoreEvidenceError(
            f"{label} must be a positive finite number."
        )
    return number


def nonnegative_number(value: object, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise IncidentRestoreEvidenceError(
            f"{label} must be a non-negative finite number."
        )
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise IncidentRestoreEvidenceError(
            f"{label} must be a non-negative finite number."
        )
    return number


def validate_staging_evidence(value: dict) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for key in REQUIRED_STAGING_CHECKS:
        item = value.get(key)
        if not isinstance(item, dict) or item.get("status") != "passed":
            raise IncidentRestoreEvidenceError(
                f"Staging evidence check {key!r} must be passed."
            )
        text_ref(item.get("evidence"), f"staging.{key}.evidence")
        checks[key] = True
    return checks


def validate_review(
    value: dict,
    *,
    release_id: str,
    now: datetime,
) -> tuple[str, datetime, datetime, float, float, float]:
    if set(value) != REVIEW_KEYS:
        raise IncidentRestoreEvidenceError(
            "Incident/restore review has an unexpected schema."
        )
    if value["schema_version"] != 1:
        raise IncidentRestoreEvidenceError(
            "Incident/restore review schema_version must be 1."
        )
    if value["release_id"] != release_id:
        raise IncidentRestoreEvidenceError(
            "Incident/restore review release_id does not match the rollout."
        )
    source_revision = require_revision(value["source_revision"])
    started = parse_time(value["exercise_started_at"], "review.exercise_started_at")
    completed = parse_time(
        value["exercise_completed_at"],
        "review.exercise_completed_at",
    )
    reject_future(started, "review.exercise_started_at", now=now)
    reject_future(completed, "review.exercise_completed_at", now=now)
    if completed < started:
        raise IncidentRestoreEvidenceError(
            "Incident/restore exercise must complete after it starts."
        )

    rto_target = positive_number(value["rto_target_minutes"], "rto_target_minutes")
    observed_restore = (completed - started).total_seconds() / 60
    if observed_restore > rto_target:
        raise IncidentRestoreEvidenceError(
            "Incident/restore exercise exceeded the reviewed RTO target."
        )

    max_data_loss = nonnegative_number(
        value["max_data_loss_seconds"],
        "max_data_loss_seconds",
    )
    observed_data_loss = nonnegative_number(
        value["observed_data_loss_seconds"],
        "observed_data_loss_seconds",
    )
    if observed_data_loss > max_data_loss:
        raise IncidentRestoreEvidenceError(
            "Incident/restore exercise exceeded the reviewed data-loss limit."
        )
    if value["failures"] != []:
        raise IncidentRestoreEvidenceError(
            "Incident/restore review contains unresolved failures."
        )
    for key in (
        "incident_reference",
        "backup_reference",
        "restore_reference",
        "temporal_restart_reference",
        "rollback_reference",
        "reviewer_reference",
    ):
        text_ref(value[key], key)
    return (
        source_revision,
        started,
        completed,
        rto_target,
        max_data_loss,
        observed_data_loss,
    )


def compile_incident_restore_evidence(
    *,
    rollout_path: Path,
    staging_evidence_path: Path,
    review_path: Path,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    rollout = load_json(rollout_path, "rollout manifest")
    release_id = text_ref(rollout.get("release_id"), "rollout.release_id")
    staging = load_json(staging_evidence_path, "staging evidence")
    checks = validate_staging_evidence(staging)
    review = load_json(review_path, "incident/restore review")
    (
        source_revision,
        started,
        completed,
        rto_target,
        max_data_loss,
        observed_data_loss,
    ) = validate_review(review, release_id=release_id, now=now)
    observed_restore = (completed - started).total_seconds() / 60

    return {
        "schema_version": 1,
        "mode": "incident_restore",
        "release_id": release_id,
        "generated_at": now.isoformat(),
        "exercise_started_at": started.isoformat(),
        "exercise_completed_at": completed.isoformat(),
        "source_revision": source_revision,
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "staging_evidence_sha256": sha256_file(staging_evidence_path),
        "review_sha256": sha256_file(review_path),
        "checks": checks,
        "rto_target_minutes": rto_target,
        "observed_restore_minutes": round(observed_restore, 3),
        "max_data_loss_seconds": max_data_loss,
        "observed_data_loss_seconds": observed_data_loss,
        "references": {
            "incident": text_ref(review["incident_reference"], "incident_reference"),
            "backup": text_ref(review["backup_reference"], "backup_reference"),
            "restore": text_ref(review["restore_reference"], "restore_reference"),
            "temporal_restart": text_ref(
                review["temporal_restart_reference"],
                "temporal_restart_reference",
            ),
            "rollback": text_ref(review["rollback_reference"], "rollback_reference"),
            "reviewer": text_ref(review["reviewer_reference"], "reviewer_reference"),
        },
        "gate_decision": "PASS",
        "failures": [],
    }


def validate_incident_restore_evidence(
    value: dict,
    *,
    release_id: str,
    rollout_sha256: str,
    expected_source_revision: str | None = None,
) -> tuple[datetime, datetime]:
    if not isinstance(value, dict) or set(value) != EVIDENCE_KEYS:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence has an unexpected schema."
        )
    if value["schema_version"] != 1 or value["mode"] != "incident_restore":
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence has an unsupported schema or mode."
        )
    if value["release_id"] != release_id:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence release_id does not match."
        )
    require_sha256(rollout_sha256, "Expected rollout manifest SHA-256")
    if value["rollout_manifest_sha256"] != rollout_sha256:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence does not bind the current rollout manifest."
        )
    revision = require_revision(value["source_revision"])
    if (
        expected_source_revision is not None
        and revision != require_revision(
            expected_source_revision,
            "expected_source_revision",
        )
    ):
        raise IncidentRestoreEvidenceError(
            "Incident/restore source revision does not match live quality evidence."
        )
    require_sha256(
        value["staging_evidence_sha256"],
        "incident_restore.staging_evidence_sha256",
    )
    require_sha256(value["review_sha256"], "incident_restore.review_sha256")
    if not isinstance(value["checks"], dict) or set(value["checks"]) != set(
        REQUIRED_STAGING_CHECKS
    ):
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence checks do not match the required set."
        )
    if any(value["checks"].get(key) is not True for key in REQUIRED_STAGING_CHECKS):
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence has an unpassed required check."
        )
    rto_target = positive_number(
        value["rto_target_minutes"],
        "incident_restore.rto_target_minutes",
    )
    observed_restore = nonnegative_number(
        value["observed_restore_minutes"],
        "incident_restore.observed_restore_minutes",
    )
    if observed_restore > rto_target:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence exceeds the reviewed RTO target."
        )
    max_data_loss = nonnegative_number(
        value["max_data_loss_seconds"],
        "incident_restore.max_data_loss_seconds",
    )
    observed_data_loss = nonnegative_number(
        value["observed_data_loss_seconds"],
        "incident_restore.observed_data_loss_seconds",
    )
    if observed_data_loss > max_data_loss:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence exceeds the reviewed data-loss limit."
        )
    if not isinstance(value["references"], dict) or set(value["references"]) != REFERENCE_KEYS:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence references have an unexpected schema."
        )
    for key, reference in value["references"].items():
        text_ref(reference, f"incident_restore.references.{key}")
    if value["gate_decision"] != "PASS" or value["failures"] != []:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence did not pass cleanly."
        )
    generated = parse_time(value["generated_at"], "incident_restore.generated_at")
    started = parse_time(
        value["exercise_started_at"],
        "incident_restore.exercise_started_at",
    )
    completed = parse_time(
        value["exercise_completed_at"],
        "incident_restore.exercise_completed_at",
    )
    now = datetime.now(timezone.utc)
    reject_future(generated, "incident_restore.generated_at", now=now)
    reject_future(started, "incident_restore.exercise_started_at", now=now)
    reject_future(completed, "incident_restore.exercise_completed_at", now=now)
    if completed < started or generated < completed:
        raise IncidentRestoreEvidenceError(
            "Incident/restore evidence timestamp ordering is invalid."
        )
    return generated, completed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile rollout-bound PA-11 incident/restore evidence from existing "
            "controlled staging recovery gates and an explicit operator review."
        )
    )
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--staging-evidence", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compile_incident_restore_evidence(
            rollout_path=args.rollout,
            staging_evidence_path=args.staging_evidence,
            review_path=args.review,
        )
    except IncidentRestoreEvidenceError as error:
        raise SystemExit(str(error)) from None
    encoded = json.dumps(result, indent=2)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
