from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from .shopping_cart_schemas import ShoppingCartItem
from .transaction_schemas import TransactionPrice


@dataclass(frozen=True)
class ShoppingCartVerification:
    """Trusted read-only merchant cart observation.

    This object is produced by a code-owned provider adapter. The adapter receives
    only an opaque merchant cart identifier and must not submit shipping, billing,
    account, or payment identity.
    """

    provider: str
    merchant_cart_id: str
    merchant_name: str
    items: tuple[ShoppingCartItem, ...]
    price: TransactionPrice
    fulfillment_method: Literal["shipping", "pickup", "digital"]
    fulfillment_terms: str
    return_terms: str
    quote_expires_at: datetime
    observed_at: datetime

    def public_snapshot(self) -> dict:
        return {
            "provider": self.provider,
            "merchant_cart_id": self.merchant_cart_id,
            "merchant_name": self.merchant_name,
            "items": [item.model_dump(mode="json") for item in self.items],
            "price": self.price.model_dump(mode="json"),
            "fulfillment_method": self.fulfillment_method,
            "fulfillment_terms": self.fulfillment_terms,
            "return_terms": self.return_terms,
            "quote_expires_at": self.quote_expires_at.isoformat(),
            "observed_at": self.observed_at.isoformat(),
        }


class ShoppingCartVerifier(Protocol):
    """Read-only provider adapter contract for TX-11.

    Implementations may retrieve an existing merchant cart by its opaque cart
    reference. They must not create/modify carts, hold inventory, submit checkout,
    send identity, or perform payment operations.
    """

    provider_name: str

    async def verify_cart(
        self,
        *,
        merchant_cart_id: str,
    ) -> ShoppingCartVerification:
        ...
