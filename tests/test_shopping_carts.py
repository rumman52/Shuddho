"""TX-10 review-only shopping cart domain."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import inspect, select

from action_samples import enable_actions
from test_coworker import account, container, signed_client

from services.coworker.action_registry import registered_transaction_operations
from services.coworker.models import ExternalAction, ShoppingCartIntent, utcnow
from services.coworker.shopping_cart_schemas import ShoppingCartReviewRequest


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
