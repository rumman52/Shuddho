from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class TransactionContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _safe_text(value: str, *, label: str) -> str:
    if any(
        ord(char) < 32 and char not in "\n\t"
        or 0x7F <= ord(char) <= 0x9F
        or 0xD800 <= ord(char) <= 0xDFFF
        for char in value
    ):
        raise ValueError(f"{label} contains unsupported control characters")
    value = value.strip()
    if not value:
        raise ValueError(f"{label} cannot be blank")
    return value


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone offset")
    return value


class TransactionTerm(TransactionContractModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    value: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _safe_text(value, label="Transaction term name")

    @field_validator("value")
    @classmethod
    def valid_value(cls, value: str) -> str:
        return _safe_text(value, label="Transaction term value")


class TransactionPrice(TransactionContractModel):
    """Exact monetary values represented only as integer minor units."""

    currency: Annotated[str, Field(min_length=3, max_length=3)]
    subtotal_minor: StrictInt = Field(ge=0)
    tax_minor: StrictInt = Field(default=0, ge=0)
    fees_minor: StrictInt = Field(default=0, ge=0)
    shipping_minor: StrictInt = Field(default=0, ge=0)
    discount_minor: StrictInt = Field(default=0, ge=0)
    total_minor: StrictInt = Field(ge=0)

    @field_validator("currency")
    @classmethod
    def canonical_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
            raise ValueError("Currency must be a three-letter ASCII code")
        return normalized

    @model_validator(mode="after")
    def exact_total(self):
        expected = (
            self.subtotal_minor
            + self.tax_minor
            + self.fees_minor
            + self.shipping_minor
            - self.discount_minor
        )
        if expected < 0 or self.total_minor != expected:
            raise ValueError(
                "Total minor units must exactly equal subtotal + tax + fees + shipping - discount"
            )
        return self


class TransactionTermsDraft(TransactionContractModel):
    """Immutable final terms plus provider quote freshness evidence."""

    terms: list[TransactionTerm] = Field(min_length=1, max_length=40)
    price: TransactionPrice
    provider_quote_id: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    quoted_at: datetime
    quote_expires_at: datetime

    @field_validator("provider_quote_id")
    @classmethod
    def valid_quote_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _safe_text(value, label="Provider quote ID")

    @field_validator("quoted_at")
    @classmethod
    def valid_quoted_at(cls, value: datetime) -> datetime:
        value = _aware(value, label="Quote time")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Quote time cannot be more than five minutes in the future")
        return value

    @field_validator("quote_expires_at")
    @classmethod
    def valid_quote_expiry(cls, value: datetime) -> datetime:
        return _aware(value, label="Quote expiry")

    @model_validator(mode="after")
    def exact_contract(self):
        if self.quote_expires_at <= self.quoted_at:
            raise ValueError("Quote expiry must be later than quote time")
        names = [item.name.casefold() for item in self.terms]
        if len(names) != len(set(names)):
            raise ValueError("Transaction term names must be unique")
        return self
