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

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from services.coworker.api import mount
from services.coworker.auth import JwtVerifier
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.migrate import upgrade
from services.coworker.models import AutomationScheduleOutbox, NotificationOutbox, utcnow

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


def test_occurrence_dedupes_to_one_bounded_run_and_one_notification(automation_client, automation_container):
    client, headers = automation_client
    auth = headers()
    _, automation = create_goal_and_automation(client, auth)
    due_at = utcnow().replace(microsecond=0)

    first = automation_container.automations.accept_occurrence(automation["id"], 1, due_at)
    second = automation_container.automations.accept_occurrence(automation["id"], 1, due_at)
    assert first["state"] == "accepted"
    assert second["replayed"] is True
    assert second["run_id"] == first["run_id"]

    overlap = automation_container.automations.accept_occurrence(
        automation["id"], 1, due_at + timedelta(minutes=1)
    )
    assert overlap["state"] == "skipped" and overlap["reason"] == "overlap"

    goal_view = client.get(f'/api/v1/goals/{automation["goal_id"]}', headers=auth).json()
    matching = [item for item in goal_view["run_links"] if item["run_id"] == first["run_id"]]
    assert len(matching) == 1 and matching[0]["goal_revision"] == automation["goal_revision"]

    notification_ids = automation_container.automations.claim_notifications()
    assert len(notification_ids) == 1
    automation_container.automations.deliver_notification(notification_ids[0])
    assert automation_container.automations.claim_notifications() == []
    inbox = client.get("/api/v1/notifications", headers=auth).json()
    assert len(inbox["notifications"]) == 1

    read = client.post(f'/api/v1/notifications/{notification_ids[0]}/read', headers=auth)
    assert read.status_code == 200 and read.json()["state"] == "read"


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
