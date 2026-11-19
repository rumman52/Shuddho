"""Day 2 controlled-staging document execution; reuses the real Coworker API/worker.

This is an operator exercise, not a production endpoint, simulation or alternate
execution engine. It never prints tokens, document text or presigned URLs.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import re
import stat
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from scripts.staging_release_evidence import write_private_json
from scripts.staging_release_freeze import canonical_sha256, clean_origin, valid_sha
from services.coworker.config import Settings


NEW_RUNTIME_CAPABILITIES = frozenset({
    "conversations", "projects", "fly_github", "conversation_replies",
    "agent_browser_read", "reviewed_research",
})
TERMINAL = {"completed", "failed", "cancelled", "needs_input"}


class Day2Failure(RuntimeError):
    pass


def require_guard() -> None:
    if (
        os.getenv("SHUDDHO_STAGING_ALLOW_DAY2_EXECUTION", "").lower() != "true"
        or os.getenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true"
    ):
        raise Day2Failure(
            "Day 2 exercise requires both explicit staging and synthetic-account guards."
        )


def check_release(freeze: object) -> dict:
    if not isinstance(freeze, dict) or freeze.get("status") != "frozen":
        raise Day2Failure("A verified frozen staging release is required.")
    release = freeze.get("release")
    if (
        not isinstance(release, dict)
        or release.get("environment") != "staging"
        or not isinstance(release.get("release_id"), str)
        or not release["release_id"].strip()
        or not valid_sha(release.get("source_revision"))
    ):
        raise Day2Failure("Frozen release must have staging identity and a full source SHA.")
    digest = freeze.get("runtime_manifest_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise Day2Failure("Frozen release is missing an exact runtime-manifest digest.")
    return release


def checked(response: httpx.Response, expected: int, label: str) -> httpx.Response:
    if response.status_code != expected:
        raise Day2Failure(f"{label} returned HTTP {response.status_code}; expected {expected}.")
    return response


def obj(response: httpx.Response, label: str) -> dict:
    try:
        value = response.json()
    except ValueError:
        raise Day2Failure(f"{label} returned invalid JSON.") from None
    if not isinstance(value, dict):
        raise Day2Failure(f"{label} returned a non-object response.")
    return value


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def attest_runtime(client: httpx.Client, token: str, freeze: dict) -> dict:
    release = check_release(freeze)
    runtime = obj(checked(client.get("/api/v1/runtime-manifest", headers=bearer(token)),
                          200, "staging runtime-manifest"), "staging runtime-manifest")
    if (
        runtime.get("schema_version") != 2
        or runtime.get("environment") != "staging"
        or runtime.get("source_revision") != release["source_revision"]
        or canonical_sha256(runtime) != freeze["runtime_manifest_sha256"]
        or not isinstance(runtime.get("capabilities"), dict)
        or runtime["capabilities"].get("coworker") is not True
    ):
        raise Day2Failure("Staging runtime manifest does not match the frozen candidate.")
    return release


def require_distinct_owners(client: httpx.Client, token_a: str, token_b: str) -> None:
    if not token_a or not token_b or token_a == token_b:
        raise Day2Failure("Two distinct synthetic access tokens are required.")
    me_a = obj(checked(client.get("/api/v1/me", headers=bearer(token_a)), 200, "owner A identity"), "owner A identity")
    me_b = obj(checked(client.get("/api/v1/me", headers=bearer(token_b)), 200, "owner B identity"), "owner B identity")
    if (
        not me_a.get("account_id") or not me_b.get("account_id")
        or me_a["account_id"] == me_b["account_id"]
        or not me_a.get("workspace_id") or not me_b.get("workspace_id")
        or me_a["workspace_id"] == me_b["workspace_id"]
    ):
        raise Day2Failure("Two distinct managed owners and workspaces are required.")


def public_signed_url(url: object, *, trusted_storage_host: str | None = None) -> str:
    # A compromised API response must not make an operator runner fetch private
    # network addresses, metadata endpoints or credential-bearing URLs.
    if not isinstance(url, str) or len(url) > 8192:
        raise Day2Failure("Private S3 presigned download URL is missing.")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https" or not host or parsed.username or parsed.password
        or parsed.fragment or any(ord(ch) < 32 or ord(ch) == 127 for ch in url)
        or host in {"localhost"} or host.endswith((".local", ".internal"))
        or "." not in host or host.endswith(".")
    ):
        raise Day2Failure("Presigned artifact URL must use a public HTTPS storage origin.")
    import ipaddress
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise Day2Failure("Presigned artifact URLs must not use IP literals.")
    if trusted_storage_host is not None and host != trusted_storage_host:
        raise Day2Failure("Presigned artifact URL does not match the configured private storage endpoint.")
    return url


def _artifact_catalog(client: httpx.Client, headers: dict[str, str], label: str) -> list:
    value = obj(checked(client.get("/api/v1/artifacts", headers=headers), 200, label), label)
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        raise Day2Failure(f"{label} did not return an artifact list.")
    return artifacts


def _artifact_entry(artifacts: list, artifact_id: str, label: str) -> dict:
    matches = [
        item for item in artifacts
        if isinstance(item, dict) and str(item.get("id") or "") == artifact_id
    ]
    if len(matches) != 1:
        raise Day2Failure(f"{label} is not present exactly once in its owner's artifact catalog.")
    item = matches[0]
    if (
        not isinstance(item.get("filename"), str) or not item["filename"].strip()
        or not isinstance(item.get("sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
        or type(item.get("byte_size")) is not int
        or not 1 <= item["byte_size"] <= 16 * 1024 * 1024
    ):
        raise Day2Failure(f"{label} has incomplete digest/size metadata.")
    return item


def _verify_artifact_access(
    client: httpx.Client,
    owner_headers: dict[str, str],
    foreign_headers: dict[str, str],
    artifact_id: str,
    metadata: dict,
    *,
    label: str,
    trusted_storage_host: str | None,
) -> dict:
    content_route = f"/api/v1/artifacts/{artifact_id}/content"
    download_route = f"/api/v1/artifacts/{artifact_id}/download"
    if client.get(content_route, headers=foreign_headers).status_code != 404:
        raise Day2Failure(f"cross-owner {label} artifact content was not denied.")
    if client.get(download_route, headers=foreign_headers).status_code != 404:
        raise Day2Failure(f"cross-owner {label} artifact download was not denied.")

    own_bytes = checked(client.get(content_route, headers=owner_headers), 200, label + " artifact content").content
    expected_sha = metadata.get("sha256")
    expected_bytes = metadata.get("byte_size")
    if (
        not isinstance(expected_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha)
        or type(expected_bytes) is not int or not 1 <= expected_bytes <= 16 * 1024 * 1024
    ):
        raise Day2Failure(f"{label} artifact identity/digest/size metadata is incomplete.")
    if len(own_bytes) != expected_bytes or hashlib.sha256(own_bytes).hexdigest() != expected_sha:
        raise Day2Failure(f"{label} artifact content does not match persisted metadata.")

    signed = obj(checked(client.get(download_route, headers=owner_headers), 200, label + " artifact URL"), label + " artifact URL")
    url = public_signed_url(signed.get("url"), trusted_storage_host=trusted_storage_host)
    signed_response = httpx.get(url, timeout=20, follow_redirects=False)
    if (
        signed_response.status_code != 200
        or len(signed_response.content) != expected_bytes
        or hashlib.sha256(signed_response.content).hexdigest() != expected_sha
    ):
        raise Day2Failure(f"{label} presigned artifact retrieval failed digest verification.")
    return {
        "artifact_sha256": expected_sha,
        "artifact_bytes": expected_bytes,
        "artifact_content_read": "passed",
        "artifact_download": "passed",
        "foreign_artifact_content": "denied_404",
        "foreign_artifact_download": "denied_404",
    }


def _document_catalog_ids(client: httpx.Client, headers: dict[str, str], label: str) -> set[str]:
    value = obj(checked(client.get("/api/v1/documents", headers=headers), 200, label), label)
    documents = value.get("documents")
    if not isinstance(documents, list):
        raise Day2Failure(f"{label} did not return a document list.")
    return {
        str(item.get("id"))
        for item in documents
        if isinstance(item, dict) and item.get("id") is not None
    }


def load_private_pdf(path: Path) -> bytes:
    """Read an operator-selected private, text-based PDF before making API writes."""
    try:
        if path.suffix.lower() != ".pdf" or path.is_symlink() or not path.is_file():
            raise Day2Failure("Select a regular, nonsymlink private PDF file.")
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise Day2Failure("The selected PDF must be owner-only (mode 0600).")
        if not 0 < metadata.st_size <= 8 * 1024 * 1024:
            raise Day2Failure("The selected PDF must be between 1 byte and 8 MiB.")
        source = path.read_bytes()
    except OSError:
        raise Day2Failure("The selected private PDF could not be read.") from None
    if not source.startswith(b"%PDF-") or not 0 < len(source) <= 8 * 1024 * 1024:
        raise Day2Failure("The selected source is not a bounded PDF.")
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(source), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 40:
            raise Day2Failure("Select an unencrypted PDF with 1–40 pages.")
        if not any((page.extract_text() or "").strip() for page in reader.pages):
            raise Day2Failure("The selected PDF must contain extractable text.")
    except Day2Failure:
        raise
    except Exception:
        raise Day2Failure("The selected PDF is invalid or unreadable.") from None
    return source


def run_probe(
    client: httpx.Client,
    token_a: str,
    token_b: str,
    freeze: dict,
    source: bytes,
    *,
    owner_b_artifact_id: str,
    timeout_seconds: int = 180,
    trusted_storage_host: str | None = None,
) -> dict:
    """Prove one owner-A PDF task and bidirectional private resource isolation.

    Owner B's task-output artifact is a pre-existing synthetic control. This
    command never creates a second provider-backed task. Keep all private bytes
    and signed URLs out of the returned evidence.
    """
    release = check_release(freeze)
    if not isinstance(source, bytes) or not 1 <= len(source) <= 8 * 1024 * 1024:
        raise Day2Failure("Day 2 source must be bounded document bytes.")
    is_pdf = source.startswith(b"%PDF-")
    if not is_pdf:
        # Preserve compatibility with the original bounded synthetic TXT probe.
        if len(source) > 4096:
            raise Day2Failure("Synthetic TXT source exceeds the Day 2 limit.")
        try:
            source.decode("utf-8")
        except UnicodeDecodeError:
            raise Day2Failure("Day 2 TXT source must contain valid UTF-8.") from None
    if not 1 <= timeout_seconds <= 1800:
        raise Day2Failure("Task timeout must be between 1 and 1800 seconds.")
    try:
        owner_b_artifact_id = str(uuid.UUID(owner_b_artifact_id))
    except (AttributeError, TypeError, ValueError):
        raise Day2Failure("Owner B synthetic artifact ID must be a valid UUID.") from None

    attest_runtime(client, token_a, freeze)
    require_distinct_owners(client, token_a, token_b)
    a, b = bearer(token_a), bearer(token_b)

    # Fail closed before creating documents or tasks if the reverse-direction
    # artifact control is absent, visible to A, or not retrievable by B.
    owner_a_artifacts_before = _artifact_catalog(client, a, "owner A artifact catalog preflight")
    owner_b_artifacts_before = _artifact_catalog(client, b, "owner B artifact catalog preflight")
    if any(str(item.get("id") or "") == owner_b_artifact_id for item in owner_a_artifacts_before if isinstance(item, dict)):
        raise Day2Failure("Owner B synthetic artifact is visible in owner A's artifact catalog.")
    owner_b_artifact = _artifact_entry(
        owner_b_artifacts_before, owner_b_artifact_id, "Owner B synthetic artifact",
    )
    owner_b_artifact_proof = _verify_artifact_access(
        client, b, a, owner_b_artifact_id, owner_b_artifact,
        label="owner B control", trusted_storage_host=trusted_storage_host,
    )

    marker = uuid.uuid4().hex
    source_sha = hashlib.sha256(source).hexdigest()
    filename = "day2-synthetic-" + marker + (".pdf" if is_pdf else ".txt")
    owner_b_source = f"Day 2 synthetic owner B control note: {marker}\n".encode("utf-8")
    owner_b_source_sha = hashlib.sha256(owner_b_source).hexdigest()
    owner_b_filename = "day2-owner-b-control-" + marker + ".txt"

    owner_b_upload = obj(checked(client.post("/api/v1/documents", headers=b, json={
        "filename": owner_b_filename,
        "byte_size": len(owner_b_source), "sha256": owner_b_source_sha,
    }), 201, "owner B control document create"), "owner B control document create")
    owner_b_document_id = str(owner_b_upload.get("id") or "")
    if not owner_b_document_id:
        raise Day2Failure("Owner B control document create did not return an id.")

    upload = obj(checked(client.post("/api/v1/documents", headers=a, json={
        "filename": filename,
        "byte_size": len(source), "sha256": source_sha,
    }), 201, "private document create"), "private document create")
    document_id = str(upload.get("id") or "")
    if not document_id or document_id == owner_b_document_id:
        raise Day2Failure("The two owners did not receive distinct private document IDs.")

    doc_content = f"/api/v1/documents/{document_id}/content"
    owner_b_doc_content = f"/api/v1/documents/{owner_b_document_id}/content"
    checked(client.put(doc_content, headers=b, content=source), 404, "cross-owner B upload of A document")
    checked(client.put(owner_b_doc_content, headers=a, content=owner_b_source), 404, "cross-owner A upload of B document")
    checked(client.put(doc_content, headers=a, content=source), 200, "owner A document upload")
    checked(client.put(owner_b_doc_content, headers=b, content=owner_b_source), 200, "owner B document upload")

    checked(client.get(doc_content, headers=b), 404, "cross-owner B read of A document")
    checked(client.get(owner_b_doc_content, headers=a), 404, "cross-owner A read of B document")
    owner_a_document = checked(client.get(doc_content, headers=a), 200, "owner A document read")
    owner_b_document = checked(client.get(owner_b_doc_content, headers=b), 200, "owner B document read")
    if hashlib.sha256(owner_a_document.content).hexdigest() != source_sha or owner_a_document.content != source:
        raise Day2Failure("Owner A private document readback did not match the uploaded bytes.")
    if hashlib.sha256(owner_b_document.content).hexdigest() != owner_b_source_sha or owner_b_document.content != owner_b_source:
        raise Day2Failure("Owner B control document readback did not match the uploaded bytes.")

    owner_a_document_ids = _document_catalog_ids(client, a, "owner A document catalog")
    owner_b_document_ids = _document_catalog_ids(client, b, "owner B document catalog")
    if document_id not in owner_a_document_ids or owner_b_document_id in owner_a_document_ids:
        raise Day2Failure("Owner A document list exposed or omitted an owner-scoped document.")
    if owner_b_document_id not in owner_b_document_ids or document_id in owner_b_document_ids:
        raise Day2Failure("Owner B document list exposed or omitted an owner-scoped document.")

    task = obj(checked(client.post("/api/v1/tasks", headers={
        **a, "Idempotency-Key": "staging-day2-" + marker,
    }, json={
        "skill_id": "report_email",
        "instruction": (
            "Summarize the selected private document in English as a short report. "
            "Use only the selected source and include an English email draft."
        ),
        "notes": "Synthetic Day 2 staging execution; no customer data or external actions.",
        "document_ids": [document_id],
        "output_language": "en",
    }), 202, "private document task create"), "private document task create")
    task_id = str(task.get("id") or "")
    if not task_id:
        raise Day2Failure("Private document task did not return an id.")
    task_route = f"/api/v1/tasks/{task_id}"
    checked(client.get(task_route, headers=b), 404, "cross-owner task read")
    checked(client.get(task_route + "/events", headers=b), 404, "cross-owner task events")

    deadline = time.monotonic() + timeout_seconds
    while True:
        result = obj(checked(client.get(task_route, headers=a), 200, "task read"), "task read")
        if result.get("state") in TERMINAL:
            break
        if time.monotonic() >= deadline:
            try:
                client.post(task_route + "/cancel", headers=a)
            except httpx.HTTPError:
                pass
            raise Day2Failure("Real document task timed out; it was not certified complete.")
        time.sleep(min(2.0, max(0.1, deadline - time.monotonic())))
    if result.get("state") != "completed":
        raise Day2Failure("Real document task did not complete successfully.")
    if (
        result.get("workflow_version") != "report_email_v1"
        or result.get("output_language") != "en"
        or not isinstance(result.get("input"), dict)
        or result["input"].get("document_ids") != [document_id]
    ):
        raise Day2Failure("Completed task is not bound to the selected private document.")
    sources = result.get("sources")
    if not isinstance(sources, list):
        raise Day2Failure("Completed report is missing source provenance.")
    selected_sources = [item for item in sources if (
        isinstance(item, dict) and item.get("document_id") == document_id
        and item.get("sha256") == source_sha and item.get("label") == filename
        and isinstance(item.get("id"), str) and item["id"].strip()
    )]
    if len(selected_sources) != 1:
        raise Day2Failure("Completed report lacks exact selected-document version provenance.")
    source_version_id = selected_sources[0]["id"]
    usage = result.get("usage")
    if (
        not isinstance(usage, dict)
        or type(usage.get("model_attempts")) is not int or usage["model_attempts"] < 1
        or type(usage.get("accounted_tokens")) is not int or usage["accounted_tokens"] < 1
    ):
        raise Day2Failure("Completed task has no real model-usage evidence.")
    draft = result.get("draft")
    if (
        not isinstance(draft, dict) or not isinstance(draft.get("report"), dict)
        or not isinstance(draft["report"].get("summary"), str)
        or not draft["report"]["summary"].strip()
    ):
        raise Day2Failure("Completed task has no generated report summary.")
    sections = draft["report"].get("sections")
    if not isinstance(sections, list) or not any(
        isinstance(item, dict) and source_version_id in item.get("source_ids", [])
        for item in sections
    ):
        raise Day2Failure("Generated report did not cite the selected document version.")
    events = obj(checked(client.get(task_route + "/events", headers=a), 200, "owned task events"), "owned task events")
    if events.get("terminal") is not True or events.get("state") != "completed" or not events.get("events"):
        raise Day2Failure("Durable task event history did not confirm completion.")

    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list):
        raise Day2Failure("Completed task has no artifact catalog.")
    pdfs = [item for item in artifacts if isinstance(item, dict) and item.get("filename") == "report.pdf"]
    if len(pdfs) != 1:
        raise Day2Failure("Completed task did not produce exactly one report PDF.")
    pdf = pdfs[0]
    artifact_id = str(pdf.get("id") or "")
    if not artifact_id or artifact_id == owner_b_artifact_id:
        raise Day2Failure("Owner A report and owner B control artifact IDs must be distinct.")
    owner_a_artifact_proof = _verify_artifact_access(
        client, a, b, artifact_id, pdf,
        label="owner A report", trusted_storage_host=trusted_storage_host,
    )

    owner_a_artifacts_after = _artifact_catalog(client, a, "owner A artifact catalog")
    owner_b_artifacts_after = _artifact_catalog(client, b, "owner B artifact catalog")
    owner_a_artifact_ids = {
        str(item.get("id")) for item in owner_a_artifacts_after if isinstance(item, dict) and item.get("id") is not None
    }
    owner_b_artifact_ids = {
        str(item.get("id")) for item in owner_b_artifacts_after if isinstance(item, dict) and item.get("id") is not None
    }
    if artifact_id not in owner_a_artifact_ids or artifact_id in owner_b_artifact_ids:
        raise Day2Failure("Owner A artifact catalog did not isolate its report artifact.")
    if owner_b_artifact_id not in owner_b_artifact_ids or owner_b_artifact_id in owner_a_artifact_ids:
        raise Day2Failure("Owner B artifact catalog did not isolate its control artifact.")

    owner_isolation = {
        "schema_version": 1,
        "status": "passed",
        "identities_distinct": True,
        "owners": {
            "a": {
                "document_id": document_id,
                "document_sha256": source_sha,
                "document_bytes": len(source),
                "document_read": "passed",
                "own_document_list": "included",
                "foreign_document_read": "denied_404",
                "foreign_document_write": "denied_404",
                "foreign_document_list": "excluded",
                "artifact_id": artifact_id,
                "artifact_sha256": owner_a_artifact_proof["artifact_sha256"],
                "artifact_bytes": owner_a_artifact_proof["artifact_bytes"],
                "artifact_content_read": owner_a_artifact_proof["artifact_content_read"],
                "artifact_download": owner_a_artifact_proof["artifact_download"],
                "own_artifact_list": "included",
                "foreign_artifact_content": owner_a_artifact_proof["foreign_artifact_content"],
                "foreign_artifact_download": owner_a_artifact_proof["foreign_artifact_download"],
                "foreign_artifact_list": "excluded",
            },
            "b": {
                "document_id": owner_b_document_id,
                "document_sha256": owner_b_source_sha,
                "document_bytes": len(owner_b_source),
                "document_read": "passed",
                "own_document_list": "included",
                "foreign_document_read": "denied_404",
                "foreign_document_write": "denied_404",
                "foreign_document_list": "excluded",
                "artifact_id": owner_b_artifact_id,
                "artifact_sha256": owner_b_artifact_proof["artifact_sha256"],
                "artifact_bytes": owner_b_artifact_proof["artifact_bytes"],
                "artifact_content_read": owner_b_artifact_proof["artifact_content_read"],
                "artifact_download": owner_b_artifact_proof["artifact_download"],
                "own_artifact_list": "included",
                "foreign_artifact_content": owner_b_artifact_proof["foreign_artifact_content"],
                "foreign_artifact_download": owner_b_artifact_proof["foreign_artifact_download"],
                "foreign_artifact_list": "excluded",
            },
        },
    }
    return {
        "status": "passed",
        "release_id": release["release_id"],
        "source_revision": release["source_revision"],
        "runtime_manifest_sha256": freeze["runtime_manifest_sha256"],
        "document_id": document_id, "document_version_id": source_version_id,
        "document_sha256": source_sha,
        "task_id": task_id, "workflow_id": "shuddho-task-" + task_id,
        "artifact_id": artifact_id, "artifact_sha256": owner_a_artifact_proof["artifact_sha256"],
        "artifact_bytes": owner_a_artifact_proof["artifact_bytes"],
        "model_attempts": usage["model_attempts"],
        "accounted_tokens": usage["accounted_tokens"],
        "owner_isolation": owner_isolation, "artifact_retrieval": "passed",
    }


def active_worker(container: Container, revision: str) -> dict:
    workers = container.repository.worker_inventory(task_queue=container.settings.task_queue)
    active = [w for w in workers if (
        w.get("task_queue") == container.settings.task_queue
        and w.get("source_revision") == revision
        and w.get("state") == "running" and w.get("heartbeat_fresh") is True
    )]
    if not active:
        raise Day2Failure("No fresh running Temporal worker matches the reviewed source SHA.")
    if any(
        w.get("state") == "running" and w.get("heartbeat_fresh") is True
        and w.get("source_revision") != revision for w in workers
    ):
        raise Day2Failure("A live worker with a different source SHA is polling the task queue.")
    return active[0]


def heartbeat_advanced(container: Container, before: dict, revision: str) -> dict:
    deadline = time.monotonic() + 15
    while True:
        workers = container.repository.worker_inventory(task_queue=container.settings.task_queue)
        current = next((w for w in workers if w.get("id") == before.get("id")), None)
        if (
            current and current.get("source_revision") == revision
            and current.get("state") == "running" and current.get("heartbeat_fresh") is True
            and isinstance(current.get("heartbeat_at"), str)
            and current["heartbeat_at"] > str(before.get("heartbeat_at") or "")
        ):
            return current
        if time.monotonic() >= deadline:
            raise Day2Failure("Matching worker did not advance its durable heartbeat.")
        time.sleep(1)


def document_outbox_receipt(task_id: str, rows: list) -> dict:
    """Prove the selected PDF task has one persisted, delivered dispatch row."""
    if not isinstance(task_id, str) or not task_id:
        raise Day2Failure("Private task id is missing before outbox verification.")
    if len(rows) != 1 or rows[0].task_id != task_id:
        raise Day2Failure("Private document task does not have exactly one durable outbox effect.")
    row = rows[0]
    if row.delivered is not True or type(row.attempts) is not int or row.attempts < 1:
        raise Day2Failure("Private document task outbox was not delivered by a real worker.")
    return {"task_id": task_id, "effect_count": 1, "delivered": True,
            "dispatch_attempts": row.attempts}


def persisted_document_outbox(container, task_id: str) -> dict:
    """Read the real database ledger, never infer outbox delivery from HTTP 200."""
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from services.coworker.models import Outbox

    try:
        with container.repository.sessions() as db:
            rows = list(db.scalars(select(Outbox).where(Outbox.task_id == task_id)).all())
    except SQLAlchemyError:
        # Avoid printing a driver exception with SQL, network details or secrets
        # into a staging operator log or shared issue evidence.
        raise Day2Failure("Private document outbox could not be independently verified.") from None
    return document_outbox_receipt(task_id, rows)


async def temporal_completed(settings: Settings, workflow_id: str) -> None:
    from temporalio.client import Client

    client = await Client.connect(
        settings.temporal_address, namespace=settings.temporal_namespace,
        api_key=settings.temporal_api_key or None, tls=settings.temporal_tls,
    )
    status = (await client.get_workflow_handle(workflow_id).describe()).status
    if str(getattr(status, "name", status)).lower() != "completed":
        raise Day2Failure("Real Temporal task workflow did not complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prove Day 2 private document/model/Temporal/worker identity in controlled staging.")
    parser.add_argument("--freeze-evidence", type=Path, required=True)
    parser.add_argument("--source-pdf", type=Path, required=True,
                        help="Approved synthetic text-based PDF in owner-only (0600) private storage.")
    parser.add_argument("--owner-b-artifact-id", required=True,
                        help="Pre-existing synthetic task-output artifact UUID owned by owner B; the operator never creates a second model task.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    container = None
    try:
        require_guard()
        if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
            raise Day2Failure("Use a new private evidence destination in an existing directory.")
        freeze = json.loads(args.freeze_evidence.read_text(encoding="utf-8"))
        release = check_release(freeze)
        source = load_private_pdf(args.source_pdf)
        settings = Settings.from_env()
        if (
            settings.environment != "staging"
            or settings.source_revision != release["source_revision"]
            or settings.storage_backend != "s3"
            or not settings.chat_provider_configured
        ):
            raise Day2Failure("Operator runtime does not match staging source, private S3 or configured model.")
        token_a = os.getenv("SHUDDHO_STAGING_TOKEN_A", "")
        token_b = os.getenv("SHUDDHO_STAGING_TOKEN_B", "")
        require_distinct = bool(token_a and token_b and token_a != token_b)
        if not require_distinct:
            raise Day2Failure("Two distinct approved synthetic staging tokens are required.")
        origin = clean_origin(os.getenv("SHUDDHO_STAGING_API_BASE_URL", ""))
        # Operator-only dependency: lightweight contract tests have no Auth/Temporal extras.
        from services.coworker.container import Container

        endpoint = urlparse(settings.storage_endpoint or "")
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise Day2Failure("Live Day 2 requires a reviewed HTTPS private S3 endpoint.")
        container = Container.create(settings)
        before = active_worker(container, release["source_revision"])
        with httpx.Client(base_url=origin, timeout=20, follow_redirects=False) as client:
            result = run_probe(
                client, token_a, token_b, freeze, source,
                owner_b_artifact_id=args.owner_b_artifact_id,
                timeout_seconds=args.timeout, trusted_storage_host=endpoint.hostname,
            )
        asyncio.run(temporal_completed(settings, result["workflow_id"]))
        result["document_outbox"] = persisted_document_outbox(container, result["task_id"])
        after = heartbeat_advanced(container, before, release["source_revision"])
        result["worker"] = {
            "id": before["id"], "task_queue": settings.task_queue,
            "source_revision": release["source_revision"],
            "heartbeat_before": before["heartbeat_at"],
            "heartbeat_after": after["heartbeat_at"],
        }
        write_private_json(args.output, result)
        print(json.dumps({"status": "passed", "written": str(args.output),
                          "checks": {"model": "passed", "artifact": "passed",
                                     "owner_isolation": "passed", "temporal": "passed",
                                     "worker_heartbeat": "passed", "document_outbox": "passed"}}, indent=2))
    except (Day2Failure, ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": str(error) if isinstance(error, Day2Failure)
                          else type(error).__name__}, indent=2))
        raise SystemExit(1) from None
    except httpx.HTTPError as error:
        print(json.dumps({"status": "failed", "error": type(error).__name__}, indent=2))
        raise SystemExit(1) from None
    finally:
        if container is not None:
            container.repository.sessions.kw["bind"].dispose()


if __name__ == "__main__":
    main()
