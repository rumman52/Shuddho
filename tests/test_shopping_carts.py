"""TX-10 review-only shopping cart domain."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import inspect, select

from action_samples import enable_actions
from test_coworker import account, container, signed_client

from services.coworker.action_registry import registered_transaction_operations
from services.coworker.models import (
    ExternalAction,
    ShoppingCartIntent,
    ShoppingCartVerificationEvidence,
    utcnow,
)
from services.coworker.shopping_cart_schemas import (
    ShoppingCartItem,
    ShoppingCartReviewRequest,
)
from services.coworker.shopping_cart_verifier import ShoppingCartVerification
from services.coworker.transaction_schemas import TransactionPrice


def enable_shopping_carts(container):
    enable_actions(container)
    settings = replace(
        container.settings,
        connector_trust_boundary_enabled=True,
        personal_transactions_enabled=True,
        transaction_operations=frozenset({"google:negotiation_commitment_email"}),
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.transactions.settings = settings
    container.shopping_carts.settings = settings


class SimulatedShoppingVerifier:
    provider_name = "simulated"

    def __init__(
        self,
        payload: dict,
        *,
        price_delta_minor: int = 0,
        observed_at=None,
    ):
        self.payload = deepcopy(payload)
        self.price_delta_minor = price_delta_minor
        self.observed_at = observed_at
        self.calls = []

    async def verify_cart(self, *, merchant_cart_id: str):
        self.calls.append({"merchant_cart_id": merchant_cart_id})
        value = deepcopy(self.payload)
        if self.price_delta_minor:
            value["price"]["fees_minor"] += self.price_delta_minor
            value["price"]["total_minor"] += self.price_delta_minor
        return ShoppingCartVerification(
            provider=self.provider_name,
            merchant_cart_id=merchant_cart_id,
            merchant_name=value["merchant_name"],
            items=tuple(
                ShoppingCartItem.model_validate(item)
                for item in value["items"]
            ),
            price=TransactionPrice.model_validate(value["price"]),
            fulfillment_method=value["fulfillment_method"],
            fulfillment_terms=value["fulfillment_terms"],
            return_terms=value["return_terms"],
            quote_expires_at=datetime.fromisoformat(value["quote_expires_at"]),
            observed_at=self.observed_at or utcnow(),
        )


def cart_payload(**changes):
    now = utcnow()
    value = {
        "quote_source": "user_supplied",
        "merchant_name": "Example Shop",
        "merchant_cart_id": "cart-quote-001",
        "items": [
            {
                "product_id": "shirt-100",
                "title": "Cotton Shirt",
                "variant": "Blue / M",
                "quantity": 2,
                "unit_price_minor": 2500,
                "line_total_minor": 5000,
            },
            {
                "product_id": "socks-200",
                "title": "Crew Socks",
                "variant": "Black",
                "quantity": 1,
                "unit_price_minor": 1200,
                "line_total_minor": 1200,
            },
        ],
        "price": {
            "currency": "USD",
            "subtotal_minor": 6200,
            "tax_minor": 500,
            "fees_minor": 100,
            "shipping_minor": 700,
            "discount_minor": 500,
            "total_minor": 7000,
        },
        "fulfillment_method": "shipping",
        "fulfillment_terms": "Standard shipping; estimated delivery shown by merchant.",
        "return_terms": "Returns accepted within 30 days if merchant conditions are met.",
        "quoted_at": now.isoformat(),
        "quote_expires_at": (now + timedelta(hours=1)).isoformat(),
    }
    value.update(changes)
    return value


def test_tx10_migration_adds_owner_scoped_shopping_cart_intents(container):
    inspector = inspect(container.repository.sessions.kw["bind"])
    assert "cw_shopping_cart_intents" in set(inspector.get_table_names())
    columns = {
        item["name"]
        for item in inspector.get_columns("cw_shopping_cart_intents")
    }
    assert {
        "transaction_id",
        "owner_id",
        "cart",
        "cart_sha256",
        "created_at",
    } <= columns


def test_tx10_api_records_exact_cart_without_checkout_authority(container, signed_client):
    enable_shopping_carts(container)
    client, headers = signed_client
    alice = headers("tx10-alice")
    bob = headers("tx10-bob")
    payload = cart_payload()

    response = client.post(
        "/api/v1/shopping-carts",
        headers=alice | {"Idempotency-Key": "tx10-cart-001"},
        json=payload,
    )
    assert response.status_code == 201
    assert response.headers["idempotent-replayed"] == "false"
    value = response.json()
    tx = value["transaction"]
    assert tx["transaction_kind"] == "shopping_cart_review"
    assert tx["provider"] == "internal"
    assert tx["connection_id"] is None
    assert tx["state"] == "terms_ready"
    assert value["terms"]["currency"] == "USD"
    assert value["terms"]["total_minor"] == 7000
    assert value["shopping_cart"]["provider_verified"] is False
    assert value["shopping_cart"]["checkout_available"] is False
    assert value["shopping_cart"]["payment_available"] is False
    assert value["execution"]["available"] is False
    assert len(value["shopping_cart"]["cart_sha256"]) == 64

    owner = client.get("/api/v1/me", headers=alice).json()["account_id"]
    with container.repository.sessions() as db:
        assert db.scalar(
            select(ExternalAction).where(ExternalAction.owner_id == owner)
        ) is None

    replay = client.post(
        "/api/v1/shopping-carts",
        headers=alice | {"Idempotency-Key": "tx10-cart-001"},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["transaction"]["id"] == tx["id"]

    hidden = client.get(f'/api/v1/shopping-carts/{tx["id"]}', headers=bob)
    assert hidden.status_code == 404

    changed = cart_payload(merchant_cart_id="cart-quote-002")
    conflict = client.post(
        "/api/v1/shopping-carts",
        headers=alice | {"Idempotency-Key": "tx10-cart-001"},
        json=changed,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_tx10_managed_cart_terms_cannot_be_rewritten_generically(container, signed_client):
    enable_shopping_carts(container)
    client, headers = signed_client
    auth = headers("tx10-managed")
    payload = cart_payload()

    created = client.post(
        "/api/v1/shopping-carts",
        headers=auth | {"Idempotency-Key": "tx10-managed-001"},
        json=payload,
    ).json()
    tx = created["transaction"]

    rewritten = client.put(
        f'/api/v1/transactions/{tx["id"]}/terms',
        headers=auth,
        json={
            "expected_revision": tx["revision"],
            "terms": [{"name": "Merchant", "value": "Changed outside shopping service"}],
            "price": payload["price"],
            "provider_quote_id": "tampered",
            "quoted_at": payload["quoted_at"],
            "quote_expires_at": payload["quote_expires_at"],
        },
    )
    assert rewritten.status_code == 409
    assert rewritten.json()["error"]["code"] == "transaction_terms_provider_managed"


def test_tx10_review_confirmation_still_cannot_checkout_or_pay(container, signed_client):
    enable_shopping_carts(container)
    client, headers = signed_client
    auth = headers("tx10-review")

    created = client.post(
        "/api/v1/shopping-carts",
        headers=auth | {"Idempotency-Key": "tx10-review-001"},
        json=cart_payload(),
    ).json()
    tx = created["transaction"]
    terms_hash = created["terms"]["terms_sha256"]

    review = client.post(
        f'/api/v1/transactions/{tx["id"]}/review',
        headers=auth,
        json={"expected_revision": tx["revision"]},
    )
    assert review.status_code == 200
    confirmed = client.post(
        f'/api/v1/transactions/{tx["id"]}/review/confirm',
        headers=auth,
        json={
            "expected_revision": review.json()["revision"],
            "terms_sha256": terms_hash,
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["transaction"]["state"] == "awaiting_approval"
    assert confirmed.json()["execution"]["available"] is False

    assert all(
        "shopping" not in operation
        and "checkout" not in operation
        and "payment" not in operation
        for operation in registered_transaction_operations()
    )
    assert client.post(
        f'/api/v1/shopping-carts/{tx["id"]}/checkout',
        headers=auth,
        json={},
    ).status_code in {404, 405}
    assert client.post(
        f'/api/v1/shopping-carts/{tx["id"]}/pay',
        headers=auth,
        json={},
    ).status_code in {404, 405}
    assert client.post(
        f'/api/v1/transactions/{tx["id"]}/execute',
        headers=auth,
        json={},
    ).status_code in {404, 405}


@pytest.mark.parametrize(
    "payload",
    [
        cart_payload(
            items=[
                {
                    "product_id": "bad",
                    "title": "Bad subtotal",
                    "quantity": 1,
                    "unit_price_minor": 100,
                    "line_total_minor": 99,
                }
            ]
        ),
        cart_payload(
            price={
                "currency": "USD",
                "subtotal_minor": 9999,
                "tax_minor": 500,
                "fees_minor": 100,
                "shipping_minor": 700,
                "discount_minor": 500,
                "total_minor": 10799,
            }
        ),
        cart_payload(
            quoted_at=(utcnow() - timedelta(hours=2)).isoformat(),
            quote_expires_at=(utcnow() - timedelta(hours=1)).isoformat(),
        ),
        cart_payload(
            items=[
                {
                    "product_id": "overflow",
                    "title": "Overflow price",
                    "quantity": 1,
                    "unit_price_minor": 9_223_372_036_854_775_808,
                    "line_total_minor": 9_223_372_036_854_775_808,
                }
            ],
            price={
                "currency": "USD",
                "subtotal_minor": 9_223_372_036_854_775_808,
                "tax_minor": 0,
                "fees_minor": 0,
                "shipping_minor": 0,
                "discount_minor": 0,
                "total_minor": 9_223_372_036_854_775_808,
            },
        ),
    ],
)
def test_tx10_schema_rejects_invalid_cart_evidence(container, signed_client, payload):
    enable_shopping_carts(container)
    client, headers = signed_client
    response = client.post(
        "/api/v1/shopping-carts",
        headers=headers("tx10-invalid") | {"Idempotency-Key": "tx10-invalid-001"},
        json=payload,
    )
    assert response.status_code == 422


def test_tx10_account_erasure_removes_shopping_cart_intent(container):
    enable_shopping_carts(container)
    owner = account(container, "tx10-retention")
    surface, _ = container.shopping_carts.create(
        owner,
        ShoppingCartReviewRequest.model_validate(cart_payload()),
        "tx10-retention-001",
    )
    transaction_id = surface["transaction"]["id"]
    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True

    with container.repository.sessions() as db:
        assert db.scalar(
            select(ShoppingCartIntent).where(
                ShoppingCartIntent.transaction_id == transaction_id
            )
        ) is None


def test_tx11_trusted_verifier_records_exact_match_without_checkout_authority(container):
    enable_shopping_carts(container)
    owner = account(container, "tx11-match")
    payload = cart_payload()
    surface, _ = container.shopping_carts.create(
        owner,
        ShoppingCartReviewRequest.model_validate(payload),
        "tx11-match-001",
    )
    transaction_id = surface["transaction"]["id"]
    verifier = SimulatedShoppingVerifier(payload)
    container.shopping_carts.verifiers["simulated"] = verifier

    verified = asyncio.run(
        container.shopping_carts.verify_with_provider(
            owner,
            transaction_id,
            "simulated",
        )
    )
    assert verifier.calls == [{"merchant_cart_id": payload["merchant_cart_id"]}]
    assert verified["shopping_cart"]["provider_verified"] is True
    assert verified["shopping_cart"]["checkout_available"] is False
    assert verified["shopping_cart"]["payment_available"] is False
    evidence = verified["shopping_cart"]["latest_verification"]
    assert evidence["matched"] is True
    assert evidence["mismatches"] == []
    assert len(evidence["snapshot_sha256"]) == 64

    with container.repository.sessions() as db:
        assert db.scalar(
            select(ExternalAction).where(ExternalAction.owner_id == owner)
        ) is None
        row = db.scalar(
            select(ShoppingCartVerificationEvidence).where(
                ShoppingCartVerificationEvidence.transaction_id == transaction_id,
                ShoppingCartVerificationEvidence.owner_id == owner,
            )
        )
        assert row is not None
        assert row.source_cart_sha256 == surface["shopping_cart"]["cart_sha256"]


def test_tx11_price_drift_is_evidence_not_silent_terms_rewrite(container):
    enable_shopping_carts(container)
    owner = account(container, "tx11-drift")
    payload = cart_payload()
    surface, _ = container.shopping_carts.create(
        owner,
        ShoppingCartReviewRequest.model_validate(payload),
        "tx11-drift-001",
    )
    transaction_id = surface["transaction"]["id"]
    original_terms_hash = surface["terms"]["terms_sha256"]
    container.shopping_carts.verifiers["simulated"] = SimulatedShoppingVerifier(
        payload,
        price_delta_minor=250,
    )

    verified = asyncio.run(
        container.shopping_carts.verify_with_provider(
            owner,
            transaction_id,
            "simulated",
        )
    )
    assert verified["shopping_cart"]["provider_verified"] is False
    assert verified["shopping_cart"]["latest_verification"]["matched"] is False
    assert "price" in verified["shopping_cart"]["latest_verification"]["mismatches"]
    assert verified["terms"]["terms_sha256"] == original_terms_hash
    assert verified["execution"]["available"] is False


def test_tx11_owner_isolation_precedes_merchant_call(container):
    enable_shopping_carts(container)
    alice = account(container, "tx11-alice")
    bob = account(container, "tx11-bob")
    payload = cart_payload()
    surface, _ = container.shopping_carts.create(
        alice,
        ShoppingCartReviewRequest.model_validate(payload),
        "tx11-owner-001",
    )
    verifier = SimulatedShoppingVerifier(payload)
    container.shopping_carts.verifiers["simulated"] = verifier

    with pytest.raises(Exception) as denied:
        asyncio.run(
            container.shopping_carts.verify_with_provider(
                bob,
                surface["transaction"]["id"],
                "simulated",
            )
        )
    assert getattr(denied.value, "status_code", None) == 404
    assert verifier.calls == []


def test_tx11_rejects_stale_observation_without_persisting_evidence(container):
    enable_shopping_carts(container)
    owner = account(container, "tx11-stale")
    payload = cart_payload()
    surface, _ = container.shopping_carts.create(
        owner,
        ShoppingCartReviewRequest.model_validate(payload),
        "tx11-stale-001",
    )
    transaction_id = surface["transaction"]["id"]
    container.shopping_carts.verifiers["simulated"] = SimulatedShoppingVerifier(
        payload,
        observed_at=utcnow() - timedelta(minutes=10),
    )

    with pytest.raises(Exception) as stale:
        asyncio.run(
            container.shopping_carts.verify_with_provider(
                owner,
                transaction_id,
                "simulated",
            )
        )
    assert getattr(stale.value, "code", None) == "shopping_cart_verification_stale"
    with container.repository.sessions() as db:
        assert db.scalar(
            select(ShoppingCartVerificationEvidence).where(
                ShoppingCartVerificationEvidence.transaction_id == transaction_id
            )
        ) is None


def test_tx11_no_public_verify_or_checkout_authority(container, signed_client):
    enable_shopping_carts(container)
    client, headers = signed_client
    auth = headers("tx11-no-authority")
    created = client.post(
        "/api/v1/shopping-carts",
        headers=auth | {"Idempotency-Key": "tx11-no-authority-001"},
        json=cart_payload(),
    )
    assert created.status_code == 201
    transaction_id = created.json()["transaction"]["id"]

    assert client.post(
        f"/api/v1/shopping-carts/{transaction_id}/verify",
        headers=auth,
        json={"provider": "simulated"},
    ).status_code in {404, 405}
    assert client.post(
        f"/api/v1/shopping-carts/{transaction_id}/checkout",
        headers=auth,
        json={},
    ).status_code in {404, 405}


def test_tx11_account_erasure_removes_verification_evidence(container):
    enable_shopping_carts(container)
    owner = account(container, "tx11-retention")
    payload = cart_payload()
    surface, _ = container.shopping_carts.create(
        owner,
        ShoppingCartReviewRequest.model_validate(payload),
        "tx11-retention-001",
    )
    transaction_id = surface["transaction"]["id"]
    container.shopping_carts.verifiers["simulated"] = SimulatedShoppingVerifier(payload)
    asyncio.run(
        container.shopping_carts.verify_with_provider(
            owner,
            transaction_id,
            "simulated",
        )
    )

    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.scalar(
            select(ShoppingCartVerificationEvidence).where(
                ShoppingCartVerificationEvidence.transaction_id == transaction_id
            )
        ) is None
