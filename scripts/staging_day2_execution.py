"""Day 2 controlled-staging document execution; reuses the real Coworker API/worker.

This is an operator exercise, not a production endpoint, simulation or alternate
execution engine. It never prints tokens, document text or presigned URLs.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from temporalio.client import Client

from scripts.staging_release_evidence import write_private_json
from scripts.staging_release_freeze import canonical_sha256, clean_origin, valid_sha
from services.coworker.config import Settings
from services.coworker.container import Container


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


def public_signed_url(url: object) -> str:
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
    return url


def run_probe(
    client: httpx.Client,
    token_a: str,
    token_b: str,
    freeze: dict,
    source: bytes,
    *,
    timeout_seconds: int = 180,
) -> dict:
    """Prove a selected private document was executed by the real model-backed task.

    Keep all private bytes and signed URLs out of the returned evidence.
    """
    release = check_release(freeze)
    if not isinstance(source, bytes) or not 1 <= len(source) <= 4096:
        raise Day2Failure("Day 2 source must be bounded synthetic UTF-8 bytes.")
    try:
        source.decode("utf-8")
    except UnicodeDecodeError:
        raise Day2Failure("Day 2 source must contain valid UTF-8.") from None
    if not 1 <= timeout_seconds <= 1800:
        raise Day2Failure("Task timeout must be between 1 and 1800 seconds.")
    attest_runtime(client, token_a, freeze)
    require_distinct_owners(client, token_a, token_b)
    a, b = bearer(token_a), bearer(token_b)
    marker = uuid.uuid4().hex
    source_sha = hashlib.sha256(source).hexdigest()

    upload = obj(checked(client.post("/api/v1/documents", headers=a, json={
        "filename": "day2-synthetic-" + marker + ".txt",
        "byte_size": len(source), "sha256": source_sha,
    }), 201, "private document create"), "private document create")
    document_id = str(upload.get("id") or "")
    if not document_id:
        raise Day2Failure("Private document create did not return an id.")
    doc_content = f"/api/v1/documents/{document_id}/content"
    checked(client.put(doc_content, headers=b, content=source), 404, "cross-owner document upload")
    checked(client.put(doc_content, headers=a, content=source), 200, "owned document upload")
    checked(client.get(doc_content, headers=b), 404, "cross-owner document read")
    download = checked(client.get(doc_content, headers=a), 200, "owned document read")
    if hashlib.sha256(download.content).hexdigest() != source_sha or download.content != source:
        raise Day2Failure("Private document readback did not match the uploaded bytes.")
    foreign_docs = obj(checked(client.get("/api/v1/documents", headers=b), 200, "foreign document list"), "foreign document list")
    if not isinstance(foreign_docs.get("documents"), list) or any(
        isinstance(item, dict) and item.get("id") == document_id
        for item in foreign_docs["documents"]
    ):
        raise Day2Failure("Cross-owner document enumeration was not denied.")

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
    expected_sha = pdf.get("sha256")
    expected_bytes = pdf.get("byte_size")
    if (
        not artifact_id
        or not isinstance(expected_sha, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha)
        or type(expected_bytes) is not int or not 1 <= expected_bytes <= 16 * 1024 * 1024
    ):
        raise Day2Failure("Report artifact identity/digest/size metadata is incomplete.")
    content_route = f"/api/v1/artifacts/{artifact_id}/content"
    url_route = f"/api/v1/artifacts/{artifact_id}/download"
    if client.get(url_route, headers=b).status_code != 404:
        raise Day2Failure("cross-owner artifact download was not denied.")
    if client.get(content_route, headers=b).status_code != 404:
        raise Day2Failure("cross-owner artifact content was not denied.")
    own_bytes = checked(client.get(content_route, headers=a), 200, "owned artifact content").content
    if len(own_bytes) != expected_bytes or hashlib.sha256(own_bytes).hexdigest() != expected_sha:
        raise Day2Failure("Owned artifact bytes do not match persisted metadata.")
    signed = obj(checked(client.get(url_route, headers=a), 200, "private artifact URL"), "private artifact URL")
    url = public_signed_url(signed.get("url"))
    signed_response = httpx.get(url, timeout=20, follow_redirects=False)
    if (
        signed_response.status_code != 200 or len(signed_response.content) != expected_bytes
        or hashlib.sha256(signed_response.content).hexdigest() != expected_sha
    ):
        raise Day2Failure("Presigned private artifact retrieval failed digest verification.")
    return {
        "status": "passed",
        "release_id": release["release_id"],
        "source_revision": release["source_revision"],
        "runtime_manifest_sha256": freeze["runtime_manifest_sha256"],
        "document_id": document_id, "document_sha256": source_sha,
        "task_id": task_id, "workflow_id": "shuddho-task-" + task_id,
        "artifact_id": artifact_id, "artifact_sha256": expected_sha,
        "artifact_bytes": expected_bytes, "model_attempts": usage["model_attempts"],
        "accounted_tokens": usage["accounted_tokens"],
        "owner_isolation": "passed", "artifact_retrieval": "passed",
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


async def temporal_completed(settings: Settings, workflow_id: str) -> None:
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
        container = Container.create(settings)
        before = active_worker(container, release["source_revision"])
        marker = uuid.uuid4().hex
        source = (
            "Day 2 synthetic private record " + marker + ".\n"
            "The test department is North Office. The sample budget is 42 units.\n"
            "Only these synthetic facts may be used; no real customer data is present.\n"
        ).encode("utf-8")
        with httpx.Client(base_url=origin, timeout=20, follow_redirects=False) as client:
            result = run_probe(client, token_a, token_b, freeze, source, timeout_seconds=args.timeout)
        asyncio.run(temporal_completed(settings, result["workflow_id"]))
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
                                     "worker_heartbeat": "passed"}}, indent=2))
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
