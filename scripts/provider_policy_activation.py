from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.provider_capacity import provider_capacity_snapshot


POLICY_KEYS = {
    "provider_max_concurrent_calls",
    "provider_max_concurrent_per_workspace",
    "provider_max_reserved_tokens",
    "provider_max_reserved_tokens_per_workspace",
    "provider_daily_token_budget",
    "daily_token_budget",
    "provider_lease_seconds",
}
DEPLOYMENT_KEYS = {
    "release_id",
    "change_reference",
    "deployed_at",
    "current_stage",
    "proposed_stage",
    "provider_policy_sha256",
}


class ProviderPolicyActivationError(RuntimeError):
    pass


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ProviderPolicyActivationError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if result.tzinfo is None:
        raise ProviderPolicyActivationError(f"{label} must include a timezone.")
    return result.astimezone(timezone.utc)


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProviderPolicyActivationError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ProviderPolicyActivationError(f"{label} must contain a JSON object.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def positive_int(value, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProviderPolicyActivationError(f"{label} must be a positive integer.")
    return value


def validate_policy(value: dict) -> datetime:
    if value.get("decision") != "ELIGIBLE_FOR_POLICY_REVIEW":
        raise ProviderPolicyActivationError(
            "Provider policy is not eligible for deployment review."
        )
    if value.get("failures") != []:
        raise ProviderPolicyActivationError("Provider policy contains failures.")
    for key in ("release_id", "current_stage", "proposed_stage"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ProviderPolicyActivationError(
                f"Provider policy {key} is required."
            )
    proposed = value.get("proposed_policy")
    if not isinstance(proposed, dict) or set(proposed) != POLICY_KEYS:
        raise ProviderPolicyActivationError(
            "Provider policy proposed_policy has an unexpected schema."
        )
    for key in POLICY_KEYS:
        positive_int(proposed[key], f"proposed_policy.{key}")
    if (
        proposed["provider_max_concurrent_per_workspace"]
        > proposed["provider_max_concurrent_calls"]
    ):
        raise ProviderPolicyActivationError(
            "Proposed workspace concurrency exceeds global concurrency."
        )
    if (
        proposed["provider_max_reserved_tokens_per_workspace"]
        > proposed["provider_max_reserved_tokens"]
    ):
        raise ProviderPolicyActivationError(
            "Proposed workspace reserve exceeds global reserve."
        )
    if proposed["daily_token_budget"] > proposed["provider_daily_token_budget"]:
        raise ProviderPolicyActivationError(
            "Proposed workspace daily budget exceeds the global provider daily budget."
        )
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ProviderPolicyActivationError(
            "Provider policy has no generated_at timestamp."
        )
    return parse_time(generated_at, "provider policy generated_at")


def validate_deployment(
    value: dict,
    policy: dict,
    policy_path: Path,
    *,
    not_before: datetime,
) -> datetime:
    if set(value) != DEPLOYMENT_KEYS:
        raise ProviderPolicyActivationError(
            "Provider policy deployment record has an unexpected schema."
        )
    if value["release_id"] != policy["release_id"]:
        raise ProviderPolicyActivationError(
            "Provider policy deployment release_id does not match."
        )
    if (
        value["current_stage"] != policy["current_stage"]
        or value["proposed_stage"] != policy["proposed_stage"]
    ):
        raise ProviderPolicyActivationError(
            "Provider policy deployment stages do not match the proposal."
        )
    if (
        not isinstance(value["change_reference"], str)
        or not value["change_reference"].strip()
    ):
        raise ProviderPolicyActivationError(
            "Provider policy deployment change_reference is required."
        )
    if value["provider_policy_sha256"] != sha256_file(policy_path):
        raise ProviderPolicyActivationError(
            "Provider policy deployment does not bind this exact policy proposal."
        )
    deployed_at = parse_time(str(value["deployed_at"]), "provider policy deployed_at")
    if deployed_at < not_before:
        raise ProviderPolicyActivationError(
            "Provider policy deployment predates the policy proposal."
        )
    return deployed_at


def validate_operator_status(
    value: dict,
    release_id: str,
    *,
    not_before: datetime,
    freshness_minutes: int,
    now: datetime,
) -> datetime:
    if value.get("release_id") != release_id:
        raise ProviderPolicyActivationError(
            "Operator status release_id does not match."
        )
    if value.get("decision") != "CONTINUE_COHORT" or value.get("breaches") != []:
        raise ProviderPolicyActivationError(
            "Operator status must be CONTINUE_COHORT with zero breaches."
        )
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ProviderPolicyActivationError(
            "Operator status has no generated_at timestamp."
        )
    generated = parse_time(generated_at, "operator status generated_at")
    if generated < not_before:
        raise ProviderPolicyActivationError(
            "Operator status must be generated after the provider policy deployment."
        )
    age_minutes = (now - generated).total_seconds() / 60
    if age_minutes < -1:
        raise ProviderPolicyActivationError("Operator status is from the future.")
    if age_minutes > freshness_minutes:
        raise ProviderPolicyActivationError(
            f"Operator status is stale ({age_minutes:.1f} minutes old)."
        )
    return generated


def deployed_policy(settings: Settings) -> dict:
    return {
        "provider_max_concurrent_calls": settings.provider_max_concurrent_calls,
        "provider_max_concurrent_per_workspace": (
            settings.provider_max_concurrent_per_workspace
        ),
        "provider_max_reserved_tokens": settings.provider_max_reserved_tokens,
        "provider_max_reserved_tokens_per_workspace": (
            settings.provider_max_reserved_tokens_per_workspace
        ),
        "provider_daily_token_budget": settings.provider_daily_token_budget,
        "daily_token_budget": settings.daily_token_budget,
        "provider_lease_seconds": settings.provider_lease_seconds,
    }


def require_deployed_policy(settings: Settings, policy: dict) -> dict:
    actual = deployed_policy(settings)
    expected = policy["proposed_policy"]
    mismatches = {
        key: {"expected": expected[key], "actual": actual[key]}
        for key in POLICY_KEYS
        if actual[key] != expected[key]
    }
    if mismatches:
        keys = ", ".join(sorted(mismatches))
        raise ProviderPolicyActivationError(
            f"Deployed provider policy does not match the reviewed proposal: {keys}."
        )
    return actual


def validate_runtime_snapshot(snapshot: dict, policy: dict) -> None:
    proposed = policy["proposed_policy"]
    if snapshot["active_calls"] > proposed["provider_max_concurrent_calls"]:
        raise ProviderPolicyActivationError(
            "Active provider calls exceed the deployed global concurrency policy."
        )
    if snapshot["reserved_tokens"] > proposed["provider_max_reserved_tokens"]:
        raise ProviderPolicyActivationError(
            "Active provider token reservations exceed the deployed reserve policy."
        )
    if snapshot["daily_allocated_tokens"] > proposed["provider_daily_token_budget"]:
        raise ProviderPolicyActivationError(
            "Current UTC-day provider allocation exceeds the deployed daily budget."
        )


def build_evidence(
    *,
    policy: dict,
    deployment: dict,
    operator_status: dict,
    actual_policy: dict,
    runtime_snapshot: dict,
    policy_path: Path,
    deployment_path: Path,
    operator_status_path: Path,
    now: datetime,
) -> dict:
    return {
        "schema_version": 1,
        "status": "provider_policy_verified",
        "release_id": policy["release_id"],
        "verified_at": now.isoformat(),
        "current_stage": policy["current_stage"],
        "proposed_stage": policy["proposed_stage"],
        "change_reference": deployment["change_reference"],
        "deployment_deployed_at": deployment["deployed_at"],
        "operator_status_generated_at": operator_status["generated_at"],
        "deployed_policy": actual_policy,
        "runtime": {
            "active_calls": int(runtime_snapshot["active_calls"]),
            "reserved_tokens": int(runtime_snapshot["reserved_tokens"]),
            "daily_allocated_tokens": int(runtime_snapshot["daily_allocated_tokens"]),
        },
        "artifact_sha256": {
            "provider_policy": sha256_file(policy_path),
            "deployment_change": sha256_file(deployment_path),
            "operator_status": sha256_file(operator_status_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a reviewed Shuddho provider policy after deployment."
    )
    parser.add_argument("--provider-policy", type=Path, required=True)
    parser.add_argument("--deployment-change", type=Path, required=True)
    parser.add_argument("--operator-status", type=Path, required=True)
    parser.add_argument("--freshness-minutes", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.freshness_minutes < 1:
        raise SystemExit("--freshness-minutes must be positive.")

    try:
        policy = load_json(args.provider_policy, "provider policy")
        policy_time = validate_policy(policy)
        deployment = load_json(
            args.deployment_change,
            "provider policy deployment",
        )
        deployment_time = validate_deployment(
            deployment,
            policy,
            args.provider_policy,
            not_before=policy_time,
        )
        operator_status = load_json(args.operator_status, "operator status")
        now = datetime.now(timezone.utc)
        validate_operator_status(
            operator_status,
            policy["release_id"],
            not_before=deployment_time,
            freshness_minutes=args.freshness_minutes,
            now=now,
        )

        settings = Settings.from_env()
        actual = require_deployed_policy(settings, policy)
        sessions = session_factory(settings.database_url)
        engine = sessions.kw["bind"]
        try:
            with sessions.begin() as db:
                runtime = provider_capacity_snapshot(db)
        finally:
            engine.dispose()
        validate_runtime_snapshot(runtime, policy)

        evidence = build_evidence(
            policy=policy,
            deployment=deployment,
            operator_status=operator_status,
            actual_policy=actual,
            runtime_snapshot=runtime,
            policy_path=args.provider_policy,
            deployment_path=args.deployment_change,
            operator_status_path=args.operator_status,
            now=now,
        )
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "written": str(args.output),
            "status": evidence["status"],
            "current_stage": evidence["current_stage"],
            "proposed_stage": evidence["proposed_stage"],
        }, indent=2))
    except (ProviderPolicyActivationError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
