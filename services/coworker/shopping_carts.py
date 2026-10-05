from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from .action_registry import stable_digest
from .errors import CoworkerError
from .models import (
    ShoppingCartIntent,
    ShoppingCartVerificationEvidence,
    ShoppingCheckoutBinding,
    Transaction,
    TransactionTermsSnapshot,
    utcnow,
)
from .repository import aware, iso, not_found
from .shopping_cart_schemas import ShoppingCartReviewRequest, ShoppingCheckoutBindingRequest
from .transaction_repository import TransactionDraft
from .transaction_schemas import TransactionTermsDraft


class ShoppingCartService:
    """Durable review-only shopping carts plus trusted read-only verification."""

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
    def _cart_value(request: ShoppingCartReviewRequest) -> dict:
        return request.model_dump(mode="json")

    def _latest_verification(
        self,
        owner: str,
        transaction_id: str,
    ) -> ShoppingCartVerificationEvidence | None:
        with self.sessions() as db:
            return db.scalar(
                select(ShoppingCartVerificationEvidence)
                .where(
                    ShoppingCartVerificationEvidence.transaction_id == transaction_id,
                    ShoppingCartVerificationEvidence.owner_id == owner,
                )
                .order_by(ShoppingCartVerificationEvidence.sequence.desc())
                .limit(1)
            )

    @staticmethod
    def _verification_dto(
        row: ShoppingCartVerificationEvidence | None,
    ) -> dict | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "sequence": row.sequence,
            "provider": row.provider,
            "merchant_cart_id": row.merchant_cart_id,
            "source_cart_sha256": row.source_cart_sha256,
            "snapshot_sha256": row.snapshot_sha256,
            "matched": row.matched,
            "mismatches": list(row.mismatches or []),
            "observed_at": iso(row.observed_at),
            "quote_expires_at": iso(row.quote_expires_at),
            "created_at": iso(row.created_at),
        }

    def _intent_dto(self, row: ShoppingCartIntent) -> dict:
        verification = self._latest_verification(row.owner_id, row.transaction_id)
        verified = bool(
            verification is not None
            and verification.matched
            and verification.source_cart_sha256 == row.cart_sha256
            and aware(verification.quote_expires_at) > utcnow()
        )
        return {
            "transaction_id": row.transaction_id,
            "cart": dict(row.cart),
            "cart_sha256": row.cart_sha256,
            "created_at": iso(row.created_at),
            "provider_verified": verified,
            "checkout_available": False,
            "payment_available": False,
            "latest_verification": self._verification_dto(verification),
        }

    def _intent(self, owner: str, transaction_id: str) -> ShoppingCartIntent:
        with self.sessions() as db:
            row = db.scalar(
                select(ShoppingCartIntent).where(
                    ShoppingCartIntent.transaction_id == transaction_id,
                    ShoppingCartIntent.owner_id == owner,
                )
            )
            if row is None:
                raise not_found()
            return row

    @staticmethod
    def _terms_from_intent(row: ShoppingCartIntent) -> TransactionTermsDraft:
        cart = ShoppingCartReviewRequest.model_validate(dict(row.cart))
        terms = [
            {"name": "Merchant", "value": cart.merchant_name},
            {"name": "Fulfillment", "value": cart.fulfillment_method},
            {"name": "Fulfillment terms", "value": cart.fulfillment_terms},
            {"name": "Return terms", "value": cart.return_terms},
            {
                "name": "Execution authority",
                "value": "Review only. Shopping verification does not authorize checkout, payment, purchase, or browser submission.",
            },
        ]
        for index, item in enumerate(cart.items, 1):
            variant = f"; variant={item.variant}" if item.variant else ""
            terms.append({
                "name": f"Item {index}",
                "value": (
                    f"{item.title}; product_id={item.product_id}{variant}; "
                    f"quantity={item.quantity}; unit_minor={item.unit_price_minor}; "
                    f"line_total_minor={item.line_total_minor}"
                ),
            })
        return TransactionTermsDraft.model_validate({
            "terms": terms,
            "price": cart.price.model_dump(mode="json"),
            "provider_quote_id": cart.merchant_cart_id,
            "quoted_at": cart.quoted_at,
            "quote_expires_at": cart.quote_expires_at,
        })

    @staticmethod
    def _expected_verification(cart: ShoppingCartReviewRequest) -> dict:
        return {
            "merchant_cart_id": cart.merchant_cart_id,
            "merchant_name": cart.merchant_name,
            "items": [item.model_dump(mode="json") for item in cart.items],
            "price": cart.price.model_dump(mode="json"),
            "fulfillment_method": cart.fulfillment_method,
            "fulfillment_terms": cart.fulfillment_terms,
            "return_terms": cart.return_terms,
            "quote_expires_at": cart.quote_expires_at.isoformat(),
        }

    async def verify_with_provider(
        self,
        owner: str,
        transaction_id: str,
        provider: str,
    ) -> dict:
        """Append one trusted read-only merchant cart observation.

        TX-11 deliberately does not mount this method as a public API endpoint.
        """
        self._require_enabled()
        provider_key = provider.strip().lower()
        verifier = self.verifiers.get(provider_key)
        if verifier is None:
            raise CoworkerError(
                "shopping_cart_verifier_unregistered",
                "This shopping cart verifier is not registered.",
                409,
            )

        transaction = self.transactions.get(owner, transaction_id)
        if (
            transaction["provider"] != "internal"
            or transaction["transaction_kind"] != "shopping_cart_review"
        ):
            raise not_found()

        intent = self._intent(owner, transaction_id)
        cart = ShoppingCartReviewRequest.model_validate(dict(intent.cart))
        observation = await verifier.verify_cart(
            merchant_cart_id=cart.merchant_cart_id,
        )
        if str(observation.provider).strip().lower() != provider_key:
            raise CoworkerError(
                "shopping_cart_provider_mismatch",
                "The shopping cart observation came from a different registered provider.",
                409,
            )
        if observation.observed_at.tzinfo is None or observation.observed_at.utcoffset() is None:
            raise CoworkerError(
                "shopping_cart_verification_invalid",
                "The shopping cart observation time is invalid.",
                409,
            )
        if observation.quote_expires_at.tzinfo is None or observation.quote_expires_at.utcoffset() is None:
            raise CoworkerError(
                "shopping_cart_verification_invalid",
                "The merchant quote expiry is invalid.",
                409,
            )

        observed_at = observation.observed_at.astimezone(timezone.utc)
        now = utcnow()
        if observed_at > now + timedelta(minutes=5):
            raise CoworkerError(
                "shopping_cart_verification_invalid",
                "The shopping cart observation time is in the future.",
                409,
            )
        if observed_at < now - timedelta(minutes=5):
            raise CoworkerError(
                "shopping_cart_verification_stale",
                "The shopping cart observation is too old to verify current terms.",
                409,
            )
        if observation.quote_expires_at.astimezone(timezone.utc) <= observed_at:
            raise CoworkerError(
                "shopping_cart_verification_invalid",
                "The merchant quote already expired at observation time.",
                409,
            )

        snapshot = observation.public_snapshot()
        expected = self._expected_verification(cart)
        actual = {key: snapshot[key] for key in expected}
        mismatches = [
            key
            for key in expected
            if stable_digest(expected[key]) != stable_digest(actual[key])
        ]
        snapshot_sha256 = stable_digest(snapshot)

        with self.sessions.begin() as db:
            locked_intent = db.scalar(
                select(ShoppingCartIntent).where(
                    ShoppingCartIntent.transaction_id == transaction_id,
                    ShoppingCartIntent.owner_id == owner,
                ).with_for_update()
            )
            if locked_intent is None:
                raise not_found()
            latest = db.scalar(
                select(ShoppingCartVerificationEvidence)
                .where(
                    ShoppingCartVerificationEvidence.transaction_id == transaction_id,
                    ShoppingCartVerificationEvidence.owner_id == owner,
                )
                .order_by(ShoppingCartVerificationEvidence.sequence.desc())
                .limit(1)
            )
            sequence = 1 if latest is None else latest.sequence + 1
            row = ShoppingCartVerificationEvidence(
                id=str(uuid4()),
                transaction_id=transaction_id,
                owner_id=owner,
                sequence=sequence,
                source_cart_sha256=locked_intent.cart_sha256,
                provider=provider_key,
                merchant_cart_id=observation.merchant_cart_id,
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
            "shopping_cart": self._intent_dto(self._intent(owner, transaction_id)),
        }

    @staticmethod
    def _binding_dto(row: ShoppingCheckoutBinding) -> dict:
        return {
            "id": row.id,
            "transaction_id": row.transaction_id,
            "verification_id": row.verification_id,
            "transaction_revision": row.transaction_revision,
            "terms_revision": row.terms_revision,
            "terms_sha256": row.terms_sha256,
            "cart_sha256": row.cart_sha256,
            "verification_snapshot_sha256": row.verification_snapshot_sha256,
            "provider": row.provider,
            "merchant_cart_id": row.merchant_cart_id,
            "currency": row.currency,
            "total_minor": row.total_minor,
            "approval_scope_sha256": row.approval_scope_sha256,
            "expires_at": iso(row.expires_at),
            "created_at": iso(row.created_at),
            "execution_available": False,
        }

    def checkout_binding(self, owner: str, transaction_id: str) -> dict:
        self._require_enabled()
        with self.sessions() as db:
            row = db.scalar(
                select(ShoppingCheckoutBinding).where(
                    ShoppingCheckoutBinding.transaction_id == transaction_id,
                    ShoppingCheckoutBinding.owner_id == owner,
                )
            )
            if row is None:
                raise not_found()
            return self._binding_dto(row)

    def create_checkout_binding(
        self,
        owner: str,
        transaction_id: str,
        request: ShoppingCheckoutBindingRequest,
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
                or transaction.transaction_kind != "shopping_cart_review"
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
                    "shopping_checkout_review_required",
                    "Confirm the exact shopping terms before preparing checkout approval.",
                    409,
                )

            intent = db.scalar(
                select(ShoppingCartIntent).where(
                    ShoppingCartIntent.transaction_id == transaction_id,
                    ShoppingCartIntent.owner_id == owner,
                )
            )
            if intent is None:
                raise not_found()
            if stable_digest(dict(intent.cart or {})) != intent.cart_sha256:
                raise CoworkerError(
                    "shopping_checkout_cart_integrity",
                    "The stored shopping cart evidence no longer matches its immutable digest.",
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
                    "The reviewed shopping quote expired. Refresh and review it again.",
                    409,
                )

            verification = db.scalar(
                select(ShoppingCartVerificationEvidence).where(
                    ShoppingCartVerificationEvidence.id == request.verification_id,
                    ShoppingCartVerificationEvidence.transaction_id == transaction_id,
                    ShoppingCartVerificationEvidence.owner_id == owner,
                )
            )
            if verification is None:
                raise not_found()

            latest_verification_id = db.scalar(
                select(ShoppingCartVerificationEvidence.id)
                .where(
                    ShoppingCartVerificationEvidence.transaction_id == transaction_id,
                    ShoppingCartVerificationEvidence.owner_id == owner,
                )
                .order_by(ShoppingCartVerificationEvidence.sequence.desc())
                .limit(1)
            )
            if latest_verification_id != verification.id:
                raise CoworkerError(
                    "shopping_checkout_verification_superseded",
                    "A newer shopping verification exists. Review the latest verification.",
                    409,
                )
            stored_snapshot = dict(verification.snapshot or {})
            if stable_digest(stored_snapshot) != verification.snapshot_sha256:
                raise CoworkerError(
                    "shopping_checkout_verification_integrity",
                    "The stored shopping verification no longer matches its immutable digest.",
                    409,
                )
            if (
                not verification.matched
                or bool(verification.mismatches)
                or verification.source_cart_sha256 != intent.cart_sha256
            ):
                raise CoworkerError(
                    "shopping_checkout_verification_mismatch",
                    "The shopping cart is not exactly verified for checkout binding.",
                    409,
                )
            if verification.snapshot_sha256 != request.verification_snapshot_sha256:
                raise CoworkerError(
                    "shopping_checkout_verification_changed",
                    "The shopping verification changed. Review the latest verification.",
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
                    "shopping_checkout_verification_invalid",
                    "The shopping verification observation time is invalid.",
                    409,
                )
            if expires_at <= now:
                raise CoworkerError(
                    "shopping_checkout_verification_stale",
                    "The shopping verification is no longer fresh enough for checkout binding.",
                    409,
                )

            snapshot = stored_snapshot
            price = snapshot.get("price")
            if (
                not isinstance(price, dict)
                or snapshot.get("provider") != verification.provider
                or snapshot.get("merchant_cart_id") != verification.merchant_cart_id
                or price.get("currency") != terms.currency
                or price.get("total_minor") != terms.total_minor
                or snapshot.get("merchant_cart_id") != terms.provider_quote_id
            ):
                raise CoworkerError(
                    "shopping_checkout_terms_mismatch",
                    "Verified merchant cart totals no longer match the reviewed transaction terms.",
                    409,
                )

            scope = {
                "schema_version": 1,
                "transaction_id": transaction.id,
                "transaction_revision": transaction.revision,
                "terms_revision": terms.revision,
                "terms_sha256": terms.terms_sha256,
                "cart_sha256": intent.cart_sha256,
                "verification_id": verification.id,
                "verification_snapshot_sha256": verification.snapshot_sha256,
                "provider": verification.provider,
                "merchant_cart_id": verification.merchant_cart_id,
                "currency": terms.currency,
                "total_minor": terms.total_minor,
                "expires_at": expires_at.isoformat(),
                "authority": "binding_only_no_execution",
            }
            approval_scope_sha256 = stable_digest(scope)

            existing = db.scalar(
                select(ShoppingCheckoutBinding).where(
                    ShoppingCheckoutBinding.transaction_id == transaction_id,
                    ShoppingCheckoutBinding.owner_id == owner,
                )
            )
            if existing is not None:
                exact = (
                    existing.transaction_revision == transaction.revision
                    and existing.terms_revision == terms.revision
                    and existing.terms_sha256 == terms.terms_sha256
                    and existing.cart_sha256 == intent.cart_sha256
                    and existing.verification_id == verification.id
                    and existing.verification_snapshot_sha256 == verification.snapshot_sha256
                    and existing.provider == verification.provider
                    and existing.merchant_cart_id == verification.merchant_cart_id
                    and existing.currency == terms.currency
                    and existing.total_minor == terms.total_minor
                    and existing.approval_scope_sha256 == approval_scope_sha256
                    and aware(existing.expires_at) == expires_at
                )
                if exact:
                    return self._binding_dto(existing), False
                raise CoworkerError(
                    "shopping_checkout_binding_conflict",
                    "A different checkout binding already exists for this transaction.",
                    409,
                )

            row = ShoppingCheckoutBinding(
                id=str(uuid4()),
                transaction_id=transaction.id,
                owner_id=owner,
                verification_id=verification.id,
                transaction_revision=transaction.revision,
                terms_revision=terms.revision,
                terms_sha256=terms.terms_sha256,
                cart_sha256=intent.cart_sha256,
                verification_snapshot_sha256=verification.snapshot_sha256,
                provider=verification.provider,
                merchant_cart_id=verification.merchant_cart_id,
                currency=terms.currency,
                total_minor=terms.total_minor,
                approval_scope_sha256=approval_scope_sha256,
                expires_at=expires_at,
                created_at=utcnow(),
            )
            db.add(row)
            db.flush()
            return self._binding_dto(row), True

    def create(
        self,
        owner: str,
        request: ShoppingCartReviewRequest,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        canonical = self._cart_value(request)
        cart_sha256 = stable_digest(canonical)
        transaction, created = self.transactions.create(
            owner,
            TransactionDraft(
                transaction_kind="shopping_cart_review",
                provider="internal",
                connection_id=None,
                currency=request.price.currency,
                counterparty=request.merchant_name,
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
                select(ShoppingCartIntent).where(
                    ShoppingCartIntent.transaction_id == tx.id,
                    ShoppingCartIntent.owner_id == owner,
                )
            )
            if intent is None:
                intent = ShoppingCartIntent(
                    transaction_id=tx.id,
                    owner_id=owner,
                    cart=canonical,
                    cart_sha256=cart_sha256,
                    created_at=utcnow(),
                )
                db.add(intent)
                db.flush()
            elif intent.cart_sha256 != cart_sha256:
                raise CoworkerError(
                    "idempotency_conflict",
                    "This request key belongs to different shopping cart details.",
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
            "shopping_cart": self._intent_dto(self._intent(owner, transaction["id"])),
        }, created

    def get(self, owner: str, transaction_id: str) -> dict:
        self._require_enabled()
        transaction = self.transactions.get(owner, transaction_id)
        if (
            transaction["provider"] != "internal"
            or transaction["transaction_kind"] != "shopping_cart_review"
        ):
            raise not_found()
        return {
            **self.transactions.review_surface(owner, transaction_id),
            "shopping_cart": self._intent_dto(self._intent(owner, transaction_id)),
        }
