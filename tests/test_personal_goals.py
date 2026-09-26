from __future__ import annotations

import time
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
