from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.coworker.action_schemas import LinkedInSocialPublish
from services.coworker.connector_actions import ConnectorFailure
from services.coworker.linkedin_actions import (
    AUTH_URL,
    IDENTITY_SCOPE,
    POSTS_URL,
    PROFILE_URL,
    SCOPES,
    TOKEN_URL,
    LinkedInActions,
    post_body,
)


class LinkedInTransport:
    def __init__(self):
        self.requests = []
        self.scope = None
        self.post_status = 201
        self.post_id = "urn:li:share:12345"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == TOKEN_URL:
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["authorization_code"]
            assert form["client_id"] == ["linkedin-client"]
            assert form["client_secret"] == ["linkedin-secret"]
            assert form["redirect_uri"] == [
                "https://shuddho.example/oauth/linkedin/callback"
            ]
            body = {
                "access_token": "linkedin-access-token",
                "expires_in": 3600,
            }
            if self.scope is not None:
                body["scope"] = self.scope
            return httpx.Response(200, json=body)
        if url == PROFILE_URL:
            assert request.headers["authorization"] == "Bearer linkedin-access-token"
            return httpx.Response(200, json={"id": "member_123"})
        if url == POSTS_URL:
            assert request.method == "POST"
            assert request.headers["authorization"] == "Bearer linkedin-access-token"
            assert request.headers["linkedin-version"] == "202609"
            assert request.headers["x-restli-protocol-version"] == "2.0.0"
            if self.post_status != 201:
                return httpx.Response(self.post_status, json={"message": "private"})
            return httpx.Response(
                201,
                headers={"x-restli-id": self.post_id},
                content=b"",
            )
        raise AssertionError(f"unexpected endpoint: {url}")


def settings():
    return SimpleNamespace(
        linkedin_client_id="linkedin-client",
        linkedin_client_secret="linkedin-secret",
        linkedin_redirect_uri="https://shuddho.example/oauth/linkedin/callback",
        linkedin_api_version="202609",
    )


def action(text="Launch update #Shuddho (reviewed)."):
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "kind": "social_publish_linkedin",
        "preview": {
            "provider": "linkedin",
            "account": "urn:li:person:member_123",
            "payload": {
                "kind": "social_publish_linkedin",
                "text": text,
            },
        },
    }


def test_authorization_url_is_exact_confidential_web_flow():
    adapter = LinkedInActions(settings())
    state = "a" * 43
    value = urlparse(adapter.authorization_url(state, "unused", "social"))
    assert value.scheme == "https"
    assert value.netloc == "www.linkedin.com"
    assert value.path == "/oauth/v2/authorization"
    params = parse_qs(value.query)
    assert params["state"] == [state]
    assert params["redirect_uri"] == [
        "https://shuddho.example/oauth/linkedin/callback"
    ]
    assert set(params["scope"][0].split()) == {
        IDENTITY_SCOPE,
        SCOPES["social"],
    }
    assert "code_challenge" not in params


def test_exchange_accepts_omitted_or_comma_delimited_scope_and_binds_identity():
    transport = LinkedInTransport()
    adapter = LinkedInActions(settings(), httpx.MockTransport(transport))
    token = asyncio.run(adapter.exchange("code", "unused"))
    assert token["scope"] == f"{IDENTITY_SCOPE} {SCOPES['social']}"
    profile = asyncio.run(adapter.profile(token["access_token"]))
    assert profile == {
        "sub": "member_123",
        "email": "urn:li:person:member_123",
    }

    transport.scope = f"{IDENTITY_SCOPE},{SCOPES['social']}"
    token = asyncio.run(adapter.exchange("code", "unused"))
    assert token["scope"].split() == [IDENTITY_SCOPE, SCOPES["social"]]


def test_exchange_rejects_provider_scope_downgrade():
    transport = LinkedInTransport()
    transport.scope = IDENTITY_SCOPE
    adapter = LinkedInActions(settings(), httpx.MockTransport(transport))
    with pytest.raises(ConnectorFailure) as failure:
        asyncio.run(adapter.exchange("code", "unused"))
    assert failure.value.code == "oauth_scope_missing"
    assert failure.value.definitive


def test_persisted_access_token_has_expiry_and_is_reused_only_while_valid():
    adapter = LinkedInActions(settings())
    credentials = adapter.persisted_credentials({
        "access_token": "linkedin-access-token",
        "expires_in": 3600,
    })
    assert set(credentials) == {"access_token", "expires_at"}
    token = asyncio.run(adapter.access_from_credentials(credentials, "social"))
    assert token == {"access_token": "linkedin-access-token"}

    with pytest.raises(ConnectorFailure) as failure:
        asyncio.run(adapter.access_from_credentials(
            {"access_token": "linkedin-access-token", "expires_at": "2000-01-01T00:00:00+00:00"},
            "social",
        ))
    assert failure.value.code == "connection_authorization"
    assert failure.value.definitive


def test_post_body_is_personal_public_text_only_and_deterministically_escaped():
    value = post_body(action("Hello (team) #Shuddho"))
    assert value["author"] == "urn:li:person:member_123"
    assert value["visibility"] == "PUBLIC"
    assert value["lifecycleState"] == "PUBLISHED"
    assert value["distribution"] == {
        "feedDistribution": "MAIN_FEED",
        "targetEntities": [],
        "thirdPartyDistributionChannels": [],
    }
    assert value["commentary"] == r"Hello \(team\) #Shuddho"
    assert "content" not in value


def test_execute_requires_confirmed_linkedin_post_receipt():
    transport = LinkedInTransport()
    adapter = LinkedInActions(settings(), httpx.MockTransport(transport))
    receipt = asyncio.run(
        adapter.execute(action(), "linkedin-access-token")
    )
    assert receipt["provider"] == "linkedin"
    assert receipt["provider_id"] == "urn:li:share:12345"
    assert receipt["status"] == "post_published"
    assert receipt["visibility"] == "PUBLIC"
    sent = json.loads(transport.requests[-1].content)
    assert sent["author"] == "urn:li:person:member_123"

    transport.post_id = "invalid"
    with pytest.raises(ConnectorFailure) as failure:
        asyncio.run(adapter.execute(action(), "linkedin-access-token"))
    assert failure.value.code == "provider_receipt_invalid"


def test_uncertain_provider_failure_is_not_definitive_or_reconciled():
    def fail(_request):
        raise httpx.ReadTimeout("lost response")

    adapter = LinkedInActions(settings(), httpx.MockTransport(fail))
    with pytest.raises(ConnectorFailure) as failure:
        asyncio.run(adapter.execute(action(), "linkedin-access-token"))
    assert not failure.value.definitive
    assert asyncio.run(adapter.reconcile(action(), "linkedin-access-token")) is None


def test_social_payload_is_plain_text_only():
    assert LinkedInSocialPublish(
        kind="social_publish_linkedin",
        text="বাংলা launch update",
    ).text == "বাংলা launch update"
    with pytest.raises(Exception):
        LinkedInSocialPublish(kind="social_publish_linkedin", text="   ")
    with pytest.raises(Exception):
        LinkedInSocialPublish(
            kind="social_publish_linkedin",
            text="x" * 3001,
        )
