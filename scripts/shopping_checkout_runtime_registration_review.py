from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.coworker.action_registry import stable_digest
from services.coworker.shopping_checkout_adapter import (
    validate_registration_proposal,
)


class ShoppingCheckoutRuntimeRegistrationReviewError(RuntimeError):
    pass


CONFORMANCE_KEYS = {
    "schema_version",
    "status",
    "provider",
    "operation",
    "adapter_revision",
    "checkout_origin",
    "qualification_sha256",
    "registration_proposal_sha256",
    "live_probe_evidence_sha256",
    "adapter_admission_sha256",
    "preview_sha256",
    "receipt_sha256",
    "idempotency_key_sha256",
    "provider_test_environment",
    "staging_provider_io",
    "provider_called",
    "create_attempts",
    "lookup_attempts",
    "evaluated_at",
    "registration_authority",
    "operation_allowlisted",
    "external_action_registered",
    "runtime_enabled",
    "identity_authority",
    "payment_authority",
    "conformance_sha256",
}

REVIEW_KEYS = {
    "schema_version",
    "provider",
    "operation",
    "adapter_revision",
    "registration_proposal_sha256",
    "conformance_sha256",
    "decision",
    "change_reference",
    "reviewer_reference",
    "reviewed_at",
}


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            f"{label} must include a timezone offset."
        )
    return value.astimezone(timezone.utc)


def _parse_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    return _aware(parsed, label=label)


def _text(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 300
        or any(ord(char) < 32 for char in value)
    ):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            f"{label} must be a non-empty review reference."
        )
    return value.strip()


def _require_sha(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            f"{label} must be a lowercase SHA-256."
        )
    return value


def validate_conformance(
    value: dict,
    *,
    proposal: dict,
    now: datetime,
    max_conformance_age_hours: int,
) -> dict:
    if not isinstance(value, dict) or set(value) != CONFORMANCE_KEYS:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 conformance evidence has an unexpected schema."
        )

    stored = _require_sha(
        value["conformance_sha256"],
        label="TX-23 conformance_sha256",
    )
    unsigned = dict(value)
    unsigned.pop("conformance_sha256")
    if stored != stable_digest(unsigned):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 conformance digest does not match its contents."
        )

    if value["status"] != "provider_implementation_conformance_passed":
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 conformance did not pass."
        )
    for field in ("provider", "operation", "adapter_revision", "checkout_origin"):
        if value[field] != proposal[field]:
            raise ShoppingCheckoutRuntimeRegistrationReviewError(
                f"TX-23 {field} does not match the reviewed TX-15 proposal."
            )
    if value["qualification_sha256"] != proposal["qualification_sha256"]:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 qualification hash does not match TX-15."
        )
    if value["registration_proposal_sha256"] != proposal["registration_proposal_sha256"]:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 registration proposal hash does not match TX-15."
        )
    for field in (
        "live_probe_evidence_sha256",
        "adapter_admission_sha256",
        "preview_sha256",
        "receipt_sha256",
        "idempotency_key_sha256",
    ):
        _require_sha(value[field], label=f"TX-23 {field}")

    if (
        value["provider_test_environment"] != "staging"
        or value["staging_provider_io"] is not True
        or value["provider_called"] is not True
        or value["create_attempts"] != 2
        or value["lookup_attempts"] != 3
    ):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 conformance does not prove the required bounded staging exercise."
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
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 conformance unexpectedly grants runtime authority."
        )

    evaluated_at = _parse_time(value["evaluated_at"], label="TX-23 evaluated_at")
    age = now - evaluated_at
    if age < -timedelta(minutes=1):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 conformance timestamp is from the future."
        )
    if age > timedelta(hours=max(1, max_conformance_age_hours)):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-23 conformance evidence is stale."
        )
    return value


def compile_runtime_registration_review(
    proposal_value: dict,
    conformance_value: dict,
    review_value: dict,
    *,
    now: datetime | None = None,
    max_conformance_age_hours: int = 24,
    max_review_age_days: int = 7,
) -> dict:
    current = _aware(
        now or datetime.now(timezone.utc),
        label="TX-24 current time",
    )

    try:
        proposal = validate_registration_proposal(proposal_value, now=current)
    except Exception as exc:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-24 requires a valid fresh TX-15 registration proposal."
        ) from exc

    conformance = validate_conformance(
        conformance_value,
        proposal=proposal,
        now=current,
        max_conformance_age_hours=max_conformance_age_hours,
    )

    if not isinstance(review_value, dict) or set(review_value) != REVIEW_KEYS:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-24 human review has an unexpected schema."
        )
    if review_value["schema_version"] != 1:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-24 human review schema version is unsupported."
        )
    if review_value["decision"] != "approved_for_runtime_registration_review":
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-24 requires an explicit approved_for_runtime_registration_review decision."
        )

    expected = {
        "provider": proposal["provider"],
        "operation": proposal["operation"],
        "adapter_revision": proposal["adapter_revision"],
        "registration_proposal_sha256": proposal["registration_proposal_sha256"],
        "conformance_sha256": conformance["conformance_sha256"],
    }
    for field, expected_value in expected.items():
        if review_value[field] != expected_value:
            raise ShoppingCheckoutRuntimeRegistrationReviewError(
                f"TX-24 human review {field} does not match the exact evidence."
            )

    change_reference = _text(
        review_value["change_reference"],
        label="TX-24 change_reference",
    )
    reviewer_reference = _text(
        review_value["reviewer_reference"],
        label="TX-24 reviewer_reference",
    )
    reviewed_at = _parse_time(
        review_value["reviewed_at"],
        label="TX-24 reviewed_at",
    )
    review_age = current - reviewed_at
    if review_age < -timedelta(minutes=1):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-24 human review timestamp is from the future."
        )
    if review_age > timedelta(days=max(1, max_review_age_days)):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-24 human review is stale."
        )
    if reviewed_at < _parse_time(
        conformance["evaluated_at"],
        label="TX-23 evaluated_at",
    ):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            "TX-24 human review must occur after TX-23 conformance."
        )

    result = {
        "schema_version": 1,
        "status": "eligible_for_runtime_registration_review",
        "provider": proposal["provider"],
        "operation": proposal["operation"],
        "adapter_revision": proposal["adapter_revision"],
        "checkout_origin": proposal["checkout_origin"],
        "qualification_sha256": proposal["qualification_sha256"],
        "registration_proposal_sha256": proposal["registration_proposal_sha256"],
        "conformance_sha256": conformance["conformance_sha256"],
        "live_probe_evidence_sha256": conformance["live_probe_evidence_sha256"],
        "receipt_sha256": conformance["receipt_sha256"],
        "change_reference": change_reference,
        "reviewer_reference": reviewer_reference,
        "reviewed_at": reviewed_at.isoformat(),
        "compiled_at": current.isoformat(),
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    result["runtime_registration_review_sha256"] = stable_digest(result)
    return result


def _load(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            f"Could not read {label}: {type(exc).__name__}."
        ) from None
    if not isinstance(value, dict):
        raise ShoppingCheckoutRuntimeRegistrationReviewError(
            f"{label} must contain a JSON object."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile inert TX-24 shopping checkout runtime-registration review evidence. "
            "This never registers or enables checkout."
        )
    )
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--conformance", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compile_runtime_registration_review(
        _load(args.proposal, "TX-15 proposal"),
        _load(args.conformance, "TX-23 conformance"),
        _load(args.review, "TX-24 human review"),
    )
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "ok", "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
