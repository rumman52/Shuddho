"""Source-only regression contracts for authenticated isolated restore readback."""
from __future__ import annotations

import base64
import hashlib
import json
import time

import httpx
import pytest

from scripts import staging_restored_api_access as access


ISSUER = "https://identity.example.test/auth/v1"
AUDIENCE = "authenticated"
SOURCE_API = "https://source.example.test"
RESTORE_API = "https://restored.example.test"
SHA = "a" * 40
DATA = b"restored synthetic document exact bytes\n"
DOC = "11111111-1111-4111-8111-111111111111"
TASK = "22222222-2222-4222-8222-222222222222"


def _token(subject: str) -> str:
    def part(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()
    claims = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": subject,
        "iat": int(time.time()) - 1, "exp": int(time.time()) + 3600,
        "role": "authenticated",
    }
    return part({"alg": "RS256", "kid": "test-asymmetric-key"}) + "." + part(claims) + ".signed"


A = _token("owner-A-subject")
B = _token("owner-B-subject")
OWNER_A = hashlib.sha256(json.dumps([ISSUER, "owner-A-subject"]).encode()).hexdigest()


def _client(*, foreign_document=404, leak_listing=False, foreign_task=404,
            tamper_bytes=False, bad_revision=False, a_account=OWNER_A,
            redirect_owner=False):
    def handle(request: httpx.Request) -> httpx.Response:
        url = request.url.path
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        owner = "A" if token == A else "B" if token == B else "unknown"
        if url == "/api/v1/runtime-manifest":
            return httpx.Response(200, json={
                "schema_version": 2, "environment": "staging",
                "source_revision": "f" * 40 if bad_revision else SHA,
            })
        if url == "/api/v1/me":
            sub = "owner-A-subject" if owner == "A" else "owner-B-subject"
            account = a_account if owner == "A" else hashlib.sha256(
                json.dumps([ISSUER, sub]).encode()
            ).hexdigest()
            return httpx.Response(200, json={"account_id": account, "workspace_id": "workspace-" + sub})
        if url == f"/api/v1/documents/{DOC}/content":
            if owner == "B":
                return httpx.Response(foreign_document)
            if redirect_owner:
                return httpx.Response(302, headers={"location": SOURCE_API + url})
            return httpx.Response(200, content=DATA + (b"wrong" if tamper_bytes else b""))
        if url == "/api/v1/documents":
            docs = [{"id": DOC}] if owner == "B" and leak_listing else []
            return httpx.Response(200, json={"documents": docs})
        if url == f"/api/v1/tasks/{TASK}":
            return httpx.Response(foreign_task) if owner == "B" else httpx.Response(
                200, json={"id": TASK, "state": "cancelled"},
            )
        raise AssertionError((url, owner))
    return httpx.Client(base_url=RESTORE_API, transport=httpx.MockTransport(handle), follow_redirects=False)


def _probe(monkeypatch, **overrides):
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_RESTORED_API_READBACK", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    with _client(**overrides) as client:
        return access.attest_restored_api_access(
            client, A, B,
            source_origin=SOURCE_API, restored_origin=RESTORE_API,
            expected_owner_id=OWNER_A, document_id=DOC, task_id=TASK,
            document_sha256=hashlib.sha256(DATA).hexdigest(), document_size=len(DATA),
            source_revision=SHA, expected_issuer=ISSUER,
            expected_audience=AUDIENCE,
        )


def test_restored_api_requires_actual_a_bytes_and_distinct_b_denials(monkeypatch):
    proof = _probe(monkeypatch)
    assert proof["status"] == "verified"
    assert proof["owner_a_document_sha256"] == hashlib.sha256(DATA).hexdigest()
    assert proof["owner_a_document_bytes"] == len(DATA)
    assert proof["owner_a_document_retrievable"] is True
    assert proof["owner_b_document_denied"] is True
    assert proof["owner_b_document_unlisted"] is True
    assert proof["owner_a_cancelled_task_verified"] is True
    assert proof["owner_b_task_denied"] is True
    assert proof["owner_a_identity_verified"] is True
    assert proof["owner_b_identity_verified"] is True
    assert proof["source_api_origin_sha256"] != proof["restored_api_origin_sha256"]
    assert not any("token" in key.lower() for key in proof)


@pytest.mark.parametrize("scenario", [
    {"foreign_document": 200},
    {"leak_listing": True},
    {"foreign_task": 200},
    {"tamper_bytes": True},
    {"bad_revision": True},
    {"a_account": "incorrect-owner"},
    {"redirect_owner": True},
])
def test_restored_api_rejects_leak_or_wrong_runtime_or_bytes(monkeypatch, scenario):
    with pytest.raises(access.RestoredAPIReadbackFailure):
        _probe(monkeypatch, **scenario)


def test_restored_api_rejects_missing_explicit_guards_before_first_request(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_RESTORED_API_READBACK", raising=False)
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    with _client() as client:
        with pytest.raises(access.RestoredAPIReadbackFailure, match="guard"):
            access.attest_restored_api_access(
                client, A, B, source_origin=SOURCE_API, restored_origin=RESTORE_API,
                expected_owner_id=OWNER_A, document_id=DOC, task_id=TASK,
                document_sha256=hashlib.sha256(DATA).hexdigest(), document_size=len(DATA),
                source_revision=SHA, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            )


@pytest.mark.parametrize("restored_origin,source_origin", [
    (SOURCE_API, SOURCE_API),
    ("http://restored.example.test", SOURCE_API),
    ("https://localhost", SOURCE_API),
    ("https://user:pass@restored.example.test", SOURCE_API),
    ("https://restored.example.test/surprise", SOURCE_API),
])
def test_restored_api_requires_distinct_public_https_origin(monkeypatch, restored_origin, source_origin):
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_RESTORED_API_READBACK", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    with _client() as client:
        with pytest.raises(access.RestoredAPIReadbackFailure):
            access.attest_restored_api_access(
                client, A, B, source_origin=source_origin, restored_origin=restored_origin,
                expected_owner_id=OWNER_A, document_id=DOC, task_id=TASK,
                document_sha256=hashlib.sha256(DATA).hexdigest(), document_size=len(DATA),
                source_revision=SHA, expected_issuer=ISSUER, expected_audience=AUDIENCE,
            )
