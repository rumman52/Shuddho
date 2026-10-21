"""TX-06 provider confirmation cannot succeed on malformed or contradictory IDs.

The fake transport never reaches OpenTable: the tests exercise the actual
provider adapter receipt boundary without a live reservation or payment.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from services.coworker.opentable_actions import OpenTableActions, OpenTableFailure


def _payload() -> dict:
    return {
        "restaurant_id": 123456,
        "restaurant_name": "Example Bistro",
        "date_time": "2026-12-01T19:00:00+06:00",
        "time_zone": "Asia/Dhaka",
        "party_size": 2,
        "reservation_attribute": "default",
        "dining_area_id": None,
        "environment": None,
        "guest_first_name": "Test",
        "guest_last_name": "Guest",
        "guest_email": "guest@example.invalid",
        "guest_phone_number": "5550100",
        "guest_phone_country_code": "+1",
        "special_request": "",
        "availability_sha256": "reviewed-availability",
    }


def _execute_with_provider_reply(monkeypatch, reply: dict) -> dict:
    adapter = OpenTableActions(SimpleNamespace(opentable_environment="sandbox"))
    payload = _payload()
    writes = []

    async def verified_availability(_payload, _access_token):
        return {"availability_sha256": "reviewed-availability"}

    async def provider_request(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/v2/booking/123456/reservations")
        writes.append(kwargs["headers"]["X-Request-Id"])
        return 201, reply, httpx.Headers()

    monkeypatch.setattr(adapter, "availability", verified_availability)
    monkeypatch.setattr(adapter, "_request", provider_request)
    action = {"id": "immutable-action-123", "preview": {"payload": payload}}
    try:
        return asyncio.run(adapter.execute(action, "sandbox-test-token"))
    finally:
        # Only the single already-approved provider mutation may be attempted.
        assert writes == ["immutable-action-123"]


def _valid_reply() -> dict:
    return {
        "confirmation_number": 741852,
        "party_size": 2,
        "date_time": "2026-12-01T19:00:00",
        "post_booking_required_action": None,
        "payment": None,
    }


@pytest.mark.parametrize("confirmation", [0, -1, True, False])
def test_success_response_without_positive_integer_confirmation_is_uncertain(
    monkeypatch, confirmation
):
    with pytest.raises(OpenTableFailure) as failure:
        _execute_with_provider_reply(
            monkeypatch, {**_valid_reply(), "confirmation_number": confirmation}
        )
    assert failure.value.code == "provider_receipt_invalid"
    assert failure.value.definitive is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rid", 999999),
        ("restaurant_id", 999999),
        ("rid", True),
        ("restaurant_id", "123456"),
    ],
)
def test_provider_restaurant_identity_cannot_contradict_approved_restaurant(
    monkeypatch, field, value
):
    with pytest.raises(OpenTableFailure) as failure:
        _execute_with_provider_reply(monkeypatch, {**_valid_reply(), field: value})
    assert failure.value.code == "provider_receipt_invalid"
    assert failure.value.definitive is False


@pytest.mark.parametrize(
    "extra",
    [{}, {"rid": 123456}, {"restaurant_id": 123456}],
)
def test_matching_or_omitted_optional_provider_restaurant_id_is_accepted(
    monkeypatch, extra
):
    receipt = _execute_with_provider_reply(monkeypatch, {**_valid_reply(), **extra})
    assert receipt["status"] == "reservation_confirmed"
    assert receipt["confirmation_number"] == 741852
    assert receipt["restaurant_id"] == 123456
