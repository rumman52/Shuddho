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

