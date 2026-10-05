from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from pydantic import Field, StrictInt, StringConstraints, field_validator, model_validator

from .action_schemas import Strict, clean_text
from .transaction_schemas import TransactionPrice


ShortText = Annotated[str, StringConstraints(min_length=1, max_length=300)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
BIGINT_MAX = 9_223_372_036_854_775_807


class ShoppingCartItem(Strict):
    product_id: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    title: Annotated[str, StringConstraints(min_length=1, max_length=240)]
    variant: Annotated[str, StringConstraints(min_length=1, max_length=160)] | None = None
    quantity: StrictInt = Field(ge=1, le=99)
    unit_price_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)
    line_total_minor: StrictInt = Field(ge=0, le=BIGINT_MAX)

    @field_validator("product_id", "title", "variant")
    @classmethod
    def safe_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Shopping item text cannot be blank")
        return value

    @model_validator(mode="after")
    def exact_line_total(self):
        if self.line_total_minor != self.unit_price_minor * self.quantity:
            raise ValueError("Shopping line total must equal unit price times quantity")
        return self


class ShoppingCartReviewRequest(Strict):
    """TX-10 exact review-only shopping cart snapshot.

    The request stores user-supplied review evidence only. It does not create a
    remote merchant cart and cannot authorize checkout or payment.
    """

    quote_source: Literal["user_supplied"] = "user_supplied"
    merchant_name: ShortText
    merchant_cart_id: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    items: list[ShoppingCartItem] = Field(min_length=1, max_length=25)
    price: TransactionPrice
    fulfillment_method: Literal["shipping", "pickup", "digital"]
    fulfillment_terms: LongText
    return_terms: LongText
    quoted_at: datetime
    quote_expires_at: datetime

    @field_validator(
        "merchant_name",
        "merchant_cart_id",
        "fulfillment_terms",
        "return_terms",
    )
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Shopping cart text cannot be blank")
        return value

    @field_validator("price")
    @classmethod
    def bounded_price(cls, value: TransactionPrice) -> TransactionPrice:
        for amount in value.model_dump(mode="python").values():
            if isinstance(amount, int) and amount > BIGINT_MAX:
                raise ValueError("Shopping money values exceed durable database limits")
        return value

    @field_validator("quoted_at", "quote_expires_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Shopping quote times must include a timezone offset")
        return value

    @model_validator(mode="after")
    def exact_cart(self):
        now = datetime.now(timezone.utc)
        quoted = self.quoted_at.astimezone(timezone.utc)
        expires = self.quote_expires_at.astimezone(timezone.utc)
        if quoted > now + timedelta(minutes=5):
            raise ValueError("Shopping quote time cannot be more than five minutes in the future")
        if expires <= quoted or expires <= now:
            raise ValueError("Shopping quote expiry must be later than the quote time and still current")
        if expires - quoted > timedelta(days=30):
            raise ValueError("Shopping quote validity cannot exceed 30 days")
        product_keys = [
            (item.product_id.casefold(), (item.variant or "").casefold())
            for item in self.items
        ]
        if len(product_keys) != len(set(product_keys)):
            raise ValueError("Duplicate product/variant lines are not allowed")
        subtotal = sum(item.line_total_minor for item in self.items)
        if subtotal != self.price.subtotal_minor:
            raise ValueError("Shopping subtotal must equal the sum of item line totals")
        return self


class ShoppingCheckoutBindingRequest(Strict):
    expected_revision: StrictInt = Field(ge=1)
    terms_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    verification_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f-]{36}$")]
    verification_snapshot_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
