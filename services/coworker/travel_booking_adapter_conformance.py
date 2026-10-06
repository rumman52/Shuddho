from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .action_registry import (
    ACTION_SPECS,
    registered_transaction_operations,
    stable_digest,
)
from .travel_booking_adapter import admit_travel_booking_adapter
from .travel_booking_contract import (
    TravelBookingPreview,
    validate_travel_booking_receipt,
)


ACTION_KIND = "travel_booking_create"


class TravelBookingAdapterConformanceError(RuntimeError):
    pass


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TravelBookingAdapterConformanceError(
            f"{label} must include a timezone offset."
        )
    return value.astimezone(timezone.utc)


def _require_runtime_closed() -> None:
    if ACTION_KIND in ACTION_SPECS:
        raise TravelBookingAdapterConformanceError(
            "TX-22 refuses provider implementation tests while travel booking is runtime registered."
        )
    if any(
        operation.endswith(f":{ACTION_KIND}")
        for operation in registered_transaction_operations()
    ):
        raise TravelBookingAdapterConformanceError(
            "TX-22 refuses provider implementation tests while a travel booking operation is allowlisted."
        )


def _require_sandbox_boundary(adapter: object) -> None:
    if getattr(adapter, "implementation_test_only", None) is not True:
        raise TravelBookingAdapterConformanceError(
            "TX-22 requires an adapter explicitly marked implementation_test_only."
        )
    if getattr(adapter, "implementation_test_environment", None) != "sandbox":
        raise TravelBookingAdapterConformanceError(
            "TX-22 provider I/O is allowed only against an explicitly declared sandbox environment."
        )


def _traveler_payload(proposal: dict, value: dict) -> dict:
    if not isinstance(value, dict):
        raise TravelBookingAdapterConformanceError(
            "TX-22 traveler data must be a dictionary."
        )

    boundary = proposal["traveler_data_boundary"]
    expected = set(boundary["shuddho_transmitted_fields"])
    if set(value) != expected:
        raise TravelBookingAdapterConformanceError(
            "TX-22 traveler data must contain exactly the reviewed Shuddho-transmitted fields."
        )

    normalized: dict[str, str] = {}
    for field in sorted(expected):
        item = value[field]
        if (
            not isinstance(item, str)
            or not item.strip()
            or len(item) > 500
            or any(ord(char) < 32 for char in item)
        ):
            raise TravelBookingAdapterConformanceError(
                f"TX-22 traveler field {field!r} is invalid."
            )
        normalized[field] = item.strip()
    return normalized


def _idempotency_key(admission: dict, preview: TravelBookingPreview) -> str:
    preview_value = preview.model_dump(mode="json")
    return stable_digest(
        {
            "schema_version": 1,
            "adapter_admission_sha256": admission["adapter_admission_sha256"],
            "booking_binding_id": str(preview.booking_binding_id),
            "booking_binding_scope_sha256": preview.booking_binding_scope_sha256,
            "preview_sha256": stable_digest(preview_value),
        }
    )


async def _lookup(
    adapter: object,
    *,
    idempotency_key: str | None = None,
    provider_booking_id: str | None = None,
) -> dict | None:
    try:
        value = await adapter.lookup_booking(
            idempotency_key=idempotency_key,
            provider_booking_id=provider_booking_id,
        )
    except Exception as exc:
        raise TravelBookingAdapterConformanceError(
            "TX-22 sandbox lookup failed."
        ) from exc
    if value is not None and not isinstance(value, dict):
        raise TravelBookingAdapterConformanceError(
            "TX-22 sandbox lookup must return a receipt dictionary or None."
        )
    return value


async def _create(
    adapter: object,
    *,
    preview: dict,
    traveler_data: dict,
    idempotency_key: str,
) -> dict:
    try:
        value = await adapter.create_booking(
            preview=preview,
            traveler_data=traveler_data,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise TravelBookingAdapterConformanceError(
            "TX-22 sandbox booking creation failed."
        ) from exc
    if not isinstance(value, dict):
        raise TravelBookingAdapterConformanceError(
            "TX-22 sandbox booking creation must return a receipt dictionary."
        )
    return value


def _validated_receipt(
    preview: dict,
    receipt: dict,
    *,
    now: datetime,
    label: str,
) -> dict:
    try:
        result = validate_travel_booking_receipt(
            preview,
            receipt,
            now=now,
        )
    except Exception as exc:
        raise TravelBookingAdapterConformanceError(
            f"TX-22 {label} receipt failed the TX-18 receipt contract."
        ) from exc
    return result


async def exercise_travel_booking_adapter(
    proposal_value: dict,
    adapter: object,
    *,
    preview_value: dict,
    traveler_data: dict,
    allow_provider_test_io: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Exercise a TX-21-admitted adapter against a sandbox implementation boundary.

    This function is intentionally disconnected from the ExternalAction registry.
    It can perform bounded provider sandbox I/O only when the caller opts in
    explicitly and the adapter declares a sandbox-only implementation-test mode.
    """

    current = _aware(
        now or datetime.now(timezone.utc),
        label="TX-22 current time",
    )
    _require_runtime_closed()

    admission = admit_travel_booking_adapter(
        proposal_value,
        adapter,
        now=current,
    )

    if allow_provider_test_io is not True:
        raise TravelBookingAdapterConformanceError(
            "TX-22 provider implementation tests require explicit allow_provider_test_io=True."
        )
    _require_sandbox_boundary(adapter)

    try:
        preview = TravelBookingPreview.model_validate(preview_value)
    except Exception as exc:
        raise TravelBookingAdapterConformanceError(
            "TX-22 preview does not satisfy the TX-18 travel booking contract."
        ) from exc

    if preview.expires_at <= current:
        raise TravelBookingAdapterConformanceError(
            "TX-22 refuses to call a provider with an expired booking preview."
        )
    if (
        preview.provider != admission["provider"]
        or preview.travel_kind != admission["travel_kind"]
    ):
        raise TravelBookingAdapterConformanceError(
            "TX-22 preview does not match the admitted provider and travel kind."
        )

    normalized_preview = preview.model_dump(mode="json")
    normalized_traveler_data = _traveler_payload(
        proposal_value,
        traveler_data,
    )
    idempotency_key = _idempotency_key(admission, preview)

    existing = await _lookup(
        adapter,
        idempotency_key=idempotency_key,
    )
    existing_validated = (
        _validated_receipt(
            normalized_preview,
            existing,
            now=current,
            label="pre-create lookup",
        )
        if existing is not None
        else None
    )

    first = await _create(
        adapter,
        preview=normalized_preview,
        traveler_data=normalized_traveler_data,
        idempotency_key=idempotency_key,
    )
    first_validated = _validated_receipt(
        normalized_preview,
        first,
        now=current,
        label="first create",
    )

    second = await _create(
        adapter,
        preview=normalized_preview,
        traveler_data=normalized_traveler_data,
        idempotency_key=idempotency_key,
    )
    second_validated = _validated_receipt(
        normalized_preview,
        second,
        now=current,
        label="idempotent create",
    )

    provider_booking_id = first_validated["receipt"]["provider_booking_id"]
    by_key = await _lookup(
        adapter,
        idempotency_key=idempotency_key,
    )
    by_provider_id = await _lookup(
        adapter,
        provider_booking_id=provider_booking_id,
    )
    if by_key is None or by_provider_id is None:
        raise TravelBookingAdapterConformanceError(
            "TX-22 requires provider readback by both idempotency key and provider booking ID."
        )

    by_key_validated = _validated_receipt(
        normalized_preview,
        by_key,
        now=current,
        label="idempotency lookup",
    )
    by_provider_id_validated = _validated_receipt(
        normalized_preview,
        by_provider_id,
        now=current,
        label="provider booking lookup",
    )

    receipt_hashes = {
        first_validated["receipt_sha256"],
        second_validated["receipt_sha256"],
        by_key_validated["receipt_sha256"],
        by_provider_id_validated["receipt_sha256"],
    }
    if existing_validated is not None:
        receipt_hashes.add(existing_validated["receipt_sha256"])
    if len(receipt_hashes) != 1:
        raise TravelBookingAdapterConformanceError(
            "TX-22 provider implementation is not idempotent or readback-stable."
        )

    _require_runtime_closed()

    result = {
        "schema_version": 1,
        "status": "provider_implementation_conformance_passed",
        "provider": admission["provider"],
        "operation": admission["operation"],
        "adapter_revision": admission["adapter_revision"],
        "travel_kind": admission["travel_kind"],
        "adapter_admission_sha256": admission["adapter_admission_sha256"],
        "preview_sha256": stable_digest(normalized_preview),
        "receipt_sha256": first_validated["receipt_sha256"],
        "idempotency_key_sha256": stable_digest(
            {"idempotency_key": idempotency_key}
        ),
        "sandbox_provider_io": True,
        "provider_called": True,
        "create_attempts": 2,
        "lookup_attempts": 3,
        "existing_booking_observed": existing_validated is not None,
        "traveler_fields_sent": sorted(normalized_traveler_data),
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    result["conformance_sha256"] = stable_digest(result)
    return result
