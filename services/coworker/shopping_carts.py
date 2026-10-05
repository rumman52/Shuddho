from __future__ import annotations

from sqlalchemy import select

from .action_registry import stable_digest
from .errors import CoworkerError
from .models import ShoppingCartIntent, Transaction, utcnow
from .repository import iso, not_found
from .shopping_cart_schemas import ShoppingCartReviewRequest
from .transaction_repository import TransactionDraft
from .transaction_schemas import TransactionTermsDraft


class ShoppingCartService:
    """TX-10 durable review-only shopping cart domain."""

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
    def _cart_value(request: ShoppingCartReviewRequest) -> dict:
        return request.model_dump(mode="json")

    @staticmethod
    def _intent_dto(row: ShoppingCartIntent) -> dict:
        return {
            "transaction_id": row.transaction_id,
            "cart": dict(row.cart),
            "cart_sha256": row.cart_sha256,
            "created_at": iso(row.created_at),
            "provider_verified": False,
            "checkout_available": False,
            "payment_available": False,
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
                "value": "Review only. TX-10 does not create a remote cart or authorize checkout, payment, purchase, or browser submission.",
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
