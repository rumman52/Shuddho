"""TX-08 review-only travel quote domain."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import inspect, select

from action_samples import enable_actions
from test_coworker import account, container, signed_client

from services.coworker.models import ExternalAction, TravelQuoteIntent, utcnow


def enable_travel_quotes(container):
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
    container.travel_quotes.settings = settings


def flight_quote(**changes):
    now = utcnow()
    departure = (now.astimezone(ZoneInfo("Asia/Dhaka")) + timedelta(days=20)).replace(second=0, microsecond=0)
    arrival = (departure.astimezone(ZoneInfo("UTC")) + timedelta(hours=2)).astimezone(ZoneInfo("Asia/Bangkok"))
    value = {
        "travel_kind": "flight",
        "quote_source": "user_supplied",
        "provider_name": "Example Air",
        "provider_quote_id": "travel-quote-001",
        "travelers": [
            {"display_name": "Alice Example", "traveler_type": "adult"},
        ],
        "flight_segments": [
            {
                "origin_code": "DAC",
                "destination_code": "BKK",
                "departure_at": departure.isoformat(),
                "arrival_at": arrival.isoformat(),
                "origin_time_zone": "Asia/Dhaka",
                "destination_time_zone": "Asia/Bangkok",
                "marketing_carrier": "EX",
                "flight_number": "101",
            }
        ],
        "price": {
            "currency": "USD",
            "subtotal_minor": 42000,
            "tax_minor": 7500,
            "fees_minor": 500,
            "shipping_minor": 0,
            "discount_minor": 0,
            "total_minor": 50000,
        },
        "cancellation_terms": "Non-refundable after ticketing.",
        "change_terms": "Changes may require a fare difference and provider fee.",
        "quoted_at": now.isoformat(),
        "quote_expires_at": (now + timedelta(minutes=30)).isoformat(),
    }
    value.update(changes)
    return value


def lodging_quote(**changes):
    now = utcnow()
    check_in = (now.astimezone(ZoneInfo("Asia/Dhaka")) + timedelta(days=30)).replace(second=0, microsecond=0)
    check_out = check_in + timedelta(days=3)
    value = {
        "travel_kind": "lodging",
        "quote_source": "user_supplied",
        "provider_name": "Example Stay",
        "provider_quote_id": "stay-quote-001",
        "travelers": [
            {"display_name": "Alice Example", "traveler_type": "adult"},
            {"display_name": "Bob Example", "traveler_type": "adult"},
        ],
        "flight_segments": [],
        "lodging": {
            "property_id": "hotel-123",
            "property_name": "Example Hotel",
            "address": "1 Example Road",
            "check_in_at": check_in.isoformat(),
            "check_out_at": check_out.isoformat(),
            "time_zone": "Asia/Dhaka",
            "room_name": "Deluxe king",
        },
        "price": {
            "currency": "BDT",
            "subtotal_minor": 3000000,
            "tax_minor": 450000,
            "fees_minor": 50000,
            "shipping_minor": 0,
            "discount_minor": 0,
            "total_minor": 3500000,
        },
        "cancellation_terms": "Free cancellation until 24 hours before check-in.",
        "change_terms": "Date changes are subject to availability and repricing.",
        "quoted_at": now.isoformat(),
        "quote_expires_at": (now + timedelta(hours=2)).isoformat(),
    }
    value.update(changes)
    return value


def test_tx08_migration_adds_owner_scoped_quote_intents(container):
    inspector = inspect(container.repository.sessions.kw["bind"])
    assert "cw_travel_quote_intents" in set(inspector.get_table_names())
    columns = {item["name"] for item in inspector.get_columns("cw_travel_quote_intents")}
    assert {"transaction_id", "owner_id", "quote", "quote_sha256", "created_at"} <= columns


def test_tx08_api_records_exact_flight_quote_without_execution_authority(container, signed_client):
    enable_travel_quotes(container)
    client, headers = signed_client
    alice = headers("tx08-alice")
    bob = headers("tx08-bob")
    payload = flight_quote()

    response = client.post(
        "/api/v1/travel-quotes",
        headers=alice | {"Idempotency-Key": "tx08-flight-001"},
        json=payload,
    )
    assert response.status_code == 201
    assert response.headers["idempotent-replayed"] == "false"
    value = response.json()
    tx = value["transaction"]
    assert tx["transaction_kind"] == "travel_flight"
    assert tx["provider"] == "internal"
    assert tx["connection_id"] is None
    assert tx["state"] == "terms_ready"
    assert value["terms"]["currency"] == "USD"
    assert value["terms"]["total_minor"] == 50000
    assert value["travel_quote"]["provider_verified"] is False
    assert value["travel_quote"]["booking_available"] is False
    assert value["execution"]["available"] is False
    assert len(value["travel_quote"]["quote_sha256"]) == 64

    with container.repository.sessions() as db:
        assert db.scalar(select(ExternalAction).where(ExternalAction.owner_id == client.get("/api/v1/me", headers=alice).json()["account_id"])) is None

    replay = client.post(
        "/api/v1/travel-quotes",
        headers=alice | {"Idempotency-Key": "tx08-flight-001"},
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["transaction"]["id"] == tx["id"]

    hidden = client.get(f'/api/v1/travel-quotes/{tx["id"]}', headers=bob)
    assert hidden.status_code == 404

    changed = flight_quote(provider_quote_id="travel-quote-002")
    conflict = client.post(
        "/api/v1/travel-quotes",
        headers=alice | {"Idempotency-Key": "tx08-flight-001"},
        json=changed,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_tx08_exact_review_can_be_confirmed_but_still_cannot_execute(container, signed_client):
    enable_travel_quotes(container)
    client, headers = signed_client
    auth = headers("tx08-review")
    created = client.post(
        "/api/v1/travel-quotes",
        headers=auth | {"Idempotency-Key": "tx08-review-001"},
        json=lodging_quote(),
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

    assert client.post(
        f'/api/v1/travel-quotes/{tx["id"]}/book',
        headers=auth,
        json={},
    ).status_code in {404, 405}
    assert client.post(
        f'/api/v1/transactions/{tx["id"]}/execute',
        headers=auth,
        json={},
    ).status_code in {404, 405}


def test_tx08_schema_rejects_mixed_itinerary_and_expired_quote(container, signed_client):
    enable_travel_quotes(container)
    client, headers = signed_client
    auth = headers("tx08-invalid")

    mixed = flight_quote(lodging=lodging_quote()["lodging"])
    response = client.post(
        "/api/v1/travel-quotes",
        headers=auth | {"Idempotency-Key": "tx08-invalid-mixed"},
        json=mixed,
    )
    assert response.status_code == 422

    expired = flight_quote(
        quoted_at=(utcnow() - timedelta(hours=2)).isoformat(),
        quote_expires_at=(utcnow() - timedelta(hours=1)).isoformat(),
    )
    response = client.post(
        "/api/v1/travel-quotes",
        headers=auth | {"Idempotency-Key": "tx08-invalid-expired"},
        json=expired,
    )
    assert response.status_code == 422


def test_tx08_account_erasure_removes_quote_intent(container):
    enable_travel_quotes(container)
    owner = account(container, "tx08-retention")
    from services.coworker.travel_quote_schemas import TravelQuoteRequest

    surface, _ = container.travel_quotes.create(
        owner,
        TravelQuoteRequest.model_validate(lodging_quote()),
        "tx08-retention-001",
    )
    transaction_id = surface["transaction"]["id"]
    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True

    with container.repository.sessions() as db:
        assert db.scalar(
            select(TravelQuoteIntent).where(
                TravelQuoteIntent.transaction_id == transaction_id
            )
        ) is None
