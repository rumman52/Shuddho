from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

TERMINAL = {"completed", "failed", "cancelled", "needs_input"}


class ExerciseFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def require_https_base(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ExerciseFailure("SHUDDHO_STAGING_API_BASE_URL must be a clean HTTPS origin.")
    return value.rstrip("/")


def env_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ExerciseFailure(f"{name} is required.")
    return value


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def expect(response: httpx.Response, status: int, label: str) -> httpx.Response:
    if response.status_code != status:
        raise ExerciseFailure(f"{label} returned HTTP {response.status_code}; expected {status}.")
    return response


def json_object(response: httpx.Response, label: str) -> dict:
    try:
        value = response.json()
    except ValueError:
        raise ExerciseFailure(f"{label} did not return JSON.") from None
    if not isinstance(value, dict):
        raise ExerciseFailure(f"{label} returned an unexpected JSON shape.")
    return value


def owner_isolation(client: httpx.Client, token_a: str, token_b: str) -> dict:
    me_a = json_object(expect(client.get("/api/v1/me", headers=auth(token_a)), 200, "account A /me"), "account A /me")
    me_b = json_object(expect(client.get("/api/v1/me", headers=auth(token_b)), 200, "account B /me"), "account B /me")
    if not me_a.get("account_id") or not me_b.get("account_id") or me_a["account_id"] == me_b["account_id"]:
        raise ExerciseFailure("The two staging tokens did not resolve to distinct owned accounts.")
    if not me_a.get("workspace_id") or me_a["workspace_id"] == me_b.get("workspace_id"):
        raise ExerciseFailure("The two staging tokens did not resolve to distinct workspaces.")

    marker = uuid.uuid4().hex
    body = ("shuddho-owner-isolation-" + marker).encode()
    upload = json_object(expect(client.post(
        "/api/v1/documents",
        headers=auth(token_a),
        json={"filename": "staging-owner-probe.txt", "byte_size": len(body), "sha256": hashlib.sha256(body).hexdigest()},
    ), 201, "create owned upload"), "create owned upload")
    document_id = str(upload.get("id") or "")
    if not document_id:
        raise ExerciseFailure("Upload creation did not return a document id.")
    content_path = f"/api/v1/documents/{document_id}/content"

    expect(client.put(content_path, headers=auth(token_b), content=body), 404, "cross-account upload write")
    expect(client.put(content_path, headers=auth(token_a), content=body), 200, "owned upload write")
    docs_b = json_object(expect(client.get("/api/v1/documents", headers=auth(token_b)), 200, "account B documents"), "account B documents")
    if any(str(item.get("id")) == document_id for item in docs_b.get("documents", [])):
        raise ExerciseFailure("Account B could enumerate account A's document.")
    expect(client.delete(f"/api/v1/documents/{document_id}", headers=auth(token_b)), 404, "cross-account document delete")
    expect(client.delete(f"/api/v1/documents/{document_id}", headers=auth(token_a)), 202, "owned document cleanup")

    idempotency_key = "staging-isolation-" + marker
    task = json_object(expect(client.post(
        "/api/v1/tasks",
        headers=auth(token_a) | {"Idempotency-Key": idempotency_key},
        json={
            "skill_id": "report_email",
            "instruction": "Create a short staging validation report.",
            "notes": "Synthetic staging probe only. No user data.",
            "document_ids": [],
            "output_language": "en",
        },
    ), 202, "create staging task"), "create staging task")
    task_id = str(task.get("id") or "")
    if not task_id:
        raise ExerciseFailure("Task creation did not return a task id.")
    task_path = f"/api/v1/tasks/{task_id}"
    expect(client.get(task_path, headers=auth(token_b)), 404, "cross-account task read")
    expect(client.get(task_path + "/events", headers=auth(token_b)), 404, "cross-account task events")
    expect(client.post(task_path + "/cancel", headers=auth(token_b)), 404, "cross-account task cancel")
    expect(client.post(task_path + "/cancel", headers=auth(token_a)), 200, "owned task cleanup")

    return passed("two distinct managed identities passed workspace, document, task, event, cancel and cleanup owner-isolation checks")


def artifact_authorization(client: httpx.Client, token_a: str, token_b: str, timeout_seconds: int) -> dict:
    marker = uuid.uuid4().hex
    task = json_object(expect(client.post(
        "/api/v1/tasks",
        headers=auth(token_a) | {"Idempotency-Key": "staging-artifact-" + marker},
        json={
            "skill_id": "report_email",
            "instruction": "Create a short staging artifact validation report.",
            "notes": "Synthetic staging artifact probe only. No user data.",
            "document_ids": [],
            "output_language": "en",
        },
    ), 202, "create artifact validation task"), "create artifact validation task")
    task_id = str(task.get("id") or "")
    if not task_id:
        raise ExerciseFailure("Artifact validation task did not return an id.")
    deadline = time.monotonic() + timeout_seconds
    result = task
    while time.monotonic() < deadline:
        result = json_object(expect(client.get(f"/api/v1/tasks/{task_id}", headers=auth(token_a)), 200, "artifact task status"), "artifact task status")
        if result.get("state") in TERMINAL:
            break
        time.sleep(2)
    else:
        client.post(f"/api/v1/tasks/{task_id}/cancel", headers=auth(token_a))
        raise ExerciseFailure("Artifact validation task did not reach a terminal state before timeout.")

    if result.get("state") not in {"completed", "needs_input"}:
        raise ExerciseFailure(f"Artifact validation task ended in state {result.get('state')!r}.")
    artifacts = result.get("artifacts") or []
    if not artifacts:
        raise ExerciseFailure("Artifact validation task produced no downloadable artifact.")
    artifact_id = str(artifacts[0].get("id") or "")
    if not artifact_id:
        raise ExerciseFailure("Artifact metadata did not include an id.")

    route = f"/api/v1/artifacts/{artifact_id}/download"
    expect(client.get(route, headers=auth(token_b)), 404, "cross-account artifact download")
    download = json_object(expect(client.get(route, headers=auth(token_a)), 200, "owned artifact download"), "owned artifact download")
    if download.get("url"):
        response = httpx.get(download["url"], timeout=20, follow_redirects=False)
        if response.status_code != 200 or not response.content:
            raise ExerciseFailure(f"Signed artifact URL returned HTTP {response.status_code} or empty content.")
    elif download.get("content_path"):
        content_path = str(download["content_path"])
        expect(client.get(content_path, headers=auth(token_b)), 404, "cross-account artifact content")
        response = expect(client.get(content_path, headers=auth(token_a)), 200, "owned artifact content")
        if not response.content:
            raise ExerciseFailure("Owned artifact content was empty.")
    else:
        raise ExerciseFailure("Artifact download response included neither a signed URL nor a content path.")

    return passed("owner-scoped artifact authorization and non-empty private download passed with synthetic staging output")


def merge_evidence(base: dict, updates: dict) -> dict:
    result = dict(base)
    result.update(updates)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the authenticated Shuddho Coworker staging owner-isolation exercise.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--artifact", action="store_true", help="Run one live synthetic Coworker task and validate artifact authorization/download.")
    parser.add_argument("--artifact-timeout", type=int, default=180)
    args = parser.parse_args()

    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token_a = env_secret("SHUDDHO_STAGING_TOKEN_A")
    token_b = env_secret("SHUDDHO_STAGING_TOKEN_B")
    if token_a == token_b:
        raise SystemExit("The two staging account tokens must be different.")

    base = {}
    if args.base_evidence:
        value = json.loads(args.base_evidence.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise SystemExit("Base staging evidence must be a JSON object.")
        base = value

    updates = {}
    try:
        with httpx.Client(base_url=base_url, timeout=20, follow_redirects=False) as client:
            updates["identity"] = owner_isolation(client, token_a, token_b)
            if args.artifact:
                updates["storage"] = artifact_authorization(client, token_a, token_b, max(30, args.artifact_timeout))
    except (httpx.HTTPError, ExerciseFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None

    result = merge_evidence(base, updates)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(args.output), "checks": {key: value["status"] for key, value in updates.items()}}, indent=2))


if __name__ == "__main__":
    main()
