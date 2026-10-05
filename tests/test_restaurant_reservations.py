"""TX-06 bounded no-payment OpenTable restaurant reservations."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import inspect, select

from action_samples import enable_actions
from test_coworker import account, container

from services.coworker.action_registry import action_spec, stable_digest
from services.coworker.action_schemas import ActionPrepare
from services.coworker.errors import CoworkerError
from services.coworker.models import RestaurantReservationIntent, utcnow
from services.coworker.permission_gateway import PermissionGateway
from services.coworker.credential_broker import CredentialBroker
from services.coworker.opentable_actions import (
    API_HOSTS,
    OAUTH_HOSTS,
    OpenTableActions,
    OpenTableFailure,
    local_provider_time,
)
from services.coworker.restaurant_reservation_schemas import (
    RestaurantReservationPrepare,
    RestaurantReservationRequest,
)
from services.coworker.transaction_schemas import TransactionTermsDraft


RID = 123456


def test_opentable_provider_local_time_accepts_provider_naive_values_but_not_user_payloads():
    assert local_provider_time("2026-10-08T19:00:00") == "2026-10-08T19:00"
    assert local_provider_time("2026-10-08T19:00:00+06:00", require_offset=True) == "2026-10-08T19:00"
    with pytest.raises(OpenTableFailure):
        local_provider_time("2026-10-08T19:00:00", require_offset=True)


class SimulatedOpenTable:
    def __init__(self):
        self.requests = []
        self.bookings = []
        self.available = True
        self.cancellation_policy = None
        self.booking_error = None
        self.lose_booking_reply = False
        self.confirmation_number = 741852

    def transport(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/v2/oauth/token":
            assert request.method == "POST"
            assert request.url.params["grant_type"] == "client_credentials"
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(
                200,
                json={
                    "access_token": "opentable-test-access",
                    "token_type": "Bearer",
                    "scope": "DEFAULT",
                },
            )

        if path == f"/v2/availability/{RID}":
            assert request.method == "GET"
            assert request.headers["authorization"] == "Bearer opentable-test-access"
            assert request.url.params["include_credit_card_results"] == "false"
            assert request.url.params["include_experiences"] == "false"
            assert request.url.params["forward_minutes"] == "0"
            assert request.url.params["backward_minutes"] == "0"
            time = request.url.params["start_date_time"]
            values = []
            if self.available:
                values = [{
                    "time": time + ":00",
                    "availability_types": [{
                        "type": "Standard",
                        "cancellationPolicy": self.cancellation_policy or {},
                        "diningArea": [{
                            "id": 55,
                            "name": "Main Dining",
                            "attributes": ["default"],
                            "environment": "Indoor",
                        }],
                    }],
                }]
            return httpx.Response(
                200,
                json={
                    "rid": RID,
                    "party_size": int(request.url.params["party_size"]),
                    "times_available": values,
                },
                headers={"OT-RequestId": "availability-request"},
            )

        if path == f"/v2/booking/{RID}/reservations":
            assert request.method == "POST"
            assert request.headers["authorization"] == "Bearer opentable-test-access"
            request_id = request.headers.get("x-request-id")
            assert request_id
            body = json.loads(request.content)
            assert "credit_card" not in body
            assert "experience" not in body
            assert "reservation_token" not in body
            assert body["restaurant_email_marketing_opt_in"] == "false"
            self.bookings.append({"request_id": request_id, "body": body})
            if self.lose_booking_reply:
                raise httpx.ReadTimeout("lost provider reply after booking")
            if self.booking_error == "payment":
                return httpx.Response(
                    400,
                    json={"errors": [{"message": "CreditCardRequired"}]},
                )
            if self.booking_error == "overlap":
                return httpx.Response(
                    409,
                    json={"errors": [{"message": "overlapping reservation"}]},
                )
            return httpx.Response(
                200,
                json={
                    "confirmation_number": self.confirmation_number,
                    "date_time": body["date_time"] + ":00",
                    "party_size": body["party_size"],
                    "message": "Standard reservation policy",
                    "manage_reservation_url": "https://www.opentable.com/booking/manage",
                },
                headers={"OT-RequestId": "booking-request"},
            )

        raise AssertionError(f"Unexpected OpenTable endpoint: {request.method} {request.url}")


def reservation_request(**changes) -> RestaurantReservationRequest:
    start = (utcnow() + timedelta(days=3)).replace(
        hour=19,
        minute=0,
        second=0,
        microsecond=0,
    )
    value = {
        "restaurant_id": RID,
        "restaurant_name": "Example Bistro",
        "date_time": start.isoformat(),
        "time_zone": "UTC",
        "party_size": 2,
        "reservation_attribute": "default",
        "dining_area_id": 55,
        "environment": "Indoor",
        "guest_first_name": "Alice",
        "guest_last_name": "Example",
        "guest_email": "alice@example.test",
        "guest_phone_number": "+14155550123",
        "guest_phone_country_code": "US",
        "special_request": "Window table if available",
        "opentable_terms_accepted": True,
        "opentable_terms_version": "2026-07-22",
        "guest_contact_sharing_approved": True,
    }
    value.update(changes)
    return RestaurantReservationRequest.model_validate(value)


def enable_restaurants(container):
    enable_actions(container)
    # enable_actions replaces container.actions with a simulated ActionService.
    # Rebind the reservation service to that service's ActionRepository so its
    # service-connection path observes the enabled test settings and shared DB.
    container.restaurant_reservations.actions = container.actions.repo
    settings = replace(
        container.settings,
        connector_trust_boundary_enabled=True,
        personal_transactions_enabled=True,
        restaurant_reservations_enabled=True,
        opentable_environment="sandbox",
        opentable_client_id="opentable-test-client",
        opentable_client_secret="opentable-test-secret",
        transaction_operations=frozenset({
            "opentable:restaurant_reservation_create",
        }),
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.transactions.settings = settings
    container.restaurant_reservations.settings = settings

    simulated = SimulatedOpenTable()
    adapter = OpenTableActions(settings, httpx.MockTransport(simulated.transport))
    container.actions.providers["opentable"] = adapter

    # The connector trust boundary is enabled above. enable_actions() replaces
    # the production-wired ActionService with a lightweight simulated service,
    # so rebuild the gateway/broker against that exact ActionRepository and the
    # full provider map before exercising worker execution.
    gateway = PermissionGateway(container.repository.sessions, settings)
    broker = CredentialBroker(
        container.actions.repo,
        gateway,
        container.actions.providers,
    )
    container.permissions = gateway
    container.credentials = broker
    container.actions.permission_gateway = gateway
    container.actions.credential_broker = broker
    container.restaurant_reservations.adapter = adapter
    return simulated


async def create_review(container, owner, key="tx06-create", **changes):
    return await container.restaurant_reservations.create(
        owner,
        reservation_request(**changes),
        key,
    )


def confirm_exact_review(container, owner, surface):
    transaction = surface["transaction"]
    terms = surface["terms"]
    review = container.transactions.start_review(
        owner,
        transaction["id"],
        transaction["revision"],
    )
    confirmed = container.transactions.confirm_review(
        owner,
        transaction["id"],
        review["revision"],
        terms["terms_sha256"],
    )
    return confirmed


def prepare_bound_action(container, owner, surface):
    confirmed = confirm_exact_review(container, owner, surface)
    return container.restaurant_reservations.prepare_action(
        owner,
        surface["transaction"]["id"],
        RestaurantReservationPrepare(
            expected_revision=confirmed["transaction"]["revision"],
            terms_sha256=surface["terms"]["terms_sha256"],
        ),
    )


def test_tx06_registry_and_config_are_fail_closed(container):
    spec = action_spec("restaurant_reservation_create", "opentable")
    assert spec.capability == "restaurant_reservation"
    assert spec.reconcile_supported is False
    assert spec.transaction is not None
    assert spec.transaction.requires_transaction_binding is True
    assert spec.transaction.preview_manifest()["transaction_binding"] == "required"

    enable_actions(container)
    with pytest.raises(ValueError, match="OpenTable client credentials"):
        replace(
            container.settings,
            connector_trust_boundary_enabled=True,
            personal_transactions_enabled=True,
            restaurant_reservations_enabled=True,
            transaction_operations=frozenset({
                "opentable:restaurant_reservation_create",
            }),
        ).validate()


def test_tx06_migration_adds_immutable_reservation_intents(container):
    inspector = inspect(container.repository.sessions.kw["bind"])
    assert "cw_restaurant_reservation_intents" in set(inspector.get_table_names())
    columns = {
        value["name"]
        for value in inspector.get_columns("cw_restaurant_reservation_intents")
    }
    assert {
        "transaction_id",
        "owner_id",
        "request",
        "request_sha256",
        "availability",
        "availability_sha256",
        "observed_at",
    } <= columns


def test_create_checks_exact_no_payment_availability_without_booking(container):
    simulated = enable_restaurants(container)
    owner = account(container, "tx06-create")
    surface, created = asyncio.run(create_review(container, owner))

    assert created is True
    transaction = surface["transaction"]
    assert transaction["transaction_kind"] == "restaurant_reservation"
    assert transaction["provider"] == "opentable"
    assert transaction["state"] == "terms_ready"
    assert transaction["currency"] == "XXX"
    assert surface["terms"]["total_minor"] == 0
    assert surface["terms"]["currency"] == "XXX"
    assert surface["reservation"]["availability"]["payment_required"] is False
    assert len(surface["reservation"]["availability_sha256"]) == 64
    assert simulated.bookings == []

    replay, replay_created = asyncio.run(create_review(container, owner))
    assert replay_created is False
    assert replay["transaction"]["id"] == transaction["id"]
    availability_calls = [
        item for item in simulated.requests
        if item.method == "GET" and "/v2/availability/" in item.url.path
    ]
    assert len(availability_calls) == 1

    with pytest.raises(CoworkerError) as conflict:
        asyncio.run(create_review(container, owner, party_size=3))
    assert conflict.value.code == "idempotency_conflict"


def test_provider_managed_terms_cannot_be_rewritten_through_generic_boundary(container):
    enable_restaurants(container)
    owner = account(container, "tx06-managed-terms")
    surface, _ = asyncio.run(create_review(container, owner, key="tx06-managed-terms"))

    with pytest.raises(CoworkerError) as blocked:
        container.transactions.set_terms(
            owner,
            surface["transaction"]["id"],
            surface["transaction"]["revision"],
            TransactionTermsDraft.model_validate({
                "terms": [{"name": "Party size", "value": "20"}],
                "price": {
                    "currency": "XXX",
                    "subtotal_minor": 0,
                    "tax_minor": 0,
                    "fees_minor": 0,
                    "shipping_minor": 0,
                    "discount_minor": 0,
                    "total_minor": 0,
                },
                "provider_quote_id": "changed",
                "quoted_at": utcnow(),
                "quote_expires_at": utcnow() + timedelta(minutes=5),
            }),
        )
    assert blocked.value.code == "transaction_terms_provider_managed"


def test_unbound_restaurant_action_is_rejected(container):
    enable_restaurants(container)
    owner = account(container, "tx06-unbound")
    surface, _ = asyncio.run(create_review(container, owner, key="tx06-unbound"))
    intent = surface["reservation"]

    with pytest.raises(CoworkerError) as blocked:
        container.actions.repo.prepare(
            owner,
            ActionPrepare.model_validate({
                "connection_id": surface["transaction"]["connection_id"],
                "payload": {
                    "kind": "restaurant_reservation_create",
                    **intent["request"],
                    "availability_sha256": intent["availability_sha256"],
                    "availability_observed_at": intent["observed_at"],
                    "no_payment_required": True,
                },
            }),
            "tx06-unbound-action",
        )
    assert blocked.value.code == "transaction_binding_required"


def test_review_prepare_approve_then_worker_books_exactly_once(container):
    simulated = enable_restaurants(container)
    owner = account(container, "tx06-success")
    surface, _ = asyncio.run(create_review(container, owner, key="tx06-success"))

    prepared = prepare_bound_action(container, owner, surface)
    action = prepared["action"]
    assert action["state"] == "awaiting_approval"
    assert action["preview"]["version"] == 7
    assert action["preview"]["transaction_binding"]["transaction_id"] == surface["transaction"]["id"]
    assert action["preview"]["payload"]["no_payment_required"] is True
    assert simulated.bookings == []

    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    assert approved["state"] == "queued"
    assert simulated.bookings == []

    asyncio.run(container.actions.execute(action["id"]))
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "succeeded"
    assert result["receipt"]["provider"] == "opentable"
    assert result["receipt"]["status"] == "reservation_confirmed"
    assert result["receipt"]["payment_required"] is False
    assert result["receipt"]["confirmation_number"] == simulated.confirmation_number
    assert len(simulated.bookings) == 1
    assert simulated.bookings[0]["request_id"] == action["id"]

    asyncio.run(container.actions.execute(action["id"]))
    assert len(simulated.bookings) == 1

    projected = container.transactions.sync_external_action(
        owner,
        surface["transaction"]["id"],
    )
    assert projected["transaction"]["state"] == "confirmed"
    assert projected["evidence"]["receipt"]["confirmation_number"] == simulated.confirmation_number


def test_fresh_availability_drift_stops_booking_before_post(container):
    simulated = enable_restaurants(container)
    owner = account(container, "tx06-drift")
    surface, _ = asyncio.run(create_review(container, owner, key="tx06-drift"))
    prepared = prepare_bound_action(container, owner, surface)
    action = prepared["action"]
    container.actions.repo.approve(owner, action["id"], action["preview_hash"])

    simulated.available = False
    asyncio.run(container.actions.execute(action["id"]))
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "failed"
    assert result["error_code"] in {
        "reservation_not_available",
        "reservation_availability_changed",
    }
    assert simulated.bookings == []


def test_provider_card_requirement_fails_without_payment_escalation(container):
    simulated = enable_restaurants(container)
    owner = account(container, "tx06-payment")
    surface, _ = asyncio.run(create_review(container, owner, key="tx06-payment"))
    prepared = prepare_bound_action(container, owner, surface)
    action = prepared["action"]
    container.actions.repo.approve(owner, action["id"], action["preview_hash"])

    simulated.booking_error = "payment"
    asyncio.run(container.actions.execute(action["id"]))
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "failed"
    assert result["error_code"] == "reservation_payment_required"
    assert len(simulated.bookings) == 1
    assert "credit_card" not in simulated.bookings[0]["body"]


def test_lost_booking_reply_is_outcome_unknown_and_never_posts_twice(container):
    simulated = enable_restaurants(container)
    owner = account(container, "tx06-unknown")
    surface, _ = asyncio.run(create_review(container, owner, key="tx06-unknown"))
    prepared = prepare_bound_action(container, owner, surface)
    action = prepared["action"]
    container.actions.repo.approve(owner, action["id"], action["preview_hash"])

    simulated.lose_booking_reply = True
    asyncio.run(container.actions.execute(action["id"]))
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "outcome_unknown"
    assert len(simulated.bookings) == 1

    asyncio.run(container.actions.execute(action["id"]))
    assert len(simulated.bookings) == 1
    still_unknown = container.actions.repo.get(owner, action["id"])
    assert still_unknown["state"] == "outcome_unknown"

    projected = container.transactions.sync_external_action(
        owner,
        surface["transaction"]["id"],
    )
    assert projected["transaction"]["state"] == "outcome_unknown"
    assert projected["evidence"]["receipt"] is None


def test_owner_isolation_and_account_erasure_remove_intent(container):
    enable_restaurants(container)
    owner = account(container, "tx06-owner")
    other = account(container, "tx06-other")
    surface, _ = asyncio.run(create_review(container, owner, key="tx06-owner"))
    transaction_id = surface["transaction"]["id"]

    with pytest.raises(CoworkerError) as hidden:
        container.restaurant_reservations.get(other, transaction_id)
    assert hidden.value.code == "not_found"

    container.transactions.transition(
        owner,
        transaction_id,
        surface["transaction"]["revision"],
        "cancelled",
    )
    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.scalar(
            select(RestaurantReservationIntent).where(
                RestaurantReservationIntent.owner_id == owner
            )
        ) is None
