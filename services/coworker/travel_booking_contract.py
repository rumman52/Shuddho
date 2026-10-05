from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt, StringConstraints, field_validator

from .action_registry import stable_digest
from .action_schemas import Strict, clean_text
from .errors import CoworkerError


BIGINT_MAX = 9_223_372_036_854_775_807
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Provider = Annotated[str, StringConstraints(min_length=1, max_length=80)]
OpaqueId = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone offset")
    return value.astimezone(timezone.utc)


class TravelBookingBindingContract(Strict):
    """Exact TX-17 binding DTO consumed by the non-executable TX-18 contract."""

    id: UUID
    transaction_id: UUID
    verification_id: UUID
    transaction_revision: StrictInt = Field(ge=1)
    terms_revision: StrictInt = Field(ge=1)
    terms_sha256: Sha256
    quote_sha256: Sha256
    verification_snapshot_sha256: Sha256
    travel_kind: Literal["flight", "lodging"]
    provider: Provider
    provider_quote_id: OpaqueId
    currency: Currency
    total_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)
    approval_scope_sha256: Sha256
    expires_at: datetime
    created_at: datetime
    execution_available: Literal[False]

    @field_validator("provider", "provider_quote_id")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Travel booking binding text cannot be blank")
        return value

    @field_validator("expires_at", "created_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return _aware(value, label="Travel booking binding time")


class TravelBookingPreview(Strict):
    """Future provider-action preview shape; TX-18 never registers or executes it."""

    schema_version: Literal[1] = 1
    kind: Literal["travel_booking_create"] = "travel_booking_create"
    booking_binding_id: UUID
    transaction_id: UUID
    verification_id: UUID
    transaction_revision: StrictInt = Field(ge=1)
    terms_revision: StrictInt = Field(ge=1)
    terms_sha256: Sha256
    quote_sha256: Sha256
    verification_snapshot_sha256: Sha256
    travel_kind: Literal["flight", "lodging"]
    provider: Provider
    provider_quote_id: OpaqueId
    currency: Currency
    total_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)
    booking_binding_scope_sha256: Sha256
    expires_at: datetime
    execution_authority: Literal["not_registered"] = "not_registered"
    identity_authority: Literal["not_bound"] = "not_bound"
    payment_authority: Literal["not_authorized"] = "not_authorized"

    @field_validator("provider", "provider_quote_id")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Travel booking preview text cannot be blank")
        return value

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        return _aware(value, label="Travel booking preview expiry")


class TravelBookingReceipt(Strict):
    """Normalized provider-confirmed receipt required by a future booking adapter."""

    provider: Provider
    provider_booking_id: OpaqueId
    provider_quote_id: OpaqueId
    travel_kind: Literal["flight", "lodging"]
    currency: Currency
    total_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)
    status: Literal["confirmed"]
    confirmed_at: datetime

    @field_validator("provider", "provider_booking_id", "provider_quote_id")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Travel booking receipt text cannot be blank")
        return value

    @field_validator("confirmed_at")
    @classmethod
    def aware_confirmation(cls, value: datetime) -> datetime:
        return _aware(value, label="Travel booking receipt confirmation")


def _binding_scope(binding: TravelBookingBindingContract) -> dict:
    return {
        "schema_version": 1,
        "transaction_id": str(binding.transaction_id),
        "transaction_revision": binding.transaction_revision,
        "terms_revision": binding.terms_revision,
        "terms_sha256": binding.terms_sha256,
        "quote_sha256": binding.quote_sha256,
        "verification_id": str(binding.verification_id),
        "verification_snapshot_sha256": binding.verification_snapshot_sha256,
        "travel_kind": binding.travel_kind,
        "provider": binding.provider,
        "provider_quote_id": binding.provider_quote_id,
        "currency": binding.currency,
        "total_minor": binding.total_minor,
        "expires_at": binding.expires_at.isoformat(),
        "authority": "binding_only_no_execution",
    }


def build_travel_booking_preview(
    binding_value: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Build a canonical, explicitly non-executable future booking preview."""

    binding = TravelBookingBindingContract.model_validate(binding_value)
    current = _aware(now or datetime.now(timezone.utc), label="Current time")
    if binding.expires_at <= current:
        raise CoworkerError(
            "travel_booking_binding_expired",
            "The travel booking binding expired. Refresh verification and approval first.",
            409,
        )

    expected_scope_sha256 = stable_digest(_binding_scope(binding))
    if not hmac.compare_digest(
        expected_scope_sha256,
        binding.approval_scope_sha256,
    ):
        raise CoworkerError(
            "travel_booking_binding_integrity",
            "The travel booking binding no longer matches its immutable approval scope.",
            409,
        )

    preview = TravelBookingPreview(
        booking_binding_id=binding.id,
        transaction_id=binding.transaction_id,
        verification_id=binding.verification_id,
        transaction_revision=binding.transaction_revision,
        terms_revision=binding.terms_revision,
        terms_sha256=binding.terms_sha256,
        quote_sha256=binding.quote_sha256,
        verification_snapshot_sha256=binding.verification_snapshot_sha256,
        travel_kind=binding.travel_kind,
        provider=binding.provider,
        provider_quote_id=binding.provider_quote_id,
        currency=binding.currency,
        total_minor=binding.total_minor,
        booking_binding_scope_sha256=binding.approval_scope_sha256,
        expires_at=binding.expires_at,
    )
    value = preview.model_dump(mode="json")
    return {
        "preview": value,
        "preview_hash": stable_digest(value),
        "execution_available": False,
    }


def validate_travel_booking_receipt(
    preview_value: dict,
    receipt_value: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Validate the exact normalized receipt a future booking adapter must return."""

    preview = TravelBookingPreview.model_validate(preview_value)
    receipt = TravelBookingReceipt.model_validate(receipt_value)
    current = _aware(now or datetime.now(timezone.utc), label="Current time")

    if receipt.confirmed_at > current + timedelta(minutes=5):
        raise CoworkerError(
            "travel_booking_receipt_invalid",
            "The booking receipt confirmation time is in the future.",
            409,
        )

    mismatches = []
    for field in (
        "provider",
        "provider_quote_id",
        "travel_kind",
        "currency",
        "total_minor",
    ):
        if getattr(receipt, field) != getattr(preview, field):
            mismatches.append(field)
    if mismatches:
        raise CoworkerError(
            "travel_booking_receipt_mismatch",
            "The provider booking receipt does not match the approved travel terms.",
            409,
        )

    value = receipt.model_dump(mode="json")
    return {
        "receipt": value,
        "receipt_sha256": stable_digest(value),
        "matched": True,
    }
