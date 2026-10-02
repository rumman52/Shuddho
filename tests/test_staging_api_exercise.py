from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scripts import staging_api_exercise as exercise


def response(status: int, payload=None, *, content=b""):
    request = httpx.Request("GET", "https://staging.example.test")
    if payload is not None:
        return httpx.Response(status, json=payload, request=request)
    return httpx.Response(status, content=content, request=request)


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, path, headers=None):
        self.calls.append(("GET", path, headers))
        if path == "/api/v1/me":
            token = headers["Authorization"]
            if token.endswith("token-a"):
                return response(200, {"account_id": "a", "workspace_id": "wa"})
            return response(200, {"account_id": "b", "workspace_id": "wb"})
        if path == "/api/v1/documents":
            return response(200, {"documents": []})
        if path.endswith("/events"):
            return response(404, {"error": {"code": "not_found"}})
        if path.startswith("/api/v1/tasks/"):
            return response(404, {"error": {"code": "not_found"}})
        raise AssertionError(path)

    def post(self, path, headers=None, json=None):
        self.calls.append(("POST", path, headers, json))
        if path == "/api/v1/documents":
            return response(201, {"id": "doc-1"})
        if path == "/api/v1/tasks":
            return response(202, {"id": "task-1"})
        if path.endswith("/cancel"):
            token = headers["Authorization"]
            return response(200 if token.endswith("token-a") else 404, {"state": "cancelled"})
        raise AssertionError(path)

    def put(self, path, headers=None, content=None):
        self.calls.append(("PUT", path, headers, content))
        token = headers["Authorization"]
        return response(200 if token.endswith("token-a") else 404, {"state": "uploaded"})

    def delete(self, path, headers=None):
        self.calls.append(("DELETE", path, headers))
        token = headers["Authorization"]
        return response(202 if token.endswith("token-a") else 404, {"state": "deleted"})


def test_owner_isolation_promotes_identity_only_after_cross_account_checks():
    client = FakeClient()
    result = exercise.owner_isolation(client, "token-a", "token-b")
    assert result["status"] == "passed"
    assert "owner-isolation" in result["evidence"]
    assert any(call[0] == "PUT" and call[2]["Authorization"].endswith("token-b") for call in client.calls)
    assert any(call[0] == "POST" and str(call[1]).endswith("/cancel") and call[2]["Authorization"].endswith("token-b") for call in client.calls)


def test_owner_isolation_rejects_same_workspace():
    class SameWorkspace(FakeClient):
        def get(self, path, headers=None):
            if path == "/api/v1/me":
                token = headers["Authorization"]
                return response(200, {"account_id": "a" if token.endswith("token-a") else "b", "workspace_id": "same"})
            return super().get(path, headers)

    with pytest.raises(exercise.ExerciseFailure, match="distinct workspaces"):
        exercise.owner_isolation(SameWorkspace(), "token-a", "token-b")


def test_require_https_base_rejects_credentials_and_non_https():
    with pytest.raises(exercise.ExerciseFailure):
        exercise.require_https_base("http://staging.example.test")
    with pytest.raises(exercise.ExerciseFailure):
        exercise.require_https_base("https://user:pass@staging.example.test")
    assert exercise.require_https_base("https://staging.example.test/") == "https://staging.example.test"


def test_merge_evidence_preserves_manual_checks():
    base = {"backup_restore": {"status": "passed", "evidence": "drill-42"}}
    updates = {"identity": {"status": "passed", "evidence": "two-account-check"}}
    merged = exercise.merge_evidence(base, updates)
    assert merged["backup_restore"]["evidence"] == "drill-42"
    assert merged["identity"]["status"] == "passed"


def test_artifact_authorization_rejects_cross_account_access(monkeypatch):
    class ArtifactClient:
        def post(self, path, headers=None, json=None):
            return response(202, {"id": "task-1"})

        def get(self, path, headers=None):
            token = headers["Authorization"]
            if path == "/api/v1/tasks/task-1":
                return response(200, {"state": "completed", "artifacts": [{"id": "artifact-1"}]})
            if path == "/api/v1/artifacts/artifact-1/download":
                if token.endswith("token-b"):
                    return response(404, {"error": {"code": "not_found"}})
                return response(200, {"filename": "report.pdf", "url": None, "content_path": "/api/v1/artifacts/artifact-1/content"})
            if path == "/api/v1/artifacts/artifact-1/content":
                return response(404 if token.endswith("token-b") else 200, content=b"pdf-bytes")
            raise AssertionError(path)

    result = exercise.artifact_authorization(ArtifactClient(), "token-a", "token-b", 30)
    assert result["status"] == "passed"
    assert "artifact authorization" in result["evidence"]



def test_artifact_authorization_requires_guessed_id_denial_and_signed_url_expiry(monkeypatch):
    artifact_id = "11111111-1111-1111-1111-111111111111"
    signed_url = "https://storage.example.test/object?signature=test"
    calls = []

    class ArtifactClient:
        def post(self, path, headers=None, json=None):
            if path == "/api/v1/tasks":
                return response(202, {"id": "task-1"})
            raise AssertionError(path)

        def get(self, path, headers=None):
            calls.append((path, headers))
            token = headers["Authorization"]
            bob = token.endswith("token-b")
            if path == "/api/v1/tasks/task-1":
                return response(
                    200,
                    {
                        "state": "completed",
                        "artifacts": [{"id": artifact_id}],
                    },
                )
            if path == f"/api/v1/artifacts/{artifact_id}/download":
                if bob:
                    return response(404, {"error": {"code": "not_found"}})
                return response(
                    200,
                    {
                        "filename": "report.pdf",
                        "url": signed_url,
                        "content_path": None,
                    },
                )
            if path == f"/api/v1/artifacts/{artifact_id}/content":
                return response(404, {"error": {"code": "not_found"}})
            if path.startswith("/api/v1/artifacts/"):
                return response(404, {"error": {"code": "not_found"}})
            raise AssertionError(path)

    web_calls = []

    def fake_get(url, timeout=None, follow_redirects=None):
        web_calls.append(url)
        if len(web_calls) == 1:
            return response(200, content=b"artifact-bytes")
        return response(403, content=b"expired")

    monkeypatch.setattr(exercise.httpx, "get", fake_get)
    monkeypatch.setattr(exercise.time, "sleep", lambda _seconds: None)

    result = exercise.artifact_authorization(
        ArtifactClient(),
        "token-a",
        "token-b",
        30,
        signed_url_expiry_wait_seconds=61,
    )

    assert result["status"] == "passed"
    assert "guessed-ID denial" in result["evidence"]
    assert "expired signed-URL denial" in result["evidence"]
    assert web_calls == [signed_url, signed_url]
    guessed_paths = [
        path
        for path, _headers in calls
        if artifact_id not in path and path.startswith("/api/v1/artifacts/")
    ]
    assert any(path.endswith("/download") for path in guessed_paths)
    assert any(path.endswith("/content") for path in guessed_paths)


def test_artifact_authorization_rejects_local_content_path_for_controlled_staging(monkeypatch):
    artifact_id = "11111111-1111-1111-1111-111111111111"

    class LocalPathClient:
        def post(self, path, headers=None, json=None):
            if path == "/api/v1/tasks":
                return response(202, {"id": "task-1"})
            raise AssertionError(path)

        def get(self, path, headers=None):
            token = headers["Authorization"]
            bob = token.endswith("token-b")
            if path == "/api/v1/tasks/task-1":
                return response(
                    200,
                    {
                        "state": "completed",
                        "artifacts": [{"id": artifact_id}],
                    },
                )
            if path == f"/api/v1/artifacts/{artifact_id}/download":
                if bob:
                    return response(404, {"error": {"code": "not_found"}})
                return response(
                    200,
                    {
                        "filename": "report.pdf",
                        "url": None,
                        "content_path": f"/api/v1/artifacts/{artifact_id}/content",
                    },
                )
            if path.startswith("/api/v1/artifacts/"):
                return response(404, {"error": {"code": "not_found"}})
            raise AssertionError(path)

    monkeypatch.setattr(exercise.time, "sleep", lambda _seconds: None)

    with pytest.raises(
        exercise.ExerciseFailure,
        match="requires a private S3 signed URL",
    ):
        exercise.artifact_authorization(
            LocalPathClient(),
            "token-a",
            "token-b",
            30,
            signed_url_expiry_wait_seconds=61,
        )


def test_artifact_authorization_fails_if_signed_url_still_works_after_expiry(monkeypatch):
    artifact_id = "11111111-1111-1111-1111-111111111111"
    signed_url = "https://storage.example.test/object?signature=test"

    class ArtifactClient:
        def post(self, path, headers=None, json=None):
            if path == "/api/v1/tasks":
                return response(202, {"id": "task-1"})
            raise AssertionError(path)

        def get(self, path, headers=None):
            token = headers["Authorization"]
            bob = token.endswith("token-b")
            if path == "/api/v1/tasks/task-1":
                return response(
                    200,
                    {
                        "state": "completed",
                        "artifacts": [{"id": artifact_id}],
                    },
                )
            if path == f"/api/v1/artifacts/{artifact_id}/download":
                if bob:
                    return response(404, {"error": {"code": "not_found"}})
                return response(
                    200,
                    {
                        "filename": "report.pdf",
                        "url": signed_url,
                        "content_path": None,
                    },
                )
            if path.startswith("/api/v1/artifacts/"):
                return response(404, {"error": {"code": "not_found"}})
            raise AssertionError(path)

    monkeypatch.setattr(
        exercise.httpx,
        "get",
        lambda *_args, **_kwargs: response(200, content=b"still-valid"),
    )
    monkeypatch.setattr(exercise.time, "sleep", lambda _seconds: None)

    with pytest.raises(
        exercise.ExerciseFailure,
        match="remained usable",
    ):
        exercise.artifact_authorization(
            ArtifactClient(),
            "token-a",
            "token-b",
            30,
            signed_url_expiry_wait_seconds=61,
        )


def test_personal_agent_owner_isolation_covers_goal_automation_and_memory():
    class PersonalAgentClient:
        def __init__(self):
            self.goal_revision = 1
            self.automation_revision = 1
            self.calls = []

        def get(self, path, headers=None):
            self.calls.append(("GET", path, headers))
            token = headers["Authorization"]
            bob = token.endswith("token-b")
            if path == "/api/v1/memory":
                return response(200, {"enabled": True, "facts": [] if bob else [{"id": "memory-1"}]})
            if path == "/api/v1/automations":
                return response(200, {"enabled": True, "automations": [] if bob else [{"id": "automation-1"}]})
            if path == "/api/v1/goals/goal-1":
                return response(404 if bob else 200, {"id": "goal-1", "revision": self.goal_revision})
            if path == "/api/v1/automations/automation-1":
                return response(404 if bob else 200, {"id": "automation-1", "revision": self.automation_revision})
            if path == "/api/v1/automations/automation-1/history":
                return response(404 if bob else 200, {"history": []})
            raise AssertionError(path)

        def post(self, path, headers=None, json=None):
            self.calls.append(("POST", path, headers, json))
            token = headers["Authorization"]
            bob = token.endswith("token-b")
            if path == "/api/v1/goals":
                return response(201, {"id": "goal-1", "revision": 1, "state": "active"})
            if path == "/api/v1/memory":
                return response(201, {"id": "memory-1", "version": 1})
            if path == "/api/v1/automations":
                return response(201, {"id": "automation-1", "revision": 1, "state": "active"})
            if path == "/api/v1/automations/automation-1/cancel":
                if bob:
                    return response(404, {"error": {"code": "not_found"}})
                self.automation_revision += 1
                return response(200, {"id": "automation-1", "revision": 2, "state": "cancelled"})
            if path == "/api/v1/goals/goal-1/cancel":
                if bob:
                    return response(404, {"error": {"code": "not_found"}})
                self.goal_revision += 1
                return response(200, {"id": "goal-1", "revision": 2, "state": "cancelled"})
            raise AssertionError(path)

        def patch(self, path, headers=None, json=None):
            self.calls.append(("PATCH", path, headers, json))
            if headers["Authorization"].endswith("token-b"):
                return response(404, {"error": {"code": "not_found"}})
            raise AssertionError(path)

        def put(self, path, headers=None, json=None):
            self.calls.append(("PUT", path, headers, json))
            if headers["Authorization"].endswith("token-b"):
                return response(404, {"error": {"code": "not_found"}})
            raise AssertionError(path)

        def delete(self, path, headers=None):
            self.calls.append(("DELETE", path, headers))
            if path == "/api/v1/memory/memory-1":
                if headers["Authorization"].endswith("token-b"):
                    return response(404, {"error": {"code": "not_found"}})
                return response(200, {"deleted": True})
            raise AssertionError(path)

    client = PersonalAgentClient()
    result = exercise.personal_agent_owner_isolation(client, "token-a", "token-b")
    assert result["status"] == "passed"
    assert "no Agent run" in result["evidence"]
    assert any(
        call[0] == "GET"
        and call[1] == "/api/v1/automations/automation-1/history"
        and call[2]["Authorization"].endswith("token-b")
        for call in client.calls
    )
    assert any(
        call[0] == "DELETE"
        and call[1] == "/api/v1/memory/memory-1"
        and call[2]["Authorization"].endswith("token-b")
        for call in client.calls
    )


def test_personal_agent_owner_isolation_fails_on_cross_owner_enumeration():
    class LeakyClient:
        def get(self, path, headers=None):
            if path == "/api/v1/memory":
                return response(200, {"enabled": True, "facts": [{"id": "memory-1"}]})
            if path == "/api/v1/goals/goal-1":
                return response(404, {"error": {"code": "not_found"}})
            raise AssertionError(path)

        def post(self, path, headers=None, json=None):
            if path == "/api/v1/goals":
                return response(201, {"id": "goal-1", "revision": 1, "state": "active"})
            if path == "/api/v1/memory":
                return response(201, {"id": "memory-1", "version": 1})
            raise AssertionError(path)

        def patch(self, path, headers=None, json=None):
            return response(404, {"error": {"code": "not_found"}})

    with pytest.raises(exercise.ExerciseFailure, match="enumerate account A's memory"):
        exercise.personal_agent_owner_isolation(LeakyClient(), "token-a", "token-b")


def test_owned_resource_manifest_is_strict(tmp_path):
    manifest = tmp_path / "resources.json"
    ids = {
        "agent_run_id": "11111111-1111-1111-1111-111111111111",
        "notification_id": "22222222-2222-2222-2222-222222222222",
        "action_id": "33333333-3333-3333-3333-333333333333",
        "artifact_id": "44444444-4444-4444-4444-444444444444",
        "connector_read_grant_id": "55555555-5555-5555-5555-555555555555",
        "connector_snapshot_id": "66666666-6666-6666-6666-666666666666",
    }
    manifest.write_text(json.dumps(ids), encoding="utf-8")
    assert exercise.owned_resource_manifest(manifest) == ids

    manifest.write_text(json.dumps(ids | {"token": "must-not-be-accepted"}), encoding="utf-8")
    with pytest.raises(exercise.ExerciseFailure, match="unexpected=token"):
        exercise.owned_resource_manifest(manifest)

    manifest.write_text(json.dumps({key: value for key, value in ids.items() if key != "action_id"}), encoding="utf-8")
    with pytest.raises(exercise.ExerciseFailure, match="missing=action_id"):
        exercise.owned_resource_manifest(manifest)


def test_remaining_owner_isolation_denies_cross_owner_surfaces():
    ids = {
        "agent_run_id": "11111111-1111-1111-1111-111111111111",
        "notification_id": "22222222-2222-2222-2222-222222222222",
        "action_id": "33333333-3333-3333-3333-333333333333",
        "artifact_id": "44444444-4444-4444-4444-444444444444",
        "connector_read_grant_id": "55555555-5555-5555-5555-555555555555",
        "connector_snapshot_id": "66666666-6666-6666-6666-666666666666",
    }

    class RemainingClient:
        def __init__(self):
            self.calls = []
            self.action = {
                "id": ids["action_id"],
                "state": "awaiting_approval",
                "preview_hash": "a" * 64,
            }

        @staticmethod
        def is_bob(headers):
            return headers["Authorization"].endswith("token-b")

        def get(self, path, headers=None):
            self.calls.append(("GET", path, headers))
            bob = self.is_bob(headers)
            if path == f"/api/v1/agent-runs/{ids['agent_run_id']}":
                return response(404 if bob else 200, {"id": ids["agent_run_id"], "state": "completed"})
            if path == "/api/v1/agent-runs":
                return response(200, {"runs": [] if bob else [{"id": ids["agent_run_id"]}]})
            if path == f"/api/v1/agent-runs/{ids['agent_run_id']}/events":
                return response(404 if bob else 200, {"events": [], "terminal": True})
            if path == "/api/v1/notifications":
                return response(
                    200,
                    {
                        "enabled": True,
                        "notifications": [] if bob else [{"id": ids["notification_id"]}],
                    },
                )
            if path == f"/api/v1/actions/{ids['action_id']}":
                return response(404 if bob else 200, self.action)
            if path == "/api/v1/actions":
                return response(200, {"actions": [] if bob else [self.action]})
            if path == "/api/v1/artifacts":
                return response(
                    200,
                    {
                        "artifacts": [] if bob else [{"id": ids["artifact_id"]}],
                        "attachments_enabled": False,
                        "document_sharing_enabled": False,
                    },
                )
            if path == f"/api/v1/artifacts/{ids['artifact_id']}/download":
                if bob:
                    return response(404, {"error": {"code": "not_found"}})
                return response(
                    200,
                    {
                        "filename": "artifact.txt",
                        "url": None,
                        "content_path": f"/api/v1/artifacts/{ids['artifact_id']}/content",
                    },
                )
            if path == f"/api/v1/artifacts/{ids['artifact_id']}/content":
                return response(404 if bob else 200, content=b"artifact")
            if path == "/api/v1/connector-read-grants":
                return response(
                    200,
                    {
                        "enabled": True,
                        "grants": [] if bob else [{"id": ids["connector_read_grant_id"]}],
                    },
                )
            if path == f"/api/v1/connector-read-grants/{ids['connector_read_grant_id']}/snapshots":
                return response(
                    404 if bob else 200,
                    {"snapshots": [] if bob else [{"id": ids["connector_snapshot_id"]}]},
                )
            if path == f"/api/v1/connector-read-grants/{ids['connector_read_grant_id']}/subscription":
                return response(404 if bob else 200, {"subscription": None})
            raise AssertionError(path)

        def post(self, path, headers=None, json=None):
            self.calls.append(("POST", path, headers, json))
            bob = self.is_bob(headers)
            if path in {
                f"/api/v1/agent-runs/{ids['agent_run_id']}/cancel",
                f"/api/v1/notifications/{ids['notification_id']}/read",
                f"/api/v1/actions/{ids['action_id']}/approve",
                f"/api/v1/actions/{ids['action_id']}/cancel",
            }:
                return response(404 if bob else 200, {"ok": True})
            raise AssertionError(path)

    client = RemainingClient()
    result = exercise.remaining_owner_isolation(client, "token-a", "token-b", ids)
    assert result["status"] == "passed"
    assert "action read/approval/cancel immutability" in result["evidence"]
    assert any(
        call[0] == "POST"
        and call[1].endswith("/approve")
        and call[2]["Authorization"].endswith("token-b")
        for call in client.calls
    )
    assert any(
        call[0] == "GET"
        and call[1].endswith("/snapshots")
        and call[2]["Authorization"].endswith("token-b")
        for call in client.calls
    )


def test_remaining_owner_isolation_fails_if_bob_can_enumerate_action():
    ids = {
        "agent_run_id": "11111111-1111-1111-1111-111111111111",
        "notification_id": "22222222-2222-2222-2222-222222222222",
        "action_id": "33333333-3333-3333-3333-333333333333",
        "artifact_id": "44444444-4444-4444-4444-444444444444",
        "connector_read_grant_id": "55555555-5555-5555-5555-555555555555",
        "connector_snapshot_id": "66666666-6666-6666-6666-666666666666",
    }

    class LeakyActionClient:
        @staticmethod
        def is_bob(headers):
            return headers["Authorization"].endswith("token-b")

        def get(self, path, headers=None):
            bob = self.is_bob(headers)
            if path == f"/api/v1/agent-runs/{ids['agent_run_id']}":
                return response(404 if bob else 200, {"id": ids["agent_run_id"]})
            if path == "/api/v1/agent-runs":
                return response(200, {"runs": []})
            if path == f"/api/v1/agent-runs/{ids['agent_run_id']}/events":
                return response(404, {"error": {"code": "not_found"}})
            if path == "/api/v1/notifications":
                return response(
                    200,
                    {"enabled": True, "notifications": [] if bob else [{"id": ids["notification_id"]}]},
                )
            if path == f"/api/v1/actions/{ids['action_id']}":
                return response(
                    404 if bob else 200,
                    {"id": ids["action_id"], "state": "awaiting_approval", "preview_hash": "a" * 64},
                )
            if path == "/api/v1/actions":
                return response(200, {"actions": [{"id": ids["action_id"]}]})
            raise AssertionError(path)

        def post(self, path, headers=None, json=None):
            return response(404, {"error": {"code": "not_found"}})

    with pytest.raises(exercise.ExerciseFailure, match="enumerate account A's action"):
        exercise.remaining_owner_isolation(
            LeakyActionClient(), "token-a", "token-b", ids
        )
