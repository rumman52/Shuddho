from __future__ import annotations

from sqlalchemy import select

from .action_registry import stable_digest
from .errors import CoworkerError
from .models import Transaction, TravelQuoteIntent, utcnow
from .repository import iso, not_found
from .transaction_repository import TransactionDraft
from .transaction_schemas import TransactionTermsDraft
from .travel_quote_schemas import TravelQuoteRequest


class TravelQuoteService:
    """TX-08 durable review-only travel quote domain.

    The service records exact user-supplied quote evidence and reuses the generic
    transaction review lifecycle. It intentionally has no provider adapter and
    no ExternalAction preparation method.
    """

    def __init__(self, transactions):
        self.transactions = transactions
        self.sessions = transactions.sessions
        self.settings = transactions.settings

    def _require_enabled(self) -> None:
        if not self.settings.personal_transactions_enabled:
            raise CoworkerError(
                "personal_transactions_disabled",
                "Personal transaction workflows are not enabled in this deployment.",
                503,
            )

    @staticmethod
    def _quote_value(request: TravelQuoteRequest) -> dict:
        return request.model_dump(mode="json")

    @staticmethod
    def _intent_dto(row: TravelQuoteIntent) -> dict:
        return {
            "transaction_id": row.transaction_id,
            "quote": dict(row.quote),
            "quote_sha256": row.quote_sha256,
            "created_at": iso(row.created_at),
            "provider_verified": False,
            "booking_available": False,
        }

    def _intent(self, owner: str, transaction_id: str) -> TravelQuoteIntent:
        with self.sessions() as db:
            row = db.scalar(
                select(TravelQuoteIntent).where(
                    TravelQuoteIntent.transaction_id == transaction_id,
                    TravelQuoteIntent.owner_id == owner,
                )
            )
            if row is None:
                raise not_found()
            return row

    @staticmethod
    def _terms_from_intent(row: TravelQuoteIntent) -> TransactionTermsDraft:
        quote = TravelQuoteRequest.model_validate(dict(row.quote))
        terms = [
            {"name": "Travel type", "value": quote.travel_kind},
            {"name": "Quote source", "value": "User supplied; not provider verified"},
            {"name": "Provider label", "value": quote.provider_name},
            {"name": "Cancellation terms", "value": quote.cancellation_terms},
            {"name": "Change terms", "value": quote.change_terms},
            {
                "name": "Execution authority",
                "value": "Review only. TX-08 does not authorize booking, payment, purchase or browser submission.",
            },
        ]
        for index, traveler in enumerate(quote.travelers, 1):
            terms.append({
                "name": f"Traveler {index}",
                "value": f"{traveler.display_name} ({traveler.traveler_type})",
            })
        if quote.travel_kind == "flight":
            for index, segment in enumerate(quote.flight_segments, 1):
                carrier = ""
                if segment.marketing_carrier:
                    carrier = " " + segment.marketing_carrier
                    if segment.flight_number:
                        carrier += segment.flight_number
                terms.append({
                    "name": f"Flight segment {index}",
                    "value": (
                        f"{segment.origin_code} -> {segment.destination_code}; "
                        f"{segment.departure_at.isoformat()} -> {segment.arrival_at.isoformat()}{carrier}"
                    ),
                })
        else:
            stay = quote.lodging
            assert stay is not None
            terms.extend([
                {"name": "Property", "value": f"{stay.property_name} ({stay.property_id})"},
                {"name": "Property address", "value": stay.address},
                {"name": "Room", "value": stay.room_name},
                {
                    "name": "Stay",
                    "value": (
                        f"{stay.check_in_at.isoformat()} -> {stay.check_out_at.isoformat()} "
                        f"({stay.time_zone})"
                    ),
                },
            ])
        return TransactionTermsDraft.model_validate({
            "terms": terms,
            "price": quote.price.model_dump(mode="json"),
            "provider_quote_id": quote.provider_quote_id,
            "quoted_at": quote.quoted_at,
            "quote_expires_at": quote.quote_expires_at,
        })

    def create(
        self,
        owner: str,
        request: TravelQuoteRequest,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        canonical = self._quote_value(request)
        quote_sha256 = stable_digest(canonical)
        transaction, created = self.transactions.create(
            owner,
            TransactionDraft(
                transaction_kind="travel_" + request.travel_kind,
                provider="internal",
                connection_id=None,
                currency=request.price.currency,
                counterparty=request.provider_name,
                expires_at=request.quote_expires_at,
                fingerprint_extra=canonical,
            ),
            idempotency_key,
        )

        with self.sessions.begin() as db:
            tx = db.scalar(
                select(Transaction).where(
                    Transaction.id == transaction["id"],
                    Transaction.owner_id == owner,
                ).with_for_update()
            )
            if tx is None:
                raise not_found()
            intent = db.scalar(
                select(TravelQuoteIntent).where(
                    TravelQuoteIntent.transaction_id == tx.id,
                    TravelQuoteIntent.owner_id == owner,
                )
            )
            if intent is None:
                intent = TravelQuoteIntent(
                    transaction_id=tx.id,
                    owner_id=owner,
                    quote=canonical,
                    quote_sha256=quote_sha256,
                    created_at=utcnow(),
                )
                db.add(intent)
                db.flush()
            elif intent.quote_sha256 != quote_sha256:
                raise CoworkerError(
                    "idempotency_conflict",
                    "This request key belongs to different travel quote details.",
                    409,
                )

        current = self.transactions.get(owner, transaction["id"])
        if current["current_terms_revision"] is None:
            intent = self._intent(owner, transaction["id"])
            try:
                self.transactions.set_terms(
                    owner,
                    transaction["id"],
                    current["revision"],
                    self._terms_from_intent(intent),
                    provider_managed=True,
                )
            except CoworkerError as error:
                if error.code != "transaction_revision_conflict":
                    raise

        return {
            **self.transactions.review_surface(owner, transaction["id"]),
            "travel_quote": self._intent_dto(self._intent(owner, transaction["id"])),
        }, created

    def get(self, owner: str, transaction_id: str) -> dict:
        self._require_enabled()
        transaction = self.transactions.get(owner, transaction_id)
        if (
            transaction["provider"] != "internal"
            or transaction["transaction_kind"] not in {"travel_flight", "travel_lodging"}
        ):
            raise not_found()
        return {
            **self.transactions.review_surface(owner, transaction_id),
            "travel_quote": self._intent_dto(self._intent(owner, transaction_id)),
        }
