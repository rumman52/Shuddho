"""TX-17 immutable travel booking approval binding."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import inspect, select

from test_coworker import container, signed_client
from test_travel_quotes import (
    SimulatedTravelVerifier,
    enable_travel_quotes,
    flight_quote,
    lodging_quote,
)

from services.coworker.action_registry import registered_transaction_operations
from services.coworker.models import (
    ExternalAction,
    TravelBookingBinding,
    TravelQuoteVerificationEvidence,
    utcnow,
)


def _verified_reviewed_travel(container, client, headers, key, *, lodging=False):
    auth = headers(key)
    payload = lodging_quote() if lodging else flight_quote()
    created = client.post(
        "/api/v1/travel-quotes",
        headers=auth | {"Idempotency-Key": f"{key}-quote"},
        json=payload,
    )
    assert created.status_code == 201
    surface = created.json()
    transaction_id = surface["transaction"]["id"]
    owner = client.get("/api/v1/me", headers=auth).json()["account_id"]

    container.travel_quotes.verifiers["simulated"] = SimulatedTravelVerifier(payload)
    verified = asyncio.run(
        container.travel_quotes.verify_with_provider(
            owner,
            transaction_id,
            "simulated",
        )
    )
    evidence = verified["travel_quote"]["latest_verification"]
    assert evidence["matched"] is True

    review = client.post(
        f"/api/v1/transactions/{transaction_id}/review",
        headers=auth,
        json={"expected_revision": surface["transaction"]["revision"]},
    )
    assert review.status_code == 200
    confirmed = client.post(
        f"/api/v1/transactions/{transaction_id}/review/confirm",
        headers=auth,
        json={
            "expected_revision": review.json()["revision"],
            "terms_sha256": surface["terms"]["terms_sha256"],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["transaction"]["state"] == "awaiting_approval"
    return {
        "auth": auth,
        "owner": owner,
        "payload": payload,
        "surface": surface,
        "transaction_id": transaction_id,
        "evidence": evidence,
        "confirmed": confirmed.json(),
    }


def _binding_request(value):
    return {
        "expected_revision": value["confirmed"]["transaction"]["revision"],
        "terms_sha256": value["surface"]["terms"]["terms_sha256"],
        "verification_id": value["evidence"]["id"],
        "verification_snapshot_sha256": value["evidence"]["snapshot_sha256"],
    }


def test_tx17_migration_adds_owner_scoped_travel_booking_bindings(container):
    inspector = inspect(container.repository.sessions.kw["bind"])
    assert "cw_travel_booking_bindings" in set(inspector.get_table_names())
    columns = {
        item["name"]
        for item in inspector.get_columns("cw_travel_booking_bindings")
    }
    assert {
        "transaction_id",
        "owner_id",
        "verification_id",
        "transaction_revision",
        "terms_revision",
        "terms_sha256",
        "quote_sha256",
        "verification_snapshot_sha256",
        "travel_kind",
        "provider",
        "provider_quote_id",
        "currency",
        "total_minor",
        "approval_scope_sha256",
        "expires_at",
        "created_at",
    } <= columns


@pytest.mark.parametrize("lodging", [False, True])
def test_tx17_exact_booking_binding_is_inert_and_idempotent(
    container,
    signed_client,
    lodging,
):
    enable_travel_quotes(container)
    client, headers = signed_client
    value = _verified_reviewed_travel(
        container,
        client,
        headers,
        f"tx17-exact-{'lodging' if lodging else 'flight'}",
        lodging=lodging,
    )
    request = _binding_request(value)
    transaction_id = value["transaction_id"]

    created = client.post(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=value["auth"],
        json=request,
    )
    assert created.status_code == 201
    assert created.headers["idempotent-replayed"] == "false"
    binding = created.json()
    assert binding["transaction_id"] == transaction_id
    assert binding["verification_id"] == value["evidence"]["id"]
    assert binding["terms_sha256"] == request["terms_sha256"]
    assert binding["quote_sha256"] == value["surface"]["travel_quote"]["quote_sha256"]
    assert binding["verification_snapshot_sha256"] == value["evidence"]["snapshot_sha256"]
    assert binding["travel_kind"] == ("lodging" if lodging else "flight")
    assert binding["provider"] == "simulated"
    assert binding["provider_quote_id"] == value["payload"]["provider_quote_id"]
    assert binding["currency"] == value["payload"]["price"]["currency"]
    assert binding["total_minor"] == value["payload"]["price"]["total_minor"]
    assert len(binding["approval_scope_sha256"]) == 64
    assert binding["execution_available"] is False

    replay = client.post(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=value["auth"],
        json=request,
    )
    assert replay.status_code == 201
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["id"] == binding["id"]

    fetched = client.get(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=value["auth"],
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == binding["id"]

    with container.repository.sessions() as db:
        assert db.scalar(
            select(ExternalAction).where(ExternalAction.owner_id == value["owner"])
        ) is None

    assert all(
        "travel" not in operation and "booking" not in operation
        for operation in registered_transaction_operations()
    )
    assert client.post(
        f"/api/v1/travel-quotes/{transaction_id}/book",
        headers=value["auth"],
        json={},
    ).status_code in {404, 405}
    assert client.post(
        f"/api/v1/transactions/{transaction_id}/execute",
        headers=value["auth"],
        json={},
    ).status_code in {404, 405}


def test_tx17_rejects_changed_or_superseded_verification(container, signed_client):
    enable_travel_quotes(container)
    client, headers = signed_client
    value = _verified_reviewed_travel(
        container,
        client,
        headers,
        "tx17-change",
    )
    transaction_id = value["transaction_id"]

    wrong_hash = client.post(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=value["auth"],
        json={
            **_binding_request(value),
            "verification_snapshot_sha256": "0" * 64,
        },
    )
    assert wrong_hash.status_code == 409
    assert wrong_hash.json()["error"]["code"] == "travel_booking_verification_changed"

    container.travel_quotes.verifiers["simulated"] = SimulatedTravelVerifier(value["payload"])
    newer = asyncio.run(
        container.travel_quotes.verify_with_provider(
            value["owner"],
            transaction_id,
            "simulated",
        )
    )["travel_quote"]["latest_verification"]
    assert newer["id"] != value["evidence"]["id"]

    superseded = client.post(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=value["auth"],
        json=_binding_request(value),
    )
    assert superseded.status_code == 409
    assert superseded.json()["error"]["code"] == "travel_booking_verification_superseded"


def test_tx17_rejects_mismatched_or_stale_verification(container, signed_client):
    enable_travel_quotes(container)
    client, headers = signed_client
    auth = headers("tx17-mismatch")
    payload = flight_quote()
    created = client.post(
        "/api/v1/travel-quotes",
        headers=auth | {"Idempotency-Key": "tx17-mismatch-quote"},
        json=payload,
    ).json()
    transaction_id = created["transaction"]["id"]
    owner = client.get("/api/v1/me", headers=auth).json()["account_id"]

    container.travel_quotes.verifiers["simulated"] = SimulatedTravelVerifier(
        payload,
        price_delta_minor=25,
    )
    mismatched = asyncio.run(
        container.travel_quotes.verify_with_provider(
            owner,
            transaction_id,
            "simulated",
        )
    )["travel_quote"]["latest_verification"]
    review = client.post(
        f"/api/v1/transactions/{transaction_id}/review",
        headers=auth,
        json={"expected_revision": created["transaction"]["revision"]},
    ).json()
    confirmed = client.post(
        f"/api/v1/transactions/{transaction_id}/review/confirm",
        headers=auth,
        json={
            "expected_revision": review["revision"],
            "terms_sha256": created["terms"]["terms_sha256"],
        },
    ).json()

    rejected = client.post(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=auth,
        json={
            "expected_revision": confirmed["transaction"]["revision"],
            "terms_sha256": created["terms"]["terms_sha256"],
            "verification_id": mismatched["id"],
            "verification_snapshot_sha256": mismatched["snapshot_sha256"],
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "travel_booking_verification_mismatch"

    fresh = _verified_reviewed_travel(
        container,
        client,
        headers,
        "tx17-stale",
    )
    with container.repository.sessions.begin() as db:
        row = db.get(TravelQuoteVerificationEvidence, fresh["evidence"]["id"])
        row.observed_at = utcnow() - timedelta(minutes=6)

    stale = client.post(
        f'/api/v1/travel-quotes/{fresh["transaction_id"]}/booking-binding',
        headers=fresh["auth"],
        json=_binding_request(fresh),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "travel_booking_verification_stale"


def test_tx17_rejects_tampered_quote_or_verification_snapshot(container, signed_client):
    enable_travel_quotes(container)
    client, headers = signed_client

    quote_value = _verified_reviewed_travel(
        container,
        client,
        headers,
        "tx17-quote-integrity",
    )
    from services.coworker.models import TravelQuoteIntent
    with container.repository.sessions.begin() as db:
        row = db.get(TravelQuoteIntent, quote_value["transaction_id"])
        tampered = dict(row.quote)
        tampered["provider_name"] = "Tampered Travel Provider"
        row.quote = tampered
    response = client.post(
        f'/api/v1/travel-quotes/{quote_value["transaction_id"]}/booking-binding',
        headers=quote_value["auth"],
        json=_binding_request(quote_value),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "travel_booking_quote_integrity"

    verification_value = _verified_reviewed_travel(
        container,
        client,
        headers,
        "tx17-verification-integrity",
    )
    with container.repository.sessions.begin() as db:
        row = db.get(
            TravelQuoteVerificationEvidence,
            verification_value["evidence"]["id"],
        )
        tampered = dict(row.snapshot)
        tampered["provider_quote_id"] = "tampered-provider-quote"
        row.snapshot = tampered
    response = client.post(
        f'/api/v1/travel-quotes/{verification_value["transaction_id"]}/booking-binding',
        headers=verification_value["auth"],
        json=_binding_request(verification_value),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "travel_booking_verification_integrity"


def test_tx17_booking_binding_is_owner_scoped_and_erased(container, signed_client):
    enable_travel_quotes(container)
    client, headers = signed_client
    value = _verified_reviewed_travel(
        container,
        client,
        headers,
        "tx17-owner",
    )
    transaction_id = value["transaction_id"]
    created = client.post(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=value["auth"],
        json=_binding_request(value),
    )
    assert created.status_code == 201
    binding_id = created.json()["id"]

    hidden = client.get(
        f"/api/v1/travel-quotes/{transaction_id}/booking-binding",
        headers=headers("tx17-other-owner"),
    )
    assert hidden.status_code == 404

    result = container.retention.erase_account(value["owner"])
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.get(TravelBookingBinding, binding_id) is None
