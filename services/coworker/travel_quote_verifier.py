from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .travel_quote_schemas import (
    TravelFlightSegment,
    TravelLodgingStay,
)
from .transaction_schemas import TransactionPrice


@dataclass(frozen=True)
class TravelQuoteVerification:
    """Trusted read-only provider observation.

    This object is produced by a code-owned provider adapter, never accepted
    from a public API request. It carries no traveler identity or payment data.
    """

    provider: str
    provider_quote_id: str
    travel_kind: str
    price: TransactionPrice
    cancellation_terms: str
    change_terms: str
    quote_expires_at: datetime
    observed_at: datetime
    flight_segments: tuple[TravelFlightSegment, ...] = ()
    lodging: TravelLodgingStay | None = None

    def public_snapshot(self) -> dict:
        return {
            "provider": self.provider,
            "provider_quote_id": self.provider_quote_id,
            "travel_kind": self.travel_kind,
            "price": self.price.model_dump(mode="json"),
            "cancellation_terms": self.cancellation_terms,
            "change_terms": self.change_terms,
            "quote_expires_at": self.quote_expires_at.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "flight_segments": [
                item.model_dump(mode="json")
                for item in self.flight_segments
            ],
            "lodging": (
                self.lodging.model_dump(mode="json")
                if self.lodging is not None
                else None
            ),
        }


class TravelQuoteVerifier(Protocol):
    """Read-only provider adapter contract for TX-09.

    Implementations may retrieve a provider quote by its opaque provider quote
    identifier. They must not book, reserve, hold inventory, create a cart,
    submit traveler identity, or perform payment operations.
    """

    provider_name: str

    async def verify_quote(
        self,
        *,
        provider_quote_id: str,
        travel_kind: str,
    ) -> TravelQuoteVerification:
        ...
