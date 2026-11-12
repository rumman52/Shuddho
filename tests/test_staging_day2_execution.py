from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from scripts import staging_release_freeze as freeze
from scripts import staging_day2_execution as day2


SHA = "a" * 40
DOC_ID = "11111111-1111-4111-8111-111111111111"
TASK_ID = "22222222-2222-4222-8222-222222222222"
ART_ID = "33333333-3333-4333-8333-333333333333"
VERSION_ID = "44444444-4444-4444-8444-444444444444"
SOURCE = b"Day 2 synthetic private note: the sample budget is forty-two units.\n"
ARTIFACT = b"%PDF-1.4\nsynthetic-test-artifact\n"
SIGNED = "https://storage.example.test/private?signature=redacted"


def runtime():
    return {
        "schema_version": 2,
        "source_revision": SHA,
        "environment": "staging",
        "capabilities": {
            **{key: False for key in freeze.RUNTIME_CAPABILITY_KEYS},
            **{key: False for key in day2.NEW_RUNTIME_CAPABILITIES},
            "coworker": True,
        },
        "reviewed_skills": {"research": {"state": "unselected"}},
        "action_providers": [],
        "cohort": {"enforced": False, "configured_members": 0, "max_users": 5},
    }


def frozen(manifest=None):
    return {
        "status": "frozen",
        "release": {"release_id": "stage-day2-001", "environment": "staging", "source_revision": SHA},
        "runtime_manifest_sha256": freeze.canonical_sha256(manifest or runtime()),
    }


class Day2API:
    def __init__(self, *, attempts=1, foreign_download=404, document_grounded=True, cites_document=True):
        self.calls = []
        self.uploaded = None
        self.task_payload = None
        self.attempts = attempts
        self.foreign_download = foreign_download
        self.document_grounded = document_grounded
        self.cites_document = cites_document
        self.manifest = runtime()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        user = request.headers.get("Authorization", "").split(" ")[-1]
        self.calls.append((method, path, user))
        def res(code, value=None, content=None):
            return httpx.Response(code, json=value, request=request) if content is None else httpx.Response(code, content=content, request=request)
        if method == "GET" and path == "/api/v1/runtime-manifest":
            return res(200, self.manifest)
        if method == "GET" and path == "/api/v1/me":
            return res(200, {"account_id": "owner-a" if user == "token-a" else "owner-b",
                             "workspace_id": "workspace-a" if user == "token-a" else "workspace-b"})
        if method == "POST" and path == "/api/v1/documents":
            value = json.loads(request.content)
            assert value["sha256"] == hashlib.sha256(SOURCE).hexdigest()
            self.document_filename = value["filename"]
            return res(201, {"id": DOC_ID, "state": "pending"})
        if method == "PUT" and path == f"/api/v1/documents/{DOC_ID}/content":
            if user == "token-b":
                return res(404, {})
            self.uploaded = request.content
            return res(200, {"id": DOC_ID, "state": "uploaded"})
        if method == "GET" and path == f"/api/v1/documents/{DOC_ID}/content":
            return res(404, {}) if user == "token-b" else res(200, content=self.uploaded)
        if method == "GET" and path == "/api/v1/documents":
            return res(200, {"documents": []})
        if method == "POST" and path == "/api/v1/tasks":
            self.task_payload = json.loads(request.content)
            return res(202, {"id": TASK_ID, "state": "queued"})
        if method == "GET" and path == f"/api/v1/tasks/{TASK_ID}":
            if user == "token-b":
                return res(404, {})
            return res(200, {
                "id": TASK_ID, "state": "completed", "workflow_version": "report_email_v1",
                "input": {"document_ids": [DOC_ID]},
                "output_language": "en",
                "draft": {"report": {"summary": "A short English summary.",
                                     "sections": [{"source_ids": [VERSION_ID if self.cites_document else "notes"]}]}},
                "sources": [{"id": VERSION_ID, "document_id": DOC_ID,
                             "label": self.document_filename,
                             "sha256": hashlib.sha256(SOURCE).hexdigest()}] if self.document_grounded else [],
                "usage": {"model_attempts": self.attempts, "accounted_tokens": 80 if self.attempts else 0},
                "artifacts": [{"id": ART_ID, "filename": "report.pdf",
                               "byte_size": len(ARTIFACT), "sha256": hashlib.sha256(ARTIFACT).hexdigest()}],
            })
        if method == "GET" and path == f"/api/v1/tasks/{TASK_ID}/events":
            return res(404, {}) if user == "token-b" else res(200, {"terminal": True, "state": "completed", "events": [{"phase": "completed"}]})
        if method == "GET" and path == f"/api/v1/artifacts/{ART_ID}/download":
            return res(self.foreign_download, {}) if user == "token-b" else res(200, {"url": SIGNED, "filename": "report.pdf"})
        if method == "GET" and path == f"/api/v1/artifacts/{ART_ID}/content":
            return res(404, {}) if user == "token-b" else res(200, content=ARTIFACT)
        raise AssertionError((method, path, user))


def exercise(monkeypatch, api):
    monkeypatch.setattr(day2.httpx, "get", lambda url, **kwargs: httpx.Response(
        200, content=ARTIFACT, request=httpx.Request("GET", url)))
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        return day2.run_probe(client, "token-a", "token-b", frozen(api.manifest), SOURCE, timeout_seconds=5)


def test_day2_real_document_artifact_and_owner_denial_contract(monkeypatch):
    api = Day2API()
    result = exercise(monkeypatch, api)
    assert result["task_id"] == TASK_ID
    assert result["document_id"] == DOC_ID
    assert result["artifact_id"] == ART_ID
    assert result["artifact_sha256"] == hashlib.sha256(ARTIFACT).hexdigest()
    assert result["model_attempts"] == 1
    assert api.uploaded == SOURCE
    assert api.task_payload["document_ids"] == [DOC_ID]
    assert api.task_payload["output_language"] == "en"
    assert any(c == ("GET", f"/api/v1/artifacts/{ART_ID}/download", "token-b") for c in api.calls)
    assert any(c == ("GET", f"/api/v1/documents/{DOC_ID}/content", "token-b") for c in api.calls)


@pytest.mark.parametrize("change", ["unfrozen", "revision", "digest", "production"])
def test_day2_rejects_wrong_release_before_any_private_write(monkeypatch, change):
    api = Day2API()
    release = frozen(api.manifest)
    if change == "unfrozen":
        release["status"] = "prepared"
    elif change == "revision":
        release["release"]["source_revision"] = "b" * 40
    elif change == "digest":
        release["runtime_manifest_sha256"] = "0" * 64
    else:
        api.manifest["environment"] = "production"
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure):
            day2.run_probe(client, "token-a", "token-b", release, SOURCE, timeout_seconds=5)
    assert not any(method == "POST" for method, _, _ in api.calls)


def test_day2_rejects_fake_model_completion(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="model"):
        exercise(monkeypatch, Day2API(attempts=0))


def test_day2_rejects_foreign_artifact_download(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="cross-owner"):
        exercise(monkeypatch, Day2API(foreign_download=200))


def test_day2_rejects_presigned_url_outside_reviewed_storage_endpoint(monkeypatch):
    api = Day2API()
    monkeypatch.setattr(day2.httpx, "get", lambda url, **kwargs: httpx.Response(
        200, content=ARTIFACT, request=httpx.Request("GET", url)))
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="configured private storage endpoint"):
            day2.run_probe(
                client, "token-a", "token-b", frozen(api.manifest), SOURCE,
                timeout_seconds=5, trusted_storage_host="approved-storage.example.test",
            )


def test_day2_rejects_missing_selected_document_provenance(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="provenance"):
        exercise(monkeypatch, Day2API(document_grounded=False))


def test_day2_rejects_report_without_document_citation(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="cite the selected document"):
        exercise(monkeypatch, Day2API(cites_document=False))


def test_day2_rejects_identical_synthetic_accounts(monkeypatch):
    api = Day2API()
    orig = api.__call__
    def same_identity(request):
        if request.url.path == "/api/v1/me":
            return httpx.Response(200, json={"account_id": "same", "workspace_id": "same"}, request=request)
        return orig(request)
    with httpx.Client(transport=httpx.MockTransport(same_identity), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="distinct"):
            day2.run_probe(client, "token-a", "token-b", frozen(), SOURCE, timeout_seconds=5)
    assert not any(method == "POST" for method, _, _ in api.calls)


def test_runtime_manifest_v2_is_frozen_without_broadening_authority():
    manifest = runtime()
    caps = {**manifest["capabilities"]}
    for name in freeze.PA10_REQUIRED_TRUE:
        caps[name] = True
    state = {
        "schema_version": 1, "status": "prepared", "release_id": "stage-day2-001",
        "expected_environment": "staging", "expected_source_revision": SHA,
        "declared_capabilities": deepcopy(caps), "declared_action_providers": [],
        "declared_cohort": {"enforced": True, "max_users": 5},
        "build_reference": "image@sha256:test", "deployment_reference": "deploy-001",
        "rollout_manifest_sha256": "1" * 64, "provider_policy_sha256": "2" * 64,
        "synthetic_account_reference": "synthetic-owners-ref", "prepared_at": "2026-11-12T00:00:00+00:00",
    }
    # The runtime's additional v2 capability names must be explicit false,
    # rather than silently ignored by the release-freeze verifier.
    manifest["capabilities"] = caps
    manifest["action_providers"] = []
    manifest["cohort"] = {"enforced": True, "max_users": 5, "configured_members": 2}
    result = freeze.verify_runtime(state, manifest)
    assert result["status"] == "frozen"
    assert result["runtime_manifest_sha256"] == freeze.canonical_sha256(manifest)
    manifest["capabilities"]["agent_browser_read"] = True
    with pytest.raises(freeze.StagingReleaseFreezeError):
        freeze.verify_runtime(state, manifest)
