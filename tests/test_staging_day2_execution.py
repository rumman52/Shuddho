from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
from io import BytesIO
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
AUTH_ISSUER = "https://auth.example.test/auth/v1"
AUTH_AUDIENCE = "authenticated"


def _b64(value):
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()


def make_test_token(subject, *, issuer=AUTH_ISSUER, audience=AUTH_AUDIENCE, expires_at=None):
    now = int(time.time())
    claims = {
        "iss": issuer, "aud": audience, "exp": expires_at if expires_at is not None else now + 3600,
        "iat": now, "sub": subject, "role": "authenticated",
    }
    return _b64({"alg": "RS256", "kid": "test-key"}) + "." + _b64(claims) + ".c2ln"


def decode_test_token_claims(token):
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


TOKEN_A = make_test_token("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
TOKEN_B = make_test_token("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")


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
                 source=SOURCE, wrong_account_binding=False, summary="A short English summary."):
        self.calls = []
        self.uploaded = None
        self.task_payload = None
        self.attempts = attempts
        self.foreign_download = foreign_download
        self.document_grounded = document_grounded
        self.cites_document = cites_document
        self.manifest = runtime()
        self.source = source
        self.summary = summary
        self.wrong_account_binding = wrong_account_binding

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        user = request.headers.get("Authorization", "").split(" ")[-1]
        self.calls.append((method, path, user))
        def res(code, value=None, content=None):
            return httpx.Response(code, json=value, request=request) if content is None else httpx.Response(code, content=content, request=request)
        if method == "GET" and path == "/api/v1/runtime-manifest":
            return res(200, self.manifest)
        if method == "GET" and path == "/api/v1/me":
            claims = decode_test_token_claims(user)
            account_id = hashlib.sha256(json.dumps([claims["iss"], claims["sub"]]).encode()).hexdigest()
            if self.wrong_account_binding:
                account_id = "account-subject-mismatch"
            return res(200, {"account_id": account_id,
                             "workspace_id": "workspace-" + str(claims["sub"])})
        if method == "POST" and path == "/api/v1/documents":
            value = json.loads(request.content)
            assert value["sha256"] == hashlib.sha256(self.source).hexdigest()
            self.document_filename = value["filename"]
            return res(201, {"id": DOC_ID, "state": "pending"})
        if method == "PUT" and path == f"/api/v1/documents/{DOC_ID}/content":
            if user == TOKEN_B:
                return res(404, {})
            self.uploaded = request.content
            return res(200, {"id": DOC_ID, "state": "uploaded"})
        if method == "GET" and path == f"/api/v1/documents/{DOC_ID}/content":
            return res(404, {}) if user == TOKEN_B else res(200, content=self.uploaded)
        if method == "GET" and path == "/api/v1/documents":
            return res(200, {"documents": []})
        if method == "POST" and path == "/api/v1/tasks":
            self.task_payload = json.loads(request.content)
            return res(202, {"id": TASK_ID, "state": "queued"})
        if method == "GET" and path == f"/api/v1/tasks/{TASK_ID}":
            if user == TOKEN_B:
                return res(404, {})
            return res(200, {
                "id": TASK_ID, "state": "completed", "workflow_version": "report_email_v1",
                "input": {"document_ids": [DOC_ID]},
                "output_language": "en",
                "draft": {"report": {"summary": self.summary,
                                     "sections": [{"source_ids": [VERSION_ID if self.cites_document else "notes"]}]}},
                "sources": [{"id": VERSION_ID, "document_id": DOC_ID,
                             "label": self.document_filename,
                             "sha256": hashlib.sha256(self.source).hexdigest()}] if self.document_grounded else [],
                "usage": {"model_attempts": self.attempts, "accounted_tokens": 80 if self.attempts else 0},
                "artifacts": [{"id": ART_ID, "filename": "report.pdf",
                               "byte_size": len(ARTIFACT), "sha256": hashlib.sha256(ARTIFACT).hexdigest()}],
            })
        if method == "GET" and path == f"/api/v1/tasks/{TASK_ID}/events":
            return res(404, {}) if user == TOKEN_B else res(200, {"terminal": True, "state": "completed", "events": [{"phase": "completed"}]})
        if method == "GET" and path == f"/api/v1/artifacts/{ART_ID}/download":
            return res(self.foreign_download, {}) if user == TOKEN_B else res(200, {"url": SIGNED, "filename": "report.pdf"})
        if method == "GET" and path == f"/api/v1/artifacts/{ART_ID}/content":
            return res(404, {}) if user == TOKEN_B else res(200, content=ARTIFACT)
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
        owner_b_downloads_a_artifact = kwargs.pop("foreign_download", owner_b_downloads_a_artifact)
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

        if method == "POST" and path == "/api/v1/documents" and user == TOKEN_B:
            self.calls.append((method, path, user))
            value = json.loads(request.content)
            self.owner_b_filename = value["filename"]
            return res(201, {"id": OWNER_B_DOC_ID, "state": "pending"})
        if method == "PUT" and path == f"/api/v1/documents/{OWNER_B_DOC_ID}/content":
            self.calls.append((method, path, user))
            if user == TOKEN_A:
                return res(self.owner_a_writes_b_document, {})
            self.owner_b_uploaded = request.content
            return res(200, {"id": OWNER_B_DOC_ID, "state": "uploaded"})
        if method == "PUT" and path == f"/api/v1/documents/{DOC_ID}/content" and user == TOKEN_B:
            self.calls.append((method, path, user))
            return res(self.owner_b_writes_a_document, {})
        if method == "GET" and path == f"/api/v1/documents/{OWNER_B_DOC_ID}/content":
            self.calls.append((method, path, user))
            if user == TOKEN_A:
                return res(self.owner_a_reads_b_document, {})
            return res(200, content=self.owner_b_uploaded or b"")
        if method == "GET" and path == f"/api/v1/documents/{DOC_ID}/content" and user == TOKEN_B:
            self.calls.append((method, path, user))
            return res(self.owner_b_reads_a_document, {})
        if method == "GET" and path == "/api/v1/documents":
            self.calls.append((method, path, user))
            if user == TOKEN_A:
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
            if user == TOKEN_A:
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
            if user == TOKEN_A:
                return res(self.owner_a_reads_b_artifact, {})
            return res(200, content=OWNER_B_ARTIFACT)
        if method == "GET" and path == f"/api/v1/artifacts/{OWNER_B_ARTIFACT_ID}/download":
            self.calls.append((method, path, user))
            if user == TOKEN_A:
                return res(self.owner_a_downloads_b_artifact, {})
            return res(200, {"url": OWNER_B_SIGNED, "filename": "owner-b-control.pdf"})
        if method == "GET" and path == f"/api/v1/artifacts/{ART_ID}/content" and user == TOKEN_B:
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
            client, TOKEN_A, TOKEN_B, frozen(api.manifest), SOURCE,
            expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
            timeout_seconds=5, owner_b_artifact_id=OWNER_B_ARTIFACT_ID,
        )


def exercise(monkeypatch, api):
    return exercise_bidirectional(monkeypatch, api)


def test_day2_real_document_artifact_and_owner_denial_contract(monkeypatch):
    api = BidirectionalDay2API()
    result = exercise(monkeypatch, api)
    assert result["task_id"] == TASK_ID
    assert result["document_id"] == DOC_ID
    assert result["artifact_id"] == ART_ID
    assert result["artifact_sha256"] == hashlib.sha256(ARTIFACT).hexdigest()
    assert result["model_attempts"] == 1
    assert api.uploaded == SOURCE
    assert api.task_payload["document_ids"] == [DOC_ID]
    assert api.task_payload["output_language"] == "en"
    assert any(c == ("GET", f"/api/v1/artifacts/{ART_ID}/download", TOKEN_B) for c in api.calls)
    assert any(c == ("GET", f"/api/v1/documents/{DOC_ID}/content", TOKEN_B) for c in api.calls)


def test_day2_pdf_source_uses_pdf_extension_and_original_bytes(monkeypatch):
    # The transport is synthetic; load_private_pdf separately validates the
    # real PDF before the operator runner can call this API path.
    source = b"%PDF-1.7\nprivate synthetic PDF protocol fixture"
    api = BidirectionalDay2API(source=source)
    def signed_get(url, **kwargs):
        content = OWNER_B_ARTIFACT if "owner-b-control" in url else ARTIFACT
        return httpx.Response(200, content=content, request=httpx.Request("GET", url))
    monkeypatch.setattr(day2.httpx, "get", signed_get)
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        result = day2.run_probe(
            client, TOKEN_A, TOKEN_B, frozen(api.manifest), source,
            expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
            owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5,
        )
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
    api = BidirectionalDay2API()
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
            day2.run_probe(client, TOKEN_A, TOKEN_B, release, SOURCE, expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE, owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5)
    assert not any(method == "POST" for method, _, _ in api.calls)


def test_day2_rejects_fake_model_completion(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="model"):
        exercise(monkeypatch, BidirectionalDay2API(attempts=0))


def test_day2_rejects_foreign_artifact_download(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="cross-owner"):
        exercise(monkeypatch, BidirectionalDay2API(foreign_download=200))


def test_day2_rejects_presigned_url_outside_reviewed_storage_endpoint(monkeypatch):
    api = BidirectionalDay2API()
    monkeypatch.setattr(day2.httpx, "get", lambda url, **kwargs: httpx.Response(
        200, content=ARTIFACT, request=httpx.Request("GET", url)))
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="configured private storage endpoint"):
            day2.run_probe(
                client, TOKEN_A, TOKEN_B, frozen(api.manifest), SOURCE,
                expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
                owner_b_artifact_id=OWNER_B_ARTIFACT_ID,
                timeout_seconds=5, trusted_storage_host="approved-storage.example.test",
            )


def test_day2_rejects_missing_selected_document_provenance(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="provenance"):
        exercise(monkeypatch, BidirectionalDay2API(document_grounded=False))


def test_day2_rejects_report_without_document_citation(monkeypatch):
    with pytest.raises(day2.Day2Failure, match="cite the selected document"):
        exercise(monkeypatch, BidirectionalDay2API(cites_document=False))


def test_day2_rejects_identical_synthetic_accounts(monkeypatch):
    api = BidirectionalDay2API()
    orig = api.__call__
    def same_identity(request):
        if request.url.path == "/api/v1/me":
            return httpx.Response(200, json={"account_id": "same", "workspace_id": "same"}, request=request)
        return orig(request)
    with httpx.Client(transport=httpx.MockTransport(same_identity), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="distinct"):
            day2.run_probe(client, TOKEN_A, TOKEN_B, frozen(), SOURCE, expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE, owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5)
    assert not any(method == "POST" for method, _, _ in api.calls)


def test_runtime_manifest_v2_is_frozen_without_broadening_authority():
    manifest = runtime()
    caps = {**manifest["capabilities"]}
    for name in freeze.PA10_REQUIRED_TRUE:
        caps[name] = True
    state = {
        "schema_version": 1, "evidence_kind": freeze.EVIDENCE_KIND,
        "status": "prepared", "release_id": "stage-day2-001",
        "expected_environment": "staging", "expected_source_revision": SHA,
        # The reviewed rollout/worker declares 43 controls. The API response
        # adds one separately checked UI-derived field.
        "declared_capabilities": {key: caps[key] for key in freeze.RUNTIME_CAPABILITY_KEYS},
        "declared_action_providers": ["google", "microsoft"],
        "declared_cohort": {"reference": "synthetic-cohort", "enforced": True, "max_users": 5},
        "build_reference": "image@sha256:test", "deployment_reference": "deploy-001",
        "rollout_manifest_sha256": "1" * 64, "provider_policy_sha256": "2" * 64,
        "synthetic_account_reference": "synthetic-owners-ref", "prepared_at": "2026-11-12T00:00:00+00:00",
    }
    # The runtime's additional v2 capability names must be explicit false,
    # rather than silently ignored by the release-freeze verifier.
    manifest["capabilities"] = caps
    manifest["action_providers"] = ["google", "microsoft"]
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
    assert proof["identity_claims"]["subjects_distinct"] is True
    for owner in ("owner_a", "owner_b"):
        for claim in ("issuer_verified", "audience_verified", "expiry_verified",
                      "subject_verified", "api_subject_binding_verified"):
            assert proof["identity_claims"][owner][claim] is True
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
        with pytest.raises(day2.Day2Failure, match=r"(?i)owner B synthetic artifact"):
            day2.run_probe(
                client, TOKEN_A, TOKEN_B, frozen(api.manifest), SOURCE,
                expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
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
    with pytest.raises(day2.Day2Failure, match="enumerat|list|catalog|visible"):
        exercise_bidirectional(monkeypatch, api)


@pytest.mark.parametrize(("token", "message"), [
    (make_test_token("cccccccc-cccc-4ccc-8ccc-cccccccccccc", issuer="https://wrong.example.test/auth/v1"), "issuer"),
    (make_test_token("dddddddd-dddd-4ddd-8ddd-dddddddddddd", audience="wrong-audience"), "audience"),
    (make_test_token("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", expires_at=int(time.time()) + 10), "expired"),
    (make_test_token(""), "subject"),
])
def test_day2_rejects_invalid_managed_identity_claims(monkeypatch, token, message):
    api = BidirectionalDay2API()
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match=message):
            day2.run_probe(
                client, token, TOKEN_B, frozen(api.manifest), SOURCE,
                expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
                owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5,
            )


def test_day2_binds_verified_subject_to_authenticated_api_identity(monkeypatch):
    api = BidirectionalDay2API(wrong_account_binding=True)
    with pytest.raises(day2.Day2Failure, match="subjects"):
        exercise_bidirectional(monkeypatch, api)


def test_day2_rejects_malformed_owner_b_artifact_id_before_api_calls():
    api = BidirectionalDay2API()
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="valid UUID"):
            day2.run_probe(
                client, TOKEN_A, TOKEN_B, frozen(api.manifest), SOURCE,
                expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
                owner_b_artifact_id="not-a-uuid", timeout_seconds=5,
            )
    assert api.calls == []


def test_day2_fails_before_private_writes_if_owner_b_artifact_is_visible_to_a():
    api = BidirectionalDay2API(leak_b_artifact_to_a=True)
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="visible in owner A"):
            day2.run_probe(
                client, TOKEN_A, TOKEN_B, frozen(api.manifest), SOURCE,
                expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
                owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5,
            )
    assert not any(method in {"POST", "PUT"} for method, _, _ in api.calls)


def _synthetic_text_pdf(body: str) -> bytes:
    """Construct a valid text PDF using only the pypdf runtime dependency."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({body}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def _anchor_probe(monkeypatch, *, report_body: str, summary: str, source_body: str):
    pytest.importorskip("pypdf", reason="Install the coworker extra for real PDF fidelity tests")
    anchor = "SYNTHETIC_BUDGET_42_UNITS"
    source = _synthetic_text_pdf(source_body)
    report = _synthetic_text_pdf(report_body)
    monkeypatch.setattr(sys.modules[__name__], "ARTIFACT", report)
    api = BidirectionalDay2API(source=source, summary=summary)

    def signed_get(url, **kwargs):
        content = OWNER_B_ARTIFACT if "owner-b-control" in url else report
        return httpx.Response(200, content=content, request=httpx.Request("GET", url))

    monkeypatch.setattr(day2.httpx, "get", signed_get)
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        receipt = day2.run_probe(
            client, TOKEN_A, TOKEN_B, frozen(api.manifest), source,
            expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
            owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5,
            expected_source_anchor=anchor,
        )
    return receipt, api


def test_day2_english_summary_and_real_report_pdf_require_source_content_anchor(monkeypatch):
    anchor = "SYNTHETIC_BUDGET_42_UNITS"
    receipt, api = _anchor_probe(
        monkeypatch,
        source_body=f"Selected English source fact: {anchor}",
        summary=f"The synthetic source records {anchor}.",
        report_body=f"English report summary: {anchor}",
    )
    assert receipt["content_anchor_verification"] == "passed"
    assert anchor in api.task_payload["instruction"]
    assert anchor not in json.dumps(receipt)  # Marker/content is never copied to private receipts.
    assert receipt["artifact_sha256"] == hashlib.sha256(ARTIFACT).hexdigest()


@pytest.mark.parametrize("invalid", ["missing_summary", "missing_pdf_marker", "invalid_pdf"])
def test_day2_rejects_unrelated_or_unreadable_pdf_content(monkeypatch, invalid):
    pytest.importorskip("pypdf", reason="Install the coworker extra for real PDF fidelity tests")
    anchor = "SYNTHETIC_BUDGET_42_UNITS"
    source = _synthetic_text_pdf(f"Selected English source fact: {anchor}")
    report = (
        b"%PDF-1.4\nnot a real report\n" if invalid == "invalid_pdf"
        else _synthetic_text_pdf("Unrelated report content" if invalid == "missing_pdf_marker" else anchor)
    )
    summary = "The sample fact was processed." if invalid == "missing_summary" else f"Sample: {anchor}"
    monkeypatch.setattr(sys.modules[__name__], "ARTIFACT", report)
    api = BidirectionalDay2API(source=source, summary=summary)

    def signed_get(url, **kwargs):
        content = OWNER_B_ARTIFACT if "owner-b-control" in url else report
        return httpx.Response(200, content=content, request=httpx.Request("GET", url))

    monkeypatch.setattr(day2.httpx, "get", signed_get)
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match="marker|readable text-based PDF"):
            day2.run_probe(
                client, TOKEN_A, TOKEN_B, frozen(api.manifest), source,
                expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
                owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5,
                expected_source_anchor=anchor,
            )


@pytest.mark.parametrize(("source_body", "anchor", "message"), [
    (None, "SYNTHETIC_BUDGET_42_UNITS", "Selected synthetic PDF"),
    ("No marker in this text", "SYNTHETIC_BUDGET_42_UNITS", "expected source marker"),
    ("SYNTHETIC_BUDGET_42_UNITS", "unsafe anchor with spaces", "uppercase ASCII"),
])
def test_day2_source_marker_is_validated_before_any_api_request(source_body, anchor, message):
    pytest.importorskip("pypdf", reason="Install the coworker extra for real PDF fidelity tests")
    source = SOURCE if source_body is None else _synthetic_text_pdf(source_body)
    api = BidirectionalDay2API(source=source)
    with httpx.Client(transport=httpx.MockTransport(api), base_url="https://stage.example.test") as client:
        with pytest.raises(day2.Day2Failure, match=message):
            day2.run_probe(
                client, TOKEN_A, TOKEN_B, frozen(api.manifest), source,
                expected_auth_issuer=AUTH_ISSUER, expected_auth_audience=AUTH_AUDIENCE,
                owner_b_artifact_id=OWNER_B_ARTIFACT_ID, timeout_seconds=5,
                expected_source_anchor=anchor,
            )
    assert api.calls == []


@pytest.mark.parametrize(("token_a", "token_b", "message"), [
    (make_test_token("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                     issuer="https://wrong.example.test/auth/v1"), TOKEN_B, "issuer"),
    (TOKEN_A, make_test_token("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                              audience="unapproved"), "audience"),
    (TOKEN_A, make_test_token("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                              expires_at=int(time.time()) + 5), "expired"),
    (TOKEN_A, make_test_token(""), "subject"),
    (TOKEN_A, TOKEN_A, "distinct"),
])
def test_invalid_either_owner_token_never_reaches_network(token_a, token_b, message):
    """Validate both synthetic bearer claims before the first authenticated request."""
    def forbid_network(_request):
        pytest.fail("An unverified synthetic bearer reached the staging API.")

    with httpx.Client(
        transport=httpx.MockTransport(forbid_network), base_url="https://stage.example.test"
    ) as client:
        with pytest.raises(day2.Day2Failure, match=message):
            day2.run_probe(
                client, token_a, token_b, frozen(), SOURCE,
                expected_auth_issuer=AUTH_ISSUER,
                expected_auth_audience=AUTH_AUDIENCE,
                owner_b_artifact_id=OWNER_B_ARTIFACT_ID,
                timeout_seconds=5,
            )


def test_day2_live_operator_destinations_are_pinned_to_approved_supabase():
    from scripts.staging_prerequisite_preflight import (
        EXPECTED_AUTH_ISSUER, EXPECTED_S3_ENDPOINT,
    )

    day2.require_approved_staging_destinations(
        api_origin="https://shuddho-api-staging.onrender.com",
        auth_issuer=EXPECTED_AUTH_ISSUER,
        storage_endpoint=EXPECTED_S3_ENDPOINT,
    )


@pytest.mark.parametrize(("api_origin", "auth_issuer", "storage_endpoint", "message"), [
    ("https://unapproved.example.test", None, None, "API origin"),
    ("https://shuddho-api-staging.onrender.com:444", None, None, "API origin"),
    (None, "https://unapproved.supabase.co/auth/v1", None, "issuer"),
    (None, "https://bsmbvjenpvcyfjzwtuax.supabase.co/auth/v1/", None, "issuer"),
    (None, None, "https://unapproved.storage.supabase.co/storage/v1/s3", "storage"),
    (None, None, "https://bsmbvjenpvcyfjzwtuax.storage.supabase.co/storage/v1/s3/", "storage"),
])
def test_day2_operator_rejects_unapproved_credential_destinations(
    api_origin, auth_issuer, storage_endpoint, message,
):
    from scripts.staging_prerequisite_preflight import (
        EXPECTED_AUTH_ISSUER, EXPECTED_S3_ENDPOINT,
    )

    with pytest.raises(day2.Day2Failure, match=message):
        day2.require_approved_staging_destinations(
            api_origin=api_origin if api_origin is not None else "https://shuddho-api-staging.onrender.com",
            auth_issuer=auth_issuer if auth_issuer is not None else EXPECTED_AUTH_ISSUER,
            storage_endpoint=storage_endpoint if storage_endpoint is not None else EXPECTED_S3_ENDPOINT,
        )


def _model_provenance_fixture():
    from types import SimpleNamespace

    attempts = [
        SimpleNamespace(
            task_id=TASK_ID, owner_id="synthetic-owner", attempt=1,
            model="deepseek-flash", state="failed", charged_tokens=12,
            input_tokens=None, output_tokens=None, latency_ms=None,
        ),
        SimpleNamespace(
            task_id=TASK_ID, owner_id="synthetic-owner", attempt=2,
            model="deepseek-flash", state="completed", charged_tokens=60,
            input_tokens=45, output_tokens=15, latency_ms=125,
        ),
    ]
    draft = {
        "generation": {
            "provider": "deepseek", "model": "deepseek-flash",
            "task_type": "report_email", "finish_reason": "stop",
            "validator_result": "passed", "prompt_sha256": "b" * 64,
            "input_tokens": 45, "output_tokens": 15,
            "total_tokens": 60, "latency_ms": 125,
        }
    }
    return attempts, draft


def _verify_model_provenance(rows, draft, **changes):
    return day2.model_provenance_receipt(
        changes.get("task_id", TASK_ID),
        changes.get("owner_id", "synthetic-owner"),
        changes.get("task_state", "completed"),
        changes.get("workflow_version", "report_email_v1"),
        rows, draft,
        expected_model=changes.get("expected_model", "deepseek-flash"),
        expected_attempts=changes.get("expected_attempts", 2),
        expected_accounted_tokens=changes.get("expected_accounted_tokens", 72),
    )


def test_day2_model_provenance_corroborates_provider_and_sql_attempts():
    attempts, draft = _model_provenance_fixture()
    proof = _verify_model_provenance(attempts, draft)
    assert proof == {
        "status": "verified", "task_id": TASK_ID, "provider": "deepseek",
        "model": "deepseek-flash", "ledger_attempt_count": 2,
        "ledger_accounted_tokens": 72, "completed_attempt": 2,
        "completed_input_tokens": 45, "completed_output_tokens": 15,
        "completed_total_tokens": 60, "prompt_sha256": "b" * 64,
        "generation_validator": "passed",
    }


@pytest.mark.parametrize("corruption", [
    "wrong_task", "wrong_owner", "unfinished_task", "wrong_workflow",
    "wrong_model", "wrong_api_attempts", "wrong_api_tokens", "wrong_ledger_task",
    "wrong_ledger_owner", "wrong_ledger_model", "reserved_model_attempt",
    "duplicate_ordinal", "nonconsecutive_ordinal", "no_completed_attempt",
    "duplicate_completed_attempt", "negative_ledger_usage", "wrong_provider",
    "wrong_generation_model", "wrong_task_type", "wrong_finish_reason",
    "wrong_validator_result", "invalid_prompt_digest", "missing_generation",
    "missing_input_tokens", "zero_output_tokens", "underreported_total",
    "completed_attempt_token_mismatch", "wrong_latency",
])
def test_day2_rejects_unverified_model_provider_or_accounting(corruption):
    attempts, draft = _model_provenance_fixture()
    changes = {}
    if corruption == "wrong_task":
        changes["task_id"] = "unrelated-task"
    elif corruption == "wrong_owner":
        changes["owner_id"] = "unrelated-owner"
    elif corruption == "unfinished_task":
        changes["task_state"] = "running"
    elif corruption == "wrong_workflow":
        changes["workflow_version"] = "research_v1"
    elif corruption == "wrong_model":
        changes["expected_model"] = "unreviewed-model"
    elif corruption == "wrong_api_attempts":
        changes["expected_attempts"] = 3
    elif corruption == "wrong_api_tokens":
        changes["expected_accounted_tokens"] = 999
    elif corruption == "wrong_ledger_task":
        attempts[0].task_id = "unrelated-task"
    elif corruption == "wrong_ledger_owner":
        attempts[1].owner_id = "unrelated-owner"
    elif corruption == "wrong_ledger_model":
        attempts[1].model = "unreviewed-model"
    elif corruption == "reserved_model_attempt":
        attempts[0].state = "reserved"
    elif corruption == "duplicate_ordinal":
        attempts[1].attempt = 1
    elif corruption == "nonconsecutive_ordinal":
        attempts[1].attempt = 3
    elif corruption == "no_completed_attempt":
        attempts[1].state = "failed"
    elif corruption == "duplicate_completed_attempt":
        attempts[0].state = "completed"
    elif corruption == "negative_ledger_usage":
        attempts[1].charged_tokens = -1
    elif corruption == "wrong_provider":
        draft["generation"]["provider"] = "unapproved-provider"
    elif corruption == "wrong_generation_model":
        draft["generation"]["model"] = "unreviewed-model"
    elif corruption == "wrong_task_type":
        draft["generation"]["task_type"] = "other"
    elif corruption == "wrong_finish_reason":
        draft["generation"]["finish_reason"] = "length"
    elif corruption == "wrong_validator_result":
        draft["generation"]["validator_result"] = "failed"
    elif corruption == "invalid_prompt_digest":
        draft["generation"]["prompt_sha256"] = "incomplete"
    elif corruption == "missing_generation":
        draft.pop("generation")
    elif corruption == "missing_input_tokens":
        draft["generation"]["input_tokens"] = None
    elif corruption == "zero_output_tokens":
        draft["generation"]["output_tokens"] = 0
    elif corruption == "underreported_total":
        draft["generation"]["total_tokens"] = 40
    elif corruption == "completed_attempt_token_mismatch":
        attempts[1].charged_tokens = 55
    elif corruption == "wrong_latency":
        draft["generation"]["latency_ms"] = 200
    with pytest.raises(day2.Day2Failure, match="model|Model|provider|task|draft|token|usage"):
        _verify_model_provenance(attempts, draft, **changes)


def test_model_provenance_sql_driver_error_redacts_private_endpoint():
    from types import SimpleNamespace

    sqlalchemy = pytest.importorskip("sqlalchemy")
    pytest.importorskip("services.coworker.models")

    class BrokenSessions:
        def __enter__(self):
            raise sqlalchemy.exc.SQLAlchemyError("private SQL endpoint: secret-postgres")

        def __exit__(self, *_args):
            return False

    container = SimpleNamespace(
        repository=SimpleNamespace(sessions=lambda: BrokenSessions())
    )
    with pytest.raises(day2.Day2Failure, match="could not be independently verified") as raised:
        day2.persisted_model_provenance(
            container, TASK_ID, expected_owner_id="synthetic-owner",
            expected_model="deepseek-flash",
            expected_attempts=2, expected_accounted_tokens=72,
        )
    assert "secret-postgres" not in str(raised.value)


def test_model_provenance_rejects_db_task_owned_by_another_managed_identity():
    from types import SimpleNamespace

    pytest.importorskip("sqlalchemy")
    pytest.importorskip("services.coworker.models")

    class ScopedSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalar(self, _query):
            return SimpleNamespace(owner_id="unrelated-owner")

        def scalars(self, _query):
            pytest.fail("Wrong owner's model ledger must never be read")

    container = SimpleNamespace(
        repository=SimpleNamespace(sessions=lambda: ScopedSession())
    )
    with pytest.raises(day2.Day2Failure, match="managed owner A"):
        day2.persisted_model_provenance(
            container, TASK_ID, expected_owner_id="verified-owner-a",
            expected_model="deepseek-flash",
            expected_attempts=1, expected_accounted_tokens=60,
        )


# Part 02 D02.T04/G01: a worker-registry "fresh" flag is necessary but
# insufficient if registration or heartbeat timestamps are malformed, forged,
# in the future, or only lexically greater under a different UTC offset.
def _staging_worker_snapshot():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    now = datetime.now(timezone.utc)
    task_queue = "day2-worker-evidence"
    worker = {
        "id": "worker-identity-1",
        "task_queue": task_queue,
        "source_revision": SHA,
        "state": "running",
        "heartbeat_fresh": True,
        "started_at": (now - timedelta(minutes=2)).isoformat(),
        "heartbeat_at": (now - timedelta(seconds=5)).isoformat(),
    }
    container = SimpleNamespace(
        settings=SimpleNamespace(task_queue=task_queue),
        repository=SimpleNamespace(worker_inventory=lambda **_: [worker]),
    )
    return now, worker, container


def test_day2_active_worker_accepts_actual_fresh_utc_registration():
    now, worker, container = _staging_worker_snapshot()
    assert day2.active_worker(container, SHA)["id"] == worker["id"]


@pytest.mark.parametrize("tamper", [
    "future_heartbeat", "stale_heartbeat", "heartbeat_before_registration",
    "future_registration", "naive_heartbeat", "non_iso_heartbeat",
    "missing_worker_id",
])
def test_day2_active_worker_rejects_untrustworthy_registry_freshness(tamper):
    from datetime import timedelta

    now, worker, container = _staging_worker_snapshot()
    if tamper == "future_heartbeat":
        worker["heartbeat_at"] = (now + timedelta(seconds=45)).isoformat()
    elif tamper == "stale_heartbeat":
        worker["heartbeat_at"] = (now - timedelta(minutes=1)).isoformat()
    elif tamper == "heartbeat_before_registration":
        worker["started_at"] = (now - timedelta(seconds=3)).isoformat()
    elif tamper == "future_registration":
        worker["started_at"] = (now + timedelta(seconds=30)).isoformat()
    elif tamper == "naive_heartbeat":
        worker["heartbeat_at"] = now.replace(tzinfo=None).isoformat()
    elif tamper == "non_iso_heartbeat":
        worker["heartbeat_at"] = "undated"
    elif tamper == "missing_worker_id":
        worker["id"] = ""
    with pytest.raises(day2.Day2Failure, match="worker|Worker|heartbeat|Heartbeat"):
        day2.active_worker(container, SHA)


def _rechecked_worker(monkeypatch, before, after, task_queue):
    from types import SimpleNamespace

    # Exhaust the existing 15-second retry window deterministically.
    times = iter((100.0, 200.0))
    monkeypatch.setattr(
        day2, "time", SimpleNamespace(
            monotonic=lambda: next(times, 200.0),
            sleep=lambda _: None,
        ),
    )
    container = SimpleNamespace(
        settings=SimpleNamespace(task_queue=task_queue),
        repository=SimpleNamespace(worker_inventory=lambda **_: [after]),
    )
    return day2.heartbeat_advanced(container, before, SHA)


def test_day2_worker_heartbeat_accepts_newer_actual_utc_instant(monkeypatch):
    from datetime import timedelta, timezone

    now, before, container = _staging_worker_snapshot()
    after = dict(before)
    after["heartbeat_at"] = (
        now - timedelta(seconds=1)
    ).astimezone(timezone(timedelta(hours=3))).isoformat()
    assert _rechecked_worker(monkeypatch, before, after, before["task_queue"])["id"] == before["id"]


@pytest.mark.parametrize("tamper", [
    "offset_lexical_reversal", "future_heartbeat", "worker_registration_changed",
    "wrong_queue", "missing_worker_id", "stale_heartbeat",
])
def test_day2_worker_heartbeat_rejects_false_advancement(monkeypatch, tamper):
    from datetime import timedelta, timezone

    now, before, container = _staging_worker_snapshot()
    after = dict(before)
    after["heartbeat_at"] = (now - timedelta(seconds=1)).isoformat()
    if tamper == "offset_lexical_reversal":
        # Lexicographically greater: UTC hour 10 becomes offset hour 13;
        # chronologically OLDER than the original heartbeat.
        after["heartbeat_at"] = (
            now - timedelta(seconds=8)
        ).astimezone(timezone(timedelta(hours=3))).isoformat()
    elif tamper == "future_heartbeat":
        after["heartbeat_at"] = (now + timedelta(hours=3)).isoformat()
    elif tamper == "worker_registration_changed":
        after["started_at"] = (now - timedelta(seconds=20)).isoformat()
    elif tamper == "wrong_queue":
        after["task_queue"] = "unapproved-queue"
    elif tamper == "missing_worker_id":
        after["id"] = ""
        before["id"] = ""
    elif tamper == "stale_heartbeat":
        after["heartbeat_at"] = (
            now - timedelta(seconds=80)
        ).astimezone(timezone(timedelta(hours=3))).isoformat()
    with pytest.raises(day2.Day2Failure, match="worker|Worker|heartbeat|Heartbeat"):
        _rechecked_worker(monkeypatch, before, after, before["task_queue"])
