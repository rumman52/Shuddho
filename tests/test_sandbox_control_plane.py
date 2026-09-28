from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from test_coworker import account, container, signed_client

from services.coworker.agent_tools import available_tools
from services.coworker.errors import CoworkerError
from services.coworker.models import SandboxExecution, SandboxSession, utcnow
from services.coworker.sandbox import SandboxRepository
from services.coworker.sandbox_schemas import SandboxExecutionCreate, SandboxSessionCreate


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
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.agent.settings = settings
    container.sandbox = SandboxRepository(container.repository.sessions, settings)
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
