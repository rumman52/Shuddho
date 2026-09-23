"""Explicitly simulated Google transport; never imported by production code."""
import base64
import json
from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs
from uuid import uuid4

import httpx

from services.coworker.action_repository import ActionRepository
from services.coworker.action_schemas import ActionPrepare
from services.coworker.actions import ActionService
from services.coworker.google_actions import GoogleActions, SCOPES, TOKEN_URL, USERINFO_URL, SEND_URL, EVENTS_URL
from services.coworker.models import utcnow


class SimulatedGoogle:
    def __init__(self):
        self.requests = []
        self.sent = []
        self.events = {}
        self.lose_reply = False
        self.reject = False
        self.profile_email = "alice@example.test"
        self.granted_scopes = list(SCOPES.values())

    def transport(self, request):
        self.requests.append(request)
        url = str(request.url).split("?")[0]
        if url == TOKEN_URL:
            form = parse_qs(request.content.decode())
            if form.get("grant_type") == ["authorization_code"]:
                assert form.get("code_verifier") and form.get("redirect_uri")
            return httpx.Response(200, json={"token_type": "Bearer", "access_token": "simulated-access-token",
                "refresh_token": "simulated-refresh-token", "scope": "openid email " + " ".join(self.granted_scopes)})
        if url == USERINFO_URL:
            return httpx.Response(200, json={"sub": "simulated-google-subject", "email": self.profile_email, "email_verified": True})
        if request.method == "POST" and url in {SEND_URL, EVENTS_URL}:
            if self.reject:
                return httpx.Response(403, json={"error": {"message": "private provider details must not leak"}})
            value = json.loads(request.content)
            if url == SEND_URL:
                self.sent.append(base64.urlsafe_b64decode(value["raw"]))
                result = {"id": "mail-" + str(len(self.sent))}
            else:
                assert request.url.params["sendUpdates"] == "all"
                result = value | {"status": "confirmed"}
                self.events[value["id"]] = result
            if self.lose_reply:
                raise httpx.ReadTimeout("simulated interruption after acceptance")
            return httpx.Response(200, json=result)
        if request.method == "GET" and url.startswith(EVENTS_URL + "/"):
            result = self.events.get(url.rsplit("/", 1)[1])
            return httpx.Response(200, json=result) if result else httpx.Response(404, json={"error": {}})
        raise AssertionError("Unexpected simulated endpoint")


def enable_actions(container):
    container.settings = replace(container.settings, actions_enabled=True,
        google_client_id="simulated-client-id", google_client_secret="simulated-client-secret",
        google_redirect_uri="http://127.0.0.1:5173/oauth/google/callback",
        connector_encryption_key=base64.urlsafe_b64encode(b"\x11" * 32).decode())
    container.settings.validate()
    container.repository.settings = container.settings
    provider = SimulatedGoogle()
    container.actions = ActionService(
        ActionRepository(container.repository.sessions, container.settings),
        {"google": GoogleActions(container.settings, httpx.MockTransport(provider.transport))},
        container.storage,
    )
    return provider


def connected(repo, owner, capability="email"):
    state, _ = repo.start_oauth(owner, capability)
    attempt = repo.consume_oauth(owner, state)
    return repo.finish_connection(owner, attempt, {"sub": "simulated-google-subject", "email": "alice@example.test"},
                                  "simulated-refresh-token", [SCOPES[capability]])


def action_request(connection, kind="email_send"):
    if kind == "email_send":
        payload = {"kind": kind, "to": ["recipient@example.org"], "cc": ["cc@example.org"], "bcc": ["private@example.org"],
                   "subject": "প্রকল্পের অগ্রগতি", "body": "দলটি ১২টি পর্যালোচনা সম্পন্ন করেছে।\nشكراً لكم."}
    else:
        start = (utcnow() + timedelta(days=2)).replace(microsecond=0)
        payload = {"kind": kind, "title": "প্রকল্পের আলোচনা", "description": "Review twelve items.", "location": "Dhaka",
                   "start_at": start.isoformat(), "end_at": (start + timedelta(hours=1)).isoformat(),
                   "time_zone": "UTC", "attendees": ["guest@example.org"]}
    return ActionPrepare(connection_id=connection["id"], payload=payload)


def approved(repo, owner, capability="email"):
    connection = connected(repo, owner, capability)
    action = repo.prepare(owner, action_request(connection, "email_send" if capability == "email" else "calendar_create"), str(uuid4()))
    return repo.approve(owner, action["id"], action["preview_hash"])
