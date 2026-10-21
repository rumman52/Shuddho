"""TX-06: OpenTable availability must be canonical before any booking POST.

All provider responses are simulated locally; no booking or payment is sent.
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
        "party_size": 2,
        "date_time": "2026-12-01T19:00:00+06:00",
        "reservation_attribute": "default",
        "dining_area_id": 55,
        "environment": "Indoor",
    }


def _provider_reply() -> dict:
    return {
        "rid": 123456,
        "party_size": 2,
        "times_available": [
            {
                "time": "2026-12-01T19:00:00",
                "availability_types": [
                    {
                        "type": "Standard",
                        "cancellationPolicy": None,
                        "diningArea": [
                            {
                                "id": 55,
                                "environment": "Indoor",
                                "attributes": ["default"],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _availability(monkeypatch, reply: dict) -> dict:
    adapter = OpenTableActions(SimpleNamespace(opentable_environment="sandbox"))
    requests = []

    async def provider_request(method, url, **kwargs):
        assert method == "GET"
        assert url.endswith("/v2/availability/123456")
        requests.append(kwargs["params"])
        return 200, reply, httpx.Headers()

    monkeypatch.setattr(adapter, "_request", provider_request)
    try:
        return asyncio.run(adapter.availability(_payload(), "sandbox-test-token"))
    finally:
        assert len(requests) == 1


@pytest.mark.parametrize(
    ("field", "uncanonical"),
    [
        ("rid", 123456.0),
        ("rid", "123456"),
        ("party_size", 2.0),
        ("party_size", "2"),
    ],
)
def test_availability_rejects_noncanonical_provider_identity(
    monkeypatch, field, uncanonical
):
    with pytest.raises(OpenTableFailure) as failure:
        _availability(
            monkeypatch,
            {**_provider_reply(), field: uncanonical},
        )
    assert failure.value.code == "provider_response_invalid"
    assert failure.value.definitive is True


def test_availability_rejects_noncanonical_dining_area_id(monkeypatch):
    reply = _provider_reply()
    reply["times_available"][0]["availability_types"][0]["diningArea"][0]["id"] = 55.0
    with pytest.raises(OpenTableFailure) as failure:
        _availability(monkeypatch, reply)
    assert failure.value.code == "reservation_not_available"
    assert failure.value.definitive is True


def test_availability_accepts_exact_integer_provider_values(monkeypatch):
    result = _availability(monkeypatch, _provider_reply())
    assert result["selection"]["restaurant_id"] == 123456
    assert result["selection"]["party_size"] == 2
    assert result["selection"]["dining_area_id"] == 55
    assert result["selection"]["payment_required"] is False


@pytest.mark.parametrize(
    ("scope", "field", "value", "expected_code"),
    [
        ("response", "payment_required", True, "reservation_payment_required"),
        ("response", "paymentRequired", 1, "reservation_payment_required"),
        ("response", "payment_required", "false", "reservation_payment_required"),
        ("response", "payment", {}, "reservation_payment_required"),
        ("slot", "payment_required", True, "reservation_not_available"),
        ("slot", "paymentRequired", "false", "reservation_not_available"),
        ("slot", "payment", {"deposit": 100}, "reservation_not_available"),
    ],
)
def test_availability_rejects_explicit_payment_requirements(
    monkeypatch, scope, field, value, expected_code
):
    """Paid inventory must not be transformed into a no-payment selection."""
    response = _provider_reply()
    target = (
        response
        if scope == "response"
        else response["times_available"][0]["availability_types"][0]
    )
    target[field] = value
    with pytest.raises(OpenTableFailure) as failure:
        _availability(monkeypatch, response)
    assert failure.value.code == expected_code
    assert failure.value.definitive is True


def test_availability_accepts_explicitly_no_payment_inventory(monkeypatch):
    response = _provider_reply()
    response["payment_required"] = False
    response["payment"] = None
    slot = response["times_available"][0]["availability_types"][0]
    slot["paymentRequired"] = False
    slot["payment"] = None
    result = _availability(monkeypatch, response)
    assert result["selection"]["payment_required"] is False


@pytest.mark.parametrize(
    ("field", "required"),
    [
        ("payment_required", True),
        ("paymentRequired", "false"),
        ("payment", {"deposit": 25}),
    ],
)
def test_availability_rejects_paid_time_slot_before_selecting_standard_type(
    monkeypatch, field, required
):
    """A slot-level payment signal must not be erased by a Standard type."""
    reply = _provider_reply()
    reply["times_available"][0][field] = required
    with pytest.raises(OpenTableFailure) as failure:
        _availability(monkeypatch, reply)
    assert failure.value.code == "reservation_not_available"
    assert failure.value.definitive is True


def test_availability_accepts_explicit_free_time_slot(monkeypatch):
    reply = _provider_reply()
    slot = reply["times_available"][0]
    slot["payment_required"] = False
    slot["paymentRequired"] = False
    slot["payment"] = None
    result = _availability(monkeypatch, reply)
    assert result["selection"]["availability_type"] == "Standard"
    assert result["selection"]["payment_required"] is False

@pytest.mark.parametrize(
    "attributes",
    [
        None,
        "default",
        123,
        {"default": True},
        ["default", 7],
        [],
        ["bar"],
    ],
)
def test_availability_rejects_unverified_dining_area_attributes(
    monkeypatch, attributes
):
    """A chosen dining area must explicitly support the approved seating."""
    reply = _provider_reply()
    area = reply["times_available"][0]["availability_types"][0]["diningArea"][0]
    area["attributes"] = attributes
    with pytest.raises(OpenTableFailure) as failure:
        _availability(monkeypatch, reply)
    assert failure.value.code == "reservation_not_available"
    assert failure.value.definitive is True


def test_availability_rejects_missing_dining_area_attributes(monkeypatch):
    reply = _provider_reply()
    area = reply["times_available"][0]["availability_types"][0]["diningArea"][0]
    area.pop("attributes")
    with pytest.raises(OpenTableFailure) as failure:
        _availability(monkeypatch, reply)
    assert failure.value.code == "reservation_not_available"
    assert failure.value.definitive is True


def test_availability_accepts_explicit_matching_dining_area_attribute(monkeypatch):
    reply = _provider_reply()
    area = reply["times_available"][0]["availability_types"][0]["diningArea"][0]
    area["attributes"] = ["bar", "default"]
    result = _availability(monkeypatch, reply)
    assert result["selection"]["dining_area_id"] == 55
    assert result["selection"]["reservation_attribute"] == "default"


def test_availability_cannot_borrow_seating_proof_from_another_area(monkeypatch):
    reply = _provider_reply()
    areas = reply["times_available"][0]["availability_types"][0]["diningArea"]
    areas[0]["attributes"] = ["bar"]
    areas.append({
        "id": 56,
        "environment": "Indoor",
        "attributes": ["default"],
    })
    with pytest.raises(OpenTableFailure) as failure:
        _availability(monkeypatch, reply)
    assert failure.value.code == "reservation_not_available"
    assert failure.value.definitive is True
