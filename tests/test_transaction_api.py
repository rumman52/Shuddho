"""TX-04 authenticated generic transaction review API boundary."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from action_samples import enable_actions
from test_coworker import container, signed_client

from services.coworker.models import utcnow


def enable_transactions(container):
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


def create_payload(**changes):
    value = {
        "transaction_kind": "reservation",
        "counterparty": "Example Hotel",
        "currency": "USD",
        "expires_at": (utcnow() + timedelta(days=2)).isoformat(),
    }
    value.update(changes)
    return value


def terms_payload(expected_revision=1, *, total=12_500, quoted_at=None, expires_at=None):
    quoted = quoted_at or utcnow()
    expiry = expires_at or quoted + timedelta(minutes=10)
    return {
        "expected_revision": expected_revision,
        "terms": [
            {"name": "Room", "value": "Deluxe room"},
            {"name": "Cancellation", "value": "Free until 24 hours before arrival"},
        ],
        "price": {
            "currency": "USD",
            "subtotal_minor": total - 1_500,
            "tax_minor": 1_000,
            "fees_minor": 500,
            "shipping_minor": 0,
            "discount_minor": 0,
            "total_minor": total,
        },
        "provider_quote_id": "quote-api-123",
        "quoted_at": quoted.isoformat(),
        "quote_expires_at": expiry.isoformat(),
    }


def test_transactions_list_is_disabled_by_default(signed_client):
    client, headers = signed_client
    response = client.get("/api/v1/transactions", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "transactions": []}


def test_public_transaction_review_flow_is_inert_owner_scoped_and_exact_hash_bound(
    container,
    signed_client,
):
    enable_transactions(container)
    client, headers = signed_client
    alice = headers("alice")
    bob = headers("bob")

    creation_payload = create_payload()
    created_response = client.post(
        "/api/v1/transactions",
        headers=alice | {"Idempotency-Key": "tx04-create-001"},
        json=creation_payload,
    )
    assert created_response.status_code == 201
    assert created_response.headers["idempotent-replayed"] == "false"
    created = created_response.json()
    assert created["provider"] == "internal"
    assert created["connection_id"] is None
    assert created["provider_account_ref"] is None
    assert created["state"] == "draft"
    assert created["revision"] == 1

    replay = client.post(
        "/api/v1/transactions",
        headers=alice | {"Idempotency-Key": "tx04-create-001"},
        json=creation_payload,
    )
    assert replay.status_code == 201
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["id"] == created["id"]

    hidden = client.get(
        f'/api/v1/transactions/{created["id"]}',
        headers=bob,
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "not_found"

    terms_response = client.put(
        f'/api/v1/transactions/{created["id"]}/terms',
        headers=alice,
        json=terms_payload(1),
    )
    assert terms_response.status_code == 200
    saved = terms_response.json()
    assert saved["transaction"]["state"] == "terms_ready"
    assert saved["transaction"]["revision"] == 2
    terms_sha256 = saved["terms"]["terms_sha256"]

    review = client.post(
        f'/api/v1/transactions/{created["id"]}/review',
        headers=alice,
        json={"expected_revision": 2},
    )
    assert review.status_code == 200
    assert review.json()["state"] == "awaiting_review"
    assert review.json()["revision"] == 3

    wrong_hash = "0" * 64 if terms_sha256 != "0" * 64 else "1" * 64
    rejected = client.post(
        f'/api/v1/transactions/{created["id"]}/review/confirm',
        headers=alice,
        json={"expected_revision": 3, "terms_sha256": wrong_hash},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "transaction_terms_changed"

    confirmed = client.post(
        f'/api/v1/transactions/{created["id"]}/review/confirm',
        headers=alice,
        json={"expected_revision": 3, "terms_sha256": terms_sha256},
    )
    assert confirmed.status_code == 200
    value = confirmed.json()
    assert value["transaction"]["state"] == "awaiting_approval"
    assert value["transaction"]["revision"] == 4
    assert value["review_binding"]["terms_sha256"] == terms_sha256
    assert value["execution"] == {
        "available": False,
        "boundary": "external_action_only",
    }

    surface = client.get(
        f'/api/v1/transactions/{created["id"]}',
        headers=alice,
    )
    assert surface.status_code == 200
    body = surface.json()
    assert body["transaction"]["state"] == "awaiting_approval"
    assert body["terms"]["terms_sha256"] == terms_sha256
    assert body["execution"]["available"] is False
    assert body["events"][-1]["event_type"] == "transaction_review_confirmed"

    no_execute = client.post(
        f'/api/v1/transactions/{created["id"]}/execute',
        headers=alice,
    )
    assert no_execute.status_code in {404, 405}


def test_public_create_rejects_provider_or_connection_authority(container, signed_client):
    enable_transactions(container)
    client, headers = signed_client
    auth = headers("authority")

    for injected in (
        {"provider": "google"},
        {"connection_id": "00000000-0000-0000-0000-000000000000"},
        {"external_action_id": "00000000-0000-0000-0000-000000000000"},
    ):
        response = client.post(
            "/api/v1/transactions",
            headers=auth | {"Idempotency-Key": "tx04-injected-" + next(iter(injected))},
            json=create_payload(**injected),
        )
        assert response.status_code == 422

    assert client.get("/api/v1/transactions", headers=auth).json()["transactions"] == []


def test_changed_terms_require_fresh_review_and_stale_revision_fails(container, signed_client):
    enable_transactions(container)
    client, headers = signed_client
    auth = headers("changed")

    created = client.post(
        "/api/v1/transactions",
        headers=auth | {"Idempotency-Key": "tx04-change-create"},
        json=create_payload(),
    ).json()
    first = client.put(
        f'/api/v1/transactions/{created["id"]}/terms',
        headers=auth,
        json=terms_payload(1),
    ).json()
    old_hash = first["terms"]["terms_sha256"]
    review = client.post(
        f'/api/v1/transactions/{created["id"]}/review',
        headers=auth,
        json={"expected_revision": 2},
    ).json()

    changed = client.put(
        f'/api/v1/transactions/{created["id"]}/terms',
        headers=auth,
        json=terms_payload(review["revision"], total=13_000),
    )
    assert changed.status_code == 200
    changed_body = changed.json()
    assert changed_body["transaction"]["state"] == "terms_ready"
    assert changed_body["terms"]["terms_sha256"] != old_hash

    stale_revision = client.post(
        f'/api/v1/transactions/{created["id"]}/review',
        headers=auth,
        json={"expected_revision": review["revision"]},
    )
    assert stale_revision.status_code == 409
    assert stale_revision.json()["error"]["code"] == "transaction_revision_conflict"

    stale_hash = client.post(
        f'/api/v1/transactions/{created["id"]}/review',
        headers=auth,
        json={"expected_revision": changed_body["transaction"]["revision"]},
    )
    assert stale_hash.status_code == 200
    confirmation = client.post(
        f'/api/v1/transactions/{created["id"]}/review/confirm',
        headers=auth,
        json={
            "expected_revision": stale_hash.json()["revision"],
            "terms_sha256": old_hash,
        },
    )
    assert confirmation.status_code == 409
    assert confirmation.json()["error"]["code"] == "transaction_terms_changed"


def test_expired_quote_cannot_enter_review(container, signed_client):
    enable_transactions(container)
    client, headers = signed_client
    auth = headers("expired")

    created = client.post(
        "/api/v1/transactions",
        headers=auth | {"Idempotency-Key": "tx04-expired-create"},
        json=create_payload(),
    ).json()
    quoted = utcnow() - timedelta(minutes=20)
    expired = client.put(
        f'/api/v1/transactions/{created["id"]}/terms',
        headers=auth,
        json=terms_payload(
            1,
            quoted_at=quoted,
            expires_at=quoted + timedelta(minutes=5),
        ),
    )
    assert expired.status_code == 200

    review = client.post(
        f'/api/v1/transactions/{created["id"]}/review',
        headers=auth,
        json={"expected_revision": 2},
    )
    assert review.status_code == 409
    assert review.json()["error"]["code"] == "transaction_quote_expired"


def test_cancel_requires_current_revision_and_is_terminal(container, signed_client):
    enable_transactions(container)
    client, headers = signed_client
    auth = headers("cancel")

    created = client.post(
        "/api/v1/transactions",
        headers=auth | {"Idempotency-Key": "tx04-cancel-create"},
        json=create_payload(),
    ).json()

    stale = client.post(
        f'/api/v1/transactions/{created["id"]}/cancel',
        headers=auth,
        json={"expected_revision": 99},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "transaction_revision_conflict"

    cancelled = client.post(
        f'/api/v1/transactions/{created["id"]}/cancel',
        headers=auth,
        json={"expected_revision": 1},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"

    terms = client.put(
        f'/api/v1/transactions/{created["id"]}/terms',
        headers=auth,
        json=terms_payload(2),
    )
    assert terms.status_code == 409
    assert terms.json()["error"]["code"] == "transaction_terms_not_editable"
