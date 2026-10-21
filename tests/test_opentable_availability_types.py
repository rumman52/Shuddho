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
