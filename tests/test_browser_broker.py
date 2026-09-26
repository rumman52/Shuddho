from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from action_samples import enable_actions
from test_coworker import account, container, signed_client

from services.coworker.browser import BrowserRepository, normalize_browser_target
from services.coworker.browser_schemas import BrowserNavigateCreate, BrowserSessionCreate
from services.coworker.errors import CoworkerError
from services.coworker.models import BrowserSession, utcnow


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
