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
OWNER_B_DOC_ID = "55555555-5555-4555-8555-555555555555"
OWNER_B_ARTIFACT_ID = "66666666-6666-4666-8666-666666666666"
OWNER_B_ARTIFACT = b"%PDF-1.4\\nowner-B-control-artifact\\n"
OWNER_B_SIGNED = "https://storage.example.test/owner-b-control?signature=redacted"


def runtime():
    return {
        "schema_version": 2,
        "source_revision": SHA,
        "environment": "staging",
        "capabilities": {
            **{key: False for key in freeze.RUNTIME_CAPABILITY_KEYS},
            **{key: False for key in day2.NEW_RUNTIME_CAPABILITIES},
            "coworker": True,
            "grounded_conversation_replies": False,
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
    def __init__(self, *, attempts=1, foreign_download=404, document_grounded=True, cites_document=True,
                 source=SOURCE):
        self.calls = []
        self.uploaded = None
        self.task_payload = None
        self.attempts = attempts
        self.foreign_download = foreign_download
        self.document_grounded = document_grounded
        self.cites_document = cites_document
        self.manifest = runtime()
        self.source = source

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
            assert value["sha256"] == hashlib.sha256(self.source).hexdigest()
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
                             "sha256": hashlib.sha256(self.source).hexdigest()}] if self.document_grounded else [],
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



class BidirectionalDay2API(Day2API):
    def __init__(
        self, *, include_owner_b_artifact=True,
        owner_a_reads_b_document=404, owner_a_writes_b_document=404,
        owner_b_reads_a_document=404, owner_b_writes_a_document=404,
        owner_a_reads_b_artifact=404, owner_a_downloads_b_artifact=404,
        owner_b_reads_a_artifact=404, owner_b_downloads_a_artifact=404,
        leak_b_document_to_a=False, leak_a_document_to_b=False,
        leak_b_artifact_to_a=False, leak_a_artifact_to_b=False,
        **kwargs,
    ):
        super().__init__(foreign_download=owner_b_downloads_a_artifact, **kwargs)
        self.include_owner_b_artifact = include_owner_b_artifact
        self.owner_a_reads_b_document = owner_a_reads_b_document
        self.owner_a_writes_b_document = owner_a_writes_b_document
        self.owner_b_reads_a_document = owner_b_reads_a_document
        self.owner_b_writes_a_document = owner_b_writes_a_document
        self.owner_a_reads_b_artifact = owner_a_reads_b_artifact
        self.owner_a_downloads_b_artifact = owner_a_downloads_b_artifact
        self.owner_b_reads_a_artifact = owner_b_reads_a_artifact
        self.leak_b_document_to_a = leak_b_document_to_a
        self.leak_a_document_to_b = leak_a_document_to_b
        self.leak_b_artifact_to_a = leak_b_artifact_to_a
        self.leak_a_artifact_to_b = leak_a_artifact_to_b
        self.owner_b_uploaded = None
        self.owner_b_filename = "owner-b-control.txt"
        self.task_created = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        user = request.headers.get("Authorization", "").split(" ")[-1]

        def res(code, value=None, content=None):
            return httpx.Response(code, json=value, request=request) if content is None else httpx.Response(code, content=content, request=request)

        if method == "POST" and path == "/api/v1/documents" and user == "token-b":
            self.calls.append((method, path, user))
            value = json.loads(request.content)
            self.owner_b_filename = value["filename"]
            return res(201, {"id": OWNER_B_DOC_ID, "state": "pending"})
        if method == "PUT" and path == f"/api/v1/documents/{OWNER_B_DOC_ID}/content":
            self.calls.append((method, path, user))
            if user == "token-a":
                return res(self.owner_a_writes_b_document, {})
            self.owner_b_uploaded = request.content
            return res(200, {"id": OWNER_B_DOC_ID, "state": "uploaded"})
        if method == "PUT" and path == f"/api/v1/documents/{DOC_ID}/content" and user == "token-b":
            self.calls.append((method, path, user))
            return res(self.owner_b_writes_a_document, {})
        if method == "GET" and path == f"/api/v1/documents/{OWNER_B_DOC_ID}/content":
            self.calls.append((method, path, user))
            if user == "token-a":
                return res(self.owner_a_reads_b_document, {})
            return res(200, content=self.owner_b_uploaded or b"")
        if method == "GET" and path == f"/api/v1/documents/{DOC_ID}/content" and user == "token-b":
            self.calls.append((method, path, user))
            return res(self.owner_b_reads_a_document, {})
        if method == "GET" and path == "/api/v1/documents":
            self.calls.append((method, path, user))
            if user == "token-a":
                documents = [{"id": DOC_ID}]
                if self.leak_b_document_to_a:
                    documents.append({"id": OWNER_B_DOC_ID})
            else:
                documents = [{"id": OWNER_B_DOC_ID}]
                if self.leak_a_document_to_b:
                    documents.append({"id": DOC_ID})
            return res(200, {"documents": documents})
        if method == "GET" and path == "/api/v1/artifacts":
            self.calls.append((method, path, user))
            owner_b = {
                "id": OWNER_B_ARTIFACT_ID, "filename": "owner-b-control.pdf",
                "byte_size": len(OWNER_B_ARTIFACT),
                "sha256": hashlib.sha256(OWNER_B_ARTIFACT).hexdigest(),
            }
            owner_a = {
                "id": ART_ID, "filename": "report.pdf", "byte_size": len(ARTIFACT),
                "sha256": hashlib.sha256(ARTIFACT).hexdigest(),
            }
            if user == "token-a":
                artifacts = [owner_a] if self.task_created else []
                if self.leak_b_artifact_to_a:
                    artifacts.append(owner_b)
            else:
                artifacts = [owner_b] if self.include_owner_b_artifact else []
                if self.leak_a_artifact_to_b and self.task_created:
                    artifacts.append(owner_a)
            return res(200, {"artifacts": artifacts})
        if method == "GET" and path == f"/api/v1/artifacts/{OWNER_B_ARTIFACT_ID}/content":
            self.calls.append((method, path, user))
            if user == "token-a":
                return res(self.owner_a_reads_b_artifact, {})
            return res(200, content=OWNER_B_ARTIFACT)
        if method == "GET" and path == f"/api/v1/artifacts/{OWNER_B_ARTIFACT_ID}/download":
            self.calls.append((method, path, user))
            if user == "token-a":
                return res(self.owner_a_downloads_b_artifact, {})
            return res(200, {"url": OWNER_B_SIGNED, "filename": "owner-b-control.pdf"})
        if method == "GET" and path == f"/api/v1/artifacts/{ART_ID}/content" and user == "token-b":
            self.calls.append((method, path, user))
            return res(self.owner_b_reads_a_artifact, {})
        if method == "POST" and path == "/api/v1/tasks":
            self.task_created = True
        return super().__call__(request)


def exercise_bidirectional(monkeypatch, api):
    def signed_get(url, **kwargs):
        content = OWNER_B_ARTIFACT if "owner-b-control" in url else ARTIFACT
        return httpx.Response(200, content=content, request=httpx.Request("GET", url))
    monkeypatch.setattr(day2.httpx, "get", signed_get)
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        return day2.run_probe(
            client, "token-a", "token-b", frozen(api.manifest), SOURCE,
            timeout_seconds=5, owner_b_artifact_id=OWNER_B_ARTIFACT_ID,
        )


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


def test_day2_pdf_source_uses_pdf_extension_and_original_bytes(monkeypatch):
    # The transport is synthetic; load_private_pdf separately validates the
    # real PDF before the operator runner can call this API path.
    source = b"%PDF-1.7\nprivate synthetic PDF protocol fixture"
    api = Day2API(source=source)
    monkeypatch.setattr(day2.httpx, "get", lambda url, **kwargs: httpx.Response(
        200, content=ARTIFACT, request=httpx.Request("GET", url)))
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        result = day2.run_probe(client, "token-a", "token-b", frozen(api.manifest), source, timeout_seconds=5)
    assert result["document_sha256"] == hashlib.sha256(source).hexdigest()
    assert api.uploaded == source
    assert api.document_filename.endswith(".pdf")
    assert api.task_payload["output_language"] == "en"


def test_day2_pdf_operator_path_requires_private_real_text_pdf(tmp_path):
    source_path = tmp_path / "selected.pdf"
    source_path.write_bytes(b"%PDF-1.7\nnot a real PDF")
    source_path.chmod(0o644)
    with pytest.raises(day2.Day2Failure, match="owner-only"):
        day2.load_private_pdf(source_path)
    link = tmp_path / "linked.pdf"
    link.symlink_to(source_path)
    with pytest.raises(day2.Day2Failure, match="nonsymlink"):
        day2.load_private_pdf(link)

    # The minimal test-and-build job omits the Coworker PDF parser extra;
    # exercise format validation in the full Coworker job instead.
    pytest.importorskip("pypdf")
    source_path.chmod(0o600)
    with pytest.raises(day2.Day2Failure, match="invalid or unreadable"):
        day2.load_private_pdf(source_path)


def test_day2_pdf_operator_path_accepts_text_based_pdf(tmp_path):
    pytest.importorskip("pypdf")
    weasyprint = pytest.importorskip("weasyprint")
    source = weasyprint.HTML(string="<p>Day 2 synthetic private English source text.</p>").write_pdf()
    path = tmp_path / "selected.pdf"
    path.write_bytes(source)
    path.chmod(0o600)
    assert day2.load_private_pdf(path) == source


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
        # The reviewed rollout/worker declares 43 controls. The API response
        # adds one separately checked UI-derived field.
        "declared_capabilities": {key: caps[key] for key in freeze.RUNTIME_CAPABILITY_KEYS},
        "declared_action_providers": [],
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


def test_document_task_persisted_outbox_proves_single_delivered_effect():
    from types import SimpleNamespace

    one = SimpleNamespace(task_id=TASK_ID, delivered=True, attempts=2)
    assert day2.document_outbox_receipt(TASK_ID, [one]) == {
        "task_id": TASK_ID, "effect_count": 1, "delivered": True,
        "dispatch_attempts": 2,
    }


@pytest.mark.parametrize("rows", [
    [], [None, None],
    [{"task_id": "not-this-task", "delivered": True, "attempts": 1}],
    [{"task_id": TASK_ID, "delivered": False, "attempts": 1}],
    [{"task_id": TASK_ID, "delivered": True, "attempts": 0}],
    [{"task_id": TASK_ID, "delivered": True, "attempts": True}],
])
def test_document_task_outbox_missing_or_undelivered_fails_closed(rows):
    from types import SimpleNamespace

    records = [SimpleNamespace(**row) if isinstance(row, dict) else row for row in rows]
    with pytest.raises(day2.Day2Failure, match="outbox"):
        day2.document_outbox_receipt(TASK_ID, records)


def test_pdf_task_outbox_sql_error_cannot_leak_driver_payload():
    from types import SimpleNamespace

    sqlalchemy = pytest.importorskip("sqlalchemy")
    pytest.importorskip("services.coworker.models")

    class BrokenSessions:
        def __enter__(self):
            raise sqlalchemy.exc.SQLAlchemyError("private SQL address and secret")

        def __exit__(self, *_args):
            return False

    container = SimpleNamespace(
        repository=SimpleNamespace(sessions=lambda: BrokenSessions())
    )
    with pytest.raises(day2.Day2Failure, match="could not be independently verified") as raised:
        day2.persisted_document_outbox(container, TASK_ID)
    assert "private SQL address" not in str(raised.value)


def test_day2_proves_bidirectional_document_and_artifact_access(monkeypatch):
    api = BidirectionalDay2API()
    result = exercise_bidirectional(monkeypatch, api)
    proof = result["owner_isolation"]
    assert proof["status"] == "passed"
    assert proof["identities_distinct"] is True
    assert proof["owners"]["a"]["document_id"] == DOC_ID
    assert proof["owners"]["b"]["document_id"] == OWNER_B_DOC_ID
    assert proof["owners"]["a"]["artifact_id"] == ART_ID
    assert proof["owners"]["b"]["artifact_id"] == OWNER_B_ARTIFACT_ID
    for owner in ("a", "b"):
        row = proof["owners"][owner]
        assert row["document_read"] == "passed"
        assert row["own_document_list"] == "included"
        assert row["foreign_document_read"] == "denied_404"
        assert row["foreign_document_write"] == "denied_404"
        assert row["foreign_document_list"] == "excluded"
        assert row["artifact_content_read"] == "passed"
        assert row["artifact_download"] == "passed"
        assert row["own_artifact_list"] == "included"
        assert row["foreign_artifact_content"] == "denied_404"
        assert row["foreign_artifact_download"] == "denied_404"
        assert row["foreign_artifact_list"] == "excluded"


def test_day2_requires_owner_b_control_artifact_before_any_private_write(monkeypatch):
    api = BidirectionalDay2API(include_owner_b_artifact=False)
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="owner B synthetic artifact"):
            day2.run_probe(
                client, "token-a", "token-b", frozen(api.manifest), SOURCE,
                timeout_seconds=5, owner_b_artifact_id=OWNER_B_ARTIFACT_ID,
            )
    assert not any(method in {"POST", "PUT"} for method, _, _ in api.calls)


@pytest.mark.parametrize("override", [
    {"owner_a_reads_b_document": 200},
    {"owner_a_writes_b_document": 200},
    {"owner_b_reads_a_document": 200},
    {"owner_b_writes_a_document": 200},
    {"owner_a_reads_b_artifact": 200},
    {"owner_a_downloads_b_artifact": 200},
    {"owner_b_reads_a_artifact": 200},
    {"owner_b_downloads_a_artifact": 200},
])
def test_day2_rejects_cross_owner_access_in_either_direction(monkeypatch, override):
    api = BidirectionalDay2API(**override)
    with pytest.raises(day2.Day2Failure, match="cross-owner"):
        exercise_bidirectional(monkeypatch, api)


@pytest.mark.parametrize("override", [
    {"leak_b_document_to_a": True},
    {"leak_a_document_to_b": True},
    {"leak_b_artifact_to_a": True},
    {"leak_a_artifact_to_b": True},
])
def test_day2_rejects_foreign_resource_enumeration(monkeypatch, override):
    api = BidirectionalDay2API(**override)
    with pytest.raises(day2.Day2Failure, match="enumerat|list"):
        exercise_bidirectional(monkeypatch, api)
