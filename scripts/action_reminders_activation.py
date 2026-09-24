from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from scripts.release_contract import normalize_capabilities
from scripts.cohort_release_gate import (
    declared_action_providers,
    load_rollout,
    validate_rollout,
)


DEPLOYMENT_KEYS = {
    "release_id",
    "change_reference",
    "current_stage",
    "deployed_at",
    "source_revision",
    "staging_evidence_sha256",
    "rollout_manifest_sha256",
}


class ActionRemindersActivationError(RuntimeError):
    pass


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ActionRemindersActivationError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ActionRemindersActivationError(
            f"{label} must contain a JSON object."
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ActionRemindersActivationError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if result.tzinfo is None:
        raise ActionRemindersActivationError(
            f"{label} must include a timezone."
        )
    return result.astimezone(timezone.utc)


def require_https_origin(value: str, label: str) -> str:
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ActionRemindersActivationError(
            f"{label} must be a clean HTTPS origin."
        )
    return clean


def validate_staging(
    evidence: dict,
    *,
    providers: list[str],
    now: datetime,
    max_age_minutes: int,
) -> datetime:
    verified_times: list[datetime] = []
    for provider in providers:
        key = f"action_reminders_{provider}"
        item = evidence.get(key)
        if not isinstance(item, dict):
            raise ActionRemindersActivationError(
                f"Staging evidence has no {key} result."
            )
        if item.get("status") != "passed":
            raise ActionRemindersActivationError(
                f"{provider} reminder staging evidence is not passed."
            )
        if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
            raise ActionRemindersActivationError(
                f"{provider} reminder staging evidence text is missing."
            )
        verified_at = item.get("verified_at")
        if not isinstance(verified_at, str):
            raise ActionRemindersActivationError(
                f"{provider} reminder staging evidence has no verified_at timestamp."
            )
        verified = parse_time(verified_at, f"{key} verified_at")
        age = (now - verified).total_seconds() / 60
        if age < -1:
            raise ActionRemindersActivationError(
                f"{provider} reminder staging evidence is from the future."
            )
        if age > max_age_minutes:
            raise ActionRemindersActivationError(
                f"{provider} reminder staging evidence is stale ({age:.1f} minutes old)."
            )
        verified_times.append(verified)
    if not verified_times:
        raise ActionRemindersActivationError(
            "Reminder activation requires at least one reviewed action provider."
        )
    return max(verified_times)

def validate_reviewed_rollout(
    rollout: dict,
    *,
    max_cohort_users: int,
) -> dict:
    failures = validate_rollout(
        rollout,
        max_cohort_users=max_cohort_users,
    )
    if failures:
        raise ActionRemindersActivationError(
            "Reviewed rollout manifest is invalid: "
            + ", ".join(failures)
        )
    capabilities = rollout["capabilities"]
    if capabilities.get("action_reminders") is not True or capabilities.get("actions") is not True:
        raise ActionRemindersActivationError(
            "Reviewed rollout manifest does not enable the required actions/action_reminders capabilities."
        )
    rollback = rollout["rollback"]
    if (
        rollback.get("action_reminders_kill_switch")
        != "SHUDDHO_ACTION_REMINDERS_ENABLED=false"
    ):
        raise ActionRemindersActivationError(
            "Reviewed rollout manifest has no exact action-reminders kill switch."
        )
    normalized = normalize_capabilities(capabilities)
    return {
        "release_id": rollout["release_id"],
        "environment": rollout["environment"],
        "capabilities": normalized,
        "action_providers": sorted(
            declared_action_providers(rollout)
        ),
        "cohort_max_users": rollout["cohort"]["max_users"],
        "change_reference": rollout["incident"]["change_reference"],
    }


def validate_deployment(
    value: dict,
    *,
    staging_path: Path,
    rollout_path: Path,
    rollout: dict,
    not_before: datetime,
) -> datetime:
    if set(value) != DEPLOYMENT_KEYS:
        raise ActionRemindersActivationError(
            "Action-reminder deployment record has an unexpected schema."
        )
    for key in (
        "release_id",
        "change_reference",
        "current_stage",
        "source_revision",
    ):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ActionRemindersActivationError(
                f"Deployment {key} is required."
            )
        if len(value[key]) > 500:
            raise ActionRemindersActivationError(
                f"Deployment {key} is too long."
            )
    revision = value["source_revision"]
    if (
        len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ActionRemindersActivationError(
            "Deployment source_revision must be a full lowercase Git SHA-1."
        )
    if value["release_id"] != rollout["release_id"]:
        raise ActionRemindersActivationError(
            "Deployment release_id does not match reviewed rollout."
        )
    if value["change_reference"] != rollout["change_reference"]:
        raise ActionRemindersActivationError(
            "Deployment change_reference does not match reviewed rollout."
        )
    if value["staging_evidence_sha256"] != sha256_file(staging_path):
        raise ActionRemindersActivationError(
            "Deployment record does not bind the exact action-reminder staging evidence."
        )
    if value["rollout_manifest_sha256"] != sha256_file(rollout_path):
        raise ActionRemindersActivationError(
            "Deployment record does not bind the exact reviewed rollout manifest."
        )
    deployed_at = parse_time(
        str(value["deployed_at"]),
        "action-reminder deployed_at",
    )
    if deployed_at < not_before:
        raise ActionRemindersActivationError(
            "Action-reminder deployment predates live staging evidence."
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
        raise ActionRemindersActivationError(
            "Operator status release_id does not match deployment."
        )
    if (
        value.get("decision") != "CONTINUE_COHORT"
        or value.get("breaches") != []
    ):
        raise ActionRemindersActivationError(
            "Operator status must be CONTINUE_COHORT with zero breaches."
        )
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ActionRemindersActivationError(
            "Operator status has no generated_at timestamp."
        )
    generated = parse_time(
        generated_at,
        "operator status generated_at",
    )
    if generated < not_before:
        raise ActionRemindersActivationError(
            "Operator status must be generated after action-reminder deployment."
        )
    age = (now - generated).total_seconds() / 60
    if age < -1:
        raise ActionRemindersActivationError(
            "Operator status is from the future."
        )
    if age > freshness_minutes:
        raise ActionRemindersActivationError(
            f"Operator status is stale ({age:.1f} minutes old)."
        )
    return generated


def fetch_runtime_manifest(
    *,
    base_url: str,
    token: str,
    timeout_seconds: int,
    transport=None,
) -> dict:
    origin = require_https_origin(
        base_url,
        "Production API base URL",
    )
    try:
        with httpx.Client(
            base_url=origin,
            timeout=max(1, timeout_seconds),
            follow_redirects=False,
            transport=transport,
        ) as client:
            response = client.get(
                "/api/v1/runtime-manifest",
                headers={"Authorization": "Bearer " + token},
            )
    except httpx.HTTPError as error:
        raise ActionRemindersActivationError(
            "Could not read deployed runtime manifest: "
            + type(error).__name__
        ) from None
    if response.status_code != 200:
        raise ActionRemindersActivationError(
            "Deployed runtime manifest returned HTTP "
            f"{response.status_code}; expected 200."
        )
    try:
        value = response.json()
    except ValueError:
        raise ActionRemindersActivationError(
            "Deployed runtime manifest did not return JSON."
        ) from None
    if not isinstance(value, dict):
        raise ActionRemindersActivationError(
            "Deployed runtime manifest has an unexpected shape."
        )
    return value


def validate_runtime_manifest(
    value: dict,
    *,
    deployment: dict,
    rollout: dict,
) -> dict:
    if set(value) != {
        "schema_version",
        "source_revision",
        "environment",
        "capabilities",
        "action_providers",
        "cohort",
    }:
        raise ActionRemindersActivationError(
            "Deployed runtime manifest has an unexpected schema."
        )
    if value.get("schema_version") != 1:
        raise ActionRemindersActivationError(
            "Deployed runtime manifest schema version is unsupported."
        )
    if value.get("source_revision") != deployment["source_revision"]:
        raise ActionRemindersActivationError(
            "Deployed backend revision does not match reviewed deployment."
        )
    if value.get("environment") != rollout["environment"]:
        raise ActionRemindersActivationError(
            "Deployed environment does not match reviewed rollout."
        )
    capabilities = value.get("capabilities")
    if capabilities != rollout["capabilities"]:
        raise ActionRemindersActivationError(
            "Deployed capability flags do not exactly match reviewed rollout."
        )
    providers = value.get("action_providers")
    if providers != rollout["action_providers"]:
        raise ActionRemindersActivationError(
            "Deployed action providers do not exactly match reviewed rollout."
        )
    cohort = value.get("cohort")
    if (
        not isinstance(cohort, dict)
        or set(cohort)
        != {"enforced", "configured_members", "max_users"}
    ):
        raise ActionRemindersActivationError(
            "Deployed cohort manifest has an unexpected shape."
        )
    if cohort.get("enforced") is not True:
        raise ActionRemindersActivationError(
            "Deployed backend does not enforce controlled-cohort admission."
        )
    if cohort.get("max_users") != rollout["cohort_max_users"]:
        raise ActionRemindersActivationError(
            "Deployed cohort ceiling does not match reviewed rollout."
        )
    members = cohort.get("configured_members")
    if (
        not isinstance(members, int)
        or isinstance(members, bool)
        or members < 1
        or members > cohort["max_users"]
    ):
        raise ActionRemindersActivationError(
            "Deployed cohort membership count is outside the reviewed ceiling."
        )
    if capabilities.get("action_reminders") is not True:
        raise ActionRemindersActivationError(
            "Deployed backend has action reminders disabled."
        )
    return {
        "schema_version": value["schema_version"],
        "source_revision": value["source_revision"],
        "environment": value["environment"],
        "capabilities": capabilities,
        "action_providers": providers,
        "cohort": cohort,
    }


def build_evidence(
    *,
    deployment: dict,
    staging_path: Path,
    rollout_path: Path,
    deployment_path: Path,
    operator_status_path: Path,
    runtime: dict,
    operator_status: dict,
    now: datetime,
) -> dict:
    return {
        "schema_version": 1,
        "status": "action_reminders_verified",
        "release_id": deployment["release_id"],
        "current_stage": deployment["current_stage"],
        "verified_at": now.isoformat(),
        "change_reference": deployment["change_reference"],
        "deployed_at": deployment["deployed_at"],
        "source_revision": deployment["source_revision"],
        "operator_status_generated_at": operator_status["generated_at"],
        "runtime": runtime,
        "runtime_manifest_sha256": canonical_sha256(runtime),
        "artifact_sha256": {
            "staging_evidence": sha256_file(staging_path),
            "rollout_manifest": sha256_file(rollout_path),
            "deployment_change": sha256_file(deployment_path),
            "operator_status": sha256_file(operator_status_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify production activation of approved calendar reminders "
            "against exact staging evidence, reviewed rollout, "
            "deployed revision/configuration, and fresh cohort health."
        )
    )
    parser.add_argument(
        "--staging-evidence",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--rollout",
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
        "--api-base-url",
        required=True,
    )
    parser.add_argument(
        "--max-cohort-users",
        type=int,
        default=25,
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
        "--timeout-seconds",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()
    if min(
        args.max_cohort_users,
        args.max_staging_age_minutes,
        args.freshness_minutes,
        args.timeout_seconds,
    ) < 1:
        raise SystemExit("Activation limits must be positive.")

    try:
        now = datetime.now(timezone.utc)
        raw_rollout = load_rollout(args.rollout)
        rollout = validate_reviewed_rollout(
            raw_rollout,
            max_cohort_users=args.max_cohort_users,
        )
        staging = load_json(
            args.staging_evidence,
            "action-reminder staging evidence",
        )
        staging_time = validate_staging(
            staging,
            providers=rollout["action_providers"],
            now=now,
            max_age_minutes=args.max_staging_age_minutes,
        )

        deployment = load_json(
            args.deployment_change,
            "action-reminder deployment",
        )
        deployment_time = validate_deployment(
            deployment,
            staging_path=args.staging_evidence,
            rollout_path=args.rollout,
            rollout=rollout,
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

        token = os.environ.get("SHUDDHO_PRODUCTION_VERIFICATION_TOKEN", "")
        if not token:
            raise ActionRemindersActivationError(
                "SHUDDHO_PRODUCTION_VERIFICATION_TOKEN is required."
            )
        remote = fetch_runtime_manifest(
            base_url=args.api_base_url,
            token=token,
            timeout_seconds=args.timeout_seconds,
        )
        runtime = validate_runtime_manifest(
            remote,
            deployment=deployment,
            rollout=rollout,
        )

        evidence = build_evidence(
            deployment=deployment,
            staging_path=args.staging_evidence,
            rollout_path=args.rollout,
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
            "source_revision": evidence["source_revision"],
        }, indent=2))
    except (
        ActionRemindersActivationError,
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
