from __future__ import annotations

import base64
import hashlib
import os

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from test_coworker import account, container, signed_client

from services.coworker.agent_tools import available_tools
from services.coworker.errors import CoworkerError
from services.coworker.interactive_artifacts import validate_static_preview_html
from services.coworker.models import Artifact, SandboxExecution, SandboxSession, utcnow
from services.coworker.sandbox import SandboxRepository
from services.coworker.sandbox_schemas import SandboxExecutionCreate, SandboxSessionCreate
from scripts.sandbox_worker import (
    WorkerError,
    build_bwrap_command,
    read_artifact_file,
    validate_claim_policy,
)


def enable_sandbox(container):
    settings = replace(
        container.settings,
        artifact_services_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_runtime_v3_enabled=True,
        code_execution_enabled=True,
        max_active_sandbox_sessions=2,
        sandbox_session_ttl_seconds=300,
        sandbox_max_source_bytes=20000,
        sandbox_max_executions_per_session=4,
        sandbox_wall_seconds=30,
        sandbox_cpu_seconds=10,
        sandbox_memory_mb=256,
        sandbox_disk_mb=64,
        sandbox_max_output_bytes=65536,
        sandbox_worker_lease_seconds=30,
        sandbox_execution_max_attempts=2,
        sandbox_worker_token="test-sandbox-worker-token-0123456789abcdef",
        sandbox_artifact_max_bytes=65536,
        sandbox_artifact_ttl_seconds=3600,
        sandbox_preview_url_ttl_seconds=60,
        sandbox_preview_origin="https://sandbox-preview.example.test",
        sandbox_preview_secret="test-sandbox-preview-secret-0123456789abcdef",
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.agent.settings = settings
    container.sandbox = SandboxRepository(
        container.repository.sessions,
        settings,
        container.storage,
    )
    return settings


def create_session(container, owner, key=None):
    return container.sandbox.create(
        owner,
        SandboxSessionCreate(purpose="code_task", runtime="python311"),
        key or "sandbox-" + str(uuid4()),
    )[0]


def create_interactive_session(container, owner, key=None):
    return container.sandbox.create(
        owner,
        SandboxSessionCreate(purpose="interactive_artifact", runtime="python311"),
        key or "sandbox-interactive-" + str(uuid4()),
    )[0]


def completion_observation(html: bytes | None = None):
    artifact = None
    if html is not None:
        artifact = {
            "kind": "interactive_html",
            "body_b64": base64.b64encode(html).decode("ascii"),
            "sha256": hashlib.sha256(html).hexdigest(),
            "byte_size": len(html),
        }
    return {
        "policy_version": "sandbox-control-v1",
        "executor_contract": "bwrap-python311-v1",
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "elapsed_ms": 12,
        "sandbox_destroyed": True,
        "network_isolated": True,
        "filesystem_isolated": True,
        "environment_sanitized": True,
        "artifact": artifact,
    }


def test_sandbox_flag_requires_runtime_v3_and_artifact_services(container):
    with pytest.raises(ValueError, match="Agent Runtime v3"):
        replace(container.settings, code_execution_enabled=True).validate()

    with pytest.raises(ValueError, match="ARTIFACT_SERVICES"):
        replace(
            container.settings,
            agent_runtime_enabled=True,
            intelligent_planner_enabled=True,
            agent_runtime_v3_enabled=True,
            code_execution_enabled=True,
        ).validate()


def test_sandbox_session_is_idempotent_owner_scoped_and_fail_closed(container):
    enable_sandbox(container)
    alice = account(container)
    bob = account(container, "sandbox-bob")
    request = SandboxSessionCreate(purpose="data_analysis", runtime="python311")
    first, created = container.sandbox.create(alice, request, "sandbox-once")
    replay, replayed = container.sandbox.create(alice, request, "sandbox-once")
    assert created is True
    assert replayed is False
    assert first["id"] == replay["id"]
    assert first["policy"]["network"] == "none"
    assert first["policy"]["dependencies"] == []
    assert first["policy"]["mounts"] == []
    assert first["policy"]["host_filesystem"] is False
    assert first["policy"]["production_secrets"] is False
    assert first["policy"]["connector_credentials"] is False
    assert first["policy"]["privileged_api_bridge"] is False
    assert first["execution"]["executor_attached"] is False
    assert first["execution"]["code_executed"] is False
    assert first["execution"]["source_trust"] == "untrusted"

    with pytest.raises(CoworkerError) as conflict:
        container.sandbox.create(
            alice,
            SandboxSessionCreate(purpose="interactive_artifact", runtime="python311"),
            "sandbox-once",
        )
    assert conflict.value.code == "idempotency_conflict"

    with pytest.raises(CoworkerError) as cross_owner:
        container.sandbox.get(bob, first["id"])
    assert cross_owner.value.status_code == 404


def test_sandbox_prepares_untrusted_source_without_executing_or_echoing_it(container):
    settings = enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner)
    source = "print('never execute in API')\n"
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(source=source),
    )
    assert prepared["state"] == "prepared"
    assert prepared["source_bytes"] == len(source.encode("utf-8"))
    assert prepared["executor_attached"] is False
    assert prepared["code_executed"] is False
    assert prepared["policy"]["network"] == "none"
    assert "source" not in prepared

    history = container.sandbox.list_executions(owner, session["id"])
    assert len(history) == 1
    assert "source" not in history[0]

    with container.repository.sessions() as db:
        stored = db.get(SandboxExecution, prepared["id"])
        assert stored.request_spec["source"] == source
        assert stored.request_spec["source_trust"] == "untrusted"

    tool_names = {item["name"] for item in available_tools(settings)}
    assert all(not name.startswith("sandbox.") for name in tool_names)


def test_sandbox_cancel_and_expiry_scrub_unexecuted_source(container):
    enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner)
    prepared = container.sandbox.prepare_execution(
        owner, session["id"], SandboxExecutionCreate(source="print('sensitive input')")
    )
    cancelled = container.sandbox.cancel(owner, session["id"])
    assert cancelled["state"] == "cancelled"
    assert cancelled["cleanup_state"] == "not_required"
    with container.repository.sessions() as db:
        stored = db.get(SandboxExecution, prepared["id"])
        assert stored.state == "cancelled"
        assert stored.request_spec == {"source_scrubbed": True}

    expiring = create_session(container, owner, "sandbox-expiring")
    pending = container.sandbox.prepare_execution(
        owner, expiring["id"], SandboxExecutionCreate(source="print('expire me')")
    )
    with container.repository.sessions.begin() as db:
        row = db.get(SandboxSession, expiring["id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
    current = container.sandbox.get(owner, expiring["id"])
    assert current["state"] == "expired"
    with container.repository.sessions() as db:
        stored = db.get(SandboxExecution, pending["id"])
        assert stored.state == "failed"
        assert stored.error_code == "session_expired"
        assert stored.request_spec == {"source_scrubbed": True}


def test_sandbox_api_is_owner_scoped_and_reports_control_plane_only(container, signed_client):
    enable_sandbox(container)
    client, headers = signed_client
    created = client.post(
        "/api/v1/sandbox-sessions",
        headers=headers() | {"Idempotency-Key": "sandbox-api-one"},
        json={"purpose": "code_task", "runtime": "python311"},
    )
    assert created.status_code == 201
    value = created.json()
    assert value["execution"]["executor_attached"] is False
    assert value["execution"]["code_executed"] is False
    assert value["policy"]["network"] == "none"

    assert client.get(
        f'/api/v1/sandbox-sessions/{value["id"]}',
        headers=headers("bob"),
    ).status_code == 404

    prepared = client.post(
        f'/api/v1/sandbox-sessions/{value["id"]}/executions',
        headers=headers(),
        json={"source": "print(1 + 1)"},
    )
    assert prepared.status_code == 202
    assert prepared.json()["state"] == "prepared"
    assert prepared.json()["code_executed"] is False


def test_sandbox_worker_claim_completion_and_api_auth(container, signed_client):
    settings = enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner, "sandbox-worker-success")
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(source="print('ok')\n"),
    )

    claimed = container.sandbox.claim_executions("sandbox-worker-a")
    assert [item["id"] for item in claimed] == [prepared["id"]]
    assert claimed[0]["source"] == "print('ok')\n"
    assert claimed[0]["policy"]["network"] == "none"
    assert claimed[0]["policy"]["executor"] == {
        "contract": "bwrap-python311-v1",
        "network_namespace": "private_empty",
        "filesystem": "minimal_readonly_runtime",
        "environment": "cleared",
        "packages": "stdlib_only",
    }
    assert claimed[0]["policy"]["resource_limits"]["output_bytes"] == 65536

    control = container.sandbox.worker_control("sandbox-worker-a", prepared["id"])
    assert control["action"] == "continue"

    completed = container.sandbox.complete_execution(
        "sandbox-worker-a",
        prepared["id"],
        {
            "policy_version": "sandbox-control-v1",
            "executor_contract": "bwrap-python311-v1",
            "exit_code": 0,
            "stdout": "ok\n",
            "stderr": "",
            "elapsed_ms": 12,
            "sandbox_destroyed": True,
            "network_isolated": True,
            "filesystem_isolated": True,
            "environment_sanitized": True,
        },
    )
    assert completed["state"] == "succeeded"
    assert completed["result"]["stdout"] == "ok\n"
    assert completed["result"]["output_trust"] == "untrusted"
    assert completed["result"]["sandbox_destroyed"] is True

    with container.repository.sessions() as db:
        stored = db.get(SandboxExecution, prepared["id"])
        assert stored.request_spec == {"source_scrubbed": True}
        assert stored.claimed_by is None
        assert stored.lease_until is None

    client, headers = signed_client
    denied = client.post(
        "/api/v1/internal/sandbox-worker/claim",
        json={"worker_id": "sandbox-worker-api", "limit": 1},
    )
    assert denied.status_code == 403

    worker_headers = {"X-Shuddho-Sandbox-Worker-Token": settings.sandbox_worker_token}
    allowed = client.post(
        "/api/v1/internal/sandbox-worker/claim",
        headers=worker_headers,
        json={"worker_id": "sandbox-worker-api", "limit": 1},
    )
    assert allowed.status_code == 200


def test_sandbox_worker_lease_recovery_is_bounded(container):
    settings = enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner, "sandbox-worker-recovery")
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(source="print('retry-safe')"),
    )
    first = container.sandbox.claim_executions("sandbox-worker-a")
    assert first[0]["attempt"] == 1

    with container.repository.sessions.begin() as db:
        row = db.get(SandboxExecution, prepared["id"])
        row.lease_until = utcnow() - timedelta(seconds=1)

    second = container.sandbox.claim_executions("sandbox-worker-b")
    assert second[0]["id"] == prepared["id"]
    assert second[0]["attempt"] == 2

    with pytest.raises(CoworkerError) as stale:
        container.sandbox.worker_control("sandbox-worker-a", prepared["id"])
    assert stale.value.code == "sandbox_worker_claim_invalid"

    with container.repository.sessions.begin() as db:
        row = db.get(SandboxExecution, prepared["id"])
        row.lease_until = utcnow() - timedelta(seconds=1)

    assert container.sandbox.claim_executions("sandbox-worker-c") == []
    with container.repository.sessions() as db:
        row = db.get(SandboxExecution, prepared["id"])
        assert row.state == "failed"
        assert row.error_code == "sandbox_worker_lost"
        assert row.request_spec == {"source_scrubbed": True}


def test_sandbox_worker_command_is_networkless_minimal_and_fail_closed(tmp_path):
    policy = {
        "version": "sandbox-control-v1",
        "network": "none",
        "dependencies": [],
        "mounts": [],
        "host_filesystem": False,
        "docker_socket": False,
        "production_secrets": False,
        "connector_credentials": False,
        "privileged_api_bridge": False,
        "resource_limits": {
            "wall_seconds": 30,
            "cpu_seconds": 10,
            "memory_mb": 256,
            "disk_mb": 64,
            "output_bytes": 65536,
        },
        "artifacts": {
            "interactive_html": {
                "path": "/tmp/shuddho-preview.html",
                "content_type": "text/html; charset=utf-8",
                "max_bytes": 65536,
            },
        },
        "executor": {
            "contract": "bwrap-python311-v1",
            "network_namespace": "private_empty",
            "filesystem": "minimal_readonly_runtime",
            "environment": "cleared",
            "packages": "stdlib_only",
        },
    }
    source = tmp_path / "main.py"
    source.write_text("print('isolated')\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    command = build_bwrap_command(
        source,
        scratch,
        policy,
        bwrap_path="/usr/bin/bwrap",
        python_executable="/usr/local/bin/python",
    )
    assert "--unshare-net" in command
    assert "--clearenv" in command
    assert "--cap-drop" in command
    assert "/work/main.py" in command
    assert str(scratch.resolve()) in command
    assert "/usr/bin" not in command
    assert "-I" in command
    assert "-S" in command
    assert str(source.resolve()) in command
    assert "/app" not in command
    assert "isolated" not in repr(command)

    unsafe = dict(policy)
    unsafe["network"] = "open"
    with pytest.raises(WorkerError) as rejected:
        validate_claim_policy({"policy": unsafe})
    assert rejected.value.code == "sandbox_policy_invalid"


def test_sandbox_worker_failure_is_terminal_and_scrubs_source(container):
    enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner, "sandbox-worker-failure")
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(source="raise RuntimeError('boom')"),
    )
    container.sandbox.claim_executions("sandbox-worker-failure")
    failed = container.sandbox.fail_execution(
        "sandbox-worker-failure",
        prepared["id"],
        "sandbox_execution_failed",
        True,
    )
    assert failed["state"] == "failed"
    assert failed["error_code"] == "sandbox_execution_failed"
    assert failed["result"]["sandbox_destroyed"] is True
    assert failed["result"]["output_trust"] == "untrusted"
    with container.repository.sessions() as db:
        stored = db.get(SandboxExecution, prepared["id"])
        assert stored.request_spec == {"source_scrubbed": True}
        assert stored.claimed_by is None
        assert stored.lease_until is None


def test_sandbox_completion_rejects_missing_isolation_evidence(container):
    enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner, "sandbox-isolation-proof")
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(source="print(1)"),
    )
    container.sandbox.claim_executions("sandbox-worker-proof")
    with pytest.raises(CoworkerError) as invalid:
        container.sandbox.complete_execution(
            "sandbox-worker-proof",
            prepared["id"],
            {
                "policy_version": "sandbox-control-v1",
                "executor_contract": "bwrap-python311-v1",
                "exit_code": 0,
                "stdout": "1\n",
                "stderr": "",
                "elapsed_ms": 5,
                "sandbox_destroyed": True,
                "network_isolated": False,
                "filesystem_isolated": True,
                "environment_sanitized": True,
            },
        )
    assert invalid.value.code == "sandbox_isolation_evidence_invalid"




def test_interactive_artifact_is_owner_scoped_private_and_previewed_without_credentials(
    container,
    signed_client,
):
    settings = enable_sandbox(container)
    owner = account(container)
    bob = account(container, "sandbox-preview-bob")
    session = create_interactive_session(container, owner, "sandbox-preview-success")
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(
            source=(
                "from pathlib import Path\n"
                "Path('/tmp/shuddho-preview.html').write_text('<html></html>')\n"
            )
        ),
    )
    claimed = container.sandbox.claim_executions("sandbox-preview-worker")
    assert claimed[0]["purpose"] == "interactive_artifact"
    assert claimed[0]["policy"]["artifacts"]["interactive_html"]["path"] == "/tmp/shuddho-preview.html"

    html = (
        b"<!doctype html><html><head><title>Private chart</title>"
        b"<style>body{font-family:sans-serif} .bar{width:40%}</style></head>"
        b"<body><main><h1>Private chart</h1><div class=\"bar\">40%</div>"
        b"<details><summary>Details</summary><p>Owned data</p></details></main></body></html>"
    )
    completed = container.sandbox.complete_execution(
        "sandbox-preview-worker",
        prepared["id"],
        completion_observation(html),
    )
    manifest = completed["result"]["artifact"]
    assert manifest["artifact_class"] == "sandbox_interactive"
    assert manifest["preview_available"] is True
    assert manifest["content_type"] == "text/html; charset=utf-8"
    assert manifest["sha256"] == hashlib.sha256(html).hexdigest()

    # Interactive HTML is intentionally excluded from the existing approved
    # email/document-sharing artifact chooser.
    assert all(
        item["id"] != manifest["id"]
        for item in container.repository.list_artifacts(owner)
    )
    with pytest.raises(CoworkerError) as cross_owner:
        container.sandbox.preview_url(bob, manifest["id"])
    assert cross_owner.value.status_code == 404

    preview = container.sandbox.preview_url(owner, manifest["id"])
    assert preview["url"].startswith(settings.sandbox_preview_origin + "/sandbox-preview/")
    assert preview["sandbox"] == {
        "scripts": False,
        "network": False,
        "forms": False,
        "privileged_api_bridge": False,
        "workspace_credentials": False,
    }
    token = preview["url"].split("token=", 1)[1]

    client, headers = signed_client
    issued = client.get(
        f'/api/v1/sandbox-artifacts/{manifest["id"]}/preview-url',
        headers=headers(),
    )
    assert issued.status_code == 200
    denied_owner = client.get(
        f'/api/v1/sandbox-artifacts/{manifest["id"]}/preview-url',
        headers=headers("sandbox-preview-bob"),
    )
    assert denied_owner.status_code == 404

    isolated_headers = {"Host": "sandbox-preview.example.test"}
    rendered = client.get(
        f'/sandbox-preview/{manifest["id"]}?token={token}',
        headers=isolated_headers,
    )
    assert rendered.status_code == 200
    assert rendered.content == html
    assert rendered.headers["cache-control"] == "no-store, max-age=0"
    assert rendered.headers["x-content-type-options"] == "nosniff"
    csp = rendered.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "script-src 'none'" in csp
    assert "connect-src 'none'" in csp
    assert "form-action 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert rendered.headers["cross-origin-opener-policy"] == "same-origin"
    assert rendered.headers["referrer-policy"] == "no-referrer"

    wrong_origin = client.get(
        f'/sandbox-preview/{manifest["id"]}?token={token}',
        headers={"Host": "shuddho-web-editor.vercel.app"},
    )
    assert wrong_origin.status_code == 404
    cookie_leak = client.get(
        f'/sandbox-preview/{manifest["id"]}?token={token}',
        headers=isolated_headers | {"Cookie": "session=must-not-cross"},
    )
    assert cookie_leak.status_code == 400
    auth_leak = client.get(
        f'/sandbox-preview/{manifest["id"]}?token={token}',
        headers=isolated_headers | {"Authorization": "Basic must-not-cross"},
    )
    assert auth_leak.status_code == 400


@pytest.mark.parametrize(
    "html",
    [
        b"<html><body><script>alert(1)</script></body></html>",
        b"<html><body><img src=\"https://evil.example/x\"></body></html>",
        b"<html><head><style>@import 'https://evil.example/x.css';</style></head><body></body></html>",
        b"<html><body onclick=\"fetch('https://evil.example')\">x</body></html>",
        b"<html><body><form action=\"https://evil.example\"></form></body></html>",
        b"<html><body><iframe src=\"https://evil.example\"></iframe></body></html>",
        b"<?xml version=\"1.0\"?><html><body>x</body></html>",
    ],
)
def test_interactive_html_rejects_active_or_network_capable_markup(html):
    with pytest.raises(CoworkerError) as unsafe:
        validate_static_preview_html(html, 65536)
    assert unsafe.value.code == "sandbox_artifact_unsafe"


def test_interactive_completion_requires_safe_exact_artifact(container):
    enable_sandbox(container)
    owner = account(container)
    session = create_interactive_session(container, owner, "sandbox-preview-unsafe")
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(source="print('preview')"),
    )
    container.sandbox.claim_executions("sandbox-preview-unsafe-worker")
    html = b"<html><body><script>alert(document.cookie)</script></body></html>"
    with pytest.raises(CoworkerError) as unsafe:
        container.sandbox.complete_execution(
            "sandbox-preview-unsafe-worker",
            prepared["id"],
            completion_observation(html),
        )
    assert unsafe.value.code == "sandbox_artifact_unsafe"
    with container.repository.sessions() as db:
        assert db.scalar(
            __import__("sqlalchemy").select(Artifact).where(
                Artifact.sandbox_execution_id == prepared["id"]
            )
        ) is None
    container.sandbox.fail_execution(
        "sandbox-preview-unsafe-worker",
        prepared["id"],
        "sandbox_artifact_unsafe",
        True,
    )


def test_worker_artifact_reader_rejects_symlink_and_accepts_regular_file(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    outside = tmp_path / "outside-secret"
    outside.write_bytes(b"host secret")
    symlink = scratch / "shuddho-preview.html"
    symlink.symlink_to(outside)
    with pytest.raises(WorkerError) as unsafe:
        read_artifact_file(symlink, 65536)
    assert unsafe.value.code == "sandbox_artifact_invalid"

    symlink.unlink()
    regular = b"<html><body><p>safe</p></body></html>"
    symlink.write_bytes(regular)
    assert read_artifact_file(symlink, 65536) == regular


def test_expired_sandbox_artifact_is_purged_and_storage_accounting_released(container):
    enable_sandbox(container)
    owner = account(container)
    session = create_interactive_session(container, owner, "sandbox-preview-expiry")
    prepared = container.sandbox.prepare_execution(
        owner,
        session["id"],
        SandboxExecutionCreate(source="print('preview')"),
    )
    container.sandbox.claim_executions("sandbox-preview-expiry-worker")
    html = b"<html><body><p>expires</p></body></html>"
    completed = container.sandbox.complete_execution(
        "sandbox-preview-expiry-worker",
        prepared["id"],
        completion_observation(html),
    )
    artifact_id = completed["result"]["artifact"]["id"]
    with container.repository.sessions.begin() as db:
        row = db.get(Artifact, artifact_id)
        object_key = row.object_key
        row.expires_at = utcnow() - timedelta(seconds=1)
    assert container.storage.get(object_key, 65536) == html

    result = container.retention.cleanup_expired_sandbox_artifacts()
    assert result == {"deleted": 1, "failed": []}
    with container.repository.sessions() as db:
        assert db.get(Artifact, artifact_id) is None
    with pytest.raises(FileNotFoundError):
        container.storage.get(object_key, 65536)


def test_sandbox_preview_configuration_fails_closed(container):
    base = replace(
        container.settings,
        artifact_services_enabled=True,
        agent_runtime_enabled=True,
        intelligent_planner_enabled=True,
        agent_runtime_v3_enabled=True,
        code_execution_enabled=True,
        sandbox_worker_token="test-sandbox-worker-token-0123456789abcdef",
        sandbox_preview_secret="test-sandbox-preview-secret-0123456789abcdef",
        sandbox_preview_origin="https://sandbox-preview.example.test",
    )
    base.validate()
    with pytest.raises(ValueError, match="PREVIEW_ORIGIN"):
        replace(base, sandbox_preview_origin="https://sandbox-preview.example.test/path").validate()
    with pytest.raises(ValueError, match="PREVIEW_SECRET"):
        replace(base, sandbox_preview_secret="short").validate()
