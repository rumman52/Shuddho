from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from services.coworker.config import Settings


class MicrosoftRolloutActivationError(RuntimeError):
    pass


DEPLOYMENT_KEYS = {
    "release_id",
    "change_reference",
    "deployed_at",
    "frontend_base_url",
    "frontend_source_revision",
    "staging_evidence_sha256",
}


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise MicrosoftRolloutActivationError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise MicrosoftRolloutActivationError(
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
        raise MicrosoftRolloutActivationError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if result.tzinfo is None:
        raise MicrosoftRolloutActivationError(
            f"{label} must include a timezone."
        )
    return result.astimezone(timezone.utc)


def validate_staging(
    evidence: dict,
    *,
    now: datetime,
    max_age_minutes: int,
) -> datetime:
    item = evidence.get("microsoft_actions")
    if not isinstance(item, dict):
        raise MicrosoftRolloutActivationError(
            "Staging evidence has no microsoft_actions result."
        )
    if item.get("status") != "passed":
        raise MicrosoftRolloutActivationError(
            "Microsoft staging evidence is not passed."
        )
    if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
        raise MicrosoftRolloutActivationError(
            "Microsoft staging evidence text is missing."
        )
    verified_at = item.get("verified_at")
    if not isinstance(verified_at, str):
        raise MicrosoftRolloutActivationError(
            "Microsoft staging evidence has no verified_at timestamp."
        )
    verified = parse_time(
        verified_at,
        "microsoft_actions verified_at",
    )
    age = (now - verified).total_seconds() / 60
    if age < -1:
        raise MicrosoftRolloutActivationError(
            "Microsoft staging evidence is from the future."
        )
    if age > max_age_minutes:
        raise MicrosoftRolloutActivationError(
            f"Microsoft staging evidence is stale ({age:.1f} minutes old)."
        )
    return verified


def validate_deployment(
    value: dict,
    evidence_path: Path,
    *,
    not_before: datetime,
) -> datetime:
    if set(value) != DEPLOYMENT_KEYS:
        raise MicrosoftRolloutActivationError(
            "Microsoft rollout deployment record has an unexpected schema."
        )
    if (
        not isinstance(value["release_id"], str)
        or not value["release_id"].strip()
        or not isinstance(value["change_reference"], str)
        or not value["change_reference"].strip()
    ):
        raise MicrosoftRolloutActivationError(
            "Deployment release/change reference is required."
        )
    if value["staging_evidence_sha256"] != sha256_file(evidence_path):
        raise MicrosoftRolloutActivationError(
            "Deployment record does not bind the exact Microsoft staging evidence."
        )
    deployed_at = parse_time(
        str(value["deployed_at"]),
        "Microsoft rollout deployed_at",
    )
    if deployed_at < not_before:
        raise MicrosoftRolloutActivationError(
            "Microsoft rollout deployment predates live staging evidence."
        )
    base = urlparse(str(value["frontend_base_url"]))
    if (
        base.scheme != "https"
        or not base.netloc
        or base.username
        or base.password
        or base.query
        or base.fragment
    ):
        raise MicrosoftRolloutActivationError(
            "frontend_base_url must be a clean HTTPS origin/base URL."
        )
    revision = value["frontend_source_revision"]
    if (
        not isinstance(revision, str)
        or len(revision) < 7
        or len(revision) > 100
        or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for char in revision
        )
    ):
        raise MicrosoftRolloutActivationError(
            "frontend_source_revision is invalid."
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
        raise MicrosoftRolloutActivationError(
            "Operator status release_id does not match rollout deployment."
        )
    if (
        value.get("decision") != "CONTINUE_COHORT"
        or value.get("breaches") != []
    ):
        raise MicrosoftRolloutActivationError(
            "Operator status must be CONTINUE_COHORT with zero breaches."
        )
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise MicrosoftRolloutActivationError(
            "Operator status has no generated_at timestamp."
        )
    generated = parse_time(
        generated_at,
        "operator status generated_at",
    )
    if generated < not_before:
        raise MicrosoftRolloutActivationError(
            "Operator status must be generated after Microsoft rollout deployment."
        )
    age = (now - generated).total_seconds() / 60
    if age < -1:
        raise MicrosoftRolloutActivationError(
            "Operator status is from the future."
        )
    if age > freshness_minutes:
        raise MicrosoftRolloutActivationError(
            f"Operator status is stale ({age:.1f} minutes old)."
        )
    return generated


def require_backend_flags(settings: Settings) -> None:
    if not settings.actions_enabled:
        raise MicrosoftRolloutActivationError(
            "Deployed backend has SHUDDHO_ACTIONS_ENABLED disabled."
        )
    if not settings.microsoft_actions_enabled:
        raise MicrosoftRolloutActivationError(
            "Deployed backend has SHUDDHO_MICROSOFT_ACTIONS_ENABLED disabled."
        )


def manifest_url(base_url: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urljoin(base, "shuddho-rollout-manifest.json")


def fetch_frontend_manifest(
    base_url: str,
    *,
    timeout_seconds: int = 15,
    transport=None,
) -> dict:
    url = manifest_url(base_url)
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            response = client.get(
                url,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as error:
        raise MicrosoftRolloutActivationError(
            f"Could not fetch frontend rollout manifest: {type(error).__name__}"
        ) from None
    if response.status_code != 200:
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest returned "
            f"HTTP {response.status_code}; expected 200."
        )
    if (
        response.headers.get("content-type", "")
        .split(";", 1)[0]
        .strip()
        .lower()
        != "application/json"
    ):
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest did not return application/json."
        )
    if len(response.content) > 16 * 1024:
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest is unexpectedly large."
        )
    try:
        value = response.json()
    except ValueError:
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest is invalid JSON."
        ) from None
    if not isinstance(value, dict):
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest has an unexpected shape."
        )
    return value


def validate_frontend_manifest(
    manifest: dict,
    *,
    expected_revision: str,
) -> None:
    expected_keys = {
        "schema_version",
        "app",
        "source_revision",
        "coworker_enabled",
        "microsoft_actions_enabled",
    }
    if set(manifest) != expected_keys:
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest has an unexpected schema."
        )
    if manifest["schema_version"] != 1:
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest version is unsupported."
        )
    if manifest["app"] != "shuddho-web-editor":
        raise MicrosoftRolloutActivationError(
            "Frontend rollout manifest is for another application."
        )
    if manifest["source_revision"] != expected_revision:
        raise MicrosoftRolloutActivationError(
            "Deployed frontend revision does not match the approved deployment."
        )
    if manifest["coworker_enabled"] is not True:
        raise MicrosoftRolloutActivationError(
            "Deployed frontend Coworker UI is disabled."
        )
    if manifest["microsoft_actions_enabled"] is not True:
        raise MicrosoftRolloutActivationError(
            "Deployed frontend Microsoft action UI is disabled."
        )


def build_evidence(
    *,
    deployment: dict,
    staging_path: Path,
    operator_status_path: Path,
    frontend_manifest: dict,
    now: datetime,
) -> dict:
    return {
        "schema_version": 1,
        "status": "microsoft_rollout_verified",
        "release_id": deployment["release_id"],
        "verified_at": now.isoformat(),
        "change_reference": deployment["change_reference"],
        "deployed_at": deployment["deployed_at"],
        "frontend_base_url": deployment["frontend_base_url"],
        "frontend_source_revision": deployment[
            "frontend_source_revision"
        ],
        "backend": {
            "actions_enabled": True,
            "microsoft_actions_enabled": True,
        },
        "frontend": {
            "coworker_enabled": frontend_manifest[
                "coworker_enabled"
            ],
            "microsoft_actions_enabled": frontend_manifest[
                "microsoft_actions_enabled"
            ],
        },
        "artifact_sha256": {
            "staging_evidence": sha256_file(staging_path),
            "operator_status": sha256_file(operator_status_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Microsoft Coworker rollout after live staging "
            "and an approved backend/frontend deployment."
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
            "Microsoft staging evidence",
        )
        staging_time = validate_staging(
            staging,
            now=now,
            max_age_minutes=args.max_staging_age_minutes,
        )
        deployment = load_json(
            args.deployment_change,
            "Microsoft rollout deployment",
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
        require_backend_flags(settings)

        frontend_manifest = fetch_frontend_manifest(
            deployment["frontend_base_url"],
        )
        validate_frontend_manifest(
            frontend_manifest,
            expected_revision=deployment[
                "frontend_source_revision"
            ],
        )

        evidence = build_evidence(
            deployment=deployment,
            staging_path=args.staging_evidence,
            operator_status_path=args.operator_status,
            frontend_manifest=frontend_manifest,
            now=now,
        )
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "written": str(args.output),
            "status": evidence["status"],
            "frontend_revision": evidence[
                "frontend_source_revision"
            ],
        }, indent=2))
    except (
        MicrosoftRolloutActivationError,
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
