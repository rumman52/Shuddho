from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.coworker.action_registry import (
    ACTION_SPECS,
    registered_transaction_operations,
    stable_digest,
)


class TransactionRuntimeRegistrationPlanError(RuntimeError):
    pass


SHOPPING_KIND = "shopping_checkout_create"
TRAVEL_KIND = "travel_booking_create"

COMMON_REVIEW_KEYS = {
    "schema_version",
    "status",
    "provider",
    "operation",
    "adapter_revision",
    "qualification_sha256",
    "registration_proposal_sha256",
    "conformance_sha256",
    "handoff_sha256",
    "change_reference",
    "reviewer_reference",
    "reviewed_at",
    "compiled_at",
    "registration_authority",
    "operation_allowlisted",
    "external_action_registered",
    "runtime_enabled",
    "identity_authority",
    "payment_authority",
    "runtime_registration_review_sha256",
}

SHOPPING_REVIEW_KEYS = COMMON_REVIEW_KEYS | {
    "checkout_origin",
    "live_probe_evidence_sha256",
}

TRAVEL_REVIEW_KEYS = COMMON_REVIEW_KEYS | {
    "booking_origin",
    "travel_kind",
    "traveler_fields_sent",
}


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TransactionRuntimeRegistrationPlanError(
            f"{label} must include a timezone offset."
        )
    return value.astimezone(timezone.utc)


def _parse_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise TransactionRuntimeRegistrationPlanError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TransactionRuntimeRegistrationPlanError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    return _aware(parsed, label=label)


def _sha(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TransactionRuntimeRegistrationPlanError(
            f"{label} must be a lowercase SHA-256."
        )
    return value


def _revision(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TransactionRuntimeRegistrationPlanError(
            f"{label} must be a full lowercase Git SHA-1."
        )
    return value


def _provider(value: object) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[a-z0-9_]{2,40}", value)
    ):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime registration provider identifier is invalid."
        )
    return value


def _review_type(value: dict) -> tuple[str, set[str]]:
    operation = value.get("operation")
    if isinstance(operation, str) and operation.endswith(f":{SHOPPING_KIND}"):
        return SHOPPING_KIND, SHOPPING_REVIEW_KEYS
    if isinstance(operation, str) and operation.endswith(f":{TRAVEL_KIND}"):
        return TRAVEL_KIND, TRAVEL_REVIEW_KEYS
    raise TransactionRuntimeRegistrationPlanError(
        "TX-26 supports only reviewed shopping checkout or travel booking operations."
    )


def _validate_review(
    value: dict,
    *,
    now: datetime,
    max_review_age_hours: int,
) -> tuple[str, dict]:
    if not isinstance(value, dict):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review must be a JSON object."
        )

    action_kind, expected_keys = _review_type(value)
    if set(value) != expected_keys:
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review has an unexpected schema."
        )
    if value["schema_version"] != 1:
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review schema version is unsupported."
        )
    if value["status"] != "eligible_for_runtime_registration_review":
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review is not eligible."
        )

    provider = _provider(value["provider"])
    expected_operation = f"{provider}:{action_kind}"
    if value["operation"] != expected_operation:
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review operation does not match provider/action kind."
        )
    _revision(value["adapter_revision"], label="adapter_revision")

    for field in (
        "qualification_sha256",
        "registration_proposal_sha256",
        "conformance_sha256",
        "handoff_sha256",
    ):
        _sha(value[field], label=field)
    if action_kind == SHOPPING_KIND:
        _sha(
            value["live_probe_evidence_sha256"],
            label="live_probe_evidence_sha256",
        )
        origin = value["checkout_origin"]
    else:
        origin = value["booking_origin"]
        if value["travel_kind"] not in {"flight", "lodging"}:
            raise TransactionRuntimeRegistrationPlanError(
                "Travel runtime review has an unsupported travel kind."
            )
        traveler_fields = value["traveler_fields_sent"]
        if (
            not isinstance(traveler_fields, list)
            or traveler_fields != sorted(traveler_fields)
            or len(traveler_fields) != len(set(traveler_fields))
            or any(not isinstance(item, str) or not item for item in traveler_fields)
        ):
            raise TransactionRuntimeRegistrationPlanError(
                "Travel runtime review traveler fields are not canonical."
            )

    if (
        not isinstance(origin, str)
        or not origin.startswith("https://")
        or "/" in origin[len("https://"):]
    ):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review origin must be a clean HTTPS origin."
        )

    if any(
        value[field] is not False
        for field in (
            "registration_authority",
            "operation_allowlisted",
            "external_action_registered",
            "runtime_enabled",
            "identity_authority",
            "payment_authority",
        )
    ):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review unexpectedly grants authority."
        )

    stored = _sha(
        value["runtime_registration_review_sha256"],
        label="runtime_registration_review_sha256",
    )
    unsigned = dict(value)
    unsigned.pop("runtime_registration_review_sha256")
    if stored != stable_digest(unsigned):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review digest does not match its contents."
        )

    reviewed_at = _parse_time(value["reviewed_at"], label="reviewed_at")
    compiled_at = _parse_time(value["compiled_at"], label="compiled_at")
    if compiled_at < reviewed_at:
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review was compiled before human review."
        )

    age = now - compiled_at
    if age < -timedelta(minutes=1):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review compilation timestamp is from the future."
        )
    if age > timedelta(hours=max(1, max_review_age_hours)):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review evidence is stale."
        )

    return action_kind, value


def _require_current_runtime_closed(action_kind: str, operation: str) -> None:
    if action_kind in ACTION_SPECS:
        raise TransactionRuntimeRegistrationPlanError(
            "TX-26 requires the action kind to remain absent from ACTION_SPECS."
        )
    if operation in registered_transaction_operations():
        raise TransactionRuntimeRegistrationPlanError(
            "TX-26 requires the provider operation to remain unregistered."
        )


def compile_runtime_registration_change_plan(
    review_value: dict,
    *,
    now: datetime | None = None,
    max_review_age_hours: int = 24,
) -> dict:
    """Compile a deterministic inert code-change plan from TX-24/TX-25 evidence.

    This function never edits the action registry, provider allowlist, settings,
    feature flags, deployment state, credentials or release ledger.
    """

    current = _aware(
        now or datetime.now(timezone.utc),
        label="TX-26 current time",
    )
    action_kind, review = _validate_review(
        review_value,
        now=current,
        max_review_age_hours=max_review_age_hours,
    )
    operation = review["operation"]
    _require_current_runtime_closed(action_kind, operation)

    if action_kind == SHOPPING_KIND:
        transaction_class = "shopping_checkout"
        reviewed_origin = review["checkout_origin"]
        source_contract = "TX-13"
        source_review = "TX-24"
        provider_evidence = {
            "qualification_sha256": review["qualification_sha256"],
            "registration_proposal_sha256": review["registration_proposal_sha256"],
            "conformance_sha256": review["conformance_sha256"],
            "live_probe_evidence_sha256": review["live_probe_evidence_sha256"],
            "handoff_sha256": review["handoff_sha256"],
        }
        privacy_boundary = {
            "payment_instrument_to_shuddho": False,
            "identity_model": "merchant_hosted_user_present",
        }
    else:
        transaction_class = "travel_booking"
        reviewed_origin = review["booking_origin"]
        source_contract = "TX-18"
        source_review = "TX-25"
        provider_evidence = {
            "qualification_sha256": review["qualification_sha256"],
            "registration_proposal_sha256": review["registration_proposal_sha256"],
            "conformance_sha256": review["conformance_sha256"],
            "handoff_sha256": review["handoff_sha256"],
        }
        privacy_boundary = {
            "traveler_fields_sent": list(review["traveler_fields_sent"]),
            "identity_documents_to_shuddho": False,
            "payment_instrument_to_shuddho": False,
        }

    plan = {
        "schema_version": 1,
        "status": "eligible_for_runtime_registration_code_change_review",
        "action_kind": action_kind,
        "transaction_class": transaction_class,
        "provider": review["provider"],
        "operation": operation,
        "adapter_revision": review["adapter_revision"],
        "reviewed_origin": reviewed_origin,
        "source_contract": source_contract,
        "source_runtime_registration_review": source_review,
        "runtime_registration_review_sha256": review[
            "runtime_registration_review_sha256"
        ],
        "provider_evidence": provider_evidence,
        "privacy_boundary": privacy_boundary,
        "required_code_changes": {
            "action_payload_schema": True,
            "action_registry_spec": True,
            "provider_adapter_runtime_binding": True,
            "execution_reconciliation_path": True,
            "owner_scoped_audit_and_receipt_persistence": True,
            "frontend_payload_type": True,
        },
        "required_configuration_change": {
            "transaction_operation_to_add_after_code_review": operation,
            "required_existing_gates": [
                "SHUDDHO_ACTIONS_ENABLED",
                "SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED",
                "SHUDDHO_PERSONAL_TRANSACTIONS_ENABLED",
            ],
            "default_operation_enabled": False,
        },
        "required_post_change_evidence": [
            "exact-source CI success",
            "controlled-staging provider execution",
            "idempotency and reconciliation verification",
            "hosted handoff equality with approved immutable terms",
            "final receipt equality after user-present completion",
            "owner isolation and audit verification",
            "rollback verification",
            "production activation verification",
            "tamper-evident release-ledger attestation",
        ],
        "compiled_at": current.isoformat(),
        "automatic_apply": False,
        "registry_mutated": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    plan["runtime_registration_change_plan_sha256"] = stable_digest(plan)
    return plan


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TransactionRuntimeRegistrationPlanError(
            f"Could not read runtime-registration review: {type(exc).__name__}."
        ) from None
    if not isinstance(value, dict):
        raise TransactionRuntimeRegistrationPlanError(
            "Runtime-registration review must contain a JSON object."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile inert TX-26 runtime-registration code-change plan. "
            "This never mutates runtime registration or deployment configuration."
        )
    )
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compile_runtime_registration_change_plan(_load(args.review))
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "ok", "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
