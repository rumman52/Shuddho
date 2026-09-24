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
from services.coworker.action_schemas import ActionPrepare, CalendarCreate, CalendarCreateWithReminder, EmailSend, OAuthFinish, OAuthStart
from services.coworker.action_repository import digest
from services.coworker.action_security import TokenVault
from services.coworker.errors import CoworkerError
from services.coworker.google_actions import GoogleFailure, GoogleActions, SEND_URL, EVENTS_URL, event_id, event_body
from services.coworker.models import AuditEvent, Connection, ExternalAction, OAuthAttempt, utcnow


def test_flags_credentials_and_token_encryption(container):
    assert not container.settings.actions_enabled
    with pytest.raises(ValueError, match="Action reminders require"):
        replace(container.settings, action_reminders_enabled=True).validate()
    with pytest.raises(ValueError, match="email threading requires"):
        replace(container.settings, action_email_threading_enabled=True).validate()
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




def test_reminder_schema_and_feature_flag_are_bounded(container):
    base = {
        "kind": "calendar_create_with_reminder",
        "title": "Meeting",
        "start_at": "2026-10-01T10:00",
        "end_at": "2026-10-01T11:00",
        "time_zone": "Asia/Dhaka",
        "reminder_minutes_before_start": 15,
    }
    value = CalendarCreateWithReminder.model_validate(base)
    assert value.reminder_minutes_before_start == 15
    for minutes in (0, 1, 45, 2880):
        with pytest.raises(ValidationError):
            CalendarCreateWithReminder.model_validate(
                base | {"reminder_minutes_before_start": minutes}
            )

    provider = enable_actions(container)
    assert provider
    owner = account(container)
    connection = connected(container.actions.repo, owner, "calendar")
    request = action_request(connection, "calendar_create_with_reminder")
    with pytest.raises(CoworkerError) as disabled:
        container.actions.repo.prepare(owner, request, "reminder-disabled")
    assert disabled.value.code == "action_reminders_disabled"

    settings = replace(container.settings, action_reminders_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    action = container.actions.repo.prepare(owner, request, "reminder-enabled")
    assert action["preview"]["payload"]["reminder_minutes_before_start"] == 15
    assert action["preview"]["reminders"] == "single_explicit"
    assert action["preview"]["approval_scope"]["policy"]["reminders"] == "single_explicit"


def test_calendar_reminder_must_still_be_in_the_future(container):
    enable_actions(container)
    settings = replace(container.settings, action_reminders_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings

    owner = account(container)
    connection = connected(container.actions.repo, owner, "calendar")
    start = (utcnow() + timedelta(minutes=10)).replace(microsecond=0)
    request = ActionPrepare.model_validate({
        "connection_id": connection["id"],
        "payload": {
            "kind": "calendar_create_with_reminder",
            "title": "Too-late reminder",
            "description": "",
            "location": "",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "time_zone": "UTC",
            "attendees": [],
            "reminder_minutes_before_start": 15,
        },
    })
    with pytest.raises(CoworkerError) as rejected:
        container.actions.repo.prepare(
            owner,
            request,
            "reminder-already-due",
        )
    assert rejected.value.code == "reminder_time"


def test_reminder_kill_switch_cancels_before_provider_mutation(container):
    provider = enable_actions(container)
    settings = replace(container.settings, action_reminders_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings

    owner = account(container)
    connection = connected(container.actions.repo, owner, "calendar")
    action = container.actions.repo.prepare(
        owner,
        action_request(connection, "calendar_create_with_reminder"),
        "reminder-kill-switch",
    )
    approved = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    assert approved["state"] == "queued"

    disabled = replace(settings, action_reminders_enabled=False)
    container.settings = disabled
    container.repository.settings = disabled
    container.actions.repo.settings = disabled

    assert container.actions.repo.claim_execution(action["id"]) is None
    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "cancelled"
    assert result["error_code"] == "action_reminders_disabled"
    assert provider.events == {}


def test_google_legacy_calendar_accepts_normalized_empty_reminders(container):
    enable_actions(container)
    owner = account(container)
    action = approved(container.actions.repo, owner, "calendar")
    expected = event_body(action)
    normalized = dict(expected)
    normalized["status"] = "confirmed"
    normalized["reminders"] = {"useDefault": False}
    receipt = GoogleActions.calendar_receipt(action, normalized)
    assert receipt["status"] == "event_created"


def test_google_calendar_reminder_executes_exact_approved_minutes(container):
    provider = enable_actions(container)
    settings = replace(container.settings, action_reminders_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings

    owner = account(container)
    connection = connected(container.actions.repo, owner, "calendar")
    request = action_request(connection, "calendar_create_with_reminder")
    action = container.actions.repo.prepare(owner, request, "google-reminder")
    action = container.actions.repo.approve(
        owner,
        action["id"],
        action["preview_hash"],
    )
    asyncio.run(container.actions.execute(action["id"]))

    result = container.actions.repo.get(owner, action["id"])
    assert result["state"] == "succeeded"
    event = next(iter(provider.events.values()))
    assert event["reminders"] == {
        "useDefault": False,
        "overrides": [{"method": "popup", "minutes": 15}],
    }
    assert result["receipt"]["provider"] == "google"

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


def test_action_proposal_promotion_requires_exact_hash_and_user_connection(
    container,
    signed_client,
):
    from services.coworker.agent_schemas import (
        AgentActionProposal,
        AgentPlanStep,
        AgentRunCreate,
    )
    from services.coworker.models import ActionProposal

    client, headers = signed_client
    provider = enable_actions(container)
    enabled = replace(
        container.settings,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_action_proposals_enabled=True,
        work_services_enabled=True,
    )
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    container.actions.repo.settings = enabled

    owner = account(container)
    connection = connected(container.actions.repo, owner)
    run, _ = container.agent.create(
        owner,
        AgentRunCreate(
            goal="Prepare a project update email proposal.",
            output_language="en",
        ),
        "proposal-promotion-run",
    )
    container.agent.save_plan(
        owner,
        run["id"],
        [AgentPlanStep(tool="email.draft", arguments={
            "instruction": "Prepare a project update email proposal.",
            "notes": "",
            "document_ids": [],
            "output_language": "en",
        })],
        action_proposals=[AgentActionProposal.model_validate({
            "payload": {
                "kind": "email_send",
                "to": ["recipient@example.org"],
                "cc": [],
                "bcc": [],
                "subject": "Project update",
                "body": "The project is ready.",
            },
            "rationale": "The user requested a project update email.",
        })],
    )
    proposal = container.agent.get(owner, run["id"])["action_proposals"][0]
    path = (
        f"/api/v1/agent-runs/{run['id']}/action-proposals/"
        f"{proposal['id']}/promote"
    )
    auth = headers()

    wrong = client.post(
        path,
        headers=auth,
        json={
            "connection_id": connection["id"],
            "proposal_hash": "0" * 64,
        },
    )
    assert wrong.status_code == 409

    other = headers("bob")
    hidden = client.post(
        path,
        headers=other,
        json={
            "connection_id": connection["id"],
            "proposal_hash": proposal["proposal_hash"],
        },
    )
    assert hidden.status_code == 404

    promoted = client.post(
        path,
        headers=auth,
        json={
            "connection_id": connection["id"],
            "proposal_hash": proposal["proposal_hash"],
        },
    )
    assert promoted.status_code == 201
    action = promoted.json()
    assert action["state"] == "awaiting_approval"
    assert action["approved_at"] is None
    assert action["receipt"] is None
    assert provider.requests == []

    replay = client.post(
        path,
        headers=auth,
        json={
            "connection_id": connection["id"],
            "proposal_hash": proposal["proposal_hash"],
        },
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == action["id"]

    with container.repository.sessions() as db:
        row = db.get(ActionProposal, proposal["id"])
        assert row.state == "promoted"
        assert row.promoted_action_id == action["id"]
        assert row.promotion_connection_id == connection["id"]

    approved_response = client.post(
        f"/api/v1/actions/{action['id']}/approve",
        headers=auth,
        json={"preview_hash": action["preview_hash"]},
    )
    assert approved_response.status_code == 202
    assert approved_response.json()["state"] == "queued"
    assert provider.requests == []


def test_action_proposal_dismiss_and_kill_switch_block_promotion(container):
    from services.coworker.agent_schemas import (
        AgentActionProposal,
        AgentPlanStep,
        AgentRunCreate,
    )

    enable_actions(container)
    enabled = replace(
        container.settings,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_action_proposals_enabled=True,
        work_services_enabled=True,
    )
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    container.actions.repo.settings = enabled
    owner = account(container)
    connection = connected(container.actions.repo, owner)

    def make_proposal(key):
        run, _ = container.agent.create(
            owner,
            AgentRunCreate(goal="Prepare an email proposal.", output_language="en"),
            key,
        )
        container.agent.save_plan(
            owner,
            run["id"],
            [AgentPlanStep(tool="email.draft", arguments={
                "instruction": "Prepare an email proposal.",
                "notes": "",
                "document_ids": [],
                "output_language": "en",
            })],
            action_proposals=[AgentActionProposal.model_validate({
                "payload": {
                    "kind": "email_send",
                    "to": ["recipient@example.org"],
                    "cc": [],
                    "bcc": [],
                    "subject": "Update",
                    "body": "Ready.",
                },
                "rationale": "Requested by the user.",
            })],
        )
        return run, container.agent.get(owner, run["id"])["action_proposals"][0]

    dismissed_run, dismissed = make_proposal("proposal-dismiss-run")
    result = container.agent.dismiss_action_proposal(
        owner,
        dismissed_run["id"],
        dismissed["id"],
        dismissed["proposal_hash"],
    )
    assert result["state"] == "dismissed"
    with pytest.raises(CoworkerError) as unavailable:
        container.actions.repo.promote_proposal(
            owner,
            dismissed_run["id"],
            dismissed["id"],
            dismissed["proposal_hash"],
            connection["id"],
        )
    assert unavailable.value.code == "proposal_unavailable"

    blocked_run, blocked = make_proposal("proposal-kill-switch-run")
    container.actions.repo.settings = replace(
        enabled,
        agent_action_proposals_enabled=False,
    )
    with pytest.raises(CoworkerError) as disabled:
        container.actions.repo.promote_proposal(
            owner,
            blocked_run["id"],
            blocked["id"],
            blocked["proposal_hash"],
            connection["id"],
        )
    assert disabled.value.code == "action_proposals_disabled"


def test_agent_proposals_cannot_invent_calendar_reminders():
    from services.coworker.agent_schemas import AgentActionProposal

    with pytest.raises(ValidationError):
        AgentActionProposal.model_validate({
            "payload": {
                "kind": "calendar_create_with_reminder",
                "title": "Model reminder",
                "description": "Must remain user-selected.",
                "location": "",
                "start_at": "2026-10-01T10:00+06:00",
                "end_at": "2026-10-01T11:00+06:00",
                "time_zone": "Asia/Dhaka",
                "attendees": [],
                "reminder_minutes_before_start": 15,
            },
            "rationale": "Attempted reminder proposal",
        })


def test_google_drive_scope_is_narrow_and_feature_gated(container):
    enable_actions(container)
    owner = account(container)
    with pytest.raises(CoworkerError) as disabled:
        asyncio.run(container.actions.connect(owner, OAuthStart(capability="drive")))
    assert disabled.value.code == "action_document_sharing_disabled"

    settings = replace(
        container.settings,
        artifact_services_enabled=True,
        action_document_sharing_enabled=True,
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    start = asyncio.run(container.actions.connect(owner, OAuthStart(capability="drive")))
    params = parse_qs(urlparse(start["authorization_url"]).query)
    assert params["scope"] == [
        "openid email https://www.googleapis.com/auth/drive.file"
    ]
    assert "https://www.googleapis.com/auth/drive" not in params["scope"][0].split()


def test_microsoft_drive_capability_fails_before_oauth_attempt(container):
    enable_actions(container)
    settings = replace(
        container.settings,
        artifact_services_enabled=True,
        action_document_sharing_enabled=True,
        microsoft_actions_enabled=True,
        microsoft_client_id="microsoft-client",
        microsoft_client_secret="microsoft-secret",
        microsoft_redirect_uri="http://127.0.0.1:5173/oauth/microsoft/callback",
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    with pytest.raises(CoworkerError) as rejected:
        asyncio.run(
            container.actions.connect(
                account(container),
                OAuthStart(capability="drive"),
                "microsoft",
            )
        )
    assert rejected.value.code == "connection_provider_disabled"


def test_google_owned_thread_reply_is_bound_and_uses_no_mailbox_read(container):
    provider = enable_actions(container)
    settings = replace(container.settings, action_email_threading_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings

    owner = account(container)
    connection = connected(container.actions.repo, owner)
    parent = container.actions.repo.prepare(
        owner,
        action_request(connection),
        "thread-parent",
    )
    parent = container.actions.repo.approve(owner, parent["id"], parent["preview_hash"])
    asyncio.run(container.actions.execute(parent["id"]))
    parent = container.actions.repo.get(owner, parent["id"])
    assert parent["receipt"]["thread_id"]

    payload = dict(parent["preview"]["payload"])
    payload["kind"] = "email_thread_reply"
    payload["parent_action_id"] = parent["id"]
    payload["bcc"] = []
    payload["body"] = "Follow-up inside the approved Shuddho thread."
    reply = container.actions.repo.prepare(
        owner,
        ActionPrepare.model_validate({
            "connection_id": connection["id"],
            "payload": payload,
        }),
        "thread-reply",
    )
    assert reply["preview"]["approval_scope"]["contract_version"] == 4
    assert reply["preview"]["reply_context"]["thread_id"] == parent["receipt"]["thread_id"]
    assert reply["preview"]["threading"]["mailbox_read"] == "none"

    reply = container.actions.repo.approve(owner, reply["id"], reply["preview_hash"])
    asyncio.run(container.actions.execute(reply["id"]))
    result = container.actions.repo.get(owner, reply["id"])
    assert result["state"] == "succeeded"
    assert result["receipt"]["thread_id"] == parent["receipt"]["thread_id"]
    mime = BytesParser(policy=policy.default).parsebytes(provider.sent[-1])
    assert str(mime["In-Reply-To"]) == parent["receipt"]["message_id"]
    assert parent["receipt"]["message_id"] in str(mime["References"])
    send_requests = [
        request for request in provider.requests
        if str(request.url).split("?")[0] == SEND_URL
    ]
    assert json.loads(send_requests[-1].content)["threadId"] == parent["receipt"]["thread_id"]


def test_thread_reply_rejects_recipient_or_subject_expansion(container):
    enable_actions(container)
    settings = replace(container.settings, action_email_threading_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    owner = account(container)
    connection = connected(container.actions.repo, owner)
    parent = container.actions.repo.prepare(owner, action_request(connection), "thread-boundary-parent")
    parent = container.actions.repo.approve(owner, parent["id"], parent["preview_hash"])
    asyncio.run(container.actions.execute(parent["id"]))
    parent = container.actions.repo.get(owner, parent["id"])

    base = {
        **parent["preview"]["payload"],
        "kind": "email_thread_reply",
        "parent_action_id": parent["id"],
        "bcc": [],
        "body": "Follow-up",
    }
    for changes in (
        {"to": ["other@example.org"]},
        {"cc": []},
        {"subject": "Changed subject"},
    ):
        request = ActionPrepare.model_validate({
            "connection_id": connection["id"],
            "payload": base | changes,
        })
        with pytest.raises(CoworkerError) as rejected:
            container.actions.repo.prepare(owner, request, "thread-boundary-" + next(iter(changes)))
        assert rejected.value.code == "thread_reply_changed"

    with pytest.raises(ValidationError):
        ActionPrepare.model_validate({
            "connection_id": connection["id"],
            "payload": base | {"bcc": ["hidden@example.org"]},
        })


def test_linkedin_agent_proposal_is_inert_and_separately_gated(container):
    from dataclasses import replace

    from action_samples import enable_actions
    from services.coworker.agent_schemas import (
        AgentActionProposal,
        AgentPlanStep,
        AgentRunCreate,
    )
    from services.coworker.errors import CoworkerError
    from services.coworker.models import ActionProposal, ExternalAction

    provider = enable_actions(container)
    base = replace(
        container.settings,
        action_social_publishing_enabled=True,
        linkedin_client_id="simulated-linkedin-client",
        linkedin_client_secret="simulated-linkedin-secret",
        linkedin_redirect_uri="http://127.0.0.1:5173/oauth/linkedin/callback",
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_action_proposals_enabled=True,
        agent_linkedin_proposals_enabled=False,
        work_services_enabled=True,
    )
    base.validate()
    container.settings = base
    container.repository.settings = base
    container.agent.settings = base
    container.actions.repo.settings = base
    owner = account(container)
    proposed = AgentActionProposal.model_validate({
        "payload": {
            "kind": "social_publish_linkedin",
            "text": "Launch update #Shuddho",
        },
        "rationale": "The user asked for an exact LinkedIn post draft.",
    })

    blocked, _ = container.agent.create(
        owner,
        AgentRunCreate(goal="Suggest the exact LinkedIn post.", output_language="en"),
        "linkedin-proposal-blocked",
    )
    with pytest.raises(CoworkerError) as disabled:
        container.agent.save_plan(
            owner,
            blocked["id"],
            [AgentPlanStep(tool="social.draft", arguments={
                "instruction": "Draft the exact LinkedIn post.",
                "notes": "",
                "document_ids": [],
                "output_language": "en",
            })],
            action_proposals=[proposed],
        )
    assert disabled.value.code == "linkedin_action_proposals_disabled"

    enabled = replace(base, agent_linkedin_proposals_enabled=True)
    enabled.validate()
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    container.actions.repo.settings = enabled
    allowed, _ = container.agent.create(
        owner,
        AgentRunCreate(goal="Suggest the exact LinkedIn post.", output_language="en"),
        "linkedin-proposal-allowed",
    )
    saved = container.agent.save_plan(
        owner,
        allowed["id"],
        [AgentPlanStep(tool="social.draft", arguments={
            "instruction": "Draft the exact LinkedIn post.",
            "notes": "",
            "document_ids": [],
            "output_language": "en",
        })],
        action_proposals=[proposed],
    )
    assert saved["action_proposals"][0]["kind"] == "social_publish_linkedin"
    assert saved["action_proposals"][0]["state"] == "suggested"
    with container.repository.sessions() as db:
        rows = db.query(ActionProposal).filter(
            ActionProposal.agent_run_id == allowed["id"],
        ).all()
        assert len(rows) == 1
        assert db.query(ExternalAction).filter(
            ExternalAction.owner_id == owner,
        ).all() == []

    connection_id = str(uuid4())
    with container.repository.sessions.begin() as db:
        db.add(Connection(
            id=connection_id,
            owner_id=owner,
            provider="linkedin",
            capability="social",
            subject="member_123",
            email="urn:li:person:member_123",
            scopes=["r_liteprofile", "w_member_social"],
            token_ciphertext="not-used-before-explicit-approval",
            active=True,
        ))
    action = container.actions.repo.promote_proposal(
        owner,
        allowed["id"],
        saved["action_proposals"][0]["id"],
        saved["action_proposals"][0]["proposal_hash"],
        connection_id,
    )
    assert action["state"] == "awaiting_approval"
    assert action["approved_at"] is None
    assert action["receipt"] is None
    assert action["preview"]["provider"] == "linkedin"
    assert action["preview"]["account"] == "urn:li:person:member_123"
    assert action["preview"]["payload"] == {
        "kind": "social_publish_linkedin",
        "text": "Launch update #Shuddho",
    }
    assert provider.requests == []


def test_linkedin_agent_proposal_flag_dependencies_fail_closed(container):
    from dataclasses import replace

    base = replace(
        container.settings,
        agent_linkedin_proposals_enabled=True,
    )
    with pytest.raises(ValueError, match="SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED"):
        base.validate()
