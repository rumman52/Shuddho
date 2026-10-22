"""Fail closed on ambiguous transaction activation evidence input.

Duplicate keys let two parsers/operators see different approved capabilities;
non-finite JSON numbers are not valid JSON and cannot be signed as evidence.
"""
from __future__ import annotations

import pytest
import httpx

from scripts import transaction_capability_activation as activation


BAD_JSON = [
    '{"schema_version":1,"schema_version":2}',
    '{"capabilities":{"restaurant_reservations":false,"restaurant_reservations":true}}',
    '{"status":"passed","status":"failed"}',
    '{"counter":NaN}',
    '{"counter":Infinity}',
    '{"counter":-Infinity}',
]


@pytest.mark.parametrize("payload", BAD_JSON)
def test_reviewed_evidence_file_rejects_duplicate_keys_and_nonfinite_values(tmp_path, payload):
    source = tmp_path / "reviewed-rollout.json"
    source.write_text(payload, encoding="utf-8")
    with pytest.raises(activation.TransactionCapabilityActivationError):
        activation.load_json(source, "reviewed rollout")


@pytest.mark.parametrize("payload", BAD_JSON)
def test_live_authority_http_response_rejects_ambiguous_json(monkeypatch, payload):
    original_client = httpx.Client

    def fixture_client(**kwargs):
        return original_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=payload.encode("utf-8"),
                    headers={"content-type": "application/json"},
                )
            ),
            **kwargs,
        )

    monkeypatch.setattr(activation.httpx, "Client", fixture_client)
    with pytest.raises(activation.TransactionCapabilityActivationError):
        activation.fetch_json(
            "https://example.invalid",
            "/api/v1/transaction-authority",
            token="not-a-secret",
            timeout_seconds=1,
        )


def test_valid_reviewed_evidence_file_is_unchanged(tmp_path):
    source = tmp_path / "reviewed-rollout.json"
    source.write_text('{"capabilities":{"restaurant_reservations":true}}', encoding="utf-8")
    assert activation.load_json(source, "reviewed rollout") == {
        "capabilities": {"restaurant_reservations": True}
    }


def test_valid_live_authority_http_response_is_unchanged(monkeypatch):
    original_client = httpx.Client

    def fixture_client(**kwargs):
        return original_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=b'{"restaurant_reservations_enabled":true}'
                )
            ),
            **kwargs,
        )

    monkeypatch.setattr(activation.httpx, "Client", fixture_client)
    assert activation.fetch_json(
        "https://example.invalid", "/api/v1/transaction-authority",
        token="not-a-secret", timeout_seconds=1
    ) == {"restaurant_reservations_enabled": True}
