"""Real authorization/approval/transport boundaries with simulated Google I/O."""
import asyncio
import base64
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from pydantic import ValidationError
from sqlalchemy import select

from test_coworker import container, account, signed_client
from action_samples import enable_actions, connected, action_request, approved
from services.coworker.action_schemas import ActionPrepare, CalendarCreate, EmailSend, OAuthFinish, OAuthStart
from services.coworker.action_repository import digest
from services.coworker.action_security import TokenVault
from services.coworker.errors import CoworkerError
from services.coworker.google_actions import GoogleFailure, GoogleActions, SEND_URL, EVENTS_URL, event_id, event_body
from services.coworker.models import AuditEvent, Connection, ExternalAction, OAuthAttempt, utcnow


def test_flags_credentials_and_token_encryption(container):
    assert not container.settings.actions_enabled
    with pytest.raises(CoworkerError, match="not available"):
        container.actions.repo.start_oauth(account(container), "email")
    enable_actions(container)
    assert "simulated-client-secret" not in repr(container.settings)
    for changes in [{"google_client_secret": ""}, {"google_redirect_uri": "https://site.test/?bad=1"},
                    {"google_redirect_uri": "https://site.test/other"}, {"connector_encryption_key": "bad"}]:
        with pytest.raises(ValueError):
            replace(container.settings, **changes).validate()
    vault = TokenVault(container.settings.connector_encryption_key)
    sealed = vault.seal({"refresh": "private-token"}, "alice:1")
    assert "private-token" not in sealed
    assert vault.open(sealed, "alice:1") == {"refresh": "private-token"}
    with pytest.raises(CoworkerError):
        vault.open(sealed, "bob:1")
    with pytest.raises(CoworkerError):
        vault.open(sealed[:-5] + "abcde", "alice:1")


def test_oauth_pkce_state_scopes_owner_expiry_and_single_use(container):
    provider = enable_actions(container)
    repo, service = container.actions.repo, container.actions
    owner, other = account(container), account(container, "bob")
    start = asyncio.run(service.connect(owner, OAuthStart(capability="email")))
    params = parse_qs(urlparse(start["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"] and params["scope"] == ["openid email https://www.googleapis.com/auth/gmail.send"]
    with repo.sessions() as db:
        row = db.get(OAuthAttempt, hashlib.sha256(start["state"].encode()).hexdigest())
        assert row and start["state"] not in row.verifier_ciphertext
        verifier = repo.vault().open(row.verifier_ciphertext, owner + ":oauth:" + row.state_hash)["verifier"]
    assert params["code_challenge"] == [base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()]
    request = OAuthFinish(state=start["state"], code="simulated-authorization-code")
    with pytest.raises(CoworkerError):
        asyncio.run(service.finish_connect(other, request))
    connection = asyncio.run(service.finish_connect(owner, request))
    assert connection["email"] == "alice@example.test"
    assert "token" not in json.dumps(connection)
    with repo.sessions() as db:
        row = db.get(Connection, connection["id"])
        assert "simulated-refresh-token" not in row.token_ciphertext
        assert db.get(OAuthAttempt, hashlib.sha256(start["state"].encode()).hexdigest()).verifier_ciphertext == ""
    with pytest.raises(CoworkerError):
        asyncio.run(service.finish_connect(owner, request))
    assert len(provider.requests) == 2
    expired, _ = repo.start_oauth(owner, "calendar")
    with repo.sessions.begin() as db:
        db.get(OAuthAttempt, hashlib.sha256(expired.encode()).hexdigest()).expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(CoworkerError):
        repo.consume_oauth(owner, expired)
    repo.claim_outbox()
    with repo.sessions() as db:
        assert db.get(OAuthAttempt, hashlib.sha256(expired.encode()).hexdigest()).verifier_ciphertext == ""


def test_partial_consent_and_newer_flow_do_not_replace_connections(container):
    provider = enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    first, _ = repo.start_oauth(owner, "email")
    old = repo.consume_oauth(owner, first)
    repo.start_oauth(owner, "calendar")
    with pytest.raises(CoworkerError):
        repo.finish_connection(owner, old, {"sub": "x", "email": "a@example.org"}, "refresh", [])
    provider.granted_scopes = []
    value = asyncio.run(container.actions.connect(owner, OAuthStart(capability="email")))
    with pytest.raises(CoworkerError, match="requested permission"):
        asyncio.run(container.actions.finish_connect(owner, OAuthFinish(state=value["state"], code="code")))
    assert repo.connections(owner) == []


@pytest.mark.parametrize("changes", [
    {"to": ["Alice <alice@example.org>"]}, {"to": ["a@example.org\r\nBcc: victim@example.org"]},
    {"to": ["missing-domain"]}, {"subject": "Hello\nInjected: yes"}, {"body": "\x00bad"},
    {"cc": ["recipient@example.org"]}, {"attachments": ["private-file"]}, {"kind": "shell"},
])
def test_email_injection_and_unapproved_features_rejected(container, changes):
    enable_actions(container)
    connection = connected(container.actions.repo, account(container))
    body = action_request(connection).model_dump(mode="json")
    body["payload"].update(changes)
    with pytest.raises(ValidationError):
        ActionPrepare.model_validate(body)


def test_timezone_daylight_saving_and_bounded_events():
    base = {"kind": "calendar_create", "title": "Meeting", "start_at": "2026-10-01T10:00", "end_at": "2026-10-01T11:00", "time_zone": "Asia/Dhaka"}
    value = CalendarCreate.model_validate(base)
    assert value.start_at.utcoffset() == timedelta(hours=6)
    assert value.model_dump(mode="json")["start_at"].endswith("+06:00")
    for changes in [{"time_zone": "Mars/Olympus"}, {"end_at": base["start_at"]}, {"start_at": "2026-10-01T10:00+05:00"},
                    {"start_at": "2026-03-08T02:30", "end_at": "2026-03-08T04:00", "time_zone": "America/New_York"},
                    {"start_at": "2026-11-01T01:30", "end_at": "2026-11-01T03:00", "time_zone": "America/New_York"}]:
        with pytest.raises(ValidationError):
            CalendarCreate.model_validate(base | changes)
    explicit = CalendarCreate.model_validate(base | {"start_at": "2026-11-01T01:30-05:00", "end_at": "2026-11-01T02:30-05:00", "time_zone": "America/New_York"})
    assert explicit.start_at.utcoffset() == timedelta(hours=-5)


def test_api_account_isolation_approval_hash_and_no_implicit_execute(signed_client, container):
    client, headers = signed_client
    provider = enable_actions(container)
    owner = account(container)
    connection = connected(container.actions.repo, owner)
    body = action_request(connection).model_dump(mode="json")
    a, b = headers(), headers("bob")
    assert client.get("/api/v1/connections").status_code == 401
    assert client.get("/api/v1/connections", headers=b).json()["connections"] == []
    assert client.post("/api/v1/actions", json=body, headers=b | {"Idempotency-Key": "first-action"}).status_code == 404
    created = client.post("/api/v1/actions", json=body, headers=a | {"Idempotency-Key": "first-action"})
    assert created.status_code == 201 and created.headers["cache-control"] == "no-store"
    action = created.json()
    assert action["state"] == "awaiting_approval" and not provider.requests
    path = "/api/v1/actions/" + action["id"]
    assert client.get(path, headers=b).status_code == 404
    for suffix, payload in [("approve", {"preview_hash": action["preview_hash"]}), ("cancel", None), ("reconcile", None)]:
        assert client.post(path + "/" + suffix, json=payload, headers=b).status_code == 404
    assert client.delete("/api/v1/connections/" + connection["id"], headers=b).status_code == 404
    assert client.post(path + "/approve", json={"preview_hash": "0" * 64}, headers=a).status_code == 409
    assert client.post(path + "/approve", json={"preview_hash": action["preview_hash"], "to": ["changed@example.org"]}, headers=a).status_code == 422
    result = client.post(path + "/approve", json={"preview_hash": action["preview_hash"]}, headers=a)
    assert result.status_code == 202 and result.json()["state"] == "queued" and not provider.requests
    assert client.post(path + "/approve", json={"preview_hash": action["preview_hash"]}, headers=a).json()["approved_at"] == result.json()["approved_at"]
    audit = client.get(path, headers=a).json()["audit"]
    assert [event["action"] for event in audit] == ["action.prepared", "action.approved"]
    assert client.post(path + "/cancel", headers=a).json()["state"] == "cancelled"
    asyncio.run(container.actions.execute(action["id"]))
    assert not provider.requests


def test_idempotent_preview_expiry_changed_content_and_limits(container):
    enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    connection = connected(repo, owner)
    request = action_request(connection)
    value = repo.prepare(owner, request, "same-key")
    assert repo.prepare(owner, request, "same-key")["id"] == value["id"]
    changed = action_request(connection)
    changed.payload.body += "Changed"
    with pytest.raises(CoworkerError) as conflict:
        repo.prepare(owner, changed, "same-key")
    assert conflict.value.code == "idempotency_conflict"
    with repo.sessions.begin() as db:
        db.get(ExternalAction, value["id"]).expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(CoworkerError):
        repo.approve(owner, value["id"], value["preview_hash"])
    repo.claim_outbox()
    assert repo.get(owner, value["id"])["state"] == "expired"
    repo.settings = replace(repo.settings, max_daily_actions=1)
    for index in range(2):
        value = repo.prepare(owner, request, "limited-" + str(index))
        if index == 0:
            repo.approve(owner, value["id"], value["preview_hash"])
        else:
            with pytest.raises(CoworkerError) as error:
                repo.approve(owner, value["id"], value["preview_hash"])
            assert error.value.code == "action_limit"


@pytest.mark.parametrize("capability", ["email", "calendar"])
def test_real_transport_payload_unicode_receipt_and_repeated_execution(container, capability):
    provider = enable_actions(container)
    owner, repo = account(container), container.actions.repo
    action = approved(repo, owner, capability)
    asyncio.run(container.actions.execute(action["id"]))
    asyncio.run(container.actions.execute(action["id"]))
    result = repo.get(owner, action["id"])
    assert result["state"] == "succeeded" and result["receipt"]["provider_id"]
    assert "simulated-access-token" not in json.dumps(result)
    if capability == "email":
        assert len(provider.sent) == 1
        mime = BytesParser(policy=policy.default).parsebytes(provider.sent[0])
        assert str(mime["Subject"]) == action["preview"]["payload"]["subject"]
        assert str(mime["From"]) == "alice@example.test"
        assert str(mime["Bcc"]) == "private@example.org"
        assert mime.get_content().strip().replace("\r\n", "\n") == action["preview"]["payload"]["body"]
        assert not mime.is_multipart()
    else:
        assert len(provider.events) == 1
        event = next(iter(provider.events.values()))
        assert event["reminders"] == {"useDefault": False, "overrides": []}
        assert event["guestsCanInviteOthers"] is False and event["start"]["timeZone"] == "UTC"


@pytest.mark.parametrize("capability", ["email", "calendar"])
def test_lost_reply_reconciles_without_second_provider_mutation(container, capability):
    provider = enable_actions(container)
    provider.lose_reply = True
    repo, owner = container.actions.repo, account(container)
    action = approved(repo, owner, capability)
    asyncio.run(container.actions.execute(action["id"]))
    asyncio.run(container.actions.execute(action["id"]))
    result = repo.get(owner, action["id"])
    assert result["state"] == ("outcome_unknown" if capability == "email" else "succeeded")
    mutations = [r for r in provider.requests if r.method == "POST" and str(r.url).split("?")[0] in {SEND_URL, EVENTS_URL}]
    assert len(mutations) == 1
    if capability == "email":
        assert result["receipt"] is None and "not automatically repeat" in result["message"]


def test_calendar_missing_or_modified_receipt_never_resends(container):
    provider = enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    action = approved(repo, owner, "calendar")
    repo.claim_execution(action["id"])
    asyncio.run(container.actions.execute(action["id"]))
    assert repo.get(owner, action["id"])["state"] == "outcome_unknown" and not provider.events
    provider.events[event_id(action["id"])] = event_body(action) | {"status": "confirmed", "summary": "Wrong event"}
    result = asyncio.run(container.actions.reconcile_owned(owner, action["id"]))
    assert result["state"] == "outcome_unknown"
    with pytest.raises(CoworkerError) as limited:
        asyncio.run(container.actions.reconcile_owned(owner, action["id"]))
    assert limited.value.status_code == 429
    with repo.sessions.begin() as db:
        for audit in db.scalars(select(AuditEvent).where(AuditEvent.resource_id == action["id"], AuditEvent.action == "action.reconciliation_requested")):
            audit.created_at = utcnow() - timedelta(minutes=2)
    provider.events[event_id(action["id"])] = event_body(action) | {"status": "confirmed"}
    result = asyncio.run(container.actions.reconcile_owned(owner, action["id"]))
    assert result["state"] == "succeeded"
    assert all(not (r.method == "POST" and str(r.url).startswith(EVENTS_URL)) for r in provider.requests)


def test_disconnect_and_preflight_failure_cannot_rewrite_inflight_result(container):
    provider = enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    action = approved(repo, owner)
    repo.claim_execution(action["id"])
    repo.finish(action["id"], "failed", error_code="preflight", unstarted=True)
    assert repo.get(owner, action["id"])["state"] == "executing"
    with pytest.raises(CoworkerError, match="may already have started"):
        repo.cancel(owner, action["id"])
    repo.disconnect(owner, action["connection_id"])
    assert repo.get(owner, action["id"])["state"] == "executing"
    repo.finish(action["id"], "outcome_unknown")
    repo.finish(action["id"], "succeeded", receipt={"provider_id": "late-confirmed"})
    repo.finish(action["id"], "outcome_unknown")
    assert repo.get(owner, action["id"])["state"] == "succeeded"
    assert not provider.sent


def test_disconnect_between_token_lookup_and_send_prevents_mutation(container):
    provider = enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    action = approved(repo, owner)
    original = container.actions.access
    async def interrupted(value):
        token = await original(value)
        repo.disconnect(owner, action["connection_id"])
        return token
    container.actions.access = interrupted
    asyncio.run(container.actions.execute(action["id"]))
    assert repo.get(owner, action["id"])["state"] == "cancelled" and not provider.sent
    with repo.sessions() as db:
        assert db.get(Connection, action["connection_id"]).token_ciphertext == ""


def test_provider_rejection_identity_change_and_kill_switch(container):
    provider = enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    action = approved(repo, owner)
    provider.profile_email = "different@example.test"
    asyncio.run(container.actions.execute(action["id"]))
    assert repo.get(owner, action["id"])["state"] == "failed" and not provider.sent
    provider.profile_email, provider.reject = "alice@example.test", True
    action = approved(repo, owner)
    asyncio.run(container.actions.execute(action["id"]))
    assert repo.get(owner, action["id"])["state"] == "failed"
    assert "private provider details" not in json.dumps(repo.get(owner, action["id"]))
    action = approved(repo, owner)
    repo.settings = replace(repo.settings, actions_enabled=False)
    before = len(provider.requests)
    with pytest.raises(CoworkerError):
        asyncio.run(container.actions.execute(action["id"]))
    assert len(provider.requests) == before
    assert repo.get(owner, action["id"])["state"] == "queued"


def test_tampered_approval_expired_queue_and_abandoned_execution(container):
    provider = enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    action = approved(repo, owner)
    with repo.sessions.begin() as db:
        row = db.get(ExternalAction, action["id"])
        row.preview = row.preview | {"account": "tampered@example.org"}
    with pytest.raises(CoworkerError):
        repo.claim_execution(action["id"])
    other = approved(repo, owner)
    with repo.sessions.begin() as db:
        db.get(ExternalAction, other["id"]).expires_at = utcnow() - timedelta(seconds=1)
    assert repo.claim_execution(other["id"]) is None
    assert repo.get(owner, other["id"])["state"] == "expired"
    stuck = approved(repo, owner)
    repo.claim_execution(stuck["id"])
    with repo.sessions.begin() as db:
        db.get(ExternalAction, stuck["id"]).started_at = utcnow() - timedelta(minutes=11)
    repo.claim_outbox()
    assert repo.get(owner, stuck["id"])["state"] == "outcome_unknown"
    assert not provider.sent


def test_provider_never_follows_redirect_or_accepts_arbitrary_url(container):
    enable_actions(container)
    requests = []
    def redirect(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.org/"})
    provider = GoogleActions(container.settings, httpx.MockTransport(redirect))
    with pytest.raises(GoogleFailure):
        asyncio.run(provider.request("POST", SEND_URL, token="private-access-token", body={}))
    assert len(requests) == 1
    with pytest.raises(ValueError):
        asyncio.run(provider.request("GET", "https://other.example.org/", token="private-access-token"))


def test_execution_revalidates_server_owned_approval_scope(container):
    enable_actions(container)
    repo, owner = container.actions.repo, account(container)
    connection = connected(repo, owner)
    request = action_request(connection)
    action = repo.prepare(owner, request, "scope-revalidation")
    assert action["preview"]["approval_scope"]["payload_sha256"]
    repo.approve(owner, action["id"], action["preview_hash"])

    with repo.sessions.begin() as db:
        row = db.get(ExternalAction, action["id"])
        preview = dict(row.preview)
        payload = dict(preview["payload"])
        payload["body"] = "Changed after approval."
        preview["payload"] = payload
        row.preview = preview
        # Simulate a storage-layer rewrite that also recomputed preview_hash.
        # The independent approval_scope must still fail execution.
        row.preview_hash = digest(preview)

    with pytest.raises(CoworkerError) as error:
        repo.claim_execution(action["id"])
    assert error.value.code == "approval_changed"
