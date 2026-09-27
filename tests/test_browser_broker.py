from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import select

from action_samples import enable_actions
from test_coworker import account, container, signed_client

from services.coworker.browser import BrowserRepository, normalize_browser_target, validate_resolved_addresses
from services.coworker.browser_schemas import BrowserFormPrepareCreate, BrowserNavigateCreate, BrowserSessionCreate, BrowserTakeoverInputCreate, BrowserTakeoverInteractionCreate
from services.coworker.errors import CoworkerError
from services.coworker.models import BrowserCommand, BrowserSession, utcnow


def enable_browser(container):
    enable_actions(container)
    settings = replace(
        container.settings,
        connector_trust_boundary_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_runtime_v3_enabled=True,
        browser_enabled=True,
        max_active_browser_sessions=2,
        browser_session_ttl_seconds=300,
        browser_worker_token="test-browser-worker-token-0123456789abcdef",
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.actions.repo.settings = settings
    container.agent.settings = settings
    container.browser = BrowserRepository(container.repository.sessions, settings)
    return settings


def create_session(container, owner, url="https://example.com/start", key=None):
    return container.browser.create(
        owner,
        BrowserSessionCreate(purpose="research", start_url=url),
        key or "browser-" + str(uuid4()),
    )[0]


def test_browser_flag_requires_v3_and_trust_boundary(container):
    with pytest.raises(ValueError, match="Agent Runtime v3"):
        replace(container.settings, browser_enabled=True).validate()

    enable_actions(container)
    with pytest.raises(ValueError, match="CONNECTOR_TRUST_BOUNDARY_ENABLED"):
        replace(
            container.settings,
            agent_runtime_enabled=True,
            intelligent_planner_enabled=True,
            agent_runtime_v3_enabled=True,
            browser_enabled=True,
        ).validate()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/",
        "https://user:secret@example.com/",
        "https://example.com/path#fragment",
        "https://localhost/",
        "https://metadata.google.internal/",
        "https://127.0.0.1/",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/",
        "https://example.com:444/",
    ],
)
def test_browser_target_policy_fails_closed(url):
    with pytest.raises(CoworkerError):
        normalize_browser_target(url)


def test_browser_session_is_idempotent_owner_scoped_and_same_origin(container):
    enable_browser(container)
    alice = account(container)
    bob = account(container, "browser-bob")
    request = BrowserSessionCreate(
        purpose="research",
        start_url="https://example.com/start?query=one",
    )
    first, created = container.browser.create(alice, request, "browser-session-once")
    replay, replayed = container.browser.create(alice, request, "browser-session-once")
    assert created is True
    assert replayed is False
    assert first["id"] == replay["id"]

    with pytest.raises(CoworkerError) as conflict:
        container.browser.create(
            alice,
            BrowserSessionCreate(purpose="research", start_url="https://example.com/other"),
            "browser-session-once",
        )
    assert conflict.value.code == "idempotency_conflict"

    with pytest.raises(CoworkerError) as cross_owner:
        container.browser.get(bob, first["id"])
    assert cross_owner.value.status_code == 404

    navigation = container.browser.prepare_navigation(
        alice,
        first["id"],
        BrowserNavigateCreate(url="https://example.com/results?page=2"),
    )
    assert navigation["state"] == "prepared"
    assert navigation["policy"]["requires_dns_ip_validation"] is True
    assert navigation["policy"]["redirect_validation"] is True
    assert navigation["policy"]["allow_downloads"] is False

    with pytest.raises(CoworkerError) as cross_origin:
        container.browser.prepare_navigation(
            alice,
            first["id"],
            BrowserNavigateCreate(url="https://other.example/results"),
        )
    assert cross_origin.value.code == "browser_origin_not_allowed"


def test_browser_takeover_cancel_and_expiry_are_deterministic(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)

    takeover = container.browser.request_takeover(owner, session["id"], "mfa")
    assert takeover["state"] == "takeover"
    assert takeover["takeover_required"] is True
    with pytest.raises(CoworkerError) as paused:
        container.browser.prepare_navigation(
            owner,
            session["id"],
            BrowserNavigateCreate(url="https://example.com/after-login"),
        )
    assert paused.value.code == "browser_takeover_active"

    resumed = container.browser.resume(owner, session["id"])
    assert resumed["state"] == "prepared"
    cancelled = container.browser.cancel(owner, session["id"])
    assert cancelled["state"] == "cancelled"
    with pytest.raises(CoworkerError) as closed:
        container.browser.prepare_navigation(
            owner,
            session["id"],
            BrowserNavigateCreate(url="https://example.com/nope"),
        )
    assert closed.value.code == "browser_session_closed"

    expiring = create_session(container, owner, key="browser-expiry-test")
    with container.repository.sessions.begin() as db:
        row = db.get(BrowserSession, expiring["id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(CoworkerError) as expired:
        container.browser.prepare_navigation(
            owner,
            expiring["id"],
            BrowserNavigateCreate(url="https://example.com/expired"),
        )
    assert expired.value.code == "browser_session_expired"


def test_browser_api_is_owner_scoped_and_never_claims_worker_execution(container, signed_client):
    enable_browser(container)
    client, headers = signed_client
    created = client.post(
        "/api/v1/browser-sessions",
        headers=headers() | {"Idempotency-Key": "browser-api-one"},
        json={"purpose": "form_prepare", "start_url": "https://example.com/form"},
    )
    assert created.status_code == 201
    value = created.json()
    assert value["execution"]["worker_attached"] is False
    assert value["execution"]["arbitrary_script_execution"] is False
    assert value["execution"]["downloads_enabled"] is False

    assert client.get(
        f'/api/v1/browser-sessions/{value["id"]}',
        headers=headers("bob"),
    ).status_code == 404
    prepared = client.post(
        f'/api/v1/browser-sessions/{value["id"]}/navigate',
        headers=headers(),
        json={"url": "https://example.com/form/step-2"},
    )
    assert prepared.status_code == 202
    assert prepared.json()["state"] == "prepared"


def test_browser_worker_rejects_private_dns_and_requires_claim_owner(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)
    navigation = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/worker"),
    )

    with pytest.raises(CoworkerError) as private:
        validate_resolved_addresses("example.com", ["127.0.0.1"])
    assert private.value.code == "browser_network_blocked"

    claimed = container.browser.claim_commands("worker-a")
    assert [item["id"] for item in claimed] == [navigation["id"]]
    assert claimed[0]["attempt"] == 1

    with pytest.raises(CoworkerError) as wrong_worker:
        container.browser.complete_command(
            "worker-b",
            navigation["id"],
            {
                "final_url": "https://example.com/worker",
                "title": "Example",
                "redirect_chain": [],
                "resolved_ips": {"example.com": ["93.184.216.34"]},
            },
        )
    assert wrong_worker.value.code == "browser_worker_claim_invalid"

    completed = container.browser.complete_command(
        "worker-a",
        navigation["id"],
        {
            "final_url": "https://example.com/worker",
            "title": "Example",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
        },
    )
    assert completed["state"] == "succeeded"
    assert completed["result"]["final_url"] == "https://example.com/worker"
    current = container.browser.get(owner, session["id"])
    assert current["state"] == "prepared"
    assert current["last_url"] == "https://example.com/worker"
    assert current["execution"]["worker_attached"] is False


def test_browser_worker_lease_recovery_is_bounded(container):
    settings = enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)
    navigation = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/recover"),
    )
    first = container.browser.claim_commands("worker-a")
    assert first[0]["attempt"] == 1

    with container.repository.sessions.begin() as db:
        row = db.get(BrowserCommand, navigation["id"])
        row.lease_until = utcnow() - timedelta(seconds=1)

    recovered = container.browser.claim_commands("worker-b")
    assert recovered[0]["id"] == navigation["id"]
    assert recovered[0]["attempt"] == 2

    with container.repository.sessions.begin() as db:
        row = db.get(BrowserCommand, navigation["id"])
        row.lease_until = utcnow() - timedelta(seconds=1)

    assert container.browser.claim_commands("worker-c") == []
    assert settings.browser_command_max_attempts == 2


def test_browser_worker_rejects_missing_dns_evidence_and_cross_origin_redirect(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)
    navigation = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/start"),
    )
    container.browser.claim_commands("worker-a")

    with pytest.raises(CoworkerError) as missing:
        container.browser.complete_command(
            "worker-a",
            navigation["id"],
            {
                "final_url": "https://example.com/final",
                "title": "Example",
                "redirect_chain": [],
                "resolved_ips": {},
            },
        )
    assert missing.value.code == "browser_dns_evidence_missing"

    failed = container.browser.fail_command("worker-a", navigation["id"], "network_blocked")
    assert failed["state"] == "failed"
    assert failed["error_code"] == "network_blocked"

    other = create_session(container, owner, key="browser-redirect")
    redirect = container.browser.prepare_navigation(
        owner,
        other["id"],
        BrowserNavigateCreate(url="https://example.com/start"),
    )
    container.browser.claim_commands("worker-b")
    with pytest.raises(CoworkerError) as cross_origin:
        container.browser.complete_command(
            "worker-b",
            redirect["id"],
            {
                "final_url": "https://evil.example/final",
                "title": "Redirected",
                "redirect_chain": ["https://example.com/start"],
                "resolved_ips": {
                    "example.com": ["93.184.216.34"],
                    "evil.example": ["93.184.216.34"],
                },
            },
        )
    assert cross_origin.value.code == "browser_origin_not_allowed"


def test_browser_worker_internal_api_requires_service_token_and_claim_binding(container, signed_client):
    settings = enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)
    command = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/internal"),
    )
    client, headers = signed_client

    denied = client.post(
        "/api/v1/internal/browser-worker/claim",
        json={"worker_id": "worker-a", "limit": 1},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "browser_worker_unauthorized"

    worker_headers = {"X-Shuddho-Browser-Worker-Token": settings.browser_worker_token}
    claimed = client.post(
        "/api/v1/internal/browser-worker/claim",
        headers=worker_headers,
        json={"worker_id": "worker-a", "limit": 1},
    )
    assert claimed.status_code == 200
    assert claimed.json()["commands"][0]["id"] == command["id"]

    cross_origin = client.post(
        f'/api/v1/internal/browser-worker/commands/{command["id"]}/network-check',
        headers=worker_headers,
        json={
            "worker_id": "worker-a",
            "url": "https://other.example/resource",
            "resolved_ips": ["93.184.216.34"],
        },
    )
    assert cross_origin.status_code == 403
    assert cross_origin.json()["error"]["code"] == "browser_origin_not_allowed"

    allowed = client.post(
        f'/api/v1/internal/browser-worker/commands/{command["id"]}/network-check',
        headers=worker_headers,
        json={
            "worker_id": "worker-a",
            "url": "https://example.com/resource",
            "resolved_ips": ["93.184.216.34"],
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["origin"] == "https://example.com"

    wrong_worker = client.post(
        f'/api/v1/internal/browser-worker/commands/{command["id"]}/network-check',
        headers=worker_headers,
        json={
            "worker_id": "worker-b",
            "url": "https://example.com/resource",
            "resolved_ips": ["93.184.216.34"],
        },
    )
    assert wrong_worker.status_code == 409
    assert wrong_worker.json()["error"]["code"] == "browser_worker_claim_invalid"


def test_browser_worker_claims_strict_session_sequence(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)
    first = container.browser.prepare_navigation(
        owner, session["id"], BrowserNavigateCreate(url="https://example.com/one")
    )
    second = container.browser.prepare_navigation(
        owner, session["id"], BrowserNavigateCreate(url="https://example.com/two")
    )

    claimed = container.browser.claim_commands("worker-a", limit=5)
    assert [item["id"] for item in claimed] == [first["id"]]

    container.browser.complete_command(
        "worker-a",
        first["id"],
        {
            "final_url": "https://example.com/one",
            "title": "One",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
        },
    )
    claimed_next = container.browser.claim_commands("worker-b", limit=5)
    assert [item["id"] for item in claimed_next] == [second["id"]]


def test_browser_cancel_stops_active_worker_command_and_clears_claim(container, signed_client):
    settings = enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)
    command = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/cancel"),
    )
    container.browser.claim_commands("worker-a")

    client, headers = signed_client
    worker_headers = {"X-Shuddho-Browser-Worker-Token": settings.browser_worker_token}
    before = client.post(
        f'/api/v1/internal/browser-worker/commands/{command["id"]}/control',
        headers=worker_headers,
        json={"worker_id": "worker-a"},
    )
    assert before.status_code == 200
    assert before.json()["action"] == "continue"

    cancelled = container.browser.cancel(owner, session["id"])
    assert cancelled["state"] == "cancelled"
    assert cancelled["execution"]["worker_attached"] is False

    after = client.post(
        f'/api/v1/internal/browser-worker/commands/{command["id"]}/control',
        headers=worker_headers,
        json={"worker_id": "worker-a"},
    )
    assert after.status_code == 200
    assert after.json() == {"action": "stop", "reason": "session_cancelled"}

    with container.repository.sessions() as db:
        row = db.get(BrowserCommand, command["id"])
        assert row.state == "cancelled"
        assert row.error_code == "session_cancelled"
        assert row.claimed_by is None
        assert row.lease_until is None


def test_browser_takeover_pauses_active_worker_and_resume_does_not_revive_old_command(container, signed_client):
    settings = enable_browser(container)
    owner = account(container)
    session = create_session(container, owner)
    command = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/login"),
    )
    container.browser.claim_commands("worker-a")
    takeover = container.browser.request_takeover(owner, session["id"], "mfa")
    assert takeover["state"] == "takeover"
    assert takeover["execution"]["worker_attached"] is False

    client, headers = signed_client
    worker_headers = {"X-Shuddho-Browser-Worker-Token": settings.browser_worker_token}
    control = client.post(
        f'/api/v1/internal/browser-worker/commands/{command["id"]}/control',
        headers=worker_headers,
        json={"worker_id": "worker-a"},
    )
    assert control.status_code == 200
    assert control.json() == {"action": "pause", "reason": "takeover_requested"}

    resumed = container.browser.resume(owner, session["id"])
    assert resumed["state"] == "prepared"
    with container.repository.sessions() as db:
        old = db.get(BrowserCommand, command["id"])
        assert old.state == "cancelled"
        assert old.error_code == "takeover_requested"
        assert old.claimed_by is None

    next_command = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/after-mfa"),
    )
    claimed = container.browser.claim_commands("worker-b")
    assert [item["id"] for item in claimed] == [next_command["id"]]


def test_browser_form_preparation_is_same_origin_bounded_and_non_submitting(container, signed_client):
    settings = enable_browser(container)
    owner = account(container)
    session = container.browser.create(
        owner,
        BrowserSessionCreate(purpose="form_prepare", start_url="https://example.com/form"),
        "browser-form-prepare",
    )[0]

    command = container.browser.prepare_form(
        owner,
        session["id"],
        BrowserFormPrepareCreate(
            url="https://example.com/form",
            fields=[
                {"by": "label", "field": "Full name", "value": "Ada Lovelace"},
                {"by": "name", "field": "email", "value": "ada@example.com"},
            ],
        ),
    )
    assert command["kind"] == "prepare_form"
    assert command["policy"] == {"allow_form_submission": False, "field_count": 2}

    claimed = container.browser.claim_commands("worker-form")
    assert [item["id"] for item in claimed] == [command["id"]]
    assert claimed[0]["policy"]["allow_form_submission"] is False
    assert [item["field"] for item in claimed[0]["policy"]["fields"]] == ["Full name", "email"]

    completed = container.browser.complete_command(
        "worker-form",
        command["id"],
        {
            "final_url": "https://example.com/form",
            "title": "Form",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": ["Full name", "email"],
            "submission_performed": False,
        },
    )
    assert completed["state"] == "succeeded"
    assert completed["result"]["prepared_fields"] == ["Full name", "email"]
    assert completed["result"]["submission_performed"] is False
    with container.repository.sessions() as db:
        stored = db.get(BrowserCommand, command["id"])
        assert stored.payload["values_scrubbed"] is True
        assert stored.payload["fields"] == [
            {"by": "label", "field": "Full name"},
            {"by": "name", "field": "email"},
        ]

    client, headers = signed_client
    api_session = client.post(
        "/api/v1/browser-sessions",
        headers=headers() | {"Idempotency-Key": "browser-form-api"},
        json={"purpose": "form_prepare", "start_url": "https://example.com/form"},
    ).json()
    prepared = client.post(
        f'/api/v1/browser-sessions/{api_session["id"]}/prepare-form',
        headers=headers(),
        json={
            "url": "https://example.com/form",
            "fields": [{"by": "label", "field": "City", "value": "Dhaka"}],
        },
    )
    assert prepared.status_code == 202
    assert prepared.json()["policy"]["allow_form_submission"] is False
    container.browser.cancel(owner, api_session["id"])

    with pytest.raises(CoworkerError) as wrong_purpose:
        research = create_session(container, owner, key="browser-research-form-denied")
        container.browser.prepare_form(
            owner,
            research["id"],
            BrowserFormPrepareCreate(
                url="https://example.com/form",
                fields=[{"by": "label", "field": "Name", "value": "Ada"}],
            ),
        )
    assert wrong_purpose.value.code == "browser_form_not_allowed"

    with pytest.raises(CoworkerError) as cross_origin:
        container.browser.prepare_form(
            owner,
            session["id"],
            BrowserFormPrepareCreate(
                url="https://other.example/form",
                fields=[{"by": "label", "field": "Name", "value": "Ada"}],
            ),
        )
    assert cross_origin.value.code == "browser_origin_not_allowed"


def test_browser_form_preparation_requires_takeover_for_sensitive_fields(container):
    enable_browser(container)
    owner = account(container)
    session = container.browser.create(
        owner,
        BrowserSessionCreate(purpose="form_prepare", start_url="https://example.com/login"),
        "browser-form-sensitive",
    )[0]

    with pytest.raises(CoworkerError) as sensitive:
        container.browser.prepare_form(
            owner,
            session["id"],
            BrowserFormPrepareCreate(
                url="https://example.com/login",
                fields=[{"by": "label", "field": "Password", "value": "do-not-store"}],
            ),
        )
    assert sensitive.value.code == "sensitive_field_requires_takeover"

    with container.repository.sessions() as db:
        commands = db.scalars(
            select(BrowserCommand).where(BrowserCommand.session_id == session["id"])
        ).all()
        assert commands == []


def test_browser_form_completion_rejects_submission_or_mismatched_evidence(container):
    enable_browser(container)
    owner = account(container)

    session = container.browser.create(
        owner,
        BrowserSessionCreate(purpose="form_prepare", start_url="https://example.com/form"),
        "browser-form-evidence",
    )[0]
    command = container.browser.prepare_form(
        owner,
        session["id"],
        BrowserFormPrepareCreate(
            url="https://example.com/form",
            fields=[{"by": "label", "field": "Name", "value": "Ada"}],
        ),
    )
    container.browser.claim_commands("worker-form-a")
    with pytest.raises(CoworkerError) as mismatch:
        container.browser.complete_command(
            "worker-form-a",
            command["id"],
            {
                "final_url": "https://example.com/form",
                "title": "Form",
                "redirect_chain": [],
                "resolved_ips": {"example.com": ["93.184.216.34"]},
                "prepared_fields": [],
                "submission_performed": False,
            },
        )
    assert mismatch.value.code == "browser_form_evidence_mismatch"
    container.browser.fail_command("worker-form-a", command["id"], "form_field_not_found")

    session2 = container.browser.create(
        owner,
        BrowserSessionCreate(purpose="form_prepare", start_url="https://example.com/form"),
        "browser-form-submission",
    )[0]
    command2 = container.browser.prepare_form(
        owner,
        session2["id"],
        BrowserFormPrepareCreate(
            url="https://example.com/form",
            fields=[{"by": "label", "field": "Name", "value": "Ada"}],
        ),
    )
    container.browser.claim_commands("worker-form-b")
    with pytest.raises(CoworkerError) as submitted:
        container.browser.complete_command(
            "worker-form-b",
            command2["id"],
            {
                "final_url": "https://example.com/form",
                "title": "Form",
                "redirect_chain": [],
                "resolved_ips": {"example.com": ["93.184.216.34"]},
                "prepared_fields": ["Name"],
                "submission_performed": True,
            },
        )
    assert submitted.value.code == "browser_form_submission_blocked"


def test_browser_command_history_is_owner_scoped_and_sanitized(container, signed_client):
    enable_browser(container)
    owner = account(container)
    bob = account(container, "browser-history-bob")
    session = container.browser.create(
        owner,
        BrowserSessionCreate(purpose="form_prepare", start_url="https://example.com/form"),
        "browser-history-session",
    )[0]
    command = container.browser.prepare_form(
        owner,
        session["id"],
        BrowserFormPrepareCreate(
            url="https://example.com/form",
            fields=[{"by": "label", "field": "City", "value": "Dhaka"}],
        ),
    )

    history = container.browser.list_commands(owner, session["id"])
    assert history[0]["id"] == command["id"]
    assert "payload" not in history[0]
    assert "Dhaka" not in repr(history[0])

    with pytest.raises(CoworkerError) as denied:
        container.browser.list_commands(bob, session["id"])
    assert denied.value.status_code == 404

    client, headers = signed_client
    allowed = client.get(
        f'/api/v1/browser-sessions/{session["id"]}/commands',
        headers=headers(),
    )
    assert allowed.status_code == 200
    assert allowed.json()["commands"][0]["id"] == command["id"]
    assert "Dhaka" not in allowed.text

    denied_api = client.get(
        f'/api/v1/browser-sessions/{session["id"]}/commands',
        headers=headers("browser-history-bob"),
    )
    assert denied_api.status_code == 404


def test_browser_session_state_is_encrypted_reused_and_cleared(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, key="browser-continuity")
    first = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/login"),
    )
    claimed = container.browser.claim_commands("worker-continuity-a")
    assert claimed[0]["id"] == first["id"]
    assert claimed[0]["storage_state"] is None
    assert claimed[0]["storage_state_version"] == 0

    state = {
        "cookies": [{
            "name": "session",
            "value": "secret-cookie-value",
            "domain": ".example.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }],
        "origins": [{
            "origin": "https://example.com",
            "localStorage": [{"name": "session_hint", "value": "opaque-session-value"}],
        }],
    }
    completed = container.browser.complete_command(
        "worker-continuity-a",
        first["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Signed in",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "storage_state": state,
        },
    )
    assert completed["state"] == "succeeded"
    current = container.browser.get(owner, session["id"])
    assert current["execution"]["authenticated_state_available"] is True
    assert current["execution"]["storage_state_version"] == 1

    with container.repository.sessions() as db:
        stored = db.get(BrowserSession, session["id"])
        assert stored.storage_state_sealed
        assert "secret-cookie-value" not in stored.storage_state_sealed
        assert "opaque-session-value" not in stored.storage_state_sealed

    second = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/account"),
    )
    claimed_again = container.browser.claim_commands("worker-continuity-b")
    assert claimed_again[0]["id"] == second["id"]
    assert claimed_again[0]["storage_state"] == state
    assert claimed_again[0]["storage_state_version"] == 1

    container.browser.complete_command(
        "worker-continuity-b",
        second["id"],
        {
            "final_url": "https://example.com/account",
            "title": "Account",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "storage_state": state,
        },
    )
    assert container.browser.get(owner, session["id"])["execution"]["storage_state_version"] == 2

    cancelled = container.browser.cancel(owner, session["id"])
    assert cancelled["execution"]["authenticated_state_available"] is False
    assert cancelled["execution"]["storage_state_version"] == 0
    with container.repository.sessions() as db:
        stored = db.get(BrowserSession, session["id"])
        assert stored.storage_state_sealed is None
        assert stored.storage_state_updated_at is None


def test_browser_session_state_rejects_cross_origin_or_oversized_secrets(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, key="browser-continuity-invalid")
    command = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/start"),
    )
    container.browser.claim_commands("worker-continuity-invalid")

    with pytest.raises(CoworkerError) as cross_origin:
        container.browser.complete_command(
            "worker-continuity-invalid",
            command["id"],
            {
                "final_url": "https://example.com/start",
                "title": "Example",
                "redirect_chain": [],
                "resolved_ips": {"example.com": ["93.184.216.34"]},
                "storage_state": {
                    "cookies": [{"name": "session", "value": "x", "domain": "evil.example", "path": "/"}],
                    "origins": [],
                },
            },
        )
    assert cross_origin.value.code == "browser_storage_state_invalid"
    container.browser.fail_command("worker-continuity-invalid", command["id"], "navigation_failed")

    session2 = create_session(container, owner, key="browser-continuity-large")
    command2 = container.browser.prepare_navigation(
        owner,
        session2["id"],
        BrowserNavigateCreate(url="https://example.com/start"),
    )
    container.browser.claim_commands("worker-continuity-large")
    with pytest.raises(CoworkerError) as too_large:
        container.browser.complete_command(
            "worker-continuity-large",
            command2["id"],
            {
                "final_url": "https://example.com/start",
                "title": "Example",
                "redirect_chain": [],
                "resolved_ips": {"example.com": ["93.184.216.34"]},
                "storage_state": {
                    "cookies": [{"name": "session", "value": "x" * 70000, "domain": "example.com", "path": "/"}],
                    "origins": [],
                },
            },
        )
    assert too_large.value.code == "browser_storage_state_too_large"
    container.browser.fail_command("worker-continuity-large", command2["id"], "navigation_failed")


def test_browser_session_ciphertext_cannot_be_replayed_into_another_session(container):
    enable_browser(container)
    owner = account(container)
    first = create_session(container, owner, key="browser-binding-first")
    command = container.browser.prepare_navigation(
        owner,
        first["id"],
        BrowserNavigateCreate(url="https://example.com/start"),
    )
    container.browser.claim_commands("worker-binding-first")
    container.browser.complete_command(
        "worker-binding-first",
        command["id"],
        {
            "final_url": "https://example.com/start",
            "title": "Example",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "storage_state": {
                "cookies": [{"name": "session", "value": "secret", "domain": "example.com", "path": "/"}],
                "origins": [],
            },
        },
    )

    second = create_session(container, owner, key="browser-binding-second")
    second_command = container.browser.prepare_navigation(
        owner,
        second["id"],
        BrowserNavigateCreate(url="https://example.com/start"),
    )
    with container.repository.sessions.begin() as db:
        source = db.get(BrowserSession, first["id"])
        target = db.get(BrowserSession, second["id"])
        target.storage_state_sealed = source.storage_state_sealed
        target.storage_state_version = source.storage_state_version

    with pytest.raises(CoworkerError) as replay:
        container.browser.claim_commands("worker-binding-second")
    assert replay.value.code == "browser_storage_unavailable"

    with container.repository.sessions() as db:
        stored = db.get(BrowserCommand, second_command["id"])
        assert stored.state == "prepared"
        assert stored.claimed_by is None


def test_browser_session_expiry_destroys_encrypted_state(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, key="browser-continuity-expiry")
    command = container.browser.prepare_navigation(
        owner,
        session["id"],
        BrowserNavigateCreate(url="https://example.com/start"),
    )
    container.browser.claim_commands("worker-continuity-expiry")
    container.browser.complete_command(
        "worker-continuity-expiry",
        command["id"],
        {
            "final_url": "https://example.com/start",
            "title": "Example",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "storage_state": {
                "cookies": [{"name": "session", "value": "secret", "domain": "example.com", "path": "/"}],
                "origins": [],
            },
        },
    )

    with container.repository.sessions.begin() as db:
        row = db.get(BrowserSession, session["id"])
        row.expires_at = utcnow() - timedelta(seconds=1)

    expired = container.browser.get(owner, session["id"])
    assert expired["state"] == "expired"
    assert expired["execution"]["authenticated_state_available"] is False
    with container.repository.sessions() as db:
        row = db.get(BrowserSession, session["id"])
        assert row.storage_state_sealed is None
        assert row.cancel_requested is True


def test_browser_takeover_secret_is_encrypted_worker_only_and_resumes(container, signed_client):
    settings = enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-takeover-secret")
    container.browser.request_takeover(owner, session["id"], "login")

    prepared = container.browser.prepare_takeover_input(
        owner,
        session["id"],
        BrowserTakeoverInputCreate(
            by="label",
            field="Password",
            value="correct-horse-battery-staple",
            submit=True,
        ),
    )
    assert prepared["kind"] == "takeover_input"
    assert prepared["policy"]["secret_concealed"] is True

    with container.repository.sessions() as db:
        command = db.get(BrowserCommand, prepared["id"])
        assert command.secret_sealed
        assert "correct-horse-battery-staple" not in command.secret_sealed

    client, headers = signed_client
    history = client.get(
        f'/api/v1/browser-sessions/{session["id"]}/commands',
        headers=headers(),
    )
    assert history.status_code == 200
    assert "correct-horse-battery-staple" not in history.text
    assert "secret_sealed" not in history.text

    claimed = container.browser.claim_commands("worker-takeover")
    assert [item["id"] for item in claimed] == [prepared["id"]]
    assert claimed[0]["takeover_input"] == {
        "by": "label",
        "field": "Password",
        "value": "correct-horse-battery-staple",
        "submit": True,
    }

    checked = container.browser.validate_worker_network_target(
        "worker-takeover",
        prepared["id"],
        "https://example.com/login",
        ["93.184.216.34"],
    )
    assert checked["origin"] == "https://example.com"

    completed = container.browser.complete_command(
        "worker-takeover",
        prepared["id"],
        {
            "final_url": "https://example.com/account",
            "title": "Account",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": ["Password"],
            "submission_performed": True,
            "storage_state": {
                "cookies": [{"name": "session", "value": "signed-in", "domain": "example.com", "path": "/"}],
                "origins": [],
            },
        },
    )
    assert completed["state"] == "succeeded"
    assert completed["result"]["submission_performed"] is True
    current = container.browser.get(owner, session["id"])
    assert current["state"] == "prepared"
    assert current["takeover_required"] is False
    assert current["takeover_reason"] is None
    assert current["execution"]["authenticated_state_available"] is True

    with container.repository.sessions() as db:
        command = db.get(BrowserCommand, prepared["id"])
        assert command.secret_sealed is None


def test_browser_takeover_input_requires_active_owner_takeover(container, signed_client):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, key="browser-takeover-owner")

    with pytest.raises(CoworkerError) as inactive:
        container.browser.prepare_takeover_input(
            owner,
            session["id"],
            BrowserTakeoverInputCreate(by="name", field="otp", value="123456", submit=True),
        )
    assert inactive.value.code == "browser_takeover_not_active"

    container.browser.request_takeover(owner, session["id"], "mfa")
    client, headers = signed_client
    denied = client.post(
        f'/api/v1/browser-sessions/{session["id"]}/takeover-input',
        headers=headers("browser-takeover-bob"),
        json={"by": "name", "field": "otp", "value": "123456", "submit": True},
    )
    assert denied.status_code == 404

    accepted = client.post(
        f'/api/v1/browser-sessions/{session["id"]}/takeover-input',
        headers=headers(),
        json={"by": "name", "field": "otp", "value": "123456", "submit": True},
    )
    assert accepted.status_code == 202
    assert "123456" not in accepted.text


def test_browser_captcha_takeover_refuses_secret_injection(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, key="browser-takeover-captcha")
    current = container.browser.request_takeover(owner, session["id"], "captcha")
    assert current["takeover_reason"] == "captcha"

    with pytest.raises(CoworkerError) as blocked:
        container.browser.prepare_takeover_input(
            owner,
            session["id"],
            BrowserTakeoverInputCreate(by="label", field="Captcha", value="abcd", submit=True),
        )
    assert blocked.value.code == "browser_captcha_requires_interactive_takeover"


def test_browser_cancel_clears_pending_takeover_secret(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, key="browser-takeover-cancel")
    container.browser.request_takeover(owner, session["id"], "mfa")
    prepared = container.browser.prepare_takeover_input(
        owner,
        session["id"],
        BrowserTakeoverInputCreate(by="name", field="otp", value="654321", submit=False),
    )
    with container.repository.sessions() as db:
        assert db.get(BrowserCommand, prepared["id"]).secret_sealed

    cancelled = container.browser.cancel(owner, session["id"])
    assert cancelled["state"] == "cancelled"
    assert cancelled["takeover_reason"] is None
    with container.repository.sessions() as db:
        command = db.get(BrowserCommand, prepared["id"])
        assert command.secret_sealed is None
        assert command.state == "cancelled"


def test_visual_takeover_frame_is_encrypted_owner_only_and_destroyed_on_resume(container, signed_client):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-visual-takeover")
    takeover = container.browser.request_takeover(owner, session["id"], "captcha")
    assert takeover["takeover_required"] is True
    assert takeover["execution"]["takeover_frame_available"] is False

    prepared = container.browser.prepare_takeover_frame(owner, session["id"])
    assert prepared["kind"] == "takeover_frame"
    claimed = container.browser.claim_commands("worker-visual-takeover")
    assert [item["id"] for item in claimed] == [prepared["id"]]
    assert claimed[0]["takeover_input"] is None

    jpeg = b"\xff\xd8\xff\xe0" + (b"visual-frame" * 20) + b"\xff\xd9"
    completed = container.browser.complete_command(
        "worker-visual-takeover",
        prepared["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Sign in",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
        },
    )
    assert completed["state"] == "succeeded"
    current = container.browser.get(owner, session["id"])
    assert current["state"] == "takeover"
    assert current["takeover_required"] is True
    assert current["execution"]["takeover_frame_available"] is True
    assert current["execution"]["takeover_frame_version"] == 1
    assert current["execution"]["takeover_live_context_available"] is True
    assert current["execution"]["takeover_live_context_expires_at"] is not None

    with container.repository.sessions() as db:
        stored = db.get(BrowserSession, session["id"])
        assert stored.takeover_frame_sealed
        assert base64.b64encode(jpeg).decode("ascii") not in stored.takeover_frame_sealed
        assert stored.takeover_frame_byte_size == len(jpeg)

    client, headers = signed_client
    visible = client.get(
        f'/api/v1/browser-sessions/{session["id"]}/takeover-frame',
        headers=headers(),
    )
    assert visible.status_code == 200
    assert visible.headers["content-type"].startswith("image/jpeg")
    assert visible.headers["cache-control"] == "no-store"
    assert visible.headers["x-content-type-options"] == "nosniff"
    assert visible.headers["x-shuddho-browser-frame-version"] == "1"
    assert visible.content == jpeg

    denied = client.get(
        f'/api/v1/browser-sessions/{session["id"]}/takeover-frame',
        headers=headers("visual-frame-bob"),
    )
    assert denied.status_code == 404

    resumed = container.browser.resume(owner, session["id"])
    assert resumed["execution"]["takeover_frame_available"] is False
    assert resumed["execution"]["takeover_live_context_available"] is False
    with container.repository.sessions() as db:
        stored = db.get(BrowserSession, session["id"])
        assert stored.takeover_frame_sealed is None
        assert stored.takeover_frame_version == 0


def test_visual_takeover_frame_rejects_mutation_or_non_jpeg_evidence(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-visual-invalid")
    container.browser.request_takeover(owner, session["id"], "login")
    prepared = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-visual-invalid")

    with pytest.raises(CoworkerError) as invalid:
        container.browser.complete_command(
            "worker-visual-invalid",
            prepared["id"],
            {
                "final_url": "https://example.com/login",
                "title": "Sign in",
                "redirect_chain": [],
                "resolved_ips": {"example.com": ["93.184.216.34"]},
                "prepared_fields": [],
                "submission_performed": False,
                "takeover_frame_b64": base64.b64encode(b"not-a-jpeg").decode("ascii"),
                "takeover_frame_content_type": "image/jpeg",
            },
        )
    assert invalid.value.code == "browser_takeover_frame_invalid"


def test_human_takeover_interaction_is_owner_scoped_and_frame_bound(container, signed_client):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-human-interaction")
    container.browser.request_takeover(owner, session["id"], "captcha")

    frame_command = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-human-frame")
    first_jpeg = b"\xff\xd8\xff\xe0" + (b"first-human-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-human-frame",
        frame_command["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(first_jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )

    prepared = container.browser.prepare_takeover_interaction(
        owner,
        session["id"],
        BrowserTakeoverInteractionCreate(
            frame_version=1,
            kind="click",
            x=0.25,
            y=0.75,
        ),
    )
    assert prepared["kind"] == "takeover_interaction"
    assert prepared["policy"] == {
        "human_only": True,
        "frame_version": 1,
        "interaction_kind": "click",
    }

    client, headers = signed_client
    denied = client.post(
        f'/api/v1/browser-sessions/{session["id"]}/takeover-interaction',
        headers=headers("human-interaction-bob"),
        json={"frame_version": 1, "kind": "click", "x": 0.1, "y": 0.1},
    )
    assert denied.status_code == 404

    wrong_worker = container.browser.claim_commands("worker-human-click")
    assert wrong_worker == []
    claimed = container.browser.claim_commands("worker-human-frame")
    assert [item["id"] for item in claimed] == [prepared["id"]]
    assert claimed[0]["policy"]["human_only"] is True
    assert claimed[0]["policy"]["expected_frame_version"] == 1
    assert claimed[0]["policy"]["expected_frame_sha256"] == hashlib.sha256(first_jpeg).hexdigest()
    assert claimed[0]["policy"]["interaction"] == {
        "kind": "click",
        "x": 0.25,
        "y": 0.75,
        "key": None,
    }

    checked = container.browser.validate_worker_network_target(
        "worker-human-frame",
        prepared["id"],
        "https://example.com/login",
        ["93.184.216.34"],
    )
    assert checked["origin"] == "https://example.com"

    second_jpeg = b"\xff\xd8\xff\xe0" + (b"second-human-frame" * 18) + b"\xff\xd9"
    completed = container.browser.complete_command(
        "worker-human-frame",
        prepared["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge updated",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(second_jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": True,
        },
    )
    assert completed["state"] == "succeeded"
    assert completed["result"]["interaction_performed"] is True
    assert completed["result"]["takeover_frame_version"] == 2

    current = container.browser.get(owner, session["id"])
    assert current["state"] == "takeover"
    assert current["takeover_required"] is True
    assert current["execution"]["takeover_frame_version"] == 2
    assert current["execution"]["takeover_live_context_available"] is True
    assert current["execution"]["takeover_live_context_expires_at"] is not None

    visible = client.get(
        f'/api/v1/browser-sessions/{session["id"]}/takeover-frame',
        headers=headers(),
    )
    assert visible.status_code == 200
    assert visible.content == second_jpeg

    with pytest.raises(CoworkerError) as stale:
        container.browser.prepare_takeover_interaction(
            owner,
            session["id"],
            BrowserTakeoverInteractionCreate(frame_version=1, kind="key", key="Tab"),
        )
    assert stale.value.code == "browser_takeover_frame_stale"


def test_human_takeover_interaction_failure_clears_stale_visual_frame(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-human-stale")
    container.browser.request_takeover(owner, session["id"], "captcha")
    frame_command = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-human-stale-frame")
    jpeg = b"\xff\xd8\xff\xe0" + (b"stale-human-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-human-stale-frame",
        frame_command["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )
    prepared = container.browser.prepare_takeover_interaction(
        owner,
        session["id"],
        BrowserTakeoverInteractionCreate(frame_version=1, kind="key", key="Escape"),
    )
    assert container.browser.claim_commands("worker-human-stale") == []
    container.browser.claim_commands("worker-human-stale-frame")
    failed = container.browser.fail_command(
        "worker-human-stale-frame",
        prepared["id"],
        "takeover_frame_stale",
    )
    assert failed["state"] == "failed"
    assert failed["error_code"] == "takeover_frame_stale"
    current = container.browser.get(owner, session["id"])
    assert current["state"] == "takeover"
    assert current["takeover_required"] is True
    assert current["execution"]["takeover_frame_available"] is False
    assert current["execution"]["takeover_frame_version"] == 0


def test_human_takeover_interaction_requires_exact_input_shape(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-human-shape")
    container.browser.request_takeover(owner, session["id"], "mfa")
    frame_command = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-human-shape-frame")
    jpeg = b"\xff\xd8\xff\xe0" + (b"shape-human-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-human-shape-frame",
        frame_command["id"],
        {
            "final_url": "https://example.com/login",
            "title": "MFA",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )

    with pytest.raises(CoworkerError) as invalid_click:
        container.browser.prepare_takeover_interaction(
            owner,
            session["id"],
            BrowserTakeoverInteractionCreate(frame_version=1, kind="click", x=0.4, y=0.5, key="Tab"),
        )
    assert invalid_click.value.code == "browser_takeover_interaction_invalid"

    with pytest.raises(CoworkerError) as invalid_key:
        container.browser.prepare_takeover_interaction(
            owner,
            session["id"],
            BrowserTakeoverInteractionCreate(frame_version=1, kind="key", key="Tab", x=0.5),
        )
    assert invalid_key.value.code == "browser_takeover_interaction_invalid"


def test_human_takeover_interaction_is_at_most_once_after_worker_lease_loss(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-human-at-most-once")
    container.browser.request_takeover(owner, session["id"], "captcha")
    frame_command = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-at-most-once-frame")
    jpeg = b"\xff\xd8\xff\xe0" + (b"at-most-once-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-at-most-once-frame",
        frame_command["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )
    prepared = container.browser.prepare_takeover_interaction(
        owner,
        session["id"],
        BrowserTakeoverInteractionCreate(frame_version=1, kind="click", x=0.5, y=0.5),
    )
    assert container.browser.claim_commands("worker-at-most-once-a") == []
    claimed = container.browser.claim_commands("worker-at-most-once-frame")
    assert [item["id"] for item in claimed] == [prepared["id"]]

    with container.repository.sessions.begin() as db:
        command = db.get(BrowserCommand, prepared["id"])
        command.lease_until = utcnow() - timedelta(seconds=1)

    reclaimed = container.browser.claim_commands("worker-at-most-once-b")
    assert reclaimed == []
    with container.repository.sessions() as db:
        command = db.get(BrowserCommand, prepared["id"])
        stored = db.get(BrowserSession, session["id"])
        assert command.state == "failed"
        assert command.error_code == "takeover_interaction_uncertain"
        assert command.attempts == 1
        assert stored.state == "takeover"
        assert stored.takeover_required is True
        assert stored.takeover_frame_sealed is None


def test_human_takeover_interaction_api_accepts_owner_frame_version(container, signed_client):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-human-api")
    container.browser.request_takeover(owner, session["id"], "captcha")
    frame_command = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-human-api-frame")
    jpeg = b"\xff\xd8\xff\xe0" + (b"api-human-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-human-api-frame",
        frame_command["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )
    client, headers = signed_client
    accepted = client.post(
        f'/api/v1/browser-sessions/{session["id"]}/takeover-interaction',
        headers=headers(),
        json={"frame_version": 1, "kind": "key", "key": "Tab"},
    )
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["kind"] == "takeover_interaction"
    assert body["policy"] == {
        "human_only": True,
        "frame_version": 1,
        "interaction_kind": "key",
    }


def test_takeover_affinity_heartbeat_routes_only_to_bound_worker(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-affinity-route")
    container.browser.request_takeover(owner, session["id"], "captcha")
    first = container.browser.prepare_takeover_frame(owner, session["id"])
    claimed = container.browser.claim_commands("worker-affinity-a")
    assert [item["id"] for item in claimed] == [first["id"]]
    jpeg = b"\xff\xd8\xff\xe0" + (b"affinity-route-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-affinity-a",
        first["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )

    current = container.browser.get(owner, session["id"])
    assert current["execution"]["takeover_live_context_available"] is True
    with container.repository.sessions() as db:
        stored = db.get(BrowserSession, session["id"])
        assert stored.takeover_worker_ref == "worker-affinity-a"
        first_expiry = stored.takeover_worker_lease_until
        assert first_expiry is not None

    heartbeat = container.browser.heartbeat_takeover_contexts(
        "worker-affinity-a",
        [session["id"], session["id"]],
    )
    assert heartbeat == {
        "keep_session_ids": [session["id"]],
        "release_session_ids": [],
    }

    interaction = container.browser.prepare_takeover_interaction(
        owner,
        session["id"],
        BrowserTakeoverInteractionCreate(frame_version=1, kind="key", key="Tab"),
    )
    assert container.browser.claim_commands("worker-affinity-b") == []
    same_worker = container.browser.claim_commands("worker-affinity-a")
    assert [item["id"] for item in same_worker] == [interaction["id"]]


def test_takeover_affinity_expiry_fails_prepared_interaction_closed(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-affinity-expiry")
    container.browser.request_takeover(owner, session["id"], "captcha")
    first = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-affinity-expiry-a")
    jpeg = b"\xff\xd8\xff\xe0" + (b"affinity-expiry-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-affinity-expiry-a",
        first["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )
    interaction = container.browser.prepare_takeover_interaction(
        owner,
        session["id"],
        BrowserTakeoverInteractionCreate(frame_version=1, kind="click", x=0.5, y=0.5),
    )

    with container.repository.sessions.begin() as db:
        stored = db.get(BrowserSession, session["id"])
        stored.takeover_worker_lease_until = utcnow() - timedelta(seconds=1)

    assert container.browser.claim_commands("worker-affinity-expiry-b") == []
    with container.repository.sessions() as db:
        stored = db.get(BrowserSession, session["id"])
        command = db.get(BrowserCommand, interaction["id"])
        assert command.state == "failed"
        assert command.error_code == "takeover_context_missing"
        assert stored.state == "takeover"
        assert stored.takeover_required is True
        assert stored.takeover_worker_ref is None
        assert stored.takeover_worker_lease_until is None
        assert stored.takeover_frame_sealed is None

    current = container.browser.get(owner, session["id"])
    assert current["execution"]["takeover_live_context_available"] is False
    assert current["execution"]["takeover_frame_available"] is False


def test_takeover_frame_refresh_requires_same_live_worker(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-affinity-refresh")
    container.browser.request_takeover(owner, session["id"], "captcha")
    first = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-affinity-refresh-a")
    jpeg = b"\xff\xd8\xff\xe0" + (b"affinity-refresh-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-affinity-refresh-a",
        first["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )

    refresh = container.browser.prepare_takeover_frame(owner, session["id"])
    with container.repository.sessions() as db:
        command = db.get(BrowserCommand, refresh["id"])
        assert command.payload["require_live_context"] is True
    assert container.browser.claim_commands("worker-affinity-refresh-b") == []
    same_worker = container.browser.claim_commands("worker-affinity-refresh-a")
    assert [item["id"] for item in same_worker] == [refresh["id"]]


def test_takeover_heartbeat_releases_wrong_worker_and_cancel_clears_affinity(container):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-affinity-cancel")
    container.browser.request_takeover(owner, session["id"], "captcha")
    first = container.browser.prepare_takeover_frame(owner, session["id"])
    container.browser.claim_commands("worker-affinity-cancel-a")
    jpeg = b"\xff\xd8\xff\xe0" + (b"affinity-cancel-frame" * 18) + b"\xff\xd9"
    container.browser.complete_command(
        "worker-affinity-cancel-a",
        first["id"],
        {
            "final_url": "https://example.com/login",
            "title": "Challenge",
            "redirect_chain": [],
            "resolved_ips": {"example.com": ["93.184.216.34"]},
            "prepared_fields": [],
            "submission_performed": False,
            "storage_state": None,
            "takeover_frame_b64": base64.b64encode(jpeg).decode("ascii"),
            "takeover_frame_content_type": "image/jpeg",
            "interaction_performed": False,
        },
    )

    wrong = container.browser.heartbeat_takeover_contexts(
        "worker-affinity-cancel-b",
        [session["id"]],
    )
    assert wrong == {
        "keep_session_ids": [],
        "release_session_ids": [session["id"]],
    }

    cancelled = container.browser.cancel(owner, session["id"])
    assert cancelled["state"] == "cancelled"
    assert cancelled["execution"]["takeover_live_context_available"] is False
    with container.repository.sessions() as db:
        stored = db.get(BrowserSession, session["id"])
        assert stored.takeover_worker_ref is None
        assert stored.takeover_worker_lease_until is None


def test_webauthn_takeover_is_read_only_and_fails_closed(container, signed_client):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-webauthn-boundary")

    client, headers = signed_client
    response = client.post(
        f'/api/v1/browser-sessions/{session["id"]}/takeover',
        headers=headers(),
        json={"reason": "webauthn"},
    )
    assert response.status_code == 200
    assert response.json()["takeover_required"] is True
    assert response.json()["takeover_reason"] == "webauthn"

    frame = container.browser.prepare_takeover_frame(owner, session["id"])
    assert frame["kind"] == "takeover_frame"
    assert frame["policy"] == {"allow_mutation": False}

    with pytest.raises(CoworkerError) as secret:
        container.browser.prepare_takeover_input(
            owner,
            session["id"],
            BrowserTakeoverInputCreate(
                by="label",
                field="Passkey",
                value="do-not-inject",
                submit=True,
            ),
        )
    assert secret.value.code == "browser_webauthn_requires_external_authenticator"

    with pytest.raises(CoworkerError) as interaction:
        container.browser.prepare_takeover_interaction(
            owner,
            session["id"],
            BrowserTakeoverInteractionCreate(
                frame_version=1,
                kind="key",
                key="Tab",
            ),
        )
    assert interaction.value.code == "browser_webauthn_requires_external_authenticator"


def test_webauthn_takeover_rejects_unknown_takeover_reason(container, signed_client):
    enable_browser(container)
    owner = account(container)
    session = create_session(container, owner, url="https://example.com/login", key="browser-webauthn-schema")
    client, headers = signed_client

    rejected = client.post(
        f'/api/v1/browser-sessions/{session["id"]}/takeover',
        headers=headers(),
        json={"reason": "virtual_authenticator"},
    )
    assert rejected.status_code == 422
