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
