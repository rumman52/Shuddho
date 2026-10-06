from __future__ import annotations

import hmac
from datetime import datetime, timezone
from urllib.parse import urlparse

from .action_registry import stable_digest
from .shopping_checkout_contract import (
    ShoppingCheckoutPreview,
    validate_checkout_receipt,
)
from .travel_booking_contract import (
    TravelBookingPreview,
    validate_travel_booking_receipt,
)


class HostedTransactionHandoffError(RuntimeError):
    pass


HANDOFF_KEYS = {
    "schema_version",
    "status",
    "action_kind",
    "provider",
    "transaction_id",
    "binding_id",
    "binding_scope_sha256",
    "preview_sha256",
    "currency",
    "total_minor",
    "handoff_id",
    "handoff_url",
    "handoff_origin",
    "created_at",
    "expires_at",
    "requires_user_present",
    "final_receipt_required",
    "payment_instrument_to_shuddho",
    "registration_authority",
    "runtime_enabled",
    "identity_authority",
    "payment_authority",
    "handoff_sha256",
}


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HostedTransactionHandoffError(
            f"{label} must include a timezone offset."
        )
    return value.astimezone(timezone.utc)


def _parse_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise HostedTransactionHandoffError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HostedTransactionHandoffError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    return _aware(parsed, label=label)


def _safe_text(value: object, *, label: str, max_length: int = 255) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > max_length
        or any(ord(char) < 32 for char in value)
    ):
        raise HostedTransactionHandoffError(
            f"{label} must be a non-empty bounded text value."
        )
    return value.strip()


def _clean_origin(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise HostedTransactionHandoffError(
            f"{label} must be a clean HTTPS origin."
        )
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise HostedTransactionHandoffError(
            f"{label} must be a clean HTTPS origin."
        )
    return clean


def _handoff_url(value: object, *, reviewed_origin: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise HostedTransactionHandoffError(
            "Hosted handoff URL must be a bounded HTTPS URL."
        )
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise HostedTransactionHandoffError(
            "Hosted handoff URL must be HTTPS, credential-free and fragment-free."
        )
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin != reviewed_origin:
        raise HostedTransactionHandoffError(
            "Hosted handoff URL origin does not match the reviewed provider origin."
        )
    return value


def _preview(value: dict):
    if not isinstance(value, dict):
        raise HostedTransactionHandoffError(
            "Hosted handoff requires a transaction preview object."
        )
    kind = value.get("kind")
    try:
        if kind == "shopping_checkout_create":
            return ShoppingCheckoutPreview.model_validate(value)
        if kind == "travel_booking_create":
            return TravelBookingPreview.model_validate(value)
    except Exception as exc:
        raise HostedTransactionHandoffError(
            "Hosted handoff preview is invalid."
        ) from exc
    raise HostedTransactionHandoffError(
        "Hosted handoff supports only shopping checkout or travel booking."
    )


def _binding_values(preview) -> tuple[str, str]:
    if preview.kind == "shopping_checkout_create":
        return (
            str(preview.checkout_binding_id),
            preview.checkout_binding_scope_sha256,
        )
    return (
        str(preview.booking_binding_id),
        preview.booking_binding_scope_sha256,
    )


def build_hosted_transaction_handoff(
    preview_value: dict,
    *,
    handoff_id: str,
    handoff_url: str,
    reviewed_handoff_origin: str,
    now: datetime | None = None,
) -> dict:
    """Build a non-final user-present provider handoff from immutable preview evidence."""

    current = _aware(
        now or datetime.now(timezone.utc),
        label="TX-27 current time",
    )
    preview = _preview(preview_value)
    if preview.expires_at <= current:
        raise HostedTransactionHandoffError(
            "TX-27 refuses to create a handoff for an expired preview."
        )

    reviewed_origin = _clean_origin(
        reviewed_handoff_origin,
        label="TX-27 reviewed handoff origin",
    )
    safe_url = _handoff_url(
        handoff_url,
        reviewed_origin=reviewed_origin,
    )
    safe_handoff_id = _safe_text(
        handoff_id,
        label="TX-27 provider handoff ID",
    )

    normalized_preview = preview.model_dump(mode="json")
    binding_id, binding_scope_sha256 = _binding_values(preview)

    result = {
        "schema_version": 1,
        "status": "awaiting_user_completion",
        "action_kind": preview.kind,
        "provider": preview.provider,
        "transaction_id": str(preview.transaction_id),
        "binding_id": binding_id,
        "binding_scope_sha256": binding_scope_sha256,
        "preview_sha256": stable_digest(normalized_preview),
        "currency": preview.currency,
        "total_minor": preview.total_minor,
        "handoff_id": safe_handoff_id,
        "handoff_url": safe_url,
        "handoff_origin": reviewed_origin,
        "created_at": current.isoformat(),
        "expires_at": preview.expires_at.isoformat(),
        "requires_user_present": True,
        "final_receipt_required": True,
        "payment_instrument_to_shuddho": False,
        "registration_authority": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    result["handoff_sha256"] = stable_digest(result)
    return result


def validate_hosted_transaction_completion(
    handoff_value: dict,
    preview_value: dict,
    receipt_value: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Validate a later provider-confirmed receipt for a prior user-present handoff."""

    current = _aware(
        now or datetime.now(timezone.utc),
        label="TX-27 completion observation time",
    )
    if not isinstance(handoff_value, dict) or set(handoff_value) != HANDOFF_KEYS:
        raise HostedTransactionHandoffError(
            "TX-27 handoff evidence has an unexpected schema."
        )

    stored = handoff_value["handoff_sha256"]
    if (
        not isinstance(stored, str)
        or len(stored) != 64
        or any(char not in "0123456789abcdef" for char in stored)
    ):
        raise HostedTransactionHandoffError(
            "TX-27 handoff SHA-256 is invalid."
        )
    unsigned = dict(handoff_value)
    unsigned.pop("handoff_sha256")
    if not hmac.compare_digest(stored, stable_digest(unsigned)):
        raise HostedTransactionHandoffError(
            "TX-27 handoff digest does not match its contents."
        )
    if handoff_value["status"] != "awaiting_user_completion":
        raise HostedTransactionHandoffError(
            "TX-27 can complete only an awaiting-user handoff."
        )

    preview = _preview(preview_value)
    normalized_preview = preview.model_dump(mode="json")
    binding_id, binding_scope_sha256 = _binding_values(preview)
    expected = {
        "action_kind": preview.kind,
        "provider": preview.provider,
        "transaction_id": str(preview.transaction_id),
        "binding_id": binding_id,
        "binding_scope_sha256": binding_scope_sha256,
        "preview_sha256": stable_digest(normalized_preview),
        "currency": preview.currency,
        "total_minor": preview.total_minor,
        "expires_at": preview.expires_at.isoformat(),
    }
    for field, value in expected.items():
        if handoff_value[field] != value:
            raise HostedTransactionHandoffError(
                f"TX-27 handoff {field} no longer matches the approved preview."
            )

    if (
        handoff_value["requires_user_present"] is not True
        or handoff_value["final_receipt_required"] is not True
        or handoff_value["payment_instrument_to_shuddho"] is not False
        or handoff_value["registration_authority"] is not False
        or handoff_value["runtime_enabled"] is not False
        or handoff_value["identity_authority"] is not False
        or handoff_value["payment_authority"] is not False
    ):
        raise HostedTransactionHandoffError(
            "TX-27 handoff unexpectedly grants authority."
        )

    try:
        if preview.kind == "shopping_checkout_create":
            validated = validate_checkout_receipt(
                normalized_preview,
                receipt_value,
                now=current,
            )
        else:
            validated = validate_travel_booking_receipt(
                normalized_preview,
                receipt_value,
                now=current,
            )
    except Exception as exc:
        raise HostedTransactionHandoffError(
            "TX-27 provider completion receipt is invalid."
        ) from exc

    confirmed_at = _parse_time(
        validated["receipt"]["confirmed_at"],
        label="TX-27 receipt confirmed_at",
    )
    expires_at = _parse_time(
        handoff_value["expires_at"],
        label="TX-27 handoff expires_at",
    )
    if confirmed_at > expires_at:
        raise HostedTransactionHandoffError(
            "TX-27 provider confirmation occurred after approval expiry."
        )

    result = {
        "schema_version": 1,
        "status": "confirmed",
        "action_kind": preview.kind,
        "provider": preview.provider,
        "transaction_id": str(preview.transaction_id),
        "handoff_sha256": stored,
        "receipt_sha256": validated["receipt_sha256"],
        "confirmed_at": confirmed_at.isoformat(),
        "observed_at": current.isoformat(),
        "user_present_handoff_completed": True,
        "payment_instrument_to_shuddho": False,
        "registration_authority": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    result["completion_sha256"] = stable_digest(result)
    return result
