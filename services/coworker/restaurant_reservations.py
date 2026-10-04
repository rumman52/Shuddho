from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from .action_registry import stable_digest
from .action_schemas import ActionPrepare
from .errors import CoworkerError
from .models import RestaurantReservationIntent, Transaction, utcnow
from .opentable_actions import SCOPES, SERVICE_ACCOUNT, SERVICE_SUBJECT
from .repository import iso, not_found
from .restaurant_reservation_schemas import (
    RestaurantReservationPrepare,
    RestaurantReservationRequest,
)
from .transaction_repository import TransactionDraft
from .transaction_schemas import TransactionTermsDraft


class RestaurantReservationService:
    """TX-06 typed OpenTable reservation workflow.

    Availability reads are provider reads only. The sole provider mutation is
    still the bound ExternalAction created after exact transaction review.
    """

    def __init__(self, transactions, actions, adapter):
        self.transactions = transactions
        self.actions = actions
        self.adapter = adapter
        self.sessions = transactions.sessions
        self.settings = transactions.settings

    def _require_enabled(self) -> None:
        if not self.settings.restaurant_reservations_enabled:
            raise CoworkerError(
                "restaurant_reservations_disabled",
                "Restaurant reservations are not enabled in this deployment.",
                503,
            )

    @staticmethod
    def _request_value(request: RestaurantReservationRequest) -> dict:
        return request.model_dump(mode="json")

    @staticmethod
    def _intent_dto(row: RestaurantReservationIntent) -> dict:
        return {
            "transaction_id": row.transaction_id,
            "request": dict(row.request),
            "request_sha256": row.request_sha256,
            "availability": dict(row.availability),
            "availability_sha256": row.availability_sha256,
            "observed_at": iso(row.observed_at),
            "created_at": iso(row.created_at),
        }

    def _intent(self, owner: str, transaction_id: str) -> RestaurantReservationIntent:
        with self.sessions() as db:
            row = db.scalar(
                select(RestaurantReservationIntent).where(
                    RestaurantReservationIntent.transaction_id == transaction_id,
                    RestaurantReservationIntent.owner_id == owner,
                )
            )
            if row is None:
                raise CoworkerError(
                    "reservation_intent_missing",
                    "The reservation details are unavailable. Create a fresh reservation review.",
                    409,
                )
            return row

    @staticmethod
    def _terms_from_intent(row: RestaurantReservationIntent) -> TransactionTermsDraft:
        request = dict(row.request)
        availability = dict(row.availability)
        special_request = request.get("special_request") or "(none)"
        dining_area = request.get("dining_area_id")
        environment = request.get("environment")
        terms = [
            {"name": "Restaurant ID", "value": str(request["restaurant_id"])},
            {"name": "Restaurant", "value": request["restaurant_name"]},
            {"name": "Reservation time", "value": request["date_time"]},
            {"name": "Time zone", "value": request["time_zone"]},
            {"name": "Party size", "value": str(request["party_size"])},
            {"name": "Seating", "value": request["reservation_attribute"]},
            {"name": "Dining area ID", "value": str(dining_area) if dining_area is not None else "(any)"},
            {"name": "Environment", "value": environment or "(any)"},
            {
                "name": "Guest",
                "value": request["guest_first_name"] + " " + request["guest_last_name"],
            },
            {"name": "Guest email", "value": request["guest_email"]},
            {
                "name": "Guest phone",
                "value": request["guest_phone_country_code"] + " " + request["guest_phone_number"],
            },
            {"name": "Special request", "value": special_request},
            {"name": "Payment", "value": "No payment or card authorization permitted"},
            {
                "name": "Provider inventory",
                "value": str(availability.get("availability_type", "Standard")),
            },
            {
                "name": "Cancellation/deposit",
                "value": "No deposit, hold, or fee-bearing policy returned in approved availability",
            },
        ]
        return TransactionTermsDraft.model_validate({
            "terms": terms,
            "price": {
                # ISO 4217 XXX means no currency/monetary transaction applies.
                "currency": "XXX",
                "subtotal_minor": 0,
                "tax_minor": 0,
                "fees_minor": 0,
                "shipping_minor": 0,
                "discount_minor": 0,
                "total_minor": 0,
            },
            "provider_quote_id": row.availability_sha256,
            "quoted_at": row.observed_at,
            "quote_expires_at": row.observed_at + timedelta(minutes=10),
        })

    async def create(
        self,
        owner: str,
        request: RestaurantReservationRequest,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        canonical = self._request_value(request)
        request_sha256 = stable_digest(canonical)
        connection = self.actions.ensure_service_connection(
            owner,
            provider="opentable",
            capability="restaurant_reservation",
            subject=SERVICE_SUBJECT,
            account=SERVICE_ACCOUNT,
            scopes=[SCOPES["restaurant_reservation"]],
        )
        transaction, created = self.transactions.create(
            owner,
            TransactionDraft(
                transaction_kind="restaurant_reservation",
                provider="opentable",
                connection_id=connection["id"],
                currency="XXX",
                counterparty=request.restaurant_name,
                expires_at=request.date_time,
                fingerprint_extra=canonical,
            ),
            idempotency_key,
        )

        with self.sessions() as db:
            intent = db.scalar(
                select(RestaurantReservationIntent).where(
                    RestaurantReservationIntent.transaction_id == transaction["id"],
                    RestaurantReservationIntent.owner_id == owner,
                )
            )
        if intent is not None and intent.request_sha256 != request_sha256:
            raise CoworkerError(
                "idempotency_conflict",
                "This request key belongs to different reservation details.",
                409,
            )

        if intent is None:
            availability = await self.adapter.service_availability(canonical)
            observed_at = utcnow()
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
                    select(RestaurantReservationIntent).where(
                        RestaurantReservationIntent.transaction_id == tx.id,
                        RestaurantReservationIntent.owner_id == owner,
                    )
                )
                if intent is None:
                    intent = RestaurantReservationIntent(
                        transaction_id=tx.id,
                        owner_id=owner,
                        request=canonical,
                        request_sha256=request_sha256,
                        availability=dict(availability["selection"]),
                        availability_sha256=availability["availability_sha256"],
                        observed_at=observed_at,
                    )
                    db.add(intent)
                    db.flush()
                elif intent.request_sha256 != request_sha256:
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to different reservation details.",
                        409,
                    )

        current = self.transactions.get(owner, transaction["id"])
        if current["current_terms_revision"] is None:
            terms = self._terms_from_intent(intent)
            try:
                self.transactions.set_terms(
                    owner,
                    transaction["id"],
                    current["revision"],
                    terms,
                    provider_managed=True,
                )
            except CoworkerError as error:
                if error.code != "transaction_revision_conflict":
                    raise
            current = self.transactions.get(owner, transaction["id"])

        surface = self.transactions.review_surface(owner, transaction["id"])
        return {
            **surface,
            "reservation": self._intent_dto(self._intent(owner, transaction["id"])),
        }, created

    def get(self, owner: str, transaction_id: str) -> dict:
        self._require_enabled()
        transaction = self.transactions.get(owner, transaction_id)
        if (
            transaction["transaction_kind"] != "restaurant_reservation"
            or transaction["provider"] != "opentable"
        ):
            raise not_found()
        return {
            **self.transactions.review_surface(owner, transaction_id),
            "reservation": self._intent_dto(self._intent(owner, transaction_id)),
        }

    def prepare_action(
        self,
        owner: str,
        transaction_id: str,
        request: RestaurantReservationPrepare,
    ) -> dict:
        self._require_enabled()
        transaction = self.transactions.get(owner, transaction_id)
        if (
            transaction["transaction_kind"] != "restaurant_reservation"
            or transaction["provider"] != "opentable"
            or transaction["state"] != "awaiting_approval"
        ):
            raise CoworkerError(
                "reservation_review_required",
                "Confirm the exact restaurant reservation review before preparing the provider action.",
                409,
            )
        if transaction["revision"] != request.expected_revision:
            raise CoworkerError(
                "transaction_revision_conflict",
                "This transaction changed. Review the latest revision before continuing.",
                409,
            )
        binding = self.transactions.review_binding(
            owner,
            transaction_id,
            request.expected_revision,
            expected_terms_sha256=request.terms_sha256,
        )
        intent = self._intent(owner, transaction_id)
        if (
            stable_digest(dict(intent.request)) != intent.request_sha256
            or stable_digest(dict(intent.availability)) != intent.availability_sha256
        ):
            raise CoworkerError(
                "reservation_intent_changed",
                "The reservation intent or availability evidence changed.",
                409,
            )
        expected_terms = self._terms_from_intent(intent)
        expected_terms_sha256 = self.transactions._terms_sha256(expected_terms)
        if expected_terms_sha256 != binding["terms_sha256"]:
            raise CoworkerError(
                "transaction_terms_changed",
                "The reviewed reservation terms no longer match the provider intent.",
                409,
            )
        payload = {
            "kind": "restaurant_reservation_create",
            **dict(intent.request),
            "availability_sha256": intent.availability_sha256,
            "availability_observed_at": iso(intent.observed_at),
            "no_payment_required": True,
        }
        action_request = ActionPrepare.model_validate({
            "connection_id": transaction["connection_id"],
            "payload": payload,
        })
        action = self.actions.prepare(
            owner,
            action_request,
            "restaurant-reservation:" + transaction_id,
            transaction_binding={
                "transaction_id": binding["transaction_id"],
                "transaction_revision": binding["transaction_revision"],
                "terms_revision": binding["terms_revision"],
                "terms_sha256": binding["terms_sha256"],
            },
        )
        link = self.transactions.bind_external_action(
            owner,
            transaction_id,
            request.expected_revision,
            action["id"],
        )
        return {
            "transaction": self.transactions.get(owner, transaction_id),
            "reservation": self._intent_dto(intent),
            "action": action,
            "link": link,
        }
