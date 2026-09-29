from __future__ import annotations

import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from services.coworker.api import mount
from services.coworker.auth import JwtVerifier
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.errors import CoworkerError
from services.coworker.migrate import upgrade
from services.coworker.models import Account, AgentRun, Automation, AutomationOccurrence, AutomationScheduleOutbox, Notification, NotificationOutbox, PersonalGoal, utcnow

ISSUER = "https://identity.example.test/auth/v1"


@pytest.fixture
def automation_container(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'automations.sqlite3'}",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        personal_goals_enabled=True,
        agent_runtime_enabled=True,
        automations_enabled=True,
    )
    upgrade(settings.database_url)
    result = Container.create(settings)
    yield result
    result.repository.sessions.kw["bind"].dispose()


@pytest.fixture
def automation_client(automation_container):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {
        "kid": "test-key", "alg": "RS256", "use": "sig"
    }
    automation_container.verifier = JwtVerifier(
        ISSUER, "authenticated",
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"keys": [jwk]})),
    )
    app = FastAPI(); mount(app, automation_container)

    def headers(subject="alice"):
        claims = {
            "iss": ISSUER, "sub": subject, "aud": "authenticated", "role": "authenticated",
            "iat": int(time.time()) - 1, "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})
        return {"Authorization": "Bearer " + token}

    with TestClient(app) as client:
        yield client, headers


def goal_payload():
    return {
        "objective": "Prepare a short daily study briefing.",
        "success_criteria": ["Produce one useful bounded briefing."],
        "constraints": ["Do not send anything externally."],
        "deadline_at": None, "timezone": "Asia/Dhaka", "state": "active",
        "milestones": [], "budget": {"max_runs": 10, "max_planner_tokens": 50000},
        "authorized_resources": [], "next_review_at": None,
    }


def create_delivered_digest(client, headers, container):
    auth = headers()
    for index in range(2):
        body = goal_payload()
        body["next_review_at"] = (utcnow() - timedelta(minutes=5)).isoformat()
        response = client.post("/api/v1/goals", headers=auth | {"Idempotency-Key": f"digest-goal-{index}"}, json=body)
        assert response.status_code == 201
    response = client.put("/api/v1/personal-suggestion-preferences", headers=auth,
                          json={"enabled": True, "delivery_enabled": True})
    assert response.status_code == 200
    with container.repository.sessions.begin() as db:
        owner = db.scalar(select(Account).where(Account.subject == "alice")).id
        now = utcnow()
        visible = now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0)
        rows = db.scalars(select(Notification).where(Notification.owner_id == owner)).all()
        assert len(rows) == 2
        for row in rows:
            row.visible_at = visible
    claimed = container.notifications.claim_notifications()
    assert len(claimed) == 2
    for notification_id in claimed:
        container.notifications.deliver_notification(notification_id)
    response = client.get("/api/v1/notification-digests", headers=auth)
    assert response.status_code == 200
    assert len(response.json()["digests"]) == 1
    return auth, owner, response.json()["digests"][0]


def test_notification_digest_restart_exact_read_and_owner_isolation(automation_client, automation_container):
    client, headers = automation_client
    auth, owner, digest = create_delivered_digest(client, headers, automation_container)
    ids = [item["id"] for item in digest["notifications"]]
    assert digest["count"] == digest["unread_count"] == 2
    assert len(client.get("/api/v1/notifications", headers=auth).json()["notifications"]) == 2
    restarted = Container.create(automation_container.settings)
    try:
        assert restarted.notifications.notification_digests(owner) == [digest]
    finally:
        restarted.repository.sessions.kw["bind"].dispose()
    bob = headers("bob")
    assert client.get("/api/v1/notification-digests", headers=bob).json()["digests"] == []
    route = f'/api/v1/notification-digests/{digest["id"]}/read'
    assert client.post(route, headers=bob, json={"notification_ids": ids}).status_code == 404
    # A previously read member retains its original read receipt when the group is read.
    single = digest["notifications"][0]
    first_response = client.post(f'/api/v1/notification-digests/{single["read_digest_id"]}/read',
                                 headers=auth, json={"notification_ids": [single["id"]]})
    assert first_response.status_code == 200
    first = first_response.json()["notifications"][0]
    result = client.post(route, headers=auth, json={"notification_ids": list(reversed(ids))})
    assert result.status_code == 200
    read_members = {item["id"]: item for item in result.json()["notifications"]}
    assert read_members[ids[0]]["read_at"] == first["read_at"]
    replay = client.post(route, headers=auth, json={"notification_ids": ids})
    assert replay.json() == result.json()
    assert client.get("/api/v1/notification-digests", headers=auth).json()["digests"][0]["unread_count"] == 0
    with automation_container.repository.sessions() as db:
        assert len(db.scalars(select(Notification).where(Notification.owner_id == owner)).all()) == 2
        assert len(db.scalars(select(NotificationOutbox)).all()) == 2
        assert db.scalars(select(AgentRun).where(AgentRun.owner_id == owner)).all() == []
        assert db.scalars(select(Automation).where(Automation.owner_id == owner)).all() == []


@pytest.mark.parametrize("change", ["expired", "pending", "revised", "dismissed", "opt_out", "delivery_opt_out", "unknown_source", "missing_source"])
def test_notification_digest_rechecks_every_member_atomically(automation_client, automation_container, change):
    client, headers = automation_client
    auth, owner, digest = create_delivered_digest(client, headers, automation_container)
    ids = [item["id"] for item in digest["notifications"]]
    if change == "opt_out":
        response = client.put("/api/v1/notification-preferences", headers=auth,
                              json={"in_app_enabled": False, "automation_updates_enabled": True})
        assert response.status_code == 200
    elif change == "delivery_opt_out":
        response = client.put("/api/v1/personal-suggestion-preferences", headers=auth,
                              json={"enabled": True, "delivery_enabled": False})
        assert response.status_code == 200
    else:
        with automation_container.repository.sessions.begin() as db:
            row = db.get(Notification, ids[0])
            if change == "expired":
                row.expires_at = utcnow() - timedelta(seconds=1)
            elif change == "pending":
                row.state = "pending"
            elif change == "revised":
                goal = db.scalar(select(PersonalGoal).where(PersonalGoal.owner_id == owner))
                goal.revision += 1
            elif change == "dismissed":
                account = db.get(Account, owner)
                prefs = dict(account.preferences)
                prefs["personal_suggestions"] = dict(prefs["personal_suggestions"], dismissed_ids=[row.source_id])
                account.preferences = prefs
            elif change == "unknown_source":
                row.source_kind = "unregistered_source"
            elif change == "missing_source":
                row.source_kind = None
                row.source_id = None
    route = f'/api/v1/notification-digests/{digest["id"]}/read'
    response = client.post(route, headers=auth, json={"notification_ids": ids})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "notification_digest_changed"
    with automation_container.repository.sessions() as db:
        assert all(db.get(Notification, value).read_at is None for value in ids)
        assert all(db.get(Notification, value).state != "read" for value in ids)
    remaining = client.get("/api/v1/notification-digests", headers=auth).json()["digests"]
    assert sum(item["count"] for item in remaining) < 2
    valid_ids = {member["id"] for item in remaining for member in item["notifications"]}
    for item in digest["notifications"]:
        member_response = client.post(f'/api/v1/notification-digests/{item["read_digest_id"]}/read',
                                      headers=auth, json={"notification_ids": [item["id"]]})
        assert member_response.status_code == (200 if item["id"] in valid_ids else 409)


def test_notification_digest_requests_are_strict_bounded_and_identity_bound(automation_client, automation_container):
    client, headers = automation_client
    auth, _, digest = create_delivered_digest(client, headers, automation_container)
    ids = [item["id"] for item in digest["notifications"]]
    route = f'/api/v1/notification-digests/{digest["id"]}/read'
    for payload in [{"notification_ids": []}, {"notification_ids": ids * 6},
                    {"notification_ids": [ids[0], ids[0]]}, {"notification_ids": ["invalid"]},
                    {"notification_ids": ids, "owner_id": "bob"}]:
        assert client.post(route, headers=auth, json=payload).status_code == 422
    assert client.post("/api/v1/notification-digests/not-a-digest/read", headers=auth,
                       json={"notification_ids": ids}).status_code == 422
    assert client.post(route, headers=auth, json={"notification_ids": ids[:1]}).status_code == 409
    assert client.post(f'/api/v1/notification-digests/{"0" * 64}/read', headers=auth,
                       json={"notification_ids": ids}).status_code == 409
    disabled = replace(automation_container.settings, automations_enabled=False)
    automation_container.settings = disabled
    automation_container.notifications.settings = disabled
    assert client.get("/api/v1/notification-digests", headers=auth).json() == {"enabled": False, "digests": []}
    assert client.post(route, headers=auth, json={"notification_ids": ids}).status_code == 409


def automation_payload(goal):
    return {
        "goal_id": goal["id"], "goal_revision": goal["revision"], "timezone": "Asia/Dhaka",
        "schedule": {"kind": "daily", "hour": 8, "minute": 30, "weekdays": []},
        "output_language": "en", "overlap_policy": "skip", "catchup_window_seconds": 3600,
        "quiet_hours": None, "expires_at": None,
    }


def create_goal_and_automation(client, auth):
    goal = client.post(
        "/api/v1/goals", headers=auth | {"Idempotency-Key": "automation-goal"},
        json=goal_payload(),
    ).json()
    response = client.post(
        "/api/v1/automations",
        headers=auth | {"Idempotency-Key": "automation-create"},
        json=automation_payload(goal),
    )
    assert response.status_code == 201
    return goal, response.json()


def test_automation_crud_is_owner_scoped_revisioned_and_reconciled(automation_client, automation_container):
    client, headers = automation_client
    alice, bob = headers(), headers("bob")
    goal, automation = create_goal_and_automation(client, alice)

    replay = client.post(
        "/api/v1/automations",
        headers=alice | {"Idempotency-Key": "automation-create"},
        json=automation_payload(goal),
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == automation["id"]
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert client.get(f'/api/v1/automations/{automation["id"]}', headers=bob).status_code == 404

    stale = client.patch(
        f'/api/v1/automations/{automation["id"]}', headers=alice,
        json={"expected_revision": 99, "catchup_window_seconds": 7200},
    )
    assert stale.status_code == 409

    paused = client.post(
        f'/api/v1/automations/{automation["id"]}/pause', headers=alice,
        json={"expected_revision": 1},
    )
    assert paused.status_code == 200
    assert paused.json()["state"] == "paused" and paused.json()["revision"] == 2

    claims = automation_container.automations.claim_reconciliation()
    assert len(claims) == 1 and claims[0]["desired_revision"] == 2
    assert automation_container.automations.claim_reconciliation() == []
    with automation_container.repository.sessions.begin() as db:
        outbox = db.get(AutomationScheduleOutbox, automation["id"])
        outbox.lease_until = utcnow() - timedelta(seconds=1)
    reclaimed = automation_container.automations.claim_reconciliation()
    assert [item["id"] for item in reclaimed] == [automation["id"]]

    resumed = client.post(
        f'/api/v1/automations/{automation["id"]}/resume', headers=alice,
        json={"expected_revision": 2},
    )
    assert resumed.status_code == 200 and resumed.json()["state"] == "active"

    automation_container.automations.settings = replace(
        automation_container.settings, max_automations=1
    )
    limited = client.post(
        "/api/v1/automations",
        headers=alice | {"Idempotency-Key": "automation-limit-second"},
        json=automation_payload(goal),
    )
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "automation_limit"


def test_kill_switch_reconciliation_pauses_and_restores_persisted_desired_state(automation_client, automation_container):
    client, headers = automation_client
    auth = headers()
    _, automation = create_goal_and_automation(client, auth)

    initial = automation_container.automations.claim_reconciliation()
    assert len(initial) == 1 and initial[0]["state"] == "active"
    automation_container.automations.reconciliation_applied(
        automation["id"], automation["revision"], True
    )

    disabled = replace(automation_container.settings, automations_enabled=False)
    automation_container.automations.settings = disabled
    paused = automation_container.automations.claim_reconciliation()
    assert len(paused) == 1 and paused[0]["state"] == "paused"
    automation_container.automations.reconciliation_applied(
        automation["id"], automation["revision"], False
    )

    automation_container.automations.settings = automation_container.settings
    restored = automation_container.automations.claim_reconciliation()
    assert len(restored) == 1 and restored[0]["state"] == "active"


def test_occurrence_dedupes_to_one_bounded_run_and_one_notification(automation_client, automation_container):
    client, headers = automation_client
    auth = headers()
    _, automation = create_goal_and_automation(client, auth)
    due_at = utcnow().replace(microsecond=0)

    first = automation_container.automations.accept_occurrence(automation["id"], 1, due_at)
    assert first["state"] == "accepted"

    restarted = Container.create(automation_container.settings)
    try:
        second = restarted.automations.accept_occurrence(automation["id"], 1, due_at)
    finally:
        restarted.repository.sessions.kw["bind"].dispose()
    assert second["replayed"] is True
    assert second["run_id"] == first["run_id"]

    overlap_due = due_at + timedelta(minutes=1)
    overlap = automation_container.automations.accept_occurrence(
        automation["id"], 1, overlap_due
    )
    assert overlap["state"] == "skipped" and overlap["reason"] == "overlap"
    with automation_container.repository.sessions.begin() as db:
        db.get(AgentRun, first["run_id"]).state = "completed"
    duplicate_overlap = automation_container.automations.accept_occurrence(
        automation["id"], 1, overlap_due
    )
    assert duplicate_overlap["state"] == "skipped"
    assert duplicate_overlap["reason"] == "overlap"
    assert duplicate_overlap["replayed"] is True

    goal_view = client.get(f'/api/v1/goals/{automation["goal_id"]}', headers=auth).json()
    matching = [item for item in goal_view["run_links"] if item["run_id"] == first["run_id"]]
    assert len(matching) == 1 and matching[0]["goal_revision"] == automation["goal_revision"]

    notification_ids = automation_container.notifications.claim_notifications()
    assert len(notification_ids) == 1
    assert automation_container.notifications.claim_notifications() == []
    with automation_container.repository.sessions.begin() as db:
        outbox = db.get(NotificationOutbox, notification_ids[0])
        outbox.lease_until = utcnow() - timedelta(seconds=1)
    assert automation_container.notifications.claim_notifications() == notification_ids
    automation_container.notifications.deliver_notification(notification_ids[0])
    assert automation_container.notifications.claim_notifications() == []
    inbox = client.get("/api/v1/notifications", headers=auth).json()
    assert len(inbox["notifications"]) == 1

    read = client.post(f'/api/v1/notifications/{notification_ids[0]}/read', headers=auth)
    assert read.status_code == 200 and read.json()["state"] == "read"


def test_notification_service_is_first_class_and_automation_keeps_compatibility(
    automation_client,
    automation_container,
):
    client, headers = automation_client
    auth = headers()
    assert automation_container.notifications is not None
    assert automation_container.automations.notifications is automation_container.notifications

    direct = automation_container.notifications.notification_preferences(
        client.get("/api/v1/me", headers=auth).json()["account_id"]
    )
    compat = automation_container.automations.notification_preferences(
        client.get("/api/v1/me", headers=auth).json()["account_id"]
    )
    assert direct == compat == {
        "in_app_enabled": True,
        "automation_updates_enabled": True,
    }


def test_notification_preferences_are_owner_scoped_and_preserve_writing_preferences(
    automation_client,
    automation_container,
):
    client, headers = automation_client
    alice, bob = headers(), headers("bob")

    assert client.get("/api/v1/notification-preferences", headers=alice).json() == {
        "in_app_enabled": True,
        "automation_updates_enabled": True,
    }
    assert client.get("/api/v1/notification-preferences", headers=bob).json() == {
        "in_app_enabled": True,
        "automation_updates_enabled": True,
    }

    writing = client.put(
        "/api/v1/preferences",
        headers=alice,
        json={"language": "bn"},
    )
    assert writing.status_code == 200

    saved = client.put(
        "/api/v1/notification-preferences",
        headers=alice,
        json={
            "in_app_enabled": False,
            "automation_updates_enabled": False,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["in_app_enabled"] is False

    with automation_container.repository.sessions() as db:
        owner = db.scalar(select(Account).where(Account.subject == "alice"))
        assert owner is not None
        assert owner.preferences["language"] == "bn"
        assert owner.preferences["notifications"] == {
            "in_app_enabled": False,
            "automation_updates_enabled": False,
        }

    rewritten = client.put(
        "/api/v1/preferences",
        headers=alice,
        json={"language": "en", "tone_goal": "concise"},
    )
    assert rewritten.status_code == 200
    assert client.get("/api/v1/notification-preferences", headers=alice).json() == {
        "in_app_enabled": False,
        "automation_updates_enabled": False,
    }
    assert client.get("/api/v1/notification-preferences", headers=bob).json() == {
        "in_app_enabled": True,
        "automation_updates_enabled": True,
    }


def test_notification_opt_out_suppresses_before_claim(
    automation_client,
    automation_container,
):
    client, headers = automation_client
    auth = headers()
    _, automation = create_goal_and_automation(client, auth)
    accepted = automation_container.automations.accept_occurrence(
        automation["id"],
        1,
        utcnow().replace(microsecond=0),
    )
    assert accepted["state"] == "accepted"

    saved = client.put(
        "/api/v1/notification-preferences",
        headers=auth,
        json={
            "in_app_enabled": False,
            "automation_updates_enabled": True,
        },
    )
    assert saved.status_code == 200
    assert automation_container.notifications.claim_notifications() == []

    with automation_container.repository.sessions() as db:
        notification = db.scalar(
            select(Notification).where(
                Notification.occurrence_id == accepted["occurrence_id"]
            )
        )
        assert notification is not None
        outbox = db.get(NotificationOutbox, notification.id)
        assert notification.state == "suppressed"
        assert outbox is not None and outbox.delivered is True
    assert client.get("/api/v1/notifications", headers=auth).json()["notifications"] == []


def test_notification_revocation_after_claim_is_rechecked_at_delivery(
    automation_client,
    automation_container,
):
    client, headers = automation_client
    auth = headers()
    _, automation = create_goal_and_automation(client, auth)
    accepted = automation_container.automations.accept_occurrence(
        automation["id"],
        1,
        utcnow().replace(microsecond=0),
    )
    assert accepted["state"] == "accepted"

    claimed = automation_container.notifications.claim_notifications()
    assert len(claimed) == 1

    saved = client.put(
        "/api/v1/notification-preferences",
        headers=auth,
        json={
            "in_app_enabled": True,
            "automation_updates_enabled": False,
        },
    )
    assert saved.status_code == 200
    automation_container.notifications.deliver_notification(claimed[0])

    with automation_container.repository.sessions() as db:
        notification = db.get(Notification, claimed[0])
        outbox = db.get(NotificationOutbox, claimed[0])
        assert notification is not None and notification.state == "suppressed"
        assert outbox is not None and outbox.delivered is True
        assert outbox.lease_until is None
    assert client.get("/api/v1/notifications", headers=auth).json()["notifications"] == []


def test_notification_preferences_reject_unreviewed_fields(automation_client):
    client, headers = automation_client
    response = client.put(
        "/api/v1/notification-preferences",
        headers=headers(),
        json={
            "in_app_enabled": True,
            "automation_updates_enabled": True,
            "email_enabled": True,
        },
    )
    assert response.status_code == 422


def test_buffer_one_keeps_only_one_waiting_occurrence(automation_client, automation_container):
    client, headers = automation_client
    auth = headers()
    goal = client.post(
        "/api/v1/goals",
        headers=auth | {"Idempotency-Key": "buffer-goal"},
        json=goal_payload(),
    ).json()
    body = automation_payload(goal)
    body["overlap_policy"] = "buffer_one"
    automation = client.post(
        "/api/v1/automations",
        headers=auth | {"Idempotency-Key": "buffer-automation"},
        json=body,
    ).json()
    due = utcnow().replace(microsecond=0)

    first = automation_container.automations.accept_occurrence(automation["id"], 1, due)
    assert first["state"] == "accepted"
    buffered = automation_container.automations.accept_occurrence(
        automation["id"], 1, due + timedelta(minutes=1)
    )
    assert buffered["state"] == "buffered"
    overflow = automation_container.automations.accept_occurrence(
        automation["id"], 1, due + timedelta(minutes=2)
    )
    assert overflow["state"] == "skipped" and overflow["reason"] == "buffer_full"
    assert automation_container.automations.claim_buffered_occurrences() == []

    with automation_container.repository.sessions.begin() as db:
        db.get(AgentRun, first["run_id"]).state = "completed"

    ready = automation_container.automations.claim_buffered_occurrences()
    assert len(ready) == 1
    assert automation_container.automations.claim_buffered_occurrences() == []
    with automation_container.repository.sessions.begin() as db:
        occurrence = db.get(AutomationOccurrence, buffered["occurrence_id"])
        occurrence.updated_at = utcnow() - timedelta(seconds=31)
    reclaimed = automation_container.automations.claim_buffered_occurrences()
    assert len(reclaimed) == 1 and reclaimed[0]["automation_id"] == automation["id"]

    released = automation_container.automations.accept_occurrence(
        reclaimed[0]["automation_id"],
        reclaimed[0]["revision"],
        __import__("datetime").datetime.fromisoformat(reclaimed[0]["due_at"]),
    )
    assert released["state"] == "accepted"
    assert released["run_id"] != first["run_id"]


def test_stale_expired_and_kill_switch_occurrences_never_start_work(automation_client, automation_container):
    client, headers = automation_client
    auth = headers()
    _, automation = create_goal_and_automation(client, auth)
    due = utcnow().replace(microsecond=0)

    revised = client.patch(
        f'/api/v1/automations/{automation["id"]}', headers=auth,
        json={"expected_revision": 1, "schedule": {"kind": "daily", "hour": 9, "minute": 0, "weekdays": []}},
    ).json()
    stale = automation_container.automations.accept_occurrence(automation["id"], 1, due)
    assert stale["state"] == "skipped" and stale["reason"] == "stale_revision"

    automation_container.automations.settings = replace(automation_container.settings, automations_enabled=False)
    killed = automation_container.automations.accept_occurrence(automation["id"], revised["revision"], due + timedelta(seconds=1))
    assert killed["state"] == "skipped" and killed["reason"] == "kill_switch"


def test_catchup_window_and_expiry_skip_late_occurrences(automation_client, automation_container):
    client, headers = automation_client
    auth = headers()
    goal = client.post(
        "/api/v1/goals",
        headers=auth | {"Idempotency-Key": "expiry-goal"},
        json=goal_payload(),
    ).json()

    body = automation_payload(goal)
    body["catchup_window_seconds"] = 60
    body["expires_at"] = (utcnow() + timedelta(minutes=5)).isoformat()
    automation = client.post(
        "/api/v1/automations",
        headers=auth | {"Idempotency-Key": "expiry-automation"},
        json=body,
    ).json()

    late = automation_container.automations.accept_occurrence(
        automation["id"], 1, utcnow() - timedelta(minutes=2)
    )
    assert late["state"] == "skipped" and late["reason"] == "catchup_window"

    expired_due = utcnow() + timedelta(minutes=10)
    expired = automation_container.automations.accept_occurrence(
        automation["id"], 1, expired_due
    )
    assert expired["state"] == "skipped" and expired["reason"] == "expired"


def test_quiet_hours_delay_notification_visibility():
    from services.coworker.automation_repository import AutomationRepository
    due = __import__("datetime").datetime(2026, 9, 26, 17, 30, tzinfo=__import__("datetime").timezone.utc)
    visible = AutomationRepository._notification_visible_at(
        due, "Asia/Dhaka", {"start": "22:00", "end": "07:00"}
    )
    assert visible > due


def test_automations_are_fail_closed_without_dependencies(tmp_path):
    with pytest.raises(ValueError, match="Automations require"):
        Settings(
            database_url=f"sqlite:///{tmp_path / 'invalid.sqlite3'}",
            auth_issuer=ISSUER, environment="development", storage_backend="local",
            local_storage_path=tmp_path / "objects", automations_enabled=True,
        ).validate()

def test_temporal_schedule_contract_uses_timezone_overlap_and_expiry():
    from services.coworker.automation_scheduler import temporal_schedule
    value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "revision": 3,
        "state": "active",
        "timezone": "America/New_York",
        "schedule": {"kind": "weekly", "hour": 8, "minute": 30, "weekdays": ["mon", "wed"]},
        "overlap_policy": "buffer_one",
        "catchup_window_seconds": 1800,
        "expires_at": "2026-10-30T00:00:00+00:00",
    }
    schedule = temporal_schedule(value, "test-queue")
    assert schedule.spec.time_zone_name == "America/New_York"
    assert schedule.spec.calendars[0].hour[0].start == 8
    assert schedule.spec.calendars[0].minute[0].start == 30
    assert schedule.policy.catchup_window == timedelta(seconds=1800)
    assert schedule.state.paused is False

def test_account_erasure_removes_goals_and_automation_state(automation_client, automation_container):
    client, headers = automation_client
    auth = headers()
    goal, automation = create_goal_and_automation(client, auth)
    with automation_container.repository.sessions() as db:
        owner_id = db.scalar(select(Account.id).where(Account.subject == "alice"))
    assert owner_id

    with pytest.raises(CoworkerError, match="reconcile automation schedule deletion"):
        automation_container.retention.erase_account(owner_id)

    cancelled = client.post(
        f'/api/v1/automations/{automation["id"]}/cancel',
        headers=auth,
        json={"expected_revision": 1},
    )
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    automation_container.automations.reconciliation_applied(
        automation["id"], cancelled.json()["revision"], False
    )

    result = automation_container.retention.erase_account(owner_id)
    assert result["database_erased"] is True
    with automation_container.repository.sessions() as db:
        assert db.get(Automation, automation["id"]) is None
        assert db.get(PersonalGoal, goal["id"]) is None




def test_personal_suggestion_delivery_is_separate_durable_deduped_and_inert(
    automation_client, automation_container,
):
    client, headers = automation_client
    auth = headers()
    body = goal_payload()
    body["next_review_at"] = (utcnow() - timedelta(minutes=5)).isoformat()
    goal = client.post(
        "/api/v1/goals",
        headers=auth | {"Idempotency-Key": "suggestion-delivery-goal"},
        json=body,
    ).json()
    preferences = client.get("/api/v1/personal-suggestion-preferences", headers=auth).json()
    assert preferences == {
        "available": True,
        "enabled": False,
        "delivery_available": True,
        "delivery_enabled": False,
        "event_delivery_available": False,
        "event_delivery_enabled": False,
        "event_timezone": "UTC",
        "dismissed_count": 0,
    }
    client.put("/api/v1/personal-suggestion-preferences", headers=auth,
               json={"enabled": True, "delivery_enabled": False})
    suggestion = client.get("/api/v1/personal-suggestions", headers=auth).json()["suggestions"][0]
    with automation_container.repository.sessions() as db:
        owner = db.scalar(select(Account).where(Account.subject == "alice"))
        assert db.scalars(select(Notification).where(
            Notification.owner_id == owner.id,
            Notification.source_kind == "personal_suggestion",
        )).all() == []

    enabled = client.put("/api/v1/personal-suggestion-preferences", headers=auth,
                         json={"enabled": True, "delivery_enabled": True})
    assert enabled.status_code == 200 and enabled.json()["delivery_enabled"] is True
    automation_container.suggestions.reconcile_delivery(owner.id)
    with automation_container.repository.sessions.begin() as db:
        rows = db.scalars(select(Notification).where(
            Notification.owner_id == owner.id,
            Notification.source_kind == "personal_suggestion",
        )).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.source_id == suggestion["id"] and row.kind == "personal_suggestion"
        row.visible_at = utcnow() - timedelta(seconds=1)

    claimed = automation_container.notifications.claim_notifications()
    assert len(claimed) == 1
    automation_container.notifications.deliver_notification(claimed[0])
    inbox = client.get("/api/v1/notifications", headers=auth).json()["notifications"]
    assert len(inbox) == 1 and inbox[0]["kind"] == "personal_suggestion"
    with automation_container.repository.sessions() as db:
        assert db.scalars(select(AgentRun).where(AgentRun.owner_id == owner.id)).all() == []
        assert db.scalars(select(Automation).where(Automation.owner_id == owner.id)).all() == []


def test_personal_suggestion_delivery_revalidates_dismissal_revision_and_opt_out(
    automation_client, automation_container,
):
    client, headers = automation_client
    auth = headers()
    body = goal_payload()
    body["next_review_at"] = (utcnow() - timedelta(minutes=5)).isoformat()
    goal = client.post(
        "/api/v1/goals",
        headers=auth | {"Idempotency-Key": "suggestion-revalidation-goal"},
        json=body,
    ).json()
    client.put("/api/v1/personal-suggestion-preferences", headers=auth,
               json={"enabled": True, "delivery_enabled": True})
    first = client.get("/api/v1/personal-suggestions", headers=auth).json()["suggestions"][0]
    dismissed = client.post(f'/api/v1/personal-suggestions/{first["id"]}/dismiss', headers=auth)
    assert dismissed.status_code == 200
    with automation_container.repository.sessions() as db:
        owner = db.scalar(select(Account).where(Account.subject == "alice"))
        old_row = db.scalar(select(Notification).where(
            Notification.owner_id == owner.id, Notification.source_id == first["id"]))
        assert old_row is not None and old_row.state == "suppressed"

    revised = client.patch(f'/api/v1/goals/{goal["id"]}', headers=auth, json={
        "expected_revision": 1,
        "next_review_at": (utcnow() - timedelta(minutes=1)).isoformat(),
    })
    assert revised.status_code == 200 and revised.json()["revision"] == 2
    second = client.get("/api/v1/personal-suggestions", headers=auth).json()["suggestions"][0]
    assert second["id"] != first["id"]
    with automation_container.repository.sessions.begin() as db:
        new_row = db.scalar(select(Notification).where(
            Notification.owner_id == owner.id, Notification.source_id == second["id"]))
        assert new_row is not None and new_row.state == "pending"
        new_row.visible_at = utcnow() - timedelta(seconds=1)

    claimed = automation_container.notifications.claim_notifications()
    assert len(claimed) == 1
    with automation_container.repository.sessions.begin() as db:
        account = db.get(Account, owner.id)
        current = dict(account.preferences or {})
        prefs = dict(current["personal_suggestions"])
        prefs["delivery_enabled"] = False
        current["personal_suggestions"] = prefs
        account.preferences = current
    automation_container.notifications.deliver_notification(claimed[0])
    with automation_container.repository.sessions() as db:
        row = db.get(Notification, claimed[0]); outbox = db.get(NotificationOutbox, claimed[0])
        assert row.state == "suppressed"
        assert outbox.delivered is True and outbox.lease_until is None
    assert client.get("/api/v1/notifications", headers=auth).json()["notifications"] == []
