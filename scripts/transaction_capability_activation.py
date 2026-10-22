from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from scripts.cohort_release_gate import (
    declared_action_providers,
    validate_rollout,
)
from scripts.release_contract import normalize_capabilities


class TransactionCapabilityActivationError(RuntimeError):
    pass


CAPABILITIES = {
    "restaurant_reservations": {
        "status": "restaurant_reservations_verified",
        "flag": "restaurant_reservations_enabled",
        "operation_suffix": "restaurant_reservation_create",
        "kill_switch": "SHUDDHO_RESTAURANT_RESERVATIONS_ENABLED=false",
        "required_provider": "opentable",
    },
    "shopping_checkout": {
        "status": "shopping_checkout_verified",
        "flag": "shopping_checkout_enabled",
        "operation_suffix": "shopping_checkout_create",
        "kill_switch": "SHUDDHO_SHOPPING_CHECKOUT_ENABLED=false",
        "required_provider": None,
    },
    "travel_booking": {
        "status": "travel_booking_verified",
        "flag": "travel_booking_enabled",
        "operation_suffix": "travel_booking_create",
        "kill_switch": "SHUDDHO_TRAVEL_BOOKING_ENABLED=false",
        "required_provider": None,
    },
}

DEPLOYMENT_KEYS = {
    "release_id",
    "change_reference",
    "current_stage",
    "deployed_at",
    "source_revision",
    "staging_evidence_sha256",
    "rollout_manifest_sha256",
}


def canonical_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise TransactionCapabilityActivationError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TransactionCapabilityActivationError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TransactionCapabilityActivationError(
            f"{label} must include a timezone offset."
        )
    return parsed.astimezone(timezone.utc)


def _reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str):
    raise ValueError(f"non-finite JSON constant: {value}")


def _strict_json_loads(raw: str | bytes):
    # Release artifacts and live authority responses must have one meaning
    # across all JSON decoders, reviewers and providers.
    return json.loads(
        raw,
        object_pairs_hook=_reject_duplicate_json_keys,
        parse_constant=_reject_nonfinite_json,
    )


def load_json(path: Path, label: str) -> dict:
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TransactionCapabilityActivationError(
            f"Could not read {label}: {type(exc).__name__}."
        ) from None
    if not isinstance(value, dict):
        raise TransactionCapabilityActivationError(
            f"{label} must contain a JSON object."
        )
    return value


def validate_reviewed_rollout(
    rollout: dict,
    *,
    capability: str,
    operation: str,
    max_cohort_users: int,
) -> dict:
    spec = CAPABILITIES[capability]
    failures = validate_rollout(rollout, max_cohort_users=max_cohort_users)
    if failures:
        raise TransactionCapabilityActivationError(
            "Reviewed rollout manifest is invalid: " + ", ".join(failures)
        )
    capabilities = normalize_capabilities(rollout["capabilities"])
    if (
        capabilities.get("actions") is not True
        or capabilities.get("connector_trust_boundary") is not True
        or capabilities.get("personal_transactions") is not True
        or capabilities.get(capability) is not True
    ):
        raise TransactionCapabilityActivationError(
            f"Reviewed rollout does not enable the prerequisites and {capability}."
        )
    if (
        rollout["rollback"].get(f"{capability}_kill_switch")
        != spec["kill_switch"]
    ):
        raise TransactionCapabilityActivationError(
            f"Reviewed rollout does not bind the exact {capability} kill switch."
        )
    operations = rollout.get("transaction_operations")
    if not isinstance(operations, list) or operation not in operations:
        raise TransactionCapabilityActivationError(
            "Reviewed rollout does not contain the exact transaction operation."
        )
    provider, separator, action_kind = operation.partition(":")
    if not separator or action_kind != spec["operation_suffix"]:
        raise TransactionCapabilityActivationError(
            "Reviewed operation does not match the selected transaction capability."
        )
    providers = sorted(declared_action_providers(rollout))
    if provider not in providers:
        raise TransactionCapabilityActivationError(
            "Reviewed operation provider is not in action_providers."
        )
    required_provider = spec["required_provider"]
    if required_provider is not None and provider != required_provider:
        raise TransactionCapabilityActivationError(
            f"{capability} requires provider {required_provider}."
        )
    return {
        "release_id": rollout["release_id"],
        "environment": rollout["environment"],
        "capabilities": capabilities,
        "action_providers": providers,
        "transaction_operations": sorted(operations),
        "cohort_max_users": rollout["cohort"]["max_users"],
        "change_reference": rollout["incident"]["change_reference"],
        "provider": provider,
        "operation": operation,
    }


def validate_staging(
    value: dict,
    *,
    capability: str,
    operation: str,
    now: datetime,
    max_age_minutes: int,
) -> datetime:
    item = value.get(capability)
    if not isinstance(item, dict):
        raise TransactionCapabilityActivationError(
            f"Staging evidence has no {capability} result."
        )
    if (
        item.get("status") != "passed"
        or not isinstance(item.get("evidence"), str)
        or not item["evidence"].strip()
        or item.get("operation") != operation
        or not isinstance(item.get("provider_evidence_sha256"), str)
        or len(item["provider_evidence_sha256"]) != 64
        or any(
            char not in "0123456789abcdef"
            for char in item["provider_evidence_sha256"]
        )
    ):
        raise TransactionCapabilityActivationError(
            f"{capability} staging evidence does not bind the exact provider operation/evidence."
        )
    verified = parse_time(item.get("verified_at"), f"{capability} verified_at")
    age = (now - verified).total_seconds() / 60
    if age < -1:
        raise TransactionCapabilityActivationError(
            f"{capability} staging evidence is from the future."
        )
    if age > max_age_minutes:
        raise TransactionCapabilityActivationError(
            f"{capability} staging evidence is stale."
        )
    return verified


def validate_deployment(
    value: dict,
    *,
    staging_path: Path,
    rollout_path: Path,
    rollout: dict,
    not_before: datetime,
) -> datetime:
    if set(value) != DEPLOYMENT_KEYS:
        raise TransactionCapabilityActivationError(
            "Transaction capability deployment has an unexpected schema."
        )
    for key in ("release_id", "change_reference", "current_stage", "source_revision"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise TransactionCapabilityActivationError(
                f"Deployment {key} is required."
            )
    revision = value["source_revision"]
    if (
        len(revision) != 40
        or revision != revision.lower()
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise TransactionCapabilityActivationError(
            "Deployment source_revision must be a full lowercase Git SHA-1."
        )
    if value["release_id"] != rollout["release_id"]:
        raise TransactionCapabilityActivationError(
            "Deployment release_id does not match reviewed rollout."
        )
    if value["change_reference"] != rollout["change_reference"]:
        raise TransactionCapabilityActivationError(
            "Deployment change_reference does not match reviewed rollout."
        )
    if value["staging_evidence_sha256"] != sha256_file(staging_path):
        raise TransactionCapabilityActivationError(
            "Deployment does not bind the exact staging evidence."
        )
    if value["rollout_manifest_sha256"] != sha256_file(rollout_path):
        raise TransactionCapabilityActivationError(
            "Deployment does not bind the exact rollout manifest."
        )
    deployed_at = parse_time(value["deployed_at"], "deployed_at")
    if deployed_at < not_before:
        raise TransactionCapabilityActivationError(
            "Deployment predates live staging evidence."
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
    if (
        value.get("release_id") != release_id
        or value.get("decision") != "CONTINUE_COHORT"
        or value.get("breaches") != []
    ):
        raise TransactionCapabilityActivationError(
            "Operator status must bind the release and be CONTINUE_COHORT with zero breaches."
        )
    generated = parse_time(value.get("generated_at"), "operator generated_at")
    if generated < not_before:
        raise TransactionCapabilityActivationError(
            "Operator status predates deployment."
        )
    age = (now - generated).total_seconds() / 60
    if age < -1 or age > freshness_minutes:
        raise TransactionCapabilityActivationError(
            "Operator status is not fresh."
        )
    return generated


def _same_json_value_and_type(actual: object, expected: object) -> bool:
    """Compare parsed JSON without Python bool/int or int/float coercion."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _same_json_value_and_type(actual[key], expected[key])
            for key in expected
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_json_value_and_type(left, right)
            for left, right in zip(actual, expected)
        )
    return actual == expected


def validate_runtime_manifest(value: dict, *, deployment: dict, rollout: dict) -> dict:
    expected_keys = {
        "schema_version",
        "source_revision",
        "environment",
        "capabilities",
        "action_providers",
        "cohort",
    }
    if (
        set(value) != expected_keys
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise TransactionCapabilityActivationError(
            "Runtime manifest has an unexpected schema."
        )
    if (
        value.get("source_revision") != deployment["source_revision"]
        or value.get("environment") != rollout["environment"]
        or not _same_json_value_and_type(
            value.get("capabilities"), rollout["capabilities"]
        )
        or not isinstance(value.get("action_providers"), list)
        or sorted(value["action_providers"]) != rollout["action_providers"]
    ):
        raise TransactionCapabilityActivationError(
            "Runtime manifest does not exactly match the reviewed deployment."
        )
    cohort = value.get("cohort")
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"enforced", "configured_members", "max_users"}
        or cohort.get("enforced") is not True
        or type(cohort.get("max_users")) is not int
        or cohort["max_users"] != rollout["cohort_max_users"]
        or not isinstance(cohort.get("configured_members"), int)
        or isinstance(cohort.get("configured_members"), bool)
        or not 1 <= cohort["configured_members"] <= cohort["max_users"]
    ):
        raise TransactionCapabilityActivationError(
            "Runtime manifest does not prove controlled-cohort enforcement."
        )
    return value


def validate_transaction_authority(
    value: dict,
    *,
    deployment: dict,
    rollout: dict,
    capability: str,
) -> dict:
    expected_keys = {
        "schema_version",
        "source_revision",
        "personal_transactions_enabled",
        "restaurant_reservations_enabled",
        "shopping_checkout_enabled",
        "travel_booking_enabled",
        "operations",
    }
    if (
        set(value) != expected_keys
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 2
    ):
        raise TransactionCapabilityActivationError(
            "Transaction authority manifest must be schema v2."
        )
    spec = CAPABILITIES[capability]
    # The endpoint reports every transaction flag, not just the selected one.
    # Reject any runtime capability that exceeds the approved rollout scope.
    reviewed_capabilities = rollout.get("capabilities")
    if not isinstance(reviewed_capabilities, dict) or any(
        type(reviewed_capabilities.get(name)) is not bool
        or value.get(specification["flag"]) is not reviewed_capabilities[name]
        for name, specification in CAPABILITIES.items()
    ):
        raise TransactionCapabilityActivationError(
            "Runtime transaction authority flags do not match reviewed capability scope."
        )
    if (
        value.get("source_revision") != deployment["source_revision"]
        or value.get("personal_transactions_enabled") is not True
        or value.get(spec["flag"]) is not True
        or value.get("operations") != rollout["transaction_operations"]
    ):
        raise TransactionCapabilityActivationError(
            "Transaction authority does not exactly match the reviewed capability/operation set."
        )
    return value


def _verified_https_origin(base_url: str) -> str:
    """Reject ambiguous or plaintext destinations before adding a bearer token."""
    error = "Production verifier API base URL must be an HTTPS origin without credentials, path, query or fragment."
    if not isinstance(base_url, str) or not base_url or base_url != base_url.strip():
        raise TransactionCapabilityActivationError(error)
    try:
        origin = httpx.URL(base_url)
    except (ValueError, TypeError):
        raise TransactionCapabilityActivationError(error) from None
    if (
        origin.scheme != "https"
        or not origin.host
        or origin.username
        or origin.password
        or origin.path != "/"
        or origin.query
        or origin.fragment
    ):
        raise TransactionCapabilityActivationError(error)
    return str(origin)


def fetch_json(
    base_url: str,
    path: str,
    *,
    token: str,
    timeout_seconds: int,
) -> dict:
    verified_origin = _verified_https_origin(base_url)
    with httpx.Client(
        base_url=verified_origin,
        timeout=timeout_seconds,
        follow_redirects=False,
    ) as client:
        response = client.get(
            path,
            headers={"Authorization": "Bearer " + token},
        )
    if response.status_code != 200:
        raise TransactionCapabilityActivationError(
            f"Runtime evidence endpoint {path} returned HTTP {response.status_code}."
        )
    try:
        value = _strict_json_loads(response.content)
    except ValueError:
        raise TransactionCapabilityActivationError(
            f"Runtime evidence endpoint {path} did not return JSON."
        ) from None
    if not isinstance(value, dict):
        raise TransactionCapabilityActivationError(
            f"Runtime evidence endpoint {path} returned an unexpected shape."
        )
    return value


def build_evidence(
    *,
    capability: str,
    deployment: dict,
    staging: dict,
    staging_path: Path,
    rollout_path: Path,
    deployment_path: Path,
    operator_status_path: Path,
    runtime: dict,
    transaction_authority: dict,
    operator_status: dict,
    now: datetime,
) -> dict:
    provider_evidence_sha256 = staging[capability]["provider_evidence_sha256"]
    result = {
        "schema_version": 1,
        "status": CAPABILITIES[capability]["status"],
        "capability": capability,
        "operation": staging[capability]["operation"],
        "provider_evidence_sha256": provider_evidence_sha256,
        "release_id": deployment["release_id"],
        "current_stage": deployment["current_stage"],
        "verified_at": now.isoformat(),
        "change_reference": deployment["change_reference"],
        "deployed_at": deployment["deployed_at"],
        "source_revision": deployment["source_revision"],
        "operator_status_generated_at": operator_status["generated_at"],
        "runtime": runtime,
        "runtime_manifest_sha256": canonical_sha256(runtime),
        "transaction_authority": transaction_authority,
        "transaction_authority_manifest_sha256": canonical_sha256(
            transaction_authority
        ),
        "artifact_sha256": {
            "staging_evidence": sha256_file(staging_path),
            "rollout_manifest": sha256_file(rollout_path),
            "deployment_change": sha256_file(deployment_path),
            "operator_status": sha256_file(operator_status_path),
        },
    }
    result["activation_sha256"] = canonical_sha256(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify one separately gated production transaction capability."
    )
    parser.add_argument(
        "--capability",
        choices=sorted(CAPABILITIES),
        required=True,
    )
    parser.add_argument("--operation", required=True)
    parser.add_argument("--staging-evidence", type=Path, required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--deployment-change", type=Path, required=True)
    parser.add_argument("--operator-status", type=Path, required=True)
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--max-cohort-users", type=int, default=25)
    parser.add_argument("--max-staging-age-minutes", type=int, default=24 * 60)
    parser.add_argument("--freshness-minutes", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
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
        rollout_path = args.rollout
        raw_rollout = load_json(rollout_path, "rollout")
        rollout = validate_reviewed_rollout(
            raw_rollout,
            capability=args.capability,
            operation=args.operation,
            max_cohort_users=args.max_cohort_users,
        )
        staging_path = args.staging_evidence
        staging = load_json(staging_path, "staging evidence")
        staging_time = validate_staging(
            staging,
            capability=args.capability,
            operation=args.operation,
            now=now,
            max_age_minutes=args.max_staging_age_minutes,
        )
        deployment_path = args.deployment_change
        deployment = load_json(deployment_path, "deployment")
        deployed_at = validate_deployment(
            deployment,
            staging_path=staging_path,
            rollout_path=rollout_path,
            rollout=rollout,
            not_before=staging_time,
        )
        operator_path = args.operator_status
        operator = load_json(operator_path, "operator status")
        validate_operator_status(
            operator,
            deployment["release_id"],
            not_before=deployed_at,
            now=now,
            freshness_minutes=args.freshness_minutes,
        )

        token = os.environ.get("SHUDDHO_PRODUCTION_VERIFICATION_TOKEN", "")
        if not token:
            raise TransactionCapabilityActivationError(
                "SHUDDHO_PRODUCTION_VERIFICATION_TOKEN is required."
            )
        runtime = validate_runtime_manifest(
            fetch_json(
                args.api_base_url,
                "/api/v1/runtime-manifest",
                token=token,
                timeout_seconds=args.timeout_seconds,
            ),
            deployment=deployment,
            rollout=rollout,
        )
        authority = validate_transaction_authority(
            fetch_json(
                args.api_base_url,
                "/api/v1/transaction-authority-manifest",
                token=token,
                timeout_seconds=args.timeout_seconds,
            ),
            deployment=deployment,
            rollout=rollout,
            capability=args.capability,
        )
        evidence = build_evidence(
            capability=args.capability,
            deployment=deployment,
            staging=staging,
            staging_path=staging_path,
            rollout_path=rollout_path,
            deployment_path=deployment_path,
            operator_status_path=operator_path,
            runtime=runtime,
            transaction_authority=authority,
            operator_status=operator,
            now=now,
        )
        args.output.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": evidence["status"],
            "capability": args.capability,
            "operation": args.operation,
            "output": str(args.output),
        }, indent=2))
    except (TransactionCapabilityActivationError, OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
