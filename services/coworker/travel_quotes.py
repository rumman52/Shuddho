from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from .action_registry import stable_digest
from .errors import CoworkerError
from .models import (
    Transaction,
    TransactionTermsSnapshot,
    TravelBookingBinding,
    TravelQuoteIntent,
    TravelQuoteVerificationEvidence,
    utcnow,
)
from .repository import aware, iso, not_found
from .transaction_repository import TransactionDraft
from .transaction_schemas import TransactionTermsDraft
from .travel_quote_schemas import TravelBookingBindingRequest, TravelQuoteRequest


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

    @staticmethod
    def _booking_binding_dto(row: TravelBookingBinding) -> dict:
        return {
            "id": row.id,
            "transaction_id": row.transaction_id,
            "verification_id": row.verification_id,
            "transaction_revision": row.transaction_revision,
            "terms_revision": row.terms_revision,
            "terms_sha256": row.terms_sha256,
            "quote_sha256": row.quote_sha256,
            "verification_snapshot_sha256": row.verification_snapshot_sha256,
            "travel_kind": row.travel_kind,
            "provider": row.provider,
            "provider_quote_id": row.provider_quote_id,
            "currency": row.currency,
            "total_minor": row.total_minor,
            "approval_scope_sha256": row.approval_scope_sha256,
            "expires_at": iso(row.expires_at),
            "created_at": iso(row.created_at),
            "execution_available": False,
        }

    def booking_binding(self, owner: str, transaction_id: str) -> dict:
        self._require_enabled()
        with self.sessions() as db:
            row = db.scalar(
                select(TravelBookingBinding).where(
                    TravelBookingBinding.transaction_id == transaction_id,
                    TravelBookingBinding.owner_id == owner,
                )
            )
            if row is None:
                raise not_found()
            return self._booking_binding_dto(row)

    def create_booking_binding(
        self,
        owner: str,
        transaction_id: str,
        request: TravelBookingBindingRequest,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        now = utcnow()

        with self.sessions.begin() as db:
            transaction = db.scalar(
                select(Transaction).where(
                    Transaction.id == transaction_id,
                    Transaction.owner_id == owner,
                ).with_for_update()
            )
            if transaction is None:
                raise not_found()
            if (
                transaction.provider != "internal"
                or transaction.transaction_kind not in {"travel_flight", "travel_lodging"}
            ):
                raise not_found()
            if transaction.revision != request.expected_revision:
                raise CoworkerError(
                    "transaction_revision_conflict",
                    "This transaction changed. Review the latest revision before continuing.",
                    409,
                )
            if transaction.state != "awaiting_approval":
                raise CoworkerError(
                    "travel_booking_review_required",
                    "Confirm the exact travel terms before preparing booking approval.",
                    409,
                )

            intent = db.scalar(
                select(TravelQuoteIntent).where(
                    TravelQuoteIntent.transaction_id == transaction_id,
                    TravelQuoteIntent.owner_id == owner,
                )
            )
            if intent is None:
                raise not_found()
            stored_quote = dict(intent.quote or {})
            if stable_digest(stored_quote) != intent.quote_sha256:
                raise CoworkerError(
                    "travel_booking_quote_integrity",
                    "The stored travel quote no longer matches its immutable digest.",
                    409,
                )
            quote = TravelQuoteRequest.model_validate(stored_quote)
            expected_kind = (
                "travel_flight" if quote.travel_kind == "flight" else "travel_lodging"
            )
            if transaction.transaction_kind != expected_kind:
                raise CoworkerError(
                    "travel_booking_quote_integrity",
                    "The travel transaction kind no longer matches its quote evidence.",
                    409,
                )

            terms = (
                db.get(
                    TransactionTermsSnapshot,
                    (transaction.id, transaction.current_terms_revision),
                )
                if transaction.current_terms_revision is not None
                else None
            )
            if terms is None or terms.owner_id != owner:
                raise CoworkerError(
                    "transaction_terms_stale",
                    "The current transaction revision does not have exact final terms.",
                    409,
                )
            if terms.terms_sha256 != request.terms_sha256:
                raise CoworkerError(
                    "transaction_terms_changed",
                    "Transaction terms changed after review. Review the latest terms again.",
                    409,
                )
            if aware(terms.quote_expires_at) <= now:
                raise CoworkerError(
                    "transaction_quote_expired",
                    "The reviewed travel quote expired. Refresh and review it again.",
                    409,
                )

            verification = db.scalar(
                select(TravelQuoteVerificationEvidence).where(
                    TravelQuoteVerificationEvidence.id == request.verification_id,
                    TravelQuoteVerificationEvidence.transaction_id == transaction_id,
                    TravelQuoteVerificationEvidence.owner_id == owner,
                )
            )
            if verification is None:
                raise not_found()

            latest_verification_id = db.scalar(
                select(TravelQuoteVerificationEvidence.id)
                .where(
                    TravelQuoteVerificationEvidence.transaction_id == transaction_id,
                    TravelQuoteVerificationEvidence.owner_id == owner,
                )
                .order_by(TravelQuoteVerificationEvidence.sequence.desc())
                .limit(1)
            )
            if latest_verification_id != verification.id:
                raise CoworkerError(
                    "travel_booking_verification_superseded",
                    "A newer travel verification exists. Review the latest verification.",
                    409,
                )

            stored_snapshot = dict(verification.snapshot or {})
            if stable_digest(stored_snapshot) != verification.snapshot_sha256:
                raise CoworkerError(
                    "travel_booking_verification_integrity",
                    "The stored travel verification no longer matches its immutable digest.",
                    409,
                )
            if (
                not verification.matched
                or bool(verification.mismatches)
                or verification.source_quote_sha256 != intent.quote_sha256
            ):
                raise CoworkerError(
                    "travel_booking_verification_mismatch",
                    "The travel quote is not exactly verified for booking binding.",
                    409,
                )
            if verification.snapshot_sha256 != request.verification_snapshot_sha256:
                raise CoworkerError(
                    "travel_booking_verification_changed",
                    "The travel verification changed. Review the latest verification.",
                    409,
                )

            observed_at = aware(verification.observed_at)
            verification_expires = aware(verification.quote_expires_at)
            freshness_expires = observed_at + timedelta(minutes=5)
            expires_at = min(
                aware(terms.quote_expires_at),
                verification_expires,
                freshness_expires,
            )
            if observed_at > now + timedelta(minutes=5):
                raise CoworkerError(
                    "travel_booking_verification_invalid",
                    "The travel verification observation time is invalid.",
                    409,
                )
            if expires_at <= now:
                raise CoworkerError(
                    "travel_booking_verification_stale",
                    "The travel verification is no longer fresh enough for booking binding.",
                    409,
                )

            price = stored_snapshot.get("price")
            if (
                not isinstance(price, dict)
                or stored_snapshot.get("provider") != verification.provider
                or stored_snapshot.get("provider_quote_id") != verification.provider_quote_id
                or stored_snapshot.get("travel_kind") != quote.travel_kind
                or verification.provider_quote_id != quote.provider_quote_id
                or terms.provider_quote_id != quote.provider_quote_id
                or price.get("currency") != terms.currency
                or price.get("total_minor") != terms.total_minor
            ):
                raise CoworkerError(
                    "travel_booking_terms_mismatch",
                    "Verified travel terms no longer match the reviewed transaction terms.",
                    409,
                )

            scope = {
                "schema_version": 1,
                "transaction_id": transaction.id,
                "transaction_revision": transaction.revision,
                "terms_revision": terms.revision,
                "terms_sha256": terms.terms_sha256,
                "quote_sha256": intent.quote_sha256,
                "verification_id": verification.id,
                "verification_snapshot_sha256": verification.snapshot_sha256,
                "travel_kind": quote.travel_kind,
                "provider": verification.provider,
                "provider_quote_id": verification.provider_quote_id,
                "currency": terms.currency,
                "total_minor": terms.total_minor,
                "expires_at": expires_at.isoformat(),
                "authority": "binding_only_no_execution",
            }
            approval_scope_sha256 = stable_digest(scope)

            existing = db.scalar(
                select(TravelBookingBinding).where(
                    TravelBookingBinding.transaction_id == transaction_id,
                    TravelBookingBinding.owner_id == owner,
                )
            )
            if existing is not None:
                exact = (
                    existing.transaction_revision == transaction.revision
                    and existing.terms_revision == terms.revision
                    and existing.terms_sha256 == terms.terms_sha256
                    and existing.quote_sha256 == intent.quote_sha256
                    and existing.verification_id == verification.id
                    and existing.verification_snapshot_sha256 == verification.snapshot_sha256
                    and existing.travel_kind == quote.travel_kind
                    and existing.provider == verification.provider
                    and existing.provider_quote_id == verification.provider_quote_id
                    and existing.currency == terms.currency
                    and existing.total_minor == terms.total_minor
                    and existing.approval_scope_sha256 == approval_scope_sha256
                    and aware(existing.expires_at) == expires_at
                )
                if exact:
                    return self._booking_binding_dto(existing), False
                raise CoworkerError(
                    "travel_booking_binding_conflict",
                    "A different travel booking binding already exists for this transaction.",
                    409,
                )

            row = TravelBookingBinding(
                id=str(uuid4()),
                transaction_id=transaction.id,
                owner_id=owner,
                verification_id=verification.id,
                transaction_revision=transaction.revision,
                terms_revision=terms.revision,
                terms_sha256=terms.terms_sha256,
                quote_sha256=intent.quote_sha256,
                verification_snapshot_sha256=verification.snapshot_sha256,
                travel_kind=quote.travel_kind,
                provider=verification.provider,
                provider_quote_id=verification.provider_quote_id,
                currency=terms.currency,
                total_minor=terms.total_minor,
                approval_scope_sha256=approval_scope_sha256,
                expires_at=expires_at,
                created_at=utcnow(),
            )
            db.add(row)
            db.flush()
            return self._booking_binding_dto(row), True

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
