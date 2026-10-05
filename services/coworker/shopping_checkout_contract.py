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


class ShoppingCheckoutBindingContract(Strict):
    """Exact TX-12 binding DTO consumed by the non-executable TX-13 contract."""

    id: UUID
    transaction_id: UUID
    verification_id: UUID
    transaction_revision: StrictInt = Field(ge=1)
    terms_revision: StrictInt = Field(ge=1)
    terms_sha256: Sha256
    cart_sha256: Sha256
    verification_snapshot_sha256: Sha256
    provider: Provider
    merchant_cart_id: OpaqueId
    currency: Currency
    total_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)
    approval_scope_sha256: Sha256
    expires_at: datetime
    created_at: datetime
    execution_available: Literal[False]

    @field_validator("provider", "merchant_cart_id")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Checkout binding text cannot be blank")
        return value

    @field_validator("expires_at", "created_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return _aware(value, label="Checkout binding time")


class ShoppingCheckoutPreview(Strict):
    """Future provider-action preview shape; TX-13 never registers or executes it."""

    schema_version: Literal[1] = 1
    kind: Literal["shopping_checkout_create"] = "shopping_checkout_create"
    checkout_binding_id: UUID
    transaction_id: UUID
    verification_id: UUID
    transaction_revision: StrictInt = Field(ge=1)
    terms_revision: StrictInt = Field(ge=1)
    terms_sha256: Sha256
    cart_sha256: Sha256
    verification_snapshot_sha256: Sha256
    provider: Provider
    merchant_cart_id: OpaqueId
    currency: Currency
    total_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)
    checkout_binding_scope_sha256: Sha256
    expires_at: datetime
    execution_authority: Literal["not_registered"] = "not_registered"
    payment_authority: Literal["not_authorized"] = "not_authorized"
    identity_authority: Literal["not_bound"] = "not_bound"

    @field_validator("provider", "merchant_cart_id")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Checkout preview text cannot be blank")
        return value

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        return _aware(value, label="Checkout preview expiry")


class ShoppingCheckoutReceipt(Strict):
    """Provider-confirmed receipt shape required by a future checkout adapter."""

    provider: Provider
    provider_order_id: OpaqueId
    merchant_cart_id: OpaqueId
    currency: Currency
    total_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)
    status: Literal["confirmed"]
    confirmed_at: datetime

    @field_validator("provider", "provider_order_id", "merchant_cart_id")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Checkout receipt text cannot be blank")
        return value

    @field_validator("confirmed_at")
    @classmethod
    def aware_confirmation(cls, value: datetime) -> datetime:
        return _aware(value, label="Checkout receipt confirmation")


def _binding_scope(binding: ShoppingCheckoutBindingContract) -> dict:
    return {
        "schema_version": 1,
        "transaction_id": str(binding.transaction_id),
        "transaction_revision": binding.transaction_revision,
        "terms_revision": binding.terms_revision,
        "terms_sha256": binding.terms_sha256,
        "cart_sha256": binding.cart_sha256,
        "verification_id": str(binding.verification_id),
        "verification_snapshot_sha256": binding.verification_snapshot_sha256,
        "provider": binding.provider,
        "merchant_cart_id": binding.merchant_cart_id,
        "currency": binding.currency,
        "total_minor": binding.total_minor,
        "expires_at": binding.expires_at.isoformat(),
        "authority": "binding_only_no_execution",
    }


def build_checkout_preview(
    binding_value: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Build a non-executable canonical future-action preview from TX-12 evidence."""

    binding = ShoppingCheckoutBindingContract.model_validate(binding_value)
    current = _aware(now or datetime.now(timezone.utc), label="Current time")
    if binding.expires_at <= current:
        raise CoworkerError(
            "shopping_checkout_binding_expired",
            "The shopping checkout binding expired. Refresh verification and approval first.",
            409,
        )

    expected_scope_sha256 = stable_digest(_binding_scope(binding))
    if not hmac.compare_digest(
        expected_scope_sha256,
        binding.approval_scope_sha256,
    ):
        raise CoworkerError(
            "shopping_checkout_binding_integrity",
            "The checkout binding no longer matches its immutable approval scope.",
            409,
        )

    preview = ShoppingCheckoutPreview(
        checkout_binding_id=binding.id,
        transaction_id=binding.transaction_id,
        verification_id=binding.verification_id,
        transaction_revision=binding.transaction_revision,
        terms_revision=binding.terms_revision,
        terms_sha256=binding.terms_sha256,
        cart_sha256=binding.cart_sha256,
        verification_snapshot_sha256=binding.verification_snapshot_sha256,
        provider=binding.provider,
        merchant_cart_id=binding.merchant_cart_id,
        currency=binding.currency,
        total_minor=binding.total_minor,
        checkout_binding_scope_sha256=binding.approval_scope_sha256,
        expires_at=binding.expires_at,
    )
    value = preview.model_dump(mode="json")
    return {
        "preview": value,
        "preview_hash": stable_digest(value),
        "execution_available": False,
    }


def validate_checkout_receipt(
    preview_value: dict,
    receipt_value: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Validate the exact receipt a future registered provider adapter must return."""

    preview = ShoppingCheckoutPreview.model_validate(preview_value)
    receipt = ShoppingCheckoutReceipt.model_validate(receipt_value)
    current = _aware(now or datetime.now(timezone.utc), label="Current time")

    if receipt.confirmed_at > current + timedelta(minutes=5):
        raise CoworkerError(
            "shopping_checkout_receipt_invalid",
            "The checkout receipt confirmation time is in the future.",
            409,
        )

    mismatches = []
    for field in ("provider", "merchant_cart_id", "currency", "total_minor"):
        if getattr(receipt, field) != getattr(preview, field):
            mismatches.append(field)
    if mismatches:
        raise CoworkerError(
            "shopping_checkout_receipt_mismatch",
            "The merchant receipt does not match the approved checkout terms.",
            409,
        )

    value = receipt.model_dump(mode="json")
    return {
        "receipt": value,
        "receipt_sha256": stable_digest(value),
        "matched": True,
    }
