from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .action_registry import (
    ACTION_SPECS,
    registered_transaction_operations,
    stable_digest,
)
from .hosted_transaction_handoff import (
    HostedTransactionHandoffError,
    build_hosted_transaction_handoff,
)
from .travel_booking_adapter import admit_travel_booking_adapter
from .travel_booking_contract import TravelBookingPreview


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


def _require_sandbox_boundary(adapter: object, *, reviewed_origin: str) -> None:
    if getattr(adapter, "implementation_test_only", None) is not True:
        raise TravelBookingAdapterConformanceError(
            "TX-22 requires an adapter explicitly marked implementation_test_only."
        )
    if getattr(adapter, "implementation_test_environment", None) != "sandbox":
        raise TravelBookingAdapterConformanceError(
            "TX-22 provider I/O is allowed only against an explicitly declared sandbox environment."
        )
    test_origin = getattr(adapter, "implementation_test_origin", None)
    if test_origin != reviewed_origin:
        raise TravelBookingAdapterConformanceError(
            "TX-22 sandbox origin must exactly match the reviewed TX-20 booking origin."
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


async def _lookup_receipt(
    adapter: object,
    *,
    idempotency_key: str | None = None,
    provider_booking_id: str | None = None,
) -> dict | None:
    try:
        value = await adapter.lookup_booking_receipt(
            idempotency_key=idempotency_key,
            provider_booking_id=provider_booking_id,
        )
    except Exception as exc:
        raise TravelBookingAdapterConformanceError(
            "TX-22 sandbox booking receipt lookup failed."
        ) from exc
    if value is not None and not isinstance(value, dict):
        raise TravelBookingAdapterConformanceError(
            "TX-22 receipt lookup must return a receipt dictionary or None."
        )
    return value


async def _create_handoff(
    adapter: object,
    *,
    preview: dict,
    traveler_data: dict,
    idempotency_key: str,
) -> dict:
    try:
        value = await adapter.create_booking_handoff(
            preview=preview,
            traveler_data=traveler_data,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise TravelBookingAdapterConformanceError(
            "TX-22 sandbox booking handoff creation failed."
        ) from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"handoff_id", "handoff_url"}
        or not isinstance(value["handoff_id"], str)
        or not isinstance(value["handoff_url"], str)
    ):
        raise TravelBookingAdapterConformanceError(
            "TX-22 booking handoff must return exactly handoff_id and handoff_url."
        )
    return value


def _validated_handoff(
    preview: dict,
    handoff: dict,
    *,
    reviewed_origin: str,
    now: datetime,
    label: str,
) -> dict:
    try:
        return build_hosted_transaction_handoff(
            preview,
            handoff_id=handoff["handoff_id"],
            handoff_url=handoff["handoff_url"],
            reviewed_handoff_origin=reviewed_origin,
            now=now,
        )
    except HostedTransactionHandoffError as exc:
        raise TravelBookingAdapterConformanceError(
            f"TX-22 {label} handoff failed the TX-27 hosted handoff contract."
        ) from exc


async def exercise_travel_booking_adapter(
    proposal_value: dict,
    adapter: object,
    *,
    preview_value: dict,
    traveler_data: dict,
    allow_provider_test_io: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Exercise a TX-21-admitted hosted travel adapter in sandbox only.

    TX-22 proves only the provider-hosted handoff boundary. It explicitly
    rejects adapters that surface a confirmed receipt before the user-present
    provider flow completes. Final receipt reconciliation is separate live
    staging/activation evidence through TX-27/TX-28.
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
    _require_sandbox_boundary(
        adapter,
        reviewed_origin=admission["booking_origin"],
    )

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

    before = await _lookup_receipt(
        adapter,
        idempotency_key=idempotency_key,
    )
    if before is not None:
        raise TravelBookingAdapterConformanceError(
            "TX-22 refuses a pre-existing confirmed receipt before hosted handoff."
        )

    first = await _create_handoff(
        adapter,
        preview=normalized_preview,
        traveler_data=normalized_traveler_data,
        idempotency_key=idempotency_key,
    )
    first_validated = _validated_handoff(
        normalized_preview,
        first,
        reviewed_origin=admission["booking_origin"],
        now=current,
        label="first",
    )

    second = await _create_handoff(
        adapter,
        preview=normalized_preview,
        traveler_data=normalized_traveler_data,
        idempotency_key=idempotency_key,
    )
    second_validated = _validated_handoff(
        normalized_preview,
        second,
        reviewed_origin=admission["booking_origin"],
        now=current,
        label="idempotent",
    )

    if first_validated["handoff_sha256"] != second_validated["handoff_sha256"]:
        raise TravelBookingAdapterConformanceError(
            "TX-22 hosted booking handoff is not idempotent."
        )

    after = await _lookup_receipt(
        adapter,
        idempotency_key=idempotency_key,
    )
    if after is not None:
        raise TravelBookingAdapterConformanceError(
            "TX-22 adapter exposed a confirmed receipt before user-present completion."
        )

    _require_runtime_closed()

    result = {
        "schema_version": 2,
        "status": "provider_handoff_conformance_passed",
        "provider": admission["provider"],
        "operation": admission["operation"],
        "adapter_revision": admission["adapter_revision"],
        "travel_kind": admission["travel_kind"],
        "qualification_sha256": admission["qualification_sha256"],
        "registration_proposal_sha256": admission["registration_proposal_sha256"],
        "adapter_admission_sha256": admission["adapter_admission_sha256"],
        "preview_sha256": stable_digest(normalized_preview),
        "handoff_sha256": first_validated["handoff_sha256"],
        "idempotency_key_sha256": stable_digest(
            {"idempotency_key": idempotency_key}
        ),
        "sandbox_provider_io": True,
        "provider_called": True,
        "handoff_attempts": 2,
        "receipt_lookup_attempts": 2,
        "completion_receipt_observed": False,
        "traveler_fields_sent": sorted(normalized_traveler_data),
        "evaluated_at": current.isoformat(),
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    result["conformance_sha256"] = stable_digest(result)
    return result
