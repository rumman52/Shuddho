"""Production verifier must never send its bearer token to an unsafe origin.

The CLI's --api-base-url is an operator-controlled string. A misspelled http://
address, embedded userinfo, or path/query/fragment must be rejected BEFORE
httpx.Client is created or an Authorization header can leave the process.
"""
from __future__ import annotations

import httpx
import pytest

from scripts import transaction_capability_activation as activation


@pytest.mark.parametrize(
    "untrusted_base_url",
    [
        "http://api.example.com",
        "http://127.0.0.1:8000",
        "ftp://api.example.com",
        "https://",
        "https:///missing-host",
        "https://operator:secret@api.example.com",
        "https://api.example.com/tenant",
        "https://api.example.com/%2e%2e/",
        "https://api.example.com/?token=secret",
        "https://api.example.com/#fragment",
        " https://api.example.com",
    ],
)
def test_production_verification_refuses_unsafe_origin_before_http_client(
    monkeypatch, untrusted_base_url
):
    constructed = []

    def fail_if_client_created(**kwargs):
        constructed.append(kwargs)
        raise AssertionError("unsafe origin constructed authenticated HTTP client")

    monkeypatch.setattr(activation.httpx, "Client", fail_if_client_created)
    with pytest.raises(
        activation.TransactionCapabilityActivationError,
        match="HTTPS origin",
    ):
        activation.fetch_json(
            untrusted_base_url,
            "/api/v1/runtime-manifest",
            token="production-test-secret",
            timeout_seconds=1,
        )
    assert constructed == []


def test_https_root_origin_fetches_only_requested_path_with_bearer(monkeypatch):
    client_class = httpx.Client
    requests = []

    def reply(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200, json={"schema_version": 1})

    def local_client(**kwargs):
        return client_class(transport=httpx.MockTransport(reply), **kwargs)

    monkeypatch.setattr(activation.httpx, "Client", local_client)
    result = activation.fetch_json(
        "https://api.example.com:8443/",
        "/api/v1/runtime-manifest",
        token="production-test-secret",
        timeout_seconds=5,
    )
    assert result == {"schema_version": 1}
    assert len(requests) == 1
    assert str(requests[0].url) == (
        "https://api.example.com:8443/api/v1/runtime-manifest"
    )
    assert requests[0].headers["authorization"] == "Bearer production-test-secret"


def test_redirect_is_not_followed_and_token_not_sent_to_other_host(monkeypatch):
    client_class = httpx.Client
    requests = []

    def reply(request: httpx.Request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": "https://untrusted.example/exfil"}
        )

    monkeypatch.setattr(
        activation.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(reply), **kwargs),
    )
    with pytest.raises(
        activation.TransactionCapabilityActivationError, match="HTTP 302"
    ):
        activation.fetch_json(
            "https://api.example.com",
            "/api/v1/runtime-manifest",
            token="production-test-secret",
            timeout_seconds=5,
        )
    assert len(requests) == 1
    assert requests[0].url.host == "api.example.com"
