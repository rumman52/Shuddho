from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from .action_registry import stable_digest
from .errors import CoworkerError
from .models import (
    Transaction,
    TravelQuoteIntent,
    TravelQuoteVerificationEvidence,
    utcnow,
)
from .repository import aware, iso, not_found
from .transaction_repository import TransactionDraft
from .transaction_schemas import TransactionTermsDraft
from .travel_quote_schemas import TravelQuoteRequest


class TravelQuoteService:
    """Durable review-only travel quotes plus trusted read-only verification.

    TX-08 records the user's exact quote. TX-09 may append a provider
    observation through a code-owned verifier, but still exposes no booking,
    payment, browser-submit, or ExternalAction path.
    """

    def __init__(self, transactions, verifiers: dict[str, object] | None = None):
        self.transactions = transactions
        self.sessions = transactions.sessions
        self.settings = transactions.settings
        self.verifiers = {
            str(key).strip().lower(): value
            for key, value in (verifiers or {}).items()
            if str(key).strip()
        }

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

    def _latest_verification(
        self,
        owner: str,
        transaction_id: str,
    ) -> TravelQuoteVerificationEvidence | None:
        with self.sessions() as db:
            return db.scalar(
                select(TravelQuoteVerificationEvidence)
                .where(
                    TravelQuoteVerificationEvidence.transaction_id == transaction_id,
                    TravelQuoteVerificationEvidence.owner_id == owner,
                )
                .order_by(TravelQuoteVerificationEvidence.sequence.desc())
                .limit(1)
            )

    @staticmethod
    def _verification_dto(row: TravelQuoteVerificationEvidence | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "sequence": row.sequence,
            "provider": row.provider,
            "provider_quote_id": row.provider_quote_id,
            "source_quote_sha256": row.source_quote_sha256,
            "snapshot_sha256": row.snapshot_sha256,
            "matched": row.matched,
            "mismatches": list(row.mismatches or []),
            "observed_at": iso(row.observed_at),
            "quote_expires_at": iso(row.quote_expires_at),
            "created_at": iso(row.created_at),
        }

    def _intent_dto(self, row: TravelQuoteIntent) -> dict:
        verification = self._latest_verification(row.owner_id, row.transaction_id)
        verified = bool(
            verification is not None
            and verification.matched
            and verification.source_quote_sha256 == row.quote_sha256
            and aware(verification.quote_expires_at) > utcnow()
        )
        return {
            "transaction_id": row.transaction_id,
            "quote": dict(row.quote),
            "quote_sha256": row.quote_sha256,
            "created_at": iso(row.created_at),
            "provider_verified": verified,
            "booking_available": False,
            "latest_verification": self._verification_dto(verification),
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
                "value": "Review only. Travel verification does not authorize booking, payment, purchase or browser submission.",
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

    @staticmethod
    def _expected_verification(quote: TravelQuoteRequest) -> dict:
        return {
            "provider_quote_id": quote.provider_quote_id,
            "travel_kind": quote.travel_kind,
            "price": quote.price.model_dump(mode="json"),
            "cancellation_terms": quote.cancellation_terms,
            "change_terms": quote.change_terms,
            "quote_expires_at": quote.quote_expires_at.isoformat(),
            "flight_segments": [
                item.model_dump(mode="json")
                for item in quote.flight_segments
            ],
            "lodging": (
                quote.lodging.model_dump(mode="json")
                if quote.lodging is not None
                else None
            ),
        }

    async def verify_with_provider(
        self,
        owner: str,
        transaction_id: str,
        provider: str,
    ) -> dict:
        """Append one trusted read-only provider observation.

        This is deliberately not mounted as a public endpoint in TX-09. A later
        provider-specific integration must select and invoke a registered
        verifier after separate feasibility/security review.
        """
        self._require_enabled()
        provider_key = provider.strip().lower()
        verifier = self.verifiers.get(provider_key)
        if verifier is None:
            raise CoworkerError(
                "travel_quote_verifier_unregistered",
                "This travel quote verifier is not registered.",
                409,
            )

        transaction = self.transactions.get(owner, transaction_id)
        if (
            transaction["provider"] != "internal"
            or transaction["transaction_kind"] not in {"travel_flight", "travel_lodging"}
        ):
            raise not_found()

        intent = self._intent(owner, transaction_id)
        quote = TravelQuoteRequest.model_validate(dict(intent.quote))
        observation = await verifier.verify_quote(
            provider_quote_id=quote.provider_quote_id,
            travel_kind=quote.travel_kind,
        )
        if str(observation.provider).strip().lower() != provider_key:
            raise CoworkerError(
                "travel_quote_provider_mismatch",
                "The travel provider observation came from a different registered provider.",
                409,
            )
        if observation.observed_at.tzinfo is None or observation.observed_at.utcoffset() is None:
            raise CoworkerError(
                "travel_quote_verification_invalid",
                "The travel provider observation time is invalid.",
                409,
            )
        if observation.quote_expires_at.tzinfo is None or observation.quote_expires_at.utcoffset() is None:
            raise CoworkerError(
                "travel_quote_verification_invalid",
                "The travel provider quote expiry is invalid.",
                409,
            )
        observed_at = observation.observed_at.astimezone(timezone.utc)
        now = utcnow()
        if observed_at > now + timedelta(minutes=5):
            raise CoworkerError(
                "travel_quote_verification_invalid",
                "The travel provider observation time is in the future.",
                409,
            )
        if observed_at < now - timedelta(minutes=5):
            raise CoworkerError(
                "travel_quote_verification_stale",
                "The travel provider observation is too old to verify current terms.",
                409,
            )
        if observation.quote_expires_at.astimezone(timezone.utc) <= observed_at:
            raise CoworkerError(
                "travel_quote_verification_invalid",
                "The travel provider quote already expired at observation time.",
                409,
            )

        snapshot = observation.public_snapshot()
        expected = self._expected_verification(quote)
        actual = {
            key: snapshot[key]
            for key in expected
        }
        mismatches = [
            key
            for key in expected
            if stable_digest(expected[key]) != stable_digest(actual[key])
        ]
        snapshot_sha256 = stable_digest(snapshot)

        with self.sessions.begin() as db:
            locked_intent = db.scalar(
                select(TravelQuoteIntent).where(
                    TravelQuoteIntent.transaction_id == transaction_id,
                    TravelQuoteIntent.owner_id == owner,
                ).with_for_update()
            )
            if locked_intent is None:
                raise not_found()
            latest = db.scalar(
                select(TravelQuoteVerificationEvidence)
                .where(
                    TravelQuoteVerificationEvidence.transaction_id == transaction_id,
                    TravelQuoteVerificationEvidence.owner_id == owner,
                )
                .order_by(TravelQuoteVerificationEvidence.sequence.desc())
                .limit(1)
            )
            sequence = 1 if latest is None else latest.sequence + 1
            row = TravelQuoteVerificationEvidence(
                id=str(uuid4()),
                transaction_id=transaction_id,
                owner_id=owner,
                sequence=sequence,
                source_quote_sha256=locked_intent.quote_sha256,
                provider=provider_key,
                provider_quote_id=observation.provider_quote_id,
                snapshot=snapshot,
                snapshot_sha256=snapshot_sha256,
                matched=not mismatches,
                mismatches=mismatches,
                observed_at=observation.observed_at,
                quote_expires_at=observation.quote_expires_at,
                created_at=utcnow(),
            )
            db.add(row)
            db.flush()

        return {
            **self.transactions.review_surface(owner, transaction_id),
            "travel_quote": self._intent_dto(self._intent(owner, transaction_id)),
        }

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
