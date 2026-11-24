"""Day 2 controlled-staging document execution; reuses the real Coworker API/worker.

This is an operator exercise, not a production endpoint, simulation or alternate
execution engine. It never prints tokens, document text or presigned URLs.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import re
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from scripts.staging_release_evidence import write_private_json
from scripts.staging_prerequisite_preflight import EXPECTED_AUTH_ISSUER, EXPECTED_S3_ENDPOINT
from scripts.staging_release_freeze import canonical_sha256, clean_origin, valid_sha
from services.coworker.config import Settings
from services.coworker.reviewed_skill_registry import WORKER_HEARTBEAT_TTL_SECONDS


# API origin read back from the actual Rumman Render staging service on 22 Nov 2026.
# A different custom domain requires a new independently reviewed release decision.
EXPECTED_STAGING_API_ORIGIN = "https://shuddho-api-staging.onrender.com"

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


def require_approved_staging_destinations(
    *, api_origin: str, auth_issuer: str, storage_endpoint: str
) -> None:
    """Reject off-project credential destinations before connecting to any service.

    This is a static approval check. It cannot replace TLS, DNS, runtime
    identity, private bucket readback, or independent hosted verification.
    """
    if api_origin != EXPECTED_STAGING_API_ORIGIN:
        raise Day2Failure("Day 2 API origin must match the reviewed Rumman Render staging service.")
    if auth_issuer != EXPECTED_AUTH_ISSUER:
        raise Day2Failure("Day 2 Auth issuer must match the approved Supabase staging project.")
    if storage_endpoint != EXPECTED_S3_ENDPOINT:
        raise Day2Failure("Day 2 private storage endpoint must match the approved Supabase staging S3 resource.")


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


def _managed_identity_claims(
    token: str,
    *,
    expected_issuer: str,
    expected_audience: str,
    minimum_validity_seconds: int,
) -> tuple[str, str]:
    """Read claims locally after the same bearer token is accepted by the API.

    The API's issuer-pinned JwtVerifier validates the RS256/ES256 signature and
    required claims on /runtime-manifest and /me. This local decode binds the
    exact token's sub to the API account_id and checks the configured claim
    values without ever retaining or printing the token or subject.
    """
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        if not signature_segment:
            raise ValueError("missing JWT signature segment")

        def decode_segment(segment: str) -> dict:
            raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("JWT segment is not an object")
            return value

        header = decode_segment(header_segment)
        if header.get("alg") not in {"RS256", "ES256"} or not isinstance(header.get("kid"), str):
            raise ValueError("unsupported JWT header")
        claims = decode_segment(payload_segment)
    except Exception:
        raise Day2Failure("Managed synthetic identity token claims could not be read.") from None
    if not isinstance(claims, dict) or claims.get("iss") != expected_issuer:
        raise Day2Failure("Managed synthetic identity issuer does not match the configured issuer.")
    audience = claims.get("aud")
    if not (
        audience == expected_audience
        or isinstance(audience, list) and expected_audience in audience
    ):
        raise Day2Failure("Managed synthetic identity audience does not match the configured audience.")
    now = time.time()
    expiry, issued_at = claims.get("exp"), claims.get("iat")
    if (
        type(expiry) not in {int, float}
        or expiry <= now + minimum_validity_seconds
        or type(issued_at) not in {int, float}
        or issued_at > now + 15
    ):
        raise Day2Failure("Managed synthetic identity is expired or does not remain valid for the task window.")
    subject = claims.get("sub")
    if (
        not isinstance(subject, str) or not 1 <= len(subject) <= 128
        or claims.get("role") != "authenticated"
        or claims.get("is_anonymous") is True
    ):
        raise Day2Failure("Managed synthetic identity subject or authenticated role is invalid.")
    account_id = hashlib.sha256(json.dumps([expected_issuer, subject]).encode()).hexdigest()
    return subject, account_id


def _prevalidate_managed_owners(
    token_a: str,
    token_b: str,
    *,
    expected_issuer: str,
    expected_audience: str,
    minimum_validity_seconds: int,
) -> tuple[str, str]:
    """Check both owner tokens locally before sending either bearer over HTTP."""
    if not token_a or not token_b or token_a == token_b:
        raise Day2Failure("Two distinct synthetic access tokens are required.")
    subject_a, expected_account_a = _managed_identity_claims(
        token_a, expected_issuer=expected_issuer, expected_audience=expected_audience,
        minimum_validity_seconds=minimum_validity_seconds,
    )
    subject_b, expected_account_b = _managed_identity_claims(
        token_b, expected_issuer=expected_issuer, expected_audience=expected_audience,
        minimum_validity_seconds=minimum_validity_seconds,
    )
    if subject_a == subject_b:
        raise Day2Failure("Two distinct managed synthetic subjects are required.")
    return expected_account_a, expected_account_b


def require_distinct_owners(
    client: httpx.Client,
    token_a: str,
    token_b: str,
    *,
    expected_issuer: str,
    expected_audience: str,
    minimum_validity_seconds: int,
) -> dict:
    # No API calls until BOTH owner tokens have passed local claim checks.
    expected_account_a, expected_account_b = _prevalidate_managed_owners(
        token_a, token_b, expected_issuer=expected_issuer,
        expected_audience=expected_audience,
        minimum_validity_seconds=minimum_validity_seconds,
    )
    me_a = obj(checked(client.get("/api/v1/me", headers=bearer(token_a)), 200, "owner A identity"), "owner A identity")
    me_b = obj(checked(client.get("/api/v1/me", headers=bearer(token_b)), 200, "owner B identity"), "owner B identity")
    if (
        me_a.get("account_id") != expected_account_a
        or me_b.get("account_id") != expected_account_b
        or not me_a.get("workspace_id") or not me_b.get("workspace_id")
        or me_a["workspace_id"] == me_b["workspace_id"]
    ):
        raise Day2Failure("Verified token subjects do not bind to two distinct managed owners and workspaces.")
    return {
        "owner_a": {
            "issuer_verified": True, "audience_verified": True,
            "expiry_verified": True, "subject_verified": True,
            "api_subject_binding_verified": True,
        },
        "owner_b": {
            "issuer_verified": True, "audience_verified": True,
            "expiry_verified": True, "subject_verified": True,
            "api_subject_binding_verified": True,
        },
        "subjects_distinct": True,
    }


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


def _extract_pdf_text(payload: bytes, label: str) -> str:
    """Require readable, extractable PDF page text, not just a .pdf filename."""
    if not isinstance(payload, bytes) or not payload.startswith(b"%PDF-"):
        raise Day2Failure(f"{label} is not a PDF.")
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(payload), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 40:
            raise Day2Failure(f"{label} must be an unencrypted PDF with 1–40 pages.")
        body = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not body.strip():
            raise Day2Failure(f"{label} has no extractable report text.")
        return body
    except Day2Failure:
        raise
    except Exception:
        raise Day2Failure(f"{label} is not a readable text-based PDF.") from None


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
    required_pdf_anchor: str | None = None,
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
    if required_pdf_anchor is not None and required_pdf_anchor not in _extract_pdf_text(own_bytes, f"{label} PDF"):
        raise Day2Failure(f"{label} PDF is missing the expected synthetic source marker.")

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
    expected_auth_issuer: str,
    expected_auth_audience: str,
    owner_b_artifact_id: str,
    timeout_seconds: int = 180,
    trusted_storage_host: str | None = None,
    expected_source_anchor: str | None = None,
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
    if expected_source_anchor is not None:
        if (
            not isinstance(expected_source_anchor, str)
            or re.fullmatch(r"SYNTHETIC_[A-Z0-9_]{8,56}", expected_source_anchor) is None
        ):
            raise Day2Failure("Expected source marker must be a synthetic uppercase ASCII identifier.")
        if not is_pdf or expected_source_anchor not in _extract_pdf_text(source, "Selected source PDF"):
            raise Day2Failure("Selected synthetic PDF does not contain the expected source marker.")

    # /me validates the approved JWTs and binds their subjects to the API.
    # Validate BOTH local tokens first: runtime-manifest must not get an
    # unchecked Authorization header even for a read-only request.
    identity_claims = require_distinct_owners(
        client, token_a, token_b,
        expected_issuer=expected_auth_issuer,
        expected_audience=expected_auth_audience,
        minimum_validity_seconds=timeout_seconds + 30,
    )
    attest_runtime(client, token_a, freeze)
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
    report_instruction = (
        "Summarize the selected private document in English as a short report. "
        "Use only the selected source and include an English email draft."
    )
    if expected_source_anchor is not None:
        report_instruction += (
            f" Reproduce the synthetic source marker {expected_source_anchor} exactly "
            "in the English summary and report PDF."
        )

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
        "instruction": report_instruction,
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
    if expected_source_anchor is not None and expected_source_anchor not in draft["report"]["summary"]:
        raise Day2Failure("English report summary is missing the expected synthetic source marker.")
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
        required_pdf_anchor=expected_source_anchor,
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
        "identity_claims": identity_claims,
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
        "content_anchor_verification": "passed" if expected_source_anchor is not None else "unverified",
    }



def model_provenance_receipt(
    task_id: str,
    owner_id: str,
    task_state: str,
    workflow_version: str,
    rows: list,
    draft_output: object,
    *,
    expected_model: str,
    expected_attempts: int,
    expected_accounted_tokens: int,
) -> dict:
    """Corroborate actual draft generation metadata with the persisted model ledger.

    An API usage aggregate alone is not evidence of provider identity: a
    charged reservation can exist even when the provider was never called.
    Only a successfully settled attempt with provider-returned token counts
    and a matching generated draft qualifies for D02.T07/G02.
    """
    if (not isinstance(task_id, str) or not task_id
            or not isinstance(owner_id, str) or not owner_id
            or task_state != "completed" or workflow_version != "report_email_v1"):
        raise Day2Failure("Model provenance is not bound to the completed private report task.")
    if (not isinstance(expected_model, str) or not expected_model.strip()
            or type(expected_attempts) is not int or expected_attempts < 1
            or type(expected_accounted_tokens) is not int or expected_accounted_tokens < 1):
        raise Day2Failure("Approved model identity or API usage totals are invalid.")
    if len(rows) != expected_attempts or not rows:
        raise Day2Failure("Model attempt ledger does not match the API-reported attempt count.")
    ordered = sorted(rows, key=lambda row: row.attempt)
    if [row.attempt for row in ordered] != list(range(1, len(ordered) + 1)):
        raise Day2Failure("Model attempt ordinals are missing, duplicated or nonconsecutive.")
    for row in ordered:
        if (row.task_id != task_id or row.owner_id != owner_id
                or row.model != expected_model
                or row.state not in {"completed", "failed", "unknown"}
                or type(row.charged_tokens) is not int or row.charged_tokens < 0):
            raise Day2Failure("Model attempt ledger contains mismatched identity, model or unsettled usage.")
    charged = sum(row.charged_tokens for row in ordered)
    if charged != expected_accounted_tokens:
        raise Day2Failure("API model usage is inconsistent with persisted charged tokens.")
    completed = [row for row in ordered if row.state == "completed"]
    if len(completed) != 1:
        raise Day2Failure("Completed report requires exactly one settled successful model attempt.")
    finished = completed[0]
    if (not isinstance(draft_output, dict)
            or not isinstance(draft_output.get("generation"), dict)):
        raise Day2Failure("Completed report is missing persisted provider-generation metadata.")
    generation = draft_output["generation"]
    if (generation.get("provider") != "deepseek"
            or generation.get("model") != expected_model
            or generation.get("task_type") != "report_email"
            or generation.get("finish_reason") != "stop"
            or generation.get("validator_result") != "passed"
            or not isinstance(generation.get("prompt_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", generation["prompt_sha256"])):
        raise Day2Failure("Report draft provider, model, prompt or validator provenance is invalid.")
    input_tokens = generation.get("input_tokens")
    output_tokens = generation.get("output_tokens")
    total_tokens = generation.get("total_tokens")
    if (type(input_tokens) is not int or input_tokens < 1
            or type(output_tokens) is not int or output_tokens < 1
            or type(total_tokens) is not int or total_tokens < input_tokens + output_tokens
            or (finished.input_tokens, finished.output_tokens, finished.charged_tokens)
            != (input_tokens, output_tokens, total_tokens)):
        raise Day2Failure("Settled model attempt lacks matching positive provider-reported token usage.")
    latency_ms = generation.get("latency_ms")
    if (type(latency_ms) is not int or latency_ms < 0
            or type(finished.latency_ms) is not int
            or finished.latency_ms != latency_ms):
        raise Day2Failure("Provider generation latency differs from the model attempt ledger.")
    return {
        "status": "verified", "task_id": task_id,
        "provider": "deepseek", "model": expected_model,
        "ledger_attempt_count": len(ordered), "ledger_accounted_tokens": charged,
        "completed_attempt": finished.attempt,
        "completed_input_tokens": input_tokens,
        "completed_output_tokens": output_tokens,
        "completed_total_tokens": total_tokens,
        "prompt_sha256": generation["prompt_sha256"],
        "generation_validator": "passed",
    }


def persisted_model_provenance(
    container: Container,
    task_id: str,
    *,
    expected_owner_id: str,
    expected_model: str,
    expected_attempts: int,
    expected_accounted_tokens: int,
) -> dict:
    """Read real cw_tasks, cw_model_attempts and cw_steps without modifying staging."""
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from services.coworker.models import ModelAttempt, Step, Task

    try:
        with container.repository.sessions() as db:
            task = db.scalar(select(Task).where(Task.id == task_id))
            if task is None:
                raise Day2Failure("Completed model task is missing from the staging database.")
            if task.owner_id != expected_owner_id:
                raise Day2Failure(
                    "Model ledger task owner does not match the verified managed owner A."
                )
            rows = list(db.scalars(
                select(ModelAttempt).where(ModelAttempt.task_id == task_id)
            ).all())
            draft = db.get(Step, (task_id, "draft"))
            return model_provenance_receipt(
                task_id, task.owner_id, task.state, task.workflow_version,
                rows, draft.output if draft is not None else None,
                expected_model=expected_model,
                expected_attempts=expected_attempts,
                expected_accounted_tokens=expected_accounted_tokens,
            )
    except SQLAlchemyError:
        # SQL driver details can contain private endpoints and should not be
        # written to operator logs or issue comments.
        raise Day2Failure("Model provider ledger could not be independently verified.") from None


def _worker_utc_time(raw: object, label: str) -> datetime:
    """Parse a real timezone-aware instant; textual ordering is not chronology."""
    if not isinstance(raw, str) or not raw:
        raise Day2Failure(f"Worker {label} must be a timezone-aware ISO timestamp.")
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("naive datetime")
        return instant.astimezone(timezone.utc)
    except (ValueError, OverflowError, TypeError):
        raise Day2Failure(f"Worker {label} must be a timezone-aware ISO timestamp.") from None


def _checked_worker_observation(
    worker: object,
    *,
    revision: str,
    task_queue: str,
    require_fresh: bool,
) -> tuple[datetime, datetime]:
    """Require a coherent authenticated-worker registry observation.

    An inventory heartbeat_fresh boolean is advisory: the operator also
    compares the actual datetime against the SAME TTL used by the repository.
    The earlier prepared snapshot may age while the real PDF model runs, so
    only the new observation must be fresh at the time it is read.
    """
    if (
        not isinstance(worker, dict)
        or not isinstance(worker.get("id"), str)
        or not worker["id"].strip()
        or worker.get("source_revision") != revision
        or worker.get("task_queue") != task_queue
        or worker.get("state") != "running"
        or worker.get("heartbeat_fresh") is not True
    ):
        raise Day2Failure("Worker inventory identity, queue, source SHA or live status is invalid.")
    started_at = _worker_utc_time(worker.get("started_at"), "registration")
    heartbeat_at = _worker_utc_time(worker.get("heartbeat_at"), "heartbeat")
    observed_at = datetime.now(timezone.utc)
    if not started_at <= heartbeat_at <= observed_at:
        raise Day2Failure("Worker registration/heartbeat chronology is invalid or future-dated.")
    if require_fresh and (observed_at - heartbeat_at).total_seconds() > WORKER_HEARTBEAT_TTL_SECONDS:
        raise Day2Failure("Worker heartbeat is stale at its actual observation time.")
    return started_at, heartbeat_at


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
    _checked_worker_observation(
        active[0], revision=revision,
        task_queue=container.settings.task_queue, require_fresh=True,
    )
    return active[0]


def heartbeat_advanced(container: Container, before: dict, revision: str) -> dict:
    task_queue = container.settings.task_queue
    before_started_at, before_heartbeat_at = _checked_worker_observation(
        before, revision=revision, task_queue=task_queue, require_fresh=False,
    )
    deadline = time.monotonic() + WORKER_HEARTBEAT_TTL_SECONDS
    while True:
        workers = container.repository.worker_inventory(task_queue=task_queue)
        current = next((w for w in workers if w.get("id") == before["id"]), None)
        if current:
            started_at, heartbeat_at = _checked_worker_observation(
                current, revision=revision, task_queue=task_queue,
                require_fresh=True,
            )
            if started_at != before_started_at:
                raise Day2Failure("Worker registration changed under the original worker identity.")
            if heartbeat_at > before_heartbeat_at:
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
    parser.add_argument("--expected-source-anchor", required=True,
                        help="Exact SYNTHETIC_... marker in source PDF, expected in English summary and report PDF.")
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
            # The currently reviewed Coworker report_email DraftModel is
            # DeepSeekDraftModel, regardless of other Chat API provider support.
            # Do not charge a task when the operator only configured Gemma.
            or settings.chat_provider != "deepseek"
            or not settings.deepseek_api_key
        ):
            raise Day2Failure("Operator runtime does not match staging source, private S3 or the reviewed DeepSeek draft provider.")
        # Pin all three credential destinations before any outbound request.
        origin = clean_origin(os.getenv("SHUDDHO_STAGING_API_BASE_URL", ""))
        require_approved_staging_destinations(
            api_origin=origin,
            auth_issuer=settings.auth_issuer,
            storage_endpoint=settings.storage_endpoint or "",
        )
        token_a = os.getenv("SHUDDHO_STAGING_TOKEN_A", "")
        token_b = os.getenv("SHUDDHO_STAGING_TOKEN_B", "")
        owner_a_account_id, _owner_b_account_id = _prevalidate_managed_owners(
            token_a, token_b, expected_issuer=settings.auth_issuer,
            expected_audience=settings.auth_audience,
            minimum_validity_seconds=args.timeout + 30,
        )
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
                expected_auth_issuer=settings.auth_issuer,
                expected_auth_audience=settings.auth_audience,
                owner_b_artifact_id=args.owner_b_artifact_id,
                timeout_seconds=args.timeout, trusted_storage_host=endpoint.hostname,
                expected_source_anchor=args.expected_source_anchor,
            )
        asyncio.run(temporal_completed(settings, result["workflow_id"]))
        result["model_evidence"] = persisted_model_provenance(
            container, result["task_id"],
            expected_owner_id=owner_a_account_id,
            expected_model=settings.deepseek_model,
            expected_attempts=result["model_attempts"],
            expected_accounted_tokens=result["accounted_tokens"],
        )
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
