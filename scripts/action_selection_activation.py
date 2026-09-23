from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from services.coworker.config import Settings, enabled as coworker_enabled


DEPLOYMENT_KEYS = {
    "release_id",
    "change_reference",
    "current_stage",
    "deployed_at",
    "staging_evidence_sha256",
}


class ActionSelectionActivationError(RuntimeError):
    pass


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ActionSelectionActivationError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ActionSelectionActivationError(
            f"{label} must contain a JSON object."
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ActionSelectionActivationError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if result.tzinfo is None:
        raise ActionSelectionActivationError(
            f"{label} must include a timezone."
        )
    return result.astimezone(timezone.utc)


def validate_staging(
    evidence: dict,
    *,
    now: datetime,
    max_age_minutes: int,
) -> datetime:
    item = evidence.get("action_selection")
    if not isinstance(item, dict):
        raise ActionSelectionActivationError(
            "Staging evidence has no action_selection result."
        )
    if item.get("status") != "passed":
        raise ActionSelectionActivationError(
            "Action-selection staging evidence is not passed."
        )
    if (
        not isinstance(item.get("evidence"), str)
        or not item["evidence"].strip()
    ):
        raise ActionSelectionActivationError(
            "Action-selection staging evidence text is missing."
        )
    verified_at = item.get("verified_at")
    if not isinstance(verified_at, str):
        raise ActionSelectionActivationError(
            "Action-selection staging evidence has no verified_at timestamp."
        )
    verified = parse_time(
        verified_at,
        "action_selection verified_at",
    )
    age = (now - verified).total_seconds() / 60
    if age < -1:
        raise ActionSelectionActivationError(
            "Action-selection staging evidence is from the future."
        )
    if age > max_age_minutes:
        raise ActionSelectionActivationError(
            f"Action-selection staging evidence is stale ({age:.1f} minutes old)."
        )
    return verified


def validate_deployment(
    value: dict,
    evidence_path: Path,
    *,
    not_before: datetime,
) -> datetime:
    if set(value) != DEPLOYMENT_KEYS:
        raise ActionSelectionActivationError(
            "Action-selection deployment record has an unexpected schema."
        )
    for key in ("release_id", "change_reference", "current_stage"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ActionSelectionActivationError(
                f"Deployment {key} is required."
            )
        if len(value[key]) > 500:
            raise ActionSelectionActivationError(
                f"Deployment {key} is too long."
            )
    if value["staging_evidence_sha256"] != sha256_file(evidence_path):
        raise ActionSelectionActivationError(
            "Deployment record does not bind the exact action-selection staging evidence."
        )
    deployed_at = parse_time(
        str(value["deployed_at"]),
        "action-selection deployed_at",
    )
    if deployed_at < not_before:
        raise ActionSelectionActivationError(
            "Action-selection deployment predates live staging evidence."
        )
    return deployed_at


def validate_operator_status(
    value: dict,
    release_id: str,
    *,
    not_before: datetime,
    now: datetime,
    freshness_minutes: int,
) -> datetime:
    if value.get("release_id") != release_id:
        raise ActionSelectionActivationError(
            "Operator status release_id does not match deployment."
        )
    if (
        value.get("decision") != "CONTINUE_COHORT"
        or value.get("breaches") != []
    ):
        raise ActionSelectionActivationError(
            "Operator status must be CONTINUE_COHORT with zero breaches."
        )
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ActionSelectionActivationError(
            "Operator status has no generated_at timestamp."
        )
    generated = parse_time(
        generated_at,
        "operator status generated_at",
    )
    if generated < not_before:
        raise ActionSelectionActivationError(
            "Operator status must be generated after action-selection deployment."
        )
    age = (now - generated).total_seconds() / 60
    if age < -1:
        raise ActionSelectionActivationError(
            "Operator status is from the future."
        )
    if age > freshness_minutes:
        raise ActionSelectionActivationError(
            f"Operator status is stale ({age:.1f} minutes old)."
        )
    return generated


def require_runtime_flags(
    settings: Settings,
    *,
    coworker_is_enabled: bool,
) -> dict:
    flags = {
        "coworker_enabled": coworker_is_enabled,
        "agent_runtime_enabled": settings.agent_runtime_enabled,
        "intelligent_planner_enabled": settings.intelligent_planner_enabled,
        "actions_enabled": settings.actions_enabled,
        "action_selection_enabled": settings.agent_action_selection_enabled,
        "cohort_enforced": settings.cohort_enforced,
    }
    missing = [key for key, value in flags.items() if value is not True]
    if missing:
        names = ", ".join(sorted(missing))
        raise ActionSelectionActivationError(
            "Deployed runtime is missing required action-selection controls: "
            + names
            + "."
        )
    return {
        **flags,
        "cohort_members_configured": len(settings.cohort_account_ids),
        "cohort_max_users": settings.cohort_max_users,
    }


def build_evidence(
    *,
    deployment: dict,
    staging_path: Path,
    deployment_path: Path,
    operator_status_path: Path,
    runtime: dict,
    operator_status: dict,
    now: datetime,
) -> dict:
    return {
        "schema_version": 1,
        "status": "action_selection_verified",
        "release_id": deployment["release_id"],
        "current_stage": deployment["current_stage"],
        "verified_at": now.isoformat(),
        "change_reference": deployment["change_reference"],
        "deployed_at": deployment["deployed_at"],
        "operator_status_generated_at": operator_status["generated_at"],
        "runtime": runtime,
        "artifact_sha256": {
            "staging_evidence": sha256_file(staging_path),
            "deployment_change": sha256_file(deployment_path),
            "operator_status": sha256_file(operator_status_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify production activation of bounded Agent action selection "
            "against exact live staging evidence and deployed runtime flags."
        )
    )
    parser.add_argument(
        "--staging-evidence",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--deployment-change",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--operator-status",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--max-staging-age-minutes",
        type=int,
        default=24 * 60,
    )
    parser.add_argument(
        "--freshness-minutes",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()
    if (
        args.max_staging_age_minutes < 1
        or args.freshness_minutes < 1
    ):
        raise SystemExit("Freshness values must be positive.")

    try:
        now = datetime.now(timezone.utc)
        staging = load_json(
            args.staging_evidence,
            "action-selection staging evidence",
        )
        staging_time = validate_staging(
            staging,
            now=now,
            max_age_minutes=args.max_staging_age_minutes,
        )

        deployment = load_json(
            args.deployment_change,
            "action-selection deployment",
        )
        deployment_time = validate_deployment(
            deployment,
            args.staging_evidence,
            not_before=staging_time,
        )

        operator_status = load_json(
            args.operator_status,
            "operator status",
        )
        validate_operator_status(
            operator_status,
            deployment["release_id"],
            not_before=deployment_time,
            now=now,
            freshness_minutes=args.freshness_minutes,
        )

        settings = Settings.from_env()
        runtime = require_runtime_flags(
            settings,
            coworker_is_enabled=coworker_enabled(),
        )

        evidence = build_evidence(
            deployment=deployment,
            staging_path=args.staging_evidence,
            deployment_path=args.deployment_change,
            operator_status_path=args.operator_status,
            runtime=runtime,
            operator_status=operator_status,
            now=now,
        )
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "written": str(args.output),
            "status": evidence["status"],
            "release_id": evidence["release_id"],
            "current_stage": evidence["current_stage"],
        }, indent=2))
    except (
        ActionSelectionActivationError,
        OSError,
        ValueError,
    ) as error:
        print(json.dumps({
            "status": "failed",
            "error": str(error),
        }, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
