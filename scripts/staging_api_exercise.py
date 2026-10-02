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


REMAINING_OWNER_RESOURCE_KEYS = {
    "agent_run_id",
    "notification_id",
    "action_id",
    "artifact_id",
    "connector_read_grant_id",
    "connector_snapshot_id",
}


def owned_resource_manifest(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ExerciseFailure(
            f"Could not read owned-resource manifest: {type(error).__name__}."
        ) from None
    if not isinstance(value, dict):
        raise ExerciseFailure("Owned-resource manifest must contain a JSON object.")
    keys = set(value)
    missing = sorted(REMAINING_OWNER_RESOURCE_KEYS - keys)
    unexpected = sorted(keys - REMAINING_OWNER_RESOURCE_KEYS)
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise ExerciseFailure(
            "Owned-resource manifest must contain only the required non-secret resource IDs ("
            + "; ".join(details)
            + ")."
        )
    result = {}
    for key in sorted(REMAINING_OWNER_RESOURCE_KEYS):
        raw = value.get(key)
        if not isinstance(raw, str) or not raw.strip():
            raise ExerciseFailure(f"{key} must be a non-empty UUID string.")
        try:
            parsed = uuid.UUID(raw.strip())
        except ValueError:
            raise ExerciseFailure(f"{key} must be a valid UUID.") from None
        result[key] = str(parsed)
    return result


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



def personal_agent_owner_isolation(
    client: httpx.Client,
    token_a: str,
    token_b: str,
) -> dict:
    """Exercise PA-10 owner boundaries without invoking a model or provider write."""
    marker = uuid.uuid4().hex
    alice = auth(token_a)
    bob = auth(token_b)

    goal_response = expect(
        client.post(
            "/api/v1/goals",
            headers=alice | {"Idempotency-Key": "staging-owner-goal-" + marker},
            json={
                "objective": "Validate PA-10 owner isolation with synthetic staging data.",
                "success_criteria": ["Keep every created resource owner scoped."],
                "constraints": ["Do not perform external actions."],
                "deadline_at": None,
                "timezone": "UTC",
                "state": "active",
                "milestones": [],
                "budget": {"max_runs": 1, "max_planner_tokens": 1000},
                "authorized_resources": [],
                "next_review_at": None,
            },
        ),
        201,
        "create owner-isolation goal",
    )
    goal = json_object(goal_response, "create owner-isolation goal")
    goal_id = str(goal.get("id") or "")
    goal_revision = int(goal.get("revision") or 0)
    if not goal_id or goal_revision < 1:
        raise ExerciseFailure("Owner-isolation goal did not return a usable id/revision.")

    expect(
        client.get(f"/api/v1/goals/{goal_id}", headers=bob),
        404,
        "cross-account goal read",
    )
    expect(
        client.patch(
            f"/api/v1/goals/{goal_id}",
            headers=bob,
            json={"expected_revision": goal_revision, "objective": "cross-owner write"},
        ),
        404,
        "cross-account goal edit",
    )

    memory_response = expect(
        client.post(
            "/api/v1/memory",
            headers=alice,
            json={
                "namespace": "preferences",
                "key": "staging.owner_isolation." + marker,
                "value": "Synthetic staging owner-isolation fact.",
                "language": "en",
            },
        ),
        201,
        "create owner-isolation memory",
    )
    memory = json_object(memory_response, "create owner-isolation memory")
    memory_id = str(memory.get("id") or "")
    if not memory_id:
        raise ExerciseFailure("Owner-isolation memory did not return an id.")

    bob_memory = json_object(
        expect(client.get("/api/v1/memory", headers=bob), 200, "account B memory"),
        "account B memory",
    )
    if any(str(item.get("id")) == memory_id for item in bob_memory.get("facts", [])):
        raise ExerciseFailure("Account B could enumerate account A's memory.")
    expect(
        client.put(
            f"/api/v1/memory/{memory_id}",
            headers=bob,
            json={"value": "cross-owner write", "language": "en"},
        ),
        404,
        "cross-account memory edit",
    )
    expect(
        client.delete(f"/api/v1/memory/{memory_id}", headers=bob),
        404,
        "cross-account memory delete",
    )

    automation_response = expect(
        client.post(
            "/api/v1/automations",
            headers=alice | {"Idempotency-Key": "staging-owner-automation-" + marker},
            json={
                "goal_id": goal_id,
                "goal_revision": goal_revision,
                "timezone": "UTC",
                "schedule": {
                    "kind": "daily",
                    "hour": 23,
                    "minute": 59,
                    "weekdays": [],
                },
                "output_language": "en",
                "overlap_policy": "skip",
                "catchup_window_seconds": 60,
                "quiet_hours": None,
                "expires_at": None,
            },
        ),
        201,
        "create owner-isolation automation",
    )
    automation = json_object(
        automation_response,
        "create owner-isolation automation",
    )
    automation_id = str(automation.get("id") or "")
    automation_revision = int(automation.get("revision") or 0)
    if not automation_id or automation_revision < 1:
        raise ExerciseFailure(
            "Owner-isolation automation did not return a usable id/revision."
        )

    expect(
        client.get(f"/api/v1/automations/{automation_id}", headers=bob),
        404,
        "cross-account automation read",
    )
    expect(
        client.get(
            f"/api/v1/automations/{automation_id}/history",
            headers=bob,
        ),
        404,
        "cross-account automation history",
    )
    expect(
        client.patch(
            f"/api/v1/automations/{automation_id}",
            headers=bob,
            json={
                "expected_revision": automation_revision,
                "catchup_window_seconds": 120,
            },
        ),
        404,
        "cross-account automation edit",
    )
    expect(
        client.post(
            f"/api/v1/automations/{automation_id}/cancel",
            headers=bob,
            json={"expected_revision": automation_revision},
        ),
        404,
        "cross-account automation cancel",
    )

    automations_b = json_object(
        expect(
            client.get("/api/v1/automations", headers=bob),
            200,
            "account B automations",
        ),
        "account B automations",
    )
    if any(
        str(item.get("id")) == automation_id
        for item in automations_b.get("automations", [])
    ):
        raise ExerciseFailure("Account B could enumerate account A's automation.")

    cancelled_automation = json_object(
        expect(
            client.post(
                f"/api/v1/automations/{automation_id}/cancel",
                headers=alice,
                json={"expected_revision": automation_revision},
            ),
            200,
            "owned automation cleanup",
        ),
        "owned automation cleanup",
    )
    if cancelled_automation.get("state") != "cancelled":
        raise ExerciseFailure("Owned automation cleanup did not cancel the automation.")

    deleted_memory = json_object(
        expect(
            client.delete(f"/api/v1/memory/{memory_id}", headers=alice),
            200,
            "owned memory cleanup",
        ),
        "owned memory cleanup",
    )
    if deleted_memory.get("deleted") is not True:
        raise ExerciseFailure("Owned memory cleanup did not confirm deletion.")

    cancelled_goal = json_object(
        expect(
            client.post(
                f"/api/v1/goals/{goal_id}/cancel",
                headers=alice,
                json={"expected_revision": goal_revision},
            ),
            200,
            "owned goal cleanup",
        ),
        "owned goal cleanup",
    )
    if cancelled_goal.get("state") != "cancelled":
        raise ExerciseFailure("Owned goal cleanup did not cancel the goal.")

    return passed(
        "two distinct managed identities passed PA-10 goal, automation, history, "
        "memory enumeration/write/delete and owner-cleanup isolation checks; no "
        "Agent run, model call, provider read or provider write was created"
    )

def remaining_owner_isolation(
    client: httpx.Client,
    token_a: str,
    token_b: str,
    resources: dict[str, str],
) -> dict:
    """Verify already-created PA-10 resources remain invisible and immutable cross-owner."""
    alice = auth(token_a)
    bob = auth(token_b)

    run_id = resources["agent_run_id"]
    run = json_object(
        expect(
            client.get(f"/api/v1/agent-runs/{run_id}", headers=alice),
            200,
            "owned Agent run",
        ),
        "owned Agent run",
    )
    if str(run.get("id") or "") != run_id:
        raise ExerciseFailure("Owned Agent run response did not match the requested id.")
    bob_runs = json_object(
        expect(client.get("/api/v1/agent-runs", headers=bob), 200, "account B Agent runs"),
        "account B Agent runs",
    )
    if any(str(item.get("id")) == run_id for item in bob_runs.get("runs", [])):
        raise ExerciseFailure("Account B could enumerate account A's Agent run.")
    expect(
        client.get(f"/api/v1/agent-runs/{run_id}", headers=bob),
        404,
        "cross-account Agent run read",
    )
    expect(
        client.get(f"/api/v1/agent-runs/{run_id}/events", headers=bob),
        404,
        "cross-account Agent run events",
    )
    expect(
        client.post(f"/api/v1/agent-runs/{run_id}/cancel", headers=bob),
        404,
        "cross-account Agent run cancel",
    )

    notification_id = resources["notification_id"]
    alice_notifications = json_object(
        expect(client.get("/api/v1/notifications", headers=alice), 200, "account A notifications"),
        "account A notifications",
    )
    if alice_notifications.get("enabled") is not True:
        raise ExerciseFailure("Notifications are not enabled for the owned-resource exercise.")
    if not any(
        str(item.get("id")) == notification_id
        for item in alice_notifications.get("notifications", [])
    ):
        raise ExerciseFailure("Account A notification was not present in its owned inbox.")
    bob_notifications = json_object(
        expect(client.get("/api/v1/notifications", headers=bob), 200, "account B notifications"),
        "account B notifications",
    )
    if any(
        str(item.get("id")) == notification_id
        for item in bob_notifications.get("notifications", [])
    ):
        raise ExerciseFailure("Account B could enumerate account A's notification.")
    expect(
        client.post(f"/api/v1/notifications/{notification_id}/read", headers=bob),
        404,
        "cross-account notification read receipt",
    )

    action_id = resources["action_id"]
    action = json_object(
        expect(client.get(f"/api/v1/actions/{action_id}", headers=alice), 200, "owned action"),
        "owned action",
    )
    if str(action.get("id") or "") != action_id:
        raise ExerciseFailure("Owned action response did not match the requested id.")
    preview_hash = action.get("preview_hash")
    if not isinstance(preview_hash, str) or not preview_hash:
        raise ExerciseFailure("Owned action does not expose an immutable preview_hash.")
    before_action_state = action.get("state")
    bob_actions = json_object(
        expect(client.get("/api/v1/actions", headers=bob), 200, "account B actions"),
        "account B actions",
    )
    if any(str(item.get("id")) == action_id for item in bob_actions.get("actions", [])):
        raise ExerciseFailure("Account B could enumerate account A's action.")
    expect(
        client.get(f"/api/v1/actions/{action_id}", headers=bob),
        404,
        "cross-account action read",
    )
    expect(
        client.post(
            f"/api/v1/actions/{action_id}/approve",
            headers=bob,
            json={"preview_hash": preview_hash},
        ),
        404,
        "cross-account action approval",
    )
    expect(
        client.post(f"/api/v1/actions/{action_id}/cancel", headers=bob),
        404,
        "cross-account action cancel",
    )
    after_action = json_object(
        expect(
            client.get(f"/api/v1/actions/{action_id}", headers=alice),
            200,
            "owned action after denied cross-owner attempts",
        ),
        "owned action after denied cross-owner attempts",
    )
    if (
        after_action.get("state") != before_action_state
        or after_action.get("preview_hash") != preview_hash
    ):
        raise ExerciseFailure(
            "Denied cross-owner action attempts changed the owned action."
        )

    artifact_id = resources["artifact_id"]
    alice_artifacts = json_object(
        expect(client.get("/api/v1/artifacts", headers=alice), 200, "account A artifacts"),
        "account A artifacts",
    )
    if not any(
        str(item.get("id")) == artifact_id
        for item in alice_artifacts.get("artifacts", [])
    ):
        raise ExerciseFailure("Account A artifact was not present in its owned catalog.")
    bob_artifacts = json_object(
        expect(client.get("/api/v1/artifacts", headers=bob), 200, "account B artifacts"),
        "account B artifacts",
    )
    if any(
        str(item.get("id")) == artifact_id
        for item in bob_artifacts.get("artifacts", [])
    ):
        raise ExerciseFailure("Account B could enumerate account A's artifact.")
    expect(
        client.get(f"/api/v1/artifacts/{artifact_id}/download", headers=bob),
        404,
        "cross-account artifact download",
    )
    expect(
        client.get(f"/api/v1/artifacts/{artifact_id}/content", headers=bob),
        404,
        "cross-account artifact content",
    )
    json_object(
        expect(
            client.get(f"/api/v1/artifacts/{artifact_id}/download", headers=alice),
            200,
            "owned artifact download authorization",
        ),
        "owned artifact download authorization",
    )

    grant_id = resources["connector_read_grant_id"]
    snapshot_id = resources["connector_snapshot_id"]
    alice_grants = json_object(
        expect(
            client.get("/api/v1/connector-read-grants", headers=alice),
            200,
            "account A connector read grants",
        ),
        "account A connector read grants",
    )
    if alice_grants.get("enabled") is not True:
        raise ExerciseFailure("Connector reads are not enabled for the owned-resource exercise.")
    if not any(
        str(item.get("id")) == grant_id
        for item in alice_grants.get("grants", [])
    ):
        raise ExerciseFailure("Account A connector read grant was not present.")
    bob_grants = json_object(
        expect(
            client.get("/api/v1/connector-read-grants", headers=bob),
            200,
            "account B connector read grants",
        ),
        "account B connector read grants",
    )
    if any(str(item.get("id")) == grant_id for item in bob_grants.get("grants", [])):
        raise ExerciseFailure("Account B could enumerate account A's connector read grant.")
    snapshots = json_object(
        expect(
            client.get(
                f"/api/v1/connector-read-grants/{grant_id}/snapshots",
                headers=alice,
            ),
            200,
            "owned connector snapshots",
        ),
        "owned connector snapshots",
    )
    if not any(
        str(item.get("id")) == snapshot_id
        for item in snapshots.get("snapshots", [])
    ):
        raise ExerciseFailure(
            "Account A connector snapshot was not present for the selected grant."
        )
    expect(
        client.get(
            f"/api/v1/connector-read-grants/{grant_id}/snapshots",
            headers=bob,
        ),
        404,
        "cross-account connector snapshots",
    )
    expect(
        client.get(
            f"/api/v1/connector-read-grants/{grant_id}/subscription",
            headers=bob,
        ),
        404,
        "cross-account connector subscription",
    )

    return passed(
        "two distinct managed identities passed remaining PA-10 owner isolation for "
        "Agent run/events/cancel, notification inbox/read receipt, action read/approval/"
        "cancel immutability, artifact catalog/download/content, and provider-derived "
        "connector grant/snapshot state using only pre-existing User A resources"
    )


def artifact_authorization(
    client: httpx.Client,
    token_a: str,
    token_b: str,
    timeout_seconds: int,
    signed_url_expiry_wait_seconds: int = 65,
) -> dict:
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

    guessed_id = str(uuid.uuid4())
    if guessed_id == artifact_id:
        guessed_id = str(uuid.uuid4())
    for label, token in (("owner guessed artifact", token_a), ("cross-account guessed artifact", token_b)):
        expect(
            client.get(
                f"/api/v1/artifacts/{guessed_id}/download",
                headers=auth(token),
            ),
            404,
            label + " download",
        )
        expect(
            client.get(
                f"/api/v1/artifacts/{guessed_id}/content",
                headers=auth(token),
            ),
            404,
            label + " content",
        )

    route = f"/api/v1/artifacts/{artifact_id}/download"
    content_route = f"/api/v1/artifacts/{artifact_id}/content"
    expect(client.get(route, headers=auth(token_b)), 404, "cross-account artifact download")
    expect(client.get(content_route, headers=auth(token_b)), 404, "cross-account artifact content")

    download = json_object(
        expect(
            client.get(route, headers=auth(token_a)),
            200,
            "owned artifact download",
        ),
        "owned artifact download",
    )
    signed_url = download.get("url")
    if not isinstance(signed_url, str) or not signed_url:
        if download.get("content_path"):
            raise ExerciseFailure(
                "Controlled staging artifact validation requires a private S3 signed URL; "
                "the API returned a local/authenticated content path instead."
            )
        raise ExerciseFailure(
            "Controlled staging artifact validation returned no private signed URL."
        )

    response = httpx.get(signed_url, timeout=20, follow_redirects=False)
    if response.status_code != 200 or not response.content:
        raise ExerciseFailure(
            f"Signed artifact URL returned HTTP {response.status_code} or empty content."
        )

    wait_seconds = max(61, int(signed_url_expiry_wait_seconds))
    time.sleep(wait_seconds)
    expired = httpx.get(signed_url, timeout=20, follow_redirects=False)
    if expired.status_code not in {400, 401, 403, 404}:
        raise ExerciseFailure(
            "Previously valid signed artifact URL remained usable after the controlled "
            f"expiry wait (HTTP {expired.status_code})."
        )

    return passed(
        "owner-scoped S3 artifact authorization passed with guessed-ID denial, "
        "cross-owner download/content denial, non-empty signed download and expired "
        "signed-URL denial; physical artifact deletion remains the separate retention/"
        "deletion staging drill"
    )


def merge_evidence(base: dict, updates: dict) -> dict:
    result = dict(base)
    result.update(updates)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the authenticated Shuddho Coworker staging owner-isolation exercise.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--artifact", action="store_true", help="Run one live synthetic Coworker task and validate artifact authorization/download.")
    parser.add_argument("--personal-agent", action="store_true", help="Exercise PA-10 goal, automation, history and memory owner isolation without starting an Agent run.")
    parser.add_argument("--owned-resource-manifest", type=Path, help="Strict non-secret JSON manifest of pre-existing User A Agent run, notification, action, artifact, connector grant and connector snapshot IDs.")
    parser.add_argument("--artifact-timeout", type=int, default=180)
    parser.add_argument("--artifact-signed-url-expiry-wait", type=int, default=65, help="Seconds to wait before requiring the same S3 signed artifact URL to be rejected; values below 61 are raised to 61.")
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
            if args.personal_agent:
                updates["personal_agent_owner_isolation"] = personal_agent_owner_isolation(
                    client, token_a, token_b
                )
            if args.owned_resource_manifest:
                updates["remaining_owner_isolation"] = remaining_owner_isolation(
                    client,
                    token_a,
                    token_b,
                    owned_resource_manifest(args.owned_resource_manifest),
                )
            if args.artifact:
                updates["storage"] = artifact_authorization(
                    client,
                    token_a,
                    token_b,
                    max(30, args.artifact_timeout),
                    max(61, args.artifact_signed_url_expiry_wait),
                )
    except (httpx.HTTPError, ExerciseFailure) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None

    result = merge_evidence(base, updates)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(args.output), "checks": {key: value["status"] for key, value in updates.items()}}, indent=2))


if __name__ == "__main__":
    main()
