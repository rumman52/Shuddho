from __future__ import annotations

import time
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
from services.coworker.migrate import upgrade
from services.coworker.models import Account, AgentRun, Document, DocumentVersion, PersonalGoal, utcnow

ISSUER = "https://identity.example.test/auth/v1"

@pytest.fixture
def goal_container(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'goals.sqlite3'}", auth_issuer=ISSUER,
        environment="development", storage_backend="local", local_storage_path=tmp_path / "objects",
        personal_goals_enabled=True, agent_runtime_enabled=True,
    )
    upgrade(settings.database_url)
    result = Container.create(settings)
    yield result
    result.repository.sessions.kw["bind"].dispose()

@pytest.fixture
def goal_client(goal_container):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": "test-key", "alg": "RS256", "use": "sig"}
    goal_container.verifier = JwtVerifier(ISSUER, "authenticated", httpx.MockTransport(lambda _request: httpx.Response(200, json={"keys": [jwk]})))
    app = FastAPI(); mount(app, goal_container)
    def headers(subject="alice"):
        claims = {"iss": ISSUER, "sub": subject, "aud": "authenticated", "role": "authenticated", "iat": int(time.time()) - 1, "exp": int(time.time()) + 3600}
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})
        return {"Authorization": "Bearer " + token}
    with TestClient(app) as client:
        yield client, headers

def payload(max_runs=2):
    return {
        "objective": "Prepare for the final examination over the next three weeks.",
        "success_criteria": ["Complete every planned revision session."],
        "constraints": ["Keep each bounded run focused on one study outcome."],
        "deadline_at": None, "timezone": "Asia/Dhaka", "state": "active",
        "milestones": [{"label": "Finish the first revision pass.", "due_at": None, "completed": False}],
        "budget": {"max_runs": max_runs, "max_planner_tokens": 50000},
        "authorized_resources": [], "next_review_at": None,
    }

def test_goal_lifecycle_is_owner_scoped_revisioned_and_links_exact_run_revision(goal_client):
    client, headers = goal_client
    alice, bob = headers(), headers("bob")
    created = client.post("/api/v1/goals", headers=alice | {"Idempotency-Key": "goal-create-001"}, json=payload())
    assert created.status_code == 201
    goal = created.json()
    assert goal["revision"] == 1 and goal["state"] == "active" and created.headers["ETag"] == '"1"'
    replay = client.post("/api/v1/goals", headers=alice | {"Idempotency-Key": "goal-create-001"}, json=payload())
    assert replay.json()["id"] == goal["id"] and replay.headers["Idempotent-Replayed"] == "true"
    conflict = client.post("/api/v1/goals", headers=alice | {"Idempotency-Key": "goal-create-001"}, json=payload() | {"objective": "A different goal."})
    assert conflict.status_code == 409
    assert client.get(f'/api/v1/goals/{goal["id"]}', headers=bob).status_code == 404

    revised = client.patch(f'/api/v1/goals/{goal["id"]}', headers=alice, json={"expected_revision": 1, "objective": "Prepare for the final examination with daily bounded study runs."})
    assert revised.status_code == 200
    goal = revised.json(); assert goal["revision"] == 2
    stale = client.patch(f'/api/v1/goals/{goal["id"]}', headers=alice, json={"expected_revision": 1, "objective": "This stale edit must fail."})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "goal_revision_conflict"
    revisions = client.get(f'/api/v1/goals/{goal["id"]}/revisions', headers=alice).json()["revisions"]
    assert [item["revision"] for item in revisions] == [1, 2]

    paused = client.post(f'/api/v1/goals/{goal["id"]}/pause', headers=alice, json={"expected_revision": 2}).json()
    assert paused["state"] == "paused" and paused["revision"] == 3
    blocked_run = client.post(f'/api/v1/goals/{goal["id"]}/run', headers=alice | {"Idempotency-Key": "goal-run-paused"}, json={"expected_revision": 3, "output_language": "en"})
    assert blocked_run.status_code == 409 and blocked_run.json()["error"]["code"] == "goal_not_active"
    resumed = client.post(f'/api/v1/goals/{goal["id"]}/resume', headers=alice, json={"expected_revision": 3}).json()
    assert resumed["state"] == "active" and resumed["revision"] == 4

    started = client.post(f'/api/v1/goals/{goal["id"]}/run', headers=alice | {"Idempotency-Key": "goal-run-001"}, json={"expected_revision": 4, "output_language": "en"})
    assert started.status_code == 202
    run = started.json()
    assert run["persistent_goal_id"] == goal["id"] and run["persistent_goal_revision"] == 4
    accepted_objective = run["goal"]
    edited = client.patch(f'/api/v1/goals/{goal["id"]}', headers=alice, json={"expected_revision": 4, "objective": "A newer objective for future runs only."}).json()
    assert edited["revision"] == 5
    historical = client.get(f'/api/v1/agent-runs/{run["id"]}', headers=alice).json()
    assert historical["goal"] == accepted_objective and historical["persistent_goal_revision"] == 4
    linked = client.get(f'/api/v1/goals/{goal["id"]}', headers=alice).json()["run_links"]
    assert linked[0]["run_id"] == run["id"] and linked[0]["goal_revision"] == 4
    cancelled = client.post(f'/api/v1/goals/{goal["id"]}/cancel', headers=alice, json={"expected_revision": 5}).json()
    assert cancelled["state"] == "cancelled" and cancelled["revision"] == 6

def test_goal_run_budget_and_resource_metadata_do_not_expand_authority(goal_client):
    client, headers = goal_client
    auth = headers()
    body = payload(max_runs=1)
    body["authorized_resources"] = [{"kind": "memory_namespace", "reference": "preferences"}]
    goal = client.post("/api/v1/goals", headers=auth | {"Idempotency-Key": "goal-budget-create"}, json=body).json()
    first = client.post(f'/api/v1/goals/{goal["id"]}/run', headers=auth | {"Idempotency-Key": "goal-budget-run-1"}, json={"expected_revision": 1, "output_language": "en"})
    assert first.status_code == 202 and first.json()["memory_namespaces"] == []
    second = client.post(f'/api/v1/goals/{goal["id"]}/run', headers=auth | {"Idempotency-Key": "goal-budget-run-2"}, json={"expected_revision": 1, "output_language": "en"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "goal_run_budget"

def test_personal_suggestions_default_off_stable_owner_scoped_and_inert(
    goal_client,
    goal_container,
):
    client, headers = goal_client
    alice, bob = headers(), headers("bob")
    body = payload()
    body["deadline_at"] = (utcnow() + timedelta(hours=20)).isoformat()
    created = client.post(
        "/api/v1/goals",
        headers=alice | {"Idempotency-Key": "suggestion-goal"},
        json=body,
    )
    assert created.status_code == 201
    goal = created.json()

    default_preferences = client.get(
        "/api/v1/personal-suggestion-preferences",
        headers=alice,
    )
    assert default_preferences.status_code == 200
    assert default_preferences.json() == {
        "available": True,
        "enabled": False,
        "dismissed_count": 0,
    }
    assert client.get(
        "/api/v1/personal-suggestions",
        headers=alice,
    ).json()["suggestions"] == []

    enabled = client.put(
        "/api/v1/personal-suggestion-preferences",
        headers=alice,
        json={"enabled": True},
    )
    assert enabled.status_code == 200 and enabled.json()["enabled"] is True

    first = client.get("/api/v1/personal-suggestions", headers=alice).json()
    second = client.get("/api/v1/personal-suggestions", headers=alice).json()
    assert first == second
    assert first["available"] is True and first["enabled"] is True
    assert len(first["suggestions"]) == 1
    suggestion = first["suggestions"][0]
    assert suggestion["goal_id"] == goal["id"]
    assert suggestion["goal_revision"] == 1
    assert suggestion["kind"] == "goal_deadline_due"
    assert suggestion["action"] == "review_goal"
    assert suggestion["context_resource_count"] == 0
    assert set(suggestion) == {
        "id", "kind", "goal_id", "goal_revision", "relevance_score",
        "reason", "due_at", "action", "context_resource_count",
    }

    assert client.get(
        "/api/v1/personal-suggestions",
        headers=bob,
    ).json()["suggestions"] == []

    with goal_container.repository.sessions() as db:
        owner = db.scalar(select(Account).where(Account.subject == "alice"))
        assert owner is not None
        assert db.scalars(
            select(AgentRun).where(AgentRun.owner_id == owner.id)
        ).all() == []


def test_personal_suggestion_dismissal_is_stable_and_revision_bound(
    goal_client,
):
    client, headers = goal_client
    auth = headers()
    body = payload()
    body["next_review_at"] = (utcnow() - timedelta(minutes=5)).isoformat()
    goal = client.post(
        "/api/v1/goals",
        headers=auth | {"Idempotency-Key": "suggestion-dismiss-goal"},
        json=body,
    ).json()
    client.put(
        "/api/v1/personal-suggestion-preferences",
        headers=auth,
        json={"enabled": True},
    )

    item = client.get(
        "/api/v1/personal-suggestions",
        headers=auth,
    ).json()["suggestions"][0]
    assert item["kind"] == "goal_review_due"

    dismissed = client.post(
        f'/api/v1/personal-suggestions/{item["id"]}/dismiss',
        headers=auth,
    )
    assert dismissed.status_code == 200
    assert dismissed.json() == {"id": item["id"], "state": "dismissed"}
    assert client.get(
        "/api/v1/personal-suggestions",
        headers=auth,
    ).json()["suggestions"] == []

    revised = client.patch(
        f'/api/v1/goals/{goal["id"]}',
        headers=auth,
        json={
            "expected_revision": 1,
            "next_review_at": (utcnow() - timedelta(minutes=1)).isoformat(),
        },
    )
    assert revised.status_code == 200
    refreshed = client.get(
        "/api/v1/personal-suggestions",
        headers=auth,
    ).json()["suggestions"]
    assert len(refreshed) == 1
    assert refreshed[0]["id"] != item["id"]
    assert refreshed[0]["goal_revision"] == 2


def test_personal_suggestion_context_uses_only_valid_authorized_metadata(
    goal_client,
    goal_container,
):
    client, headers = goal_client
    auth = headers()
    owner_response = client.get("/api/v1/me", headers=auth)
    assert owner_response.status_code == 200

    with goal_container.repository.sessions.begin() as db:
        owner = db.scalar(select(Account).where(Account.subject == "alice"))
        assert owner is not None
        workspace_id = owner_response.json()["workspace_id"]
        document = Document(
            id="11111111-1111-1111-1111-111111111111",
            owner_id=owner.id,
            workspace_id=workspace_id,
            filename="PRIVATE-SYLLABUS-NAME.txt",
        )
        db.add(document)
        db.flush()
        db.add(DocumentVersion(
            id="22222222-2222-2222-2222-222222222222",
            document_id=document.id,
            owner_id=owner.id,
            version=1,
            kind="txt",
            byte_size=10,
            sha256="a" * 64,
            object_key=f"{owner.id}/inputs/test/private.txt",
            state="uploaded",
            expires_at=utcnow() + timedelta(days=30),
        ))

    body = payload()
    body["objective"] = "PRIVATE-GOAL-CONTENT that must not appear in a suggestion payload."
    body["authorized_resources"] = [{
        "kind": "document",
        "reference": "11111111-1111-1111-1111-111111111111",
    }]
    goal = client.post(
        "/api/v1/goals",
        headers=auth | {"Idempotency-Key": "suggestion-context-goal"},
        json=body,
    )
    assert goal.status_code == 201
    client.put(
        "/api/v1/personal-suggestion-preferences",
        headers=auth,
        json={"enabled": True},
    )

    response = client.get("/api/v1/personal-suggestions", headers=auth)
    assert response.status_code == 200
    payload_value = response.json()
    assert len(payload_value["suggestions"]) == 1
    suggestion = payload_value["suggestions"][0]
    assert suggestion["kind"] == "goal_context_ready"
    assert suggestion["context_resource_count"] == 1
    assert "PRIVATE-GOAL-CONTENT" not in response.text
    assert "PRIVATE-SYLLABUS-NAME" not in response.text
    assert "11111111-1111-1111-1111-111111111111" not in response.text

    with goal_container.repository.sessions.begin() as db:
        db.get(Document, "11111111-1111-1111-1111-111111111111").deleted = True

    assert client.get(
        "/api/v1/personal-suggestions",
        headers=auth,
    ).json()["suggestions"] == []


def test_personal_suggestion_preferences_reject_unreviewed_fields(goal_client):
    client, headers = goal_client
    response = client.put(
        "/api/v1/personal-suggestion-preferences",
        headers=headers(),
        json={"enabled": True, "external_push": True},
    )
    assert response.status_code == 422


def test_goal_draft_activation_and_patch_null_contract(goal_client):
    client, headers = goal_client
    auth = headers()
    body = payload()
    body["state"] = "draft"
    created = client.post(
        "/api/v1/goals",
        headers=auth | {"Idempotency-Key": "goal-draft-create"},
        json=body,
    )
    assert created.status_code == 201
    goal = created.json()
    assert goal["state"] == "draft" and goal["revision"] == 1

    blocked = client.post(
        f'/api/v1/goals/{goal["id"]}/run',
        headers=auth | {"Idempotency-Key": "goal-draft-run"},
        json={"expected_revision": 1, "output_language": "en"},
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "goal_not_active"

    resumed = client.post(
        f'/api/v1/goals/{goal["id"]}/resume',
        headers=auth,
        json={"expected_revision": 1},
    )
    assert resumed.status_code == 200
    goal = resumed.json()
    assert goal["state"] == "active" and goal["revision"] == 2

    for field in ("objective", "success_criteria", "constraints", "timezone", "milestones", "budget", "authorized_resources"):
        rejected = client.patch(
            f'/api/v1/goals/{goal["id"]}',
            headers=auth,
            json={"expected_revision": 2, field: None},
        )
        assert rejected.status_code == 422, field

    current = client.get(f'/api/v1/goals/{goal["id"]}', headers=auth).json()
    assert current["revision"] == 2
    assert current["objective"] == goal["objective"]
    assert current["timezone"] == goal["timezone"]

    cleared = client.patch(
        f'/api/v1/goals/{goal["id"]}',
        headers=auth,
        json={"expected_revision": 2, "deadline_at": None, "next_review_at": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["revision"] == 3

