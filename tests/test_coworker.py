"""Public boundary, workflow checkpoints, parser, and real artifact regressions."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import time
import zipfile
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for Part 2 tests")
pytest.importorskip("temporalio", reason="Install the coworker extra for Part 2 tests")

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from docx import Document as WordDocument
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select

from services.coworker.api import mount
from services.coworker.auth import JwtVerifier, Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.drafting import DeepSeekDraftModel, DraftFailure, DraftResult
from services.coworker.errors import CoworkerError
from services.coworker.extraction import extract_in_subprocess, extract_text
from services.coworker.exports import render_in_subprocess
from services.coworker.migrate import upgrade
from services.coworker.models import Account, Artifact, DailyUsage, ModelAttempt, Outbox, Task, utcnow
from services.coworker.runner import DocumentRunner
from services.coworker.schemas import DraftPackage, TaskCreate, UploadRequest
from services.coworker.worker import Dispatcher

ISSUER = "https://identity.example.test/auth/v1"


@pytest.fixture
def container(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'workspace.sqlite3'}", auth_issuer=ISSUER,
                        environment="development", storage_backend="local", local_storage_path=tmp_path / "objects")
    upgrade(settings.database_url)
    result = Container.create(settings)
    yield result
    result.repository.sessions.kw["bind"].dispose()


def principal(subject="alice"):
    return Principal(ISSUER, subject, int(time.time()) + 3600)


def account(container, subject="alice"):
    return container.repository.ensure_account(principal(subject))["account_id"]


def new_task(container, owner=None, **kwargs):
    return container.repository.create_task(owner or account(container), TaskCreate(
        instruction="Prepare a project report and email.", notes="Team completed 12 reviews on 10 September 2026.", **kwargs), "task-key-" + str(time.time_ns()))[0]


def draft(language="en", missing=False):
    title, summary = {
        "en": ("Project update", "The team completed 12 reviews."),
        "bn": ("প্রকল্পের অগ্রগতি", "দলটি ১২টি পর্যালোচনা সম্পন্ন করেছে।"),
        "ar": ("تحديث المشروع", "أكمل الفريق 12 مراجعة."),
    }.get(language, ("Project update", "The team completed 12 reviews."))
    return DraftPackage.model_validate({"report": {"title": title, "summary": summary,
        "sections": [{"heading": title, "paragraphs": [summary], "source_ids": ["notes"]}]},
        "email": {"subject": title, "body": summary}, "output_language": language,
        "missing_information": ["Who is the recipient?"] if missing else []})


class FakeModel:
    def __init__(self, language="en", missing=False):
        self.calls = 0
        self.value = draft(language, missing)

    def messages(self, task, sources):
        return [{"role": "user", "content": json.dumps(sources)}]

    async def generate(self, *_args):
        self.calls += 1
        return DraftResult(self.value, 180, 5)


@pytest.fixture
def signed_client(container):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": "test-key", "alg": "RS256", "use": "sig"}
    container.verifier = JwtVerifier(ISSUER, "authenticated", httpx.MockTransport(lambda request: httpx.Response(200, json={"keys": [jwk]})))
    app = FastAPI()
    mount(app, container)

    def headers(subject="alice", **changes):
        claims = {"iss": ISSUER, "sub": subject, "aud": "authenticated", "role": "authenticated",
                  "iat": int(time.time()) - 1, "exp": int(time.time()) + 3600} | changes
        token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})
        return {"Authorization": "Bearer " + token}

    with TestClient(app) as client:
        yield client, headers


def test_auth_validation_and_private_errors(signed_client):
    client, headers = signed_client
    assert client.get("/api/v1/me").status_code == 401
    for overrides in [{"exp": 1}, {"aud": "wrong"}, {"iss": "https://other.test"}, {"role": "service_role"}, {"is_anonymous": True}]:
        assert client.get("/api/v1/me", headers=headers(**overrides)).status_code == 401
    response = client.get("/api/v1/me", headers=headers())
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    secret_notes = "PRIVATE-DOCUMENT-SENTINEL"
    invalid = client.post("/api/v1/tasks", headers=headers() | {"Idempotency-Key": "invalid-body"}, json={"notes": secret_notes})
    assert invalid.status_code == 422
    assert secret_notes not in invalid.text
    assert client.post("/api/v1/tasks", headers=headers(), content=b" " * 262145).status_code == 413
    assert client.post("/api/check", headers=headers(), json={}).status_code == 400


def test_malformed_jwks_is_a_safe_unavailable_error():
    verifier = JwtVerifier(ISSUER, "authenticated", httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [None]})))
    with pytest.raises(CoworkerError, match="temporarily unavailable") as error:
        asyncio.run(verifier._refresh())
    assert error.value.status_code == 503


def test_owned_documents_tasks_events_and_preferences(signed_client, container):
    client, headers = signed_client
    a, b = headers(), headers("bob")
    body = "Meeting notes: 12 reviews completed.".encode()
    upload = client.post("/api/v1/documents", headers=a, json={"filename": "notes.txt", "byte_size": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    assert upload.status_code == 201
    doc = upload.json()
    path = f'/api/v1/documents/{doc["id"]}/content'
    assert client.put(path, headers=b, content=body).status_code == 404
    assert client.put(path, headers=a, content=b"x" * len(body)).status_code == 409
    assert client.put(path, headers=a, content=body).status_code == 200
    payload = {"instruction": "Create report and email", "document_ids": [doc["id"]], "output_language": "bn"}
    assert client.post("/api/v1/tasks", headers=b | {"Idempotency-Key": "other-user-key"}, json=payload).status_code == 404
    response = client.post("/api/v1/tasks", headers=a | {"Idempotency-Key": "submit-once"}, json=payload)
    assert response.status_code == 202
    task = response.json()
    task_path = f'/api/v1/tasks/{task["id"]}'
    replay = client.post("/api/v1/tasks", headers=a | {"Idempotency-Key": "submit-once"}, json=payload)
    assert replay.json()["id"] == task["id"] and replay.headers["Idempotent-Replayed"] == "true"
    conflict = client.post("/api/v1/tasks", headers=a | {"Idempotency-Key": "submit-once"}, json=payload | {"output_language": "en"})
    assert conflict.status_code == 409
    for suffix in ["", "/events", "/events?stream=true"]:
        assert client.get(task_path + suffix, headers=b).status_code == 404
    assert client.post(task_path + "/cancel", headers=b).status_code == 404
    assert client.get("/api/v1/tasks", headers=b).json()["tasks"] == []
    assert client.get("/api/v1/documents", headers=b).json()["documents"] == []
    client.put("/api/v1/preferences", headers=a, json={"language": "bn"})
    assert client.get("/api/v1/me", headers=b).json()["preferences"] == {}
    assert client.post(task_path + "/cancel", headers=a).json()["state"] == "cancelled"
    events = client.get(task_path + "/events?after=1", headers=a).json()
    assert events["terminal"] and events["events"][0]["sequence"] == 2
    sse = client.get(task_path + "/events?stream=true", headers=a | {"Last-Event-ID": "1"})
    assert "id: 2" in sse.text and "id: 1" not in sse.text
    assert client.get(task_path + "/events", headers=a | {"Last-Event-ID": "bad"}).status_code == 400


@pytest.mark.parametrize("language", ["en", "bn", "ar"])
def test_real_multilingual_exports_and_checkpoint_recovery(container, language):
    owner = account(container)
    task = new_task(container, owner, output_language=language)
    model = FakeModel(language)
    first_worker = DocumentRunner(container, model)
    asyncio.run(first_worker.phase(task["id"], "extract"))
    asyncio.run(first_worker.phase(task["id"], "draft"))
    # New worker instance starts from durable checkpoints. No repeat model call.
    resumed = DocumentRunner(container, model)
    asyncio.run(resumed.run_for_test(task["id"]))
    asyncio.run(DocumentRunner(container, model).run_for_test(task["id"]))
    result = container.repository.get_task(owner, task["id"])
    assert model.calls == 1 and result["state"] == "completed"
    assert all("text" not in source for source in container.repository.step(task["id"], "extract")["sources"])
    assert result["usage"] == {"model_attempts": 1, "accounted_tokens": 180}
    assert {item["filename"] for item in result["artifacts"]} == {"report.docx", "report.pdf", "email-draft.txt", "source-manifest.json"}
    for item in result["artifacts"]:
        stored = container.repository.artifact(owner, item["id"])
        raw = container.storage.get(stored["object_key"], stored["byte_size"])
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        if item["filename"] == "report.docx":
            assert draft(language).report.title in "\n".join(p.text for p in WordDocument(io.BytesIO(raw)).paragraphs)
            if language == "ar":
                with zipfile.ZipFile(io.BytesIO(raw)) as package:
                    assert b"w:bidi" in package.read("word/document.xml")
        if item["filename"] == "report.pdf":
            assert len(PdfReader(io.BytesIO(raw)).pages) >= 1
        with pytest.raises(CoworkerError) as denied:
            container.repository.artifact(account(container, "bob"), item["id"])
        assert denied.value.status_code == 404


def test_needs_input_is_reviewable_not_a_sent_email(container, signed_client):
    client, headers = signed_client
    owner = account(container)
    task = new_task(container, owner)
    asyncio.run(DocumentRunner(container, FakeModel(missing=True)).run_for_test(task["id"]))
    result = client.get(f'/api/v1/tasks/{task["id"]}', headers=headers()).json()
    assert result["state"] == "needs_input" and result["draft"]["missing_information"]
    item = result["artifacts"][0]
    route = f'/api/v1/artifacts/{item["id"]}/download'
    assert client.get(route, headers=headers("bob")).status_code == 404
    download = client.get(route, headers=headers()).json()
    assert download["url"] is None
    assert client.get(download["content_path"], headers=headers()).status_code == 200
    assert client.get(download["content_path"], headers=headers("bob")).status_code == 404


def test_budget_unknown_outcomes_and_cancel_block_future_calls(container):
    owner = account(container)
    task = new_task(container, owner)
    repo = container.repository
    a = repo.reserve_model(task["id"], 45000)
    repo.settle_model(task["id"], a, None, None, "unknown")
    repo.settle_model(task["id"], a, 0, None, "completed")
    assert repo.get_task(owner, task["id"])["usage"]["accounted_tokens"] == 45000
    b = repo.reserve_model(task["id"], 45000)
    repo.settle_model(task["id"], b, 25, 10, "completed")
    with pytest.raises(CoworkerError) as budget:
        repo.reserve_model(task["id"], 100)
    assert budget.value.code == "task_budget"
    repo.cancel(owner, task["id"])
    with pytest.raises(CoworkerError) as cancelled:
        asyncio.run(DocumentRunner(container, FakeModel()).phase(task["id"], "draft"))
    assert cancelled.value.code == "task_cancelled"


def test_deadline_expires_without_dispatcher_and_does_not_block_quota(container):
    owner = account(container)
    task = new_task(container, owner)
    with container.repository.sessions.begin() as db:
        db.get(Task, task["id"]).deadline_at = utcnow() - timedelta(seconds=1)
    assert container.repository.get_task(owner, task["id"])["error_code"] == "task_expired"
    assert new_task(container, owner)["state"] == "queued"


def test_abandoned_upload_releases_reservation_once(container):
    owner = account(container)
    request = UploadRequest(filename="test.txt", byte_size=100, sha256="a" * 64)
    result = container.repository.create_upload(owner, request)
    from services.coworker.models import DocumentVersion
    with container.repository.sessions.begin() as db:
        db.get(DocumentVersion, result["version_id"]).expires_at = utcnow() - timedelta(minutes=3)
    assert len(container.repository.expired_uploads()) == 1
    container.repository.expired_uploads()
    with container.repository.sessions() as db:
        assert db.get(Account, owner).storage_bytes == 0
    with pytest.raises(CoworkerError):
        container.repository.finish_upload(owner, result["id"])


def test_source_deletion_checks_ownership_and_active_usage(signed_client, container):
    client, headers = signed_client
    raw = b"Project notes"
    uploaded = client.post("/api/v1/documents", headers=headers(), json={"filename": "remove.txt", "byte_size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}).json()
    route = f'/api/v1/documents/{uploaded["id"]}'
    assert client.put(route + "/content", headers=headers(), content=raw).status_code == 200
    assert client.delete(route, headers=headers("bob")).status_code == 404
    task = new_task(container, document_ids=[uploaded["id"]])
    assert client.delete(route, headers=headers()).status_code == 409
    container.repository.cancel(account(container), task["id"])
    assert client.delete(route, headers=headers()).status_code == 202
    assert client.get("/api/v1/documents", headers=headers()).json()["documents"] == []
    assert client.put(route + "/content", headers=headers(), content=raw).status_code == 404
    # A cancelled task can still be consumed from the outbox after source deletion.
    assert container.repository.worker_task(task["id"], False)["state"] == "cancelled"


def test_source_scans_expansion_and_production_tls():
    from pypdf.generic import DictionaryObject, NameObject, NumberObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(100, 100)
    image = DecodedStreamObject()
    image.set_data(b"\xff\xff\xff")
    image.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Image"),
                  NameObject("/Width"): NumberObject(1), NameObject("/Height"): NumberObject(1),
                  NameObject("/ColorSpace"): NameObject("/DeviceRGB"), NameObject("/BitsPerComponent"): NumberObject(8)})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Image1"): writer._add_object(image)})})
    raw = io.BytesIO()
    writer.write(raw)
    with pytest.raises(CoworkerError) as scan:
        extract_in_subprocess(raw.getvalue(), "pdf", 20000)
    assert scan.value.code == "ocr_required"
    expanded = io.BytesIO()
    with zipfile.ZipFile(expanded, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b" " * (33 * 1024 * 1024))
    with pytest.raises(CoworkerError) as bomb:
        extract_text(expanded.getvalue(), "docx")
    assert bomb.value.code == "document_expansion_limit"
    settings = Settings(database_url="postgresql+psycopg://user:placeholder@host/db", auth_issuer=ISSUER, storage_bucket="test")
    with pytest.raises(ValueError, match="sslmode"):
        settings.validate()


def test_unexpected_database_errors_do_not_echo_private_parameters(signed_client, container, monkeypatch, caplog):
    client, headers = signed_client
    assert client.get("/api/v1/me", headers=headers()).status_code == 200
    def fail(_owner):
        raise RuntimeError("PRIVATE-DATABASE-PARAMETER")
    monkeypatch.setattr(container.repository, "list_tasks", fail)
    response = client.get("/api/v1/tasks", headers=headers())
    assert response.status_code == 503
    assert "PRIVATE-DATABASE-PARAMETER" not in response.text + caplog.text


def test_file_parser_limits_and_real_docx_pdf():
    assert extract_in_subprocess("বাংলা notes".encode(), "txt", 20000) == "বাংলা notes"
    for data, code in [(b"", "empty_document"), (b"\xff", "text_encoding"), (b"\x00binary", "document_invalid")]:
        with pytest.raises(CoworkerError) as failure:
            extract_in_subprocess(data, "txt", 20000)
        assert failure.value.code == code
    doc = WordDocument()
    doc.add_paragraph("Project facts")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "12 reviews"
    buf = io.BytesIO()
    doc.save(buf)
    assert "12 reviews" in extract_in_subprocess(buf.getvalue(), "docx", 20000)
    dangerous = io.BytesIO()
    with zipfile.ZipFile(dangerous, "w") as package:
        package.writestr("word/vbaProject.bin", "macro")
        package.writestr("word/document.xml", "<x/>")
    with pytest.raises(CoworkerError) as failure:
        extract_in_subprocess(dangerous.getvalue(), "docx", 20000)
    assert failure.value.code == "document_active_content"
    writer = PdfWriter()
    for _ in range(41):
        writer.add_blank_page(100, 100)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(CoworkerError) as failure:
        extract_text(buffer.getvalue(), "pdf")
    assert failure.value.code == "page_limit"


@pytest.mark.parametrize("change", ["truncated", "source", "language", "tool", "control"])
def test_model_rejects_unusable_or_unattributed_output(container, change):
    payload = draft().model_dump()
    if change == "source":
        payload["report"]["sections"][0]["source_ids"] = ["invented"]
    if change == "language":
        payload["output_language"] = "fr"
    if change == "control":
        payload["report"]["title"] = "bad\x00title"
    message = {"content": json.dumps(payload)}
    if change == "tool":
        message["tool_calls"] = [{"name": "send_email"}]
    envelope = {"choices": [{"finish_reason": "length" if change == "truncated" else "stop", "message": message}], "usage": {"total_tokens": 123}}
    model = DeepSeekDraftModel(replace(container.settings, deepseek_api_key="test-only-placeholder"), httpx.MockTransport(lambda _: httpx.Response(200, json=envelope)))
    with pytest.raises(DraftFailure) as failure:
        asyncio.run(model.generate([], "en", {"notes"}))
    assert failure.value.code == "invalid_draft" and failure.value.total_tokens == 123


def test_model_success_and_retryable_provider_failure(container):
    settings = replace(container.settings, deepseek_api_key="test-only-placeholder")
    def respond(request):
        body = json.loads(request.content)
        assert body["thinking"] == {"type": "disabled"}
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": draft().model_dump_json()}}], "usage": {"total_tokens": 200}})
    model = DeepSeekDraftModel(settings, httpx.MockTransport(respond))
    assert asyncio.run(model.generate([], "en", {"notes"})).total_tokens == 200
    model = DeepSeekDraftModel(settings, httpx.MockTransport(lambda _: httpx.Response(429, text="PRIVATE PROVIDER BODY")))
    with pytest.raises(DraftFailure) as failure:
        asyncio.run(model.generate([], "en", {"notes"}))
    assert failure.value.retryable and "PRIVATE" not in failure.value.message


def test_outbox_recovery_does_not_start_another_workflow(container):
    from temporalio.exceptions import WorkflowAlreadyStartedError
    task = new_task(container)
    started = set()
    class Client:
        async def start_workflow(self, _workflow, task_id, **options):
            assert options["id"] == "shuddho-task-" + task_id
            if task_id in started:
                raise WorkflowAlreadyStartedError(options["id"], "shuddho_report_email_v1")
            started.add(task_id)
    dispatcher = Dispatcher(container, Client())
    asyncio.run(dispatcher.tick())
    with container.repository.sessions.begin() as db:
        row = db.get(Outbox, task["id"])
        row.delivered = False
        row.lease_until = utcnow() - timedelta(seconds=1)
    asyncio.run(dispatcher.tick())
    assert started == {task["id"]}
    with container.repository.sessions() as db:
        assert db.get(Outbox, task["id"]).delivered
