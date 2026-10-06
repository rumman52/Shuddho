from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.cohort_release_gate import declared_action_providers, load_rollout, validate_rollout
from scripts.personal_transactions_activation import (
    canonical_sha256,
    fetch_runtime_manifest,
    fetch_transaction_authority_manifest,
    load_json,
    parse_time,
    sha256_file,
    validate_deployment as validate_base_deployment,
    validate_operator_status as validate_base_operator_status,
)
from scripts.release_contract import normalize_capabilities


class NegotiationProposalPromotionActivationError(RuntimeError):
    pass


def _raise(message: str):
    raise NegotiationProposalPromotionActivationError(message)


def validate_staging(
    evidence: dict,
    *,
    expected_operations: list[str],
    now: datetime,
    max_age_minutes: int,
) -> datetime:
    item = evidence.get("negotiation_proposal_promotion")
    if not isinstance(item, dict) or item.get("status") != "passed":
        _raise("Negotiation-proposal-promotion staging evidence is not passed.")
    if not isinstance(item.get("evidence"), str) or not item["evidence"].strip():
        _raise("Negotiation-proposal-promotion staging evidence text is missing.")
    operation_evidence = item.get("operation_evidence")
    if not isinstance(operation_evidence, dict) or set(operation_evidence) != set(expected_operations):
        _raise(
            "Negotiation-proposal-promotion staging evidence does not exactly "
            "match the reviewed transaction-operation allowlist."
        )
    verified: list[datetime] = []
    for operation in sorted(expected_operations):
        record = operation_evidence.get(operation)
        if (
            not isinstance(record, dict)
            or set(record) != {"evidence", "verified_at"}
            or not isinstance(record.get("evidence"), str)
            or not record["evidence"].strip()
            or not isinstance(record.get("verified_at"), str)
        ):
            _raise(f"Promotion staging evidence for {operation} is invalid.")
        when = parse_time(record["verified_at"], f"negotiation_proposal_promotion {operation} verified_at")
        age = (now - when).total_seconds() / 60
        if age < -1:
            _raise(f"Promotion staging evidence for {operation} is from the future.")
        if age > max_age_minutes:
            _raise(f"Promotion staging evidence for {operation} is stale ({age:.1f} minutes old).")
        verified.append(when)
    if not verified:
        _raise("Promotion staging evidence contains no qualified operations.")
    return max(verified)


def validate_reviewed_rollout(rollout: dict, *, max_cohort_users: int) -> dict:
    failures = validate_rollout(rollout, max_cohort_users=max_cohort_users)
    if failures:
        _raise("Reviewed rollout manifest is invalid: " + ", ".join(failures))
    capabilities = rollout["capabilities"]
    required = (
        "coworker",
        "actions",
        "connector_trust_boundary",
        "personal_transactions",
        "agent_runtime",
        "intelligent_planner",
        "action_proposals",
        "negotiation_proposal_promotion",
    )
    missing = [key for key in required if capabilities.get(key) is not True]
    if missing:
        _raise(
            "Reviewed rollout does not enable promotion prerequisites: "
            + ", ".join(missing)
        )
    rollback = rollout["rollback"]
    if (
        rollback.get("negotiation_proposal_promotion_kill_switch")
        != "SHUDDHO_NEGOTIATION_PROPOSAL_PROMOTION_ENABLED=false"
    ):
        _raise("Reviewed rollout has no exact negotiation-promotion kill switch.")
    operations = sorted(rollout.get("transaction_operations", []))
    if not operations or any(
        not isinstance(value, str)
        or not value.endswith(":negotiation_commitment_email")
        for value in operations
    ):
        _raise(
            "Reviewed promotion rollout requires one or more qualified "
            "negotiation_commitment_email operations."
        )
    providers = sorted(declared_action_providers(rollout))
    operation_providers = sorted({item.split(":", 1)[0] for item in operations})
    if any(provider not in providers for provider in operation_providers):
        _raise("Reviewed transaction operations include an undeclared action provider.")
    return {
        "release_id": rollout["release_id"],
        "environment": rollout["environment"],
        "capabilities": normalize_capabilities(capabilities),
        "action_providers": providers,
        "transaction_operations": operations,
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
    try:
        return validate_base_deployment(
            value,
            staging_path=staging_path,
            rollout_path=rollout_path,
            rollout=rollout,
            not_before=not_before,
        )
    except Exception as error:
        _raise(str(error))


def validate_operator_status(
    value: dict,
    release_id: str,
    *,
    not_before: datetime,
    now: datetime,
    freshness_minutes: int,
) -> datetime:
    try:
        return validate_base_operator_status(
            value,
            release_id,
            not_before=not_before,
            now=now,
            freshness_minutes=freshness_minutes,
        )
    except Exception as error:
        _raise(str(error))


def validate_runtime_manifest(value: dict, *, deployment: dict, rollout: dict) -> dict:
    required_keys = {
        "schema_version", "source_revision", "environment",
        "capabilities", "action_providers", "cohort",
    }
    if set(value) != required_keys or value.get("schema_version") != 1:
        _raise("Deployed runtime manifest has an unexpected schema.")
    if value.get("source_revision") != deployment["source_revision"]:
        _raise("Deployed backend revision does not match reviewed deployment.")
    if value.get("environment") != rollout["environment"]:
        _raise("Deployed environment does not match reviewed rollout.")
    if value.get("capabilities") != rollout["capabilities"]:
        _raise("Deployed capability flags do not exactly match reviewed rollout.")
    if value.get("action_providers") != rollout["action_providers"]:
        _raise("Deployed action providers do not exactly match reviewed rollout.")
    cohort = value.get("cohort")
    if (
        not isinstance(cohort, dict)
        or set(cohort) != {"enforced", "configured_members", "max_users"}
        or cohort.get("enforced") is not True
        or cohort.get("max_users") != rollout["cohort_max_users"]
    ):
        _raise("Deployed cohort enforcement does not match reviewed rollout.")
    members = cohort.get("configured_members")
    if (
        not isinstance(members, int)
        or isinstance(members, bool)
        or members < 1
        or members > cohort["max_users"]
    ):
        _raise("Deployed cohort membership is outside the reviewed ceiling.")
    capabilities = value["capabilities"]
    for key in (
        "coworker", "actions", "connector_trust_boundary",
        "personal_transactions", "agent_runtime", "intelligent_planner",
        "action_proposals", "negotiation_proposal_promotion",
    ):
        if capabilities.get(key) is not True:
            _raise(f"Deployed runtime does not enable required capability {key}.")
    return {
        "schema_version": 1,
        "source_revision": value["source_revision"],
        "environment": value["environment"],
        "capabilities": capabilities,
        "action_providers": value["action_providers"],
        "cohort": cohort,
    }


def validate_transaction_authority_manifest(
    value: dict,
    *,
    deployment: dict,
    rollout: dict,
) -> dict:
    schema = value.get("schema_version")
    base_keys = {
        "schema_version",
        "source_revision",
        "personal_transactions_enabled",
        "operations",
    }
    v1_keys = base_keys | {"restaurant_reservations_enabled"}
    v2_keys = v1_keys | {
        "shopping_checkout_enabled",
        "travel_booking_enabled",
    }
    if (
        schema == 1
        and set(value) not in {frozenset(base_keys), frozenset(v1_keys)}
    ) or (
        schema == 2
        and set(value) != v2_keys
    ) or schema not in {1, 2}:
        message = "Deployed transaction authority manifest has an unexpected schema."
        _raise(message)
    if value.get("source_revision") != deployment["source_revision"]:
        message = "Deployed transaction authority revision does not match reviewed deployment."
        _raise(message)
    if value.get("personal_transactions_enabled") is not True:
        message = "Deployed transaction authority has personal transactions disabled."
        _raise(message)
    operations = value.get("operations")
    if (
        not isinstance(operations, list)
        or operations != rollout["transaction_operations"]
    ):
        message = "Deployed transaction operations do not exactly match reviewed rollout."
        _raise(message)
    normalized = {
        "schema_version": schema,
        "source_revision": value["source_revision"],
        "personal_transactions_enabled": True,
        "operations": list(operations),
    }
    if "restaurant_reservations_enabled" in value:
        normalized["restaurant_reservations_enabled"] = value[
            "restaurant_reservations_enabled"
        ]
    if schema == 2:
        normalized["shopping_checkout_enabled"] = value["shopping_checkout_enabled"]
        normalized["travel_booking_enabled"] = value["travel_booking_enabled"]
    return normalized


def build_evidence(
    *,
    deployment: dict,
    staging_path: Path,
    rollout_path: Path,
    deployment_path: Path,
    operator_status_path: Path,
    runtime: dict,
    transaction_authority: dict,
    operator_status: dict,
    now: datetime,
) -> dict:
    return {
        "schema_version": 1,
        "status": "negotiation_proposal_promotion_verified",
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
        "transaction_authority_manifest_sha256": canonical_sha256(transaction_authority),
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
            "Verify production activation of the exact-hash PA-09 negotiation "
            "proposal-promotion bridge."
        )
    )
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
        reviewed = validate_reviewed_rollout(
            load_rollout(args.rollout),
            max_cohort_users=args.max_cohort_users,
        )
        staging = load_json(args.staging_evidence, "promotion staging evidence")
        staging_time = validate_staging(
            staging,
            expected_operations=reviewed["transaction_operations"],
            now=now,
            max_age_minutes=args.max_staging_age_minutes,
        )
        deployment = load_json(args.deployment_change, "promotion deployment")
        deployment_time = validate_deployment(
            deployment,
            staging_path=args.staging_evidence,
            rollout_path=args.rollout,
            rollout=reviewed,
            not_before=staging_time,
        )
        operator = load_json(args.operator_status, "operator status")
        validate_operator_status(
            operator,
            deployment["release_id"],
            not_before=deployment_time,
            now=now,
            freshness_minutes=args.freshness_minutes,
        )
        token = os.environ.get("SHUDDHO_PRODUCTION_VERIFICATION_TOKEN", "")
        if not token:
            _raise("SHUDDHO_PRODUCTION_VERIFICATION_TOKEN is required.")
        runtime = validate_runtime_manifest(
            fetch_runtime_manifest(
                base_url=args.api_base_url,
                token=token,
                timeout_seconds=args.timeout_seconds,
            ),
            deployment=deployment,
            rollout=reviewed,
        )
        authority = validate_transaction_authority_manifest(
            fetch_transaction_authority_manifest(
                base_url=args.api_base_url,
                token=token,
                timeout_seconds=args.timeout_seconds,
            ),
            deployment=deployment,
            rollout=reviewed,
        )
        evidence = build_evidence(
            deployment=deployment,
            staging_path=args.staging_evidence,
            rollout_path=args.rollout,
            deployment_path=args.deployment_change,
            operator_status_path=args.operator_status,
            runtime=runtime,
            transaction_authority=authority,
            operator_status=operator,
            now=now,
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(evidence, indent=2))
    except Exception as error:
        if isinstance(error, SystemExit):
            raise
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
