from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.coworker.action_registry import stable_digest
from services.coworker.travel_booking_adapter import validate_registration_proposal


class TravelBookingRuntimeRegistrationReviewError(RuntimeError):
    pass


CONFORMANCE_KEYS = {
    "schema_version",
    "status",
    "provider",
    "operation",
    "adapter_revision",
    "travel_kind",
    "qualification_sha256",
    "registration_proposal_sha256",
    "adapter_admission_sha256",
    "preview_sha256",
    "handoff_sha256",
    "idempotency_key_sha256",
    "sandbox_provider_io",
    "provider_called",
    "handoff_attempts",
    "receipt_lookup_attempts",
    "completion_receipt_observed",
    "traveler_fields_sent",
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
    "travel_kind",
    "registration_proposal_sha256",
    "conformance_sha256",
    "decision",
    "change_reference",
    "reviewer_reference",
    "reviewed_at",
}


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TravelBookingRuntimeRegistrationReviewError(
            f"{label} must include a timezone offset."
        )
    return value.astimezone(timezone.utc)


def _parse_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise TravelBookingRuntimeRegistrationReviewError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TravelBookingRuntimeRegistrationReviewError(
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
        raise TravelBookingRuntimeRegistrationReviewError(
            f"{label} must be a lowercase SHA-256."
        )
    return value


def _text(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 300
        or any(ord(char) < 32 for char in value)
    ):
        raise TravelBookingRuntimeRegistrationReviewError(
            f"{label} must be a non-empty review reference."
        )
    return value.strip()


def validate_conformance(
    value: dict,
    *,
    proposal: dict,
    now: datetime,
    max_conformance_age_hours: int,
) -> dict:
    if not isinstance(value, dict) or set(value) != CONFORMANCE_KEYS:
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 conformance evidence has an unexpected schema."
        )

    stored = _sha(value["conformance_sha256"], label="TX-22 conformance_sha256")
    unsigned = dict(value)
    unsigned.pop("conformance_sha256")
    if stored != stable_digest(unsigned):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 conformance digest does not match its contents."
        )

    if (
        value["schema_version"] != 2
        or value["status"] != "provider_handoff_conformance_passed"
    ):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 conformance did not pass."
        )

    for field in ("provider", "operation", "adapter_revision", "travel_kind"):
        if value[field] != proposal[field]:
            raise TravelBookingRuntimeRegistrationReviewError(
                f"TX-22 {field} does not match the reviewed TX-20 proposal."
            )

    if value["qualification_sha256"] != proposal["qualification_sha256"]:
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 qualification hash does not match TX-20."
        )
    if value["registration_proposal_sha256"] != proposal["registration_proposal_sha256"]:
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 registration proposal hash does not match TX-20."
        )

    for field in (
        "adapter_admission_sha256",
        "preview_sha256",
        "handoff_sha256",
        "idempotency_key_sha256",
    ):
        _sha(value[field], label=f"TX-22 {field}")

    if (
        value["sandbox_provider_io"] is not True
        or value["provider_called"] is not True
        or value["handoff_attempts"] != 2
        or value["receipt_lookup_attempts"] != 2
        or value["completion_receipt_observed"] is not False
    ):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 conformance does not prove the required bounded sandbox exercise."
        )

    reviewed_fields = proposal["traveler_data_boundary"]["shuddho_transmitted_fields"]
    if value["traveler_fields_sent"] != reviewed_fields:
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 traveler fields do not match the reviewed transmission boundary."
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
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 conformance unexpectedly grants runtime authority."
        )

    evaluated_at = _parse_time(value["evaluated_at"], label="TX-22 evaluated_at")
    age = now - evaluated_at
    if age < -timedelta(minutes=1):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 conformance timestamp is from the future."
        )
    if age > timedelta(hours=max(1, max_conformance_age_hours)):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-22 conformance evidence is stale."
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
    current = _aware(now or datetime.now(timezone.utc), label="TX-25 current time")

    try:
        proposal = validate_registration_proposal(proposal_value, now=current)
    except Exception as exc:
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-25 requires a valid fresh TX-20 registration proposal."
        ) from exc

    conformance = validate_conformance(
        conformance_value,
        proposal=proposal,
        now=current,
        max_conformance_age_hours=max_conformance_age_hours,
    )

    if not isinstance(review_value, dict) or set(review_value) != REVIEW_KEYS:
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-25 human review has an unexpected schema."
        )
    if review_value["schema_version"] != 1:
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-25 human review schema version is unsupported."
        )
    if review_value["decision"] != "approved_for_runtime_registration_review":
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-25 requires approved_for_runtime_registration_review."
        )

    expected = {
        "provider": proposal["provider"],
        "operation": proposal["operation"],
        "adapter_revision": proposal["adapter_revision"],
        "travel_kind": proposal["travel_kind"],
        "registration_proposal_sha256": proposal["registration_proposal_sha256"],
        "conformance_sha256": conformance["conformance_sha256"],
    }
    for field, expected_value in expected.items():
        if review_value[field] != expected_value:
            raise TravelBookingRuntimeRegistrationReviewError(
                f"TX-25 human review {field} does not match the exact evidence."
            )

    change_reference = _text(
        review_value["change_reference"], label="TX-25 change_reference"
    )
    reviewer_reference = _text(
        review_value["reviewer_reference"], label="TX-25 reviewer_reference"
    )
    reviewed_at = _parse_time(review_value["reviewed_at"], label="TX-25 reviewed_at")
    review_age = current - reviewed_at
    if review_age < -timedelta(minutes=1):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-25 human review timestamp is from the future."
        )
    if review_age > timedelta(days=max(1, max_review_age_days)):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-25 human review is stale."
        )
    if reviewed_at < _parse_time(
        conformance["evaluated_at"], label="TX-22 evaluated_at"
    ):
        raise TravelBookingRuntimeRegistrationReviewError(
            "TX-25 human review must occur after TX-22 conformance."
        )

    result = {
        "schema_version": 1,
        "status": "eligible_for_runtime_registration_review",
        "provider": proposal["provider"],
        "operation": proposal["operation"],
        "adapter_revision": proposal["adapter_revision"],
        "booking_origin": proposal["booking_origin"],
        "travel_kind": proposal["travel_kind"],
        "qualification_sha256": proposal["qualification_sha256"],
        "registration_proposal_sha256": proposal["registration_proposal_sha256"],
        "conformance_sha256": conformance["conformance_sha256"],
        "handoff_sha256": conformance["handoff_sha256"],
        "traveler_fields_sent": conformance["traveler_fields_sent"],
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
        raise TravelBookingRuntimeRegistrationReviewError(
            f"Could not read {label}: {type(exc).__name__}."
        ) from None
    if not isinstance(value, dict):
        raise TravelBookingRuntimeRegistrationReviewError(
            f"{label} must contain a JSON object."
        )
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile inert TX-25 travel booking runtime-registration review evidence. "
            "This never registers or enables travel booking."
        )
    )
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--conformance", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compile_runtime_registration_review(
        _load(args.proposal, "TX-20 proposal"),
        _load(args.conformance, "TX-22 conformance"),
        _load(args.review, "TX-25 human review"),
    )
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "ok", "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
