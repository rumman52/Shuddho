"""Microsoft Graph adapter through the shared consequential-action boundary."""
import asyncio
import base64
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from test_coworker import account, container, signed_client
from action_samples import action_request
from services.coworker.action_repository import ActionRepository
from services.coworker.action_schemas import OAuthFinish, OAuthStart
from services.coworker.actions import ActionService
from services.coworker.errors import CoworkerError
from services.coworker.google_actions import GoogleActions
from services.coworker.microsoft_actions import (
    EVENTS_URL,
    ME_URL,
    MicrosoftActions,
    SCOPES,
    SEND_URL,
    _token_url,
    event_body,
)


class SimulatedMicrosoft:
    def __init__(self, settings):
        self.settings = settings
        self.requests = []
        self.sent = []
        self.events = {}
        self.lose_reply = False
        self.reject = False
        self.profile_email = "alice@example.test"

    def transport(self, request):
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        if url == _token_url(self.settings):
            form = parse_qs(request.content.decode())
            if form.get("grant_type") == ["authorization_code"]:
                assert form.get("code_verifier")
                assert form.get("redirect_uri") == [
                    self.settings.microsoft_redirect_uri
                ]
            scope = form.get("scope", [
                "openid offline_access User.Read Mail.Send Calendars.ReadWrite"
            ])[0]
            return httpx.Response(200, json={
                "token_type": "Bearer",
                "access_token": "simulated-ms-access",
                "refresh_token": "simulated-ms-refresh",
                "scope": scope,
            })
        if url == ME_URL:
            assert request.url.params.get("$select") == "id,mail,userPrincipalName"
            return httpx.Response(200, json={
                "id": "microsoft-subject-1",
                "mail": self.profile_email,
                "userPrincipalName": self.profile_email,
            })
        if request.method == "POST" and url == SEND_URL:
            if self.reject:
                return httpx.Response(
                    403,
                    json={"error": {"message": "private provider detail"}},
                )
            self.sent.append(json.loads(request.content))
            if self.lose_reply:
                raise httpx.ReadTimeout(
                    "simulated interruption after acceptance"
                )
            return httpx.Response(202)
        if request.method == "POST" and url == EVENTS_URL:
            if self.reject:
                return httpx.Response(403, json={"error": {}})
            body = json.loads(request.content)
            provider_id = "event-" + str(len(self.events) + 1)
            result = body | {
                "id": provider_id,
                "isCancelled": False,
            }
            self.events[provider_id] = result
            if self.lose_reply:
                raise httpx.ReadTimeout(
                    "simulated interruption after acceptance"
                )
            return httpx.Response(201, json=result)
        raise AssertionError("Unexpected Microsoft endpoint: " + url)


def enable_microsoft(container):
    settings = replace(
        container.settings,
        actions_enabled=True,
        google_client_id="google-client",
        google_client_secret="google-secret",
        google_redirect_uri="http://127.0.0.1:5173/oauth/google/callback",
        microsoft_actions_enabled=True,
        microsoft_client_id="microsoft-client",
        microsoft_client_secret="microsoft-secret",
        microsoft_redirect_uri=(
            "http://127.0.0.1:5173/oauth/microsoft/callback"
        ),
        microsoft_tenant="organizations",
        connector_encryption_key=base64.urlsafe_b64encode(
            b"\x22" * 32
        ).decode(),
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    simulated = SimulatedMicrosoft(settings)
    microsoft = MicrosoftActions(
        settings,
        httpx.MockTransport(simulated.transport),
    )
    container.actions = ActionService(
        ActionRepository(container.repository.sessions, settings),
        {
            "google": GoogleActions(settings),
            "microsoft": microsoft,
        },
    )
    return simulated


async def connect_microsoft(container, owner, capability="email"):
    start = await container.actions.connect(
        owner,
        OAuthStart(capability=capability),
        "microsoft",
    )
    return await container.actions.finish_connect(
        owner,
        OAuthFinish(
            state=start["state"],
            code="simulated-ms-code",
        ),
        "microsoft",
    )


def test_microsoft_oauth_pkce_scopes_and_provider_binding(container):
    simulated = enable_microsoft(container)
    owner = account(container)
    start = asyncio.run(container.actions.connect(
        owner,
        OAuthStart(capability="email"),
        "microsoft",
    ))
    url = urlparse(start["authorization_url"])
    params = parse_qs(url.query)
    assert url.hostname == "login.microsoftonline.com"
    assert "/organizations/oauth2/v2.0/authorize" == url.path
    assert params["code_challenge_method"] == ["S256"]
    assert "offline_access" in params["scope"][0]
    assert "User.Read" in params["scope"][0]
    assert SCOPES["email"] in params["scope"][0]

    with pytest.raises(CoworkerError, match="different provider"):
        asyncio.run(container.actions.finish_connect(
            owner,
            OAuthFinish(state=start["state"], code="wrong-provider"),
            "google",
        ))

    # The wrong-provider callback consumes the one-time state by design.
    start = asyncio.run(container.actions.connect(
        owner,
        OAuthStart(capability="email"),
        "microsoft",
    ))
    connection = asyncio.run(container.actions.finish_connect(
        owner,
        OAuthFinish(state=start["state"], code="ok"),
        "microsoft",
    ))
    assert connection["provider"] == "microsoft"
    assert connection["email"] == "alice@example.test"
    assert all(
        "simulated-ms-refresh" not in json.dumps(item)
        for item in [connection, container.actions.repo.connections(owner)]
    )
    assert simulated.requests


@pytest.mark.parametrize(
    ("capability", "kind"),
    [("email", "email_send"), ("calendar", "calendar_create")],
)
def test_microsoft_actions_use_shared_approval_boundary(
    container,
    capability,
    kind,
):
    simulated = enable_microsoft(container)
    owner = account(container)
    connection = asyncio.run(
        connect_microsoft(container, owner, capability)
    )
    request = action_request(connection, kind)
    action = container.actions.repo.prepare(
        owner,
        request,
        "ms-" + str(uuid4()),
    )
    assert action["preview"]["provider"] == "microsoft"
    assert action["preview"]["version"] == 2
    assert (
        action["preview"]["approval_scope"]["provider"]
        == "microsoft"
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    asyncio.run(container.actions.execute(approved["id"]))
    result = container.actions.repo.get(owner, approved["id"])
    assert result["state"] == "succeeded"
    assert result["receipt"]["provider"] == "microsoft"
    if capability == "email":
        assert len(simulated.sent) == 1
        body = simulated.sent[0]["message"]
        assert body["subject"] == action["preview"]["payload"]["subject"]
        assert body["body"]["contentType"] == "Text"
        assert simulated.sent[0]["saveToSentItems"] is True
    else:
        assert len(simulated.events) == 1
        sent = next(iter(simulated.events.values()))
        expected = event_body(approved)
        assert sent["transactionId"] == expected["transactionId"]
        assert sent["isReminderOn"] is False
        assert sent["start"]["timeZone"] == "UTC"


def test_microsoft_unknown_email_outcome_never_posts_twice(container):
    simulated = enable_microsoft(container)
    owner = account(container)
    connection = asyncio.run(connect_microsoft(container, owner, "email"))
    action = container.actions.repo.prepare(
        owner,
        action_request(connection, "email_send"),
        "ms-unknown-email",
    )
    action = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    simulated.lose_reply = True
    asyncio.run(container.actions.execute(action["id"]))
    assert container.actions.repo.get(owner, action["id"])["state"] == "outcome_unknown"
    assert len(simulated.sent) == 1
    simulated.lose_reply = False
    asyncio.run(container.actions.execute(action["id"]))
    assert len(simulated.sent) == 1


def test_microsoft_routes_are_disabled_without_connector_flag(
    signed_client,
    container,
):
    client, headers = signed_client
    owner = account(container)
    assert owner
    response = client.post(
        "/api/v1/connections/microsoft/start",
        json={"capability": "email"},
        headers=headers(),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "connection_provider_disabled"


def test_microsoft_setting_validation_is_fail_closed(container):
    base = replace(
        container.settings,
        actions_enabled=True,
        google_client_id="google-client",
        google_client_secret="google-secret",
        google_redirect_uri="http://127.0.0.1:5173/oauth/google/callback",
        connector_encryption_key=base64.urlsafe_b64encode(
            b"\x33" * 32
        ).decode(),
    )
    with pytest.raises(ValueError, match="Microsoft actions require"):
        replace(
            base,
            microsoft_actions_enabled=True,
            microsoft_client_id="",
        ).validate()
    with pytest.raises(ValueError, match="Microsoft actions require"):
        replace(
            base,
            microsoft_actions_enabled=True,
            microsoft_client_id="client",
            microsoft_client_secret="secret",
            microsoft_redirect_uri="https://site.test/oauth/microsoft/callback",
            microsoft_tenant="../common",
        ).validate()
