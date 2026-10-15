from __future__ import annotations

import asyncio
import base64
import hashlib
import os

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import select

from test_coworker import account, container, signed_client

from services.coworker.agent_planner import exact_user_python_source, intelligent_tool_names
from services.coworker.agent_runtime import AgentRuntime
from services.coworker.agent_schemas import AgentRunCreate, AgentV3Decision
from services.coworker.agent_tools import available_tools
from services.coworker.errors import CoworkerError
from services.coworker.interactive_artifacts import (
    create_preview_token,
    validate_static_preview_html,
    verify_preview_token,
)
from services.coworker.models import Artifact, SandboxExecution, SandboxSession, ToolInvocation, ToolReceipt, utcnow
from services.coworker.sandbox import SandboxRepository
from services.coworker.sandbox_schemas import SandboxExecutionCreate, SandboxSessionCreate
from scripts import sandbox_worker as sandbox_worker_module
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



def test_planner_sandbox_gate_is_separate_and_exact_user_source_only(container):
    base = enable_sandbox(container)
    assert "sandbox.execute_python" not in {
        item["name"] for item in available_tools(base)
    }
    with pytest.raises(ValueError, match="CODE_EXECUTION"):
        replace(
            container.settings,
            code_execution_enabled=False,
            agent_sandbox_tool_enabled=True,
        ).validate()

    settings = replace(base, agent_sandbox_tool_enabled=True)
    settings.validate()
    source = "values = [1, 2, 3]\nprint(sum(values))"
    goal = "Run only my code and report the result.\n\n```python\n" + source + "\n```"
    assert exact_user_python_source(goal, settings) == source
    assert "sandbox.execute_python" in intelligent_tool_names(
        settings, goal=goal, runtime_version=3
    )
    assert "sandbox.execute_python" not in intelligent_tool_names(
        settings, goal=goal, runtime_version=2
    )
    assert "sandbox.execute_python" not in intelligent_tool_names(
        settings,
        goal=goal + "\n\n```python\nprint('second')\n```",
        runtime_version=3,
    )


def test_runtime_v3_sandbox_tool_executes_only_user_supplied_python(container):
    base = enable_sandbox(container)
    settings = replace(base, agent_sandbox_tool_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.agent.settings = settings
    container.sandbox.settings = settings

    owner = account(container)
    source = "value = 20 + 22\nprint(value)"
    goal = "Execute this exact Python and report its output.\n\n```python\n" + source + "\n```"
    run, _ = container.agent.create(
        owner,
        AgentRunCreate(goal=goal, output_language="en"),
        "agent-sandbox-exact-user-source",
    )
    assert run["runtime_version"] == 3

    class Planner:
        def __init__(self):
            self.calls = 0
            self.tools = []

        async def decide(self, _goal, tools, observations, *, remaining_budget, dependencies):
            self.calls += 1
            self.tools.append(list(tools))
            if self.calls == 1:
                return AgentV3Decision(
                    decision="next_step",
                    tool="sandbox.execute_python",
                    objective="print('MODEL MUST NOT BECOME EXECUTABLE SOURCE')",
                ), 25, 1, {
                    "model": "synthetic-v3",
                    "prompt_sha256": "a" * 64,
                    "tool_schema_sha256": "b" * 64,
                }
            assert observations[0]["tool"] == "sandbox.execute_python"
            assert observations[0]["summary"]["stdout_excerpt"] == "42\n"
            assert observations[0]["summary"]["output_trust"] == "untrusted"
            return AgentV3Decision(decision="complete"), 25, 1, {
                "model": "synthetic-v3",
                "prompt_sha256": "c" * 64,
                "tool_schema_sha256": "d" * 64,
            }

    planner = Planner()
    runtime = AgentRuntime(container, None, planner=planner)
    decision = asyncio.run(runtime.decide_v3(run["id"]))
    assert decision == {"decision": "next_step", "ordinal": 1}
    assert "sandbox.execute_python" in planner.tools[0]

    invocation = container.agent.invocation_for_step(run["id"], 1)
    assert invocation["arguments"] == {"source": source}

    first = asyncio.run(runtime.execute_step(run["id"], 1))
    assert first["status"] == "executing"
    claimed = container.sandbox.claim_executions("agent-sandbox-worker")
    assert len(claimed) == 1
    assert claimed[0]["source"] == source
    assert "MODEL MUST NOT BECOME EXECUTABLE SOURCE" not in claimed[0]["source"]

    completed = container.sandbox.complete_execution(
        "agent-sandbox-worker",
        claimed[0]["id"],
        {
            "policy_version": "sandbox-control-v1",
            "executor_contract": "bwrap-python311-v1",
            "exit_code": 0,
            "stdout": "42\n",
            "stderr": "",
            "elapsed_ms": 5,
            "sandbox_destroyed": True,
            "network_isolated": True,
            "filesystem_isolated": True,
            "environment_sanitized": True,
        },
    )
    assert completed["state"] == "succeeded"
    assert asyncio.run(runtime.execute_step(run["id"], 1)) == {"status": "completed"}
    assert asyncio.run(runtime.decide_v3(run["id"])) == {"decision": "complete"}

    saved = container.agent.get(owner, run["id"])
    receipt = saved["tool_invocations"][0]["receipt"]
    assert receipt["resource_type"] == "sandbox_execution"
    assert receipt["summary"]["stdout_excerpt"] == "42\n"
    assert receipt["summary"]["sandbox_destroyed"] is True



@pytest.mark.parametrize("worker_already_completed", [False, True])
def test_agent_sandbox_resume_refuses_source_substitution(container, worker_already_completed):
    """A replay cannot attach a different program to the original result."""
    base = enable_sandbox(container)
    enabled = replace(base, agent_sandbox_tool_enabled=True)
    enabled.validate()
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    container.sandbox.settings = enabled

    owner = account(container)
    original = "print(101)"
    replacement = "print(999)"  # Same UTF-8 size; digest must still bind.
    goal = "Execute my exact source.\n\n```python\n" + original + "\n```"
    run, _ = container.agent.create(
        owner,
        AgentRunCreate(goal=goal, output_language="en"),
        "sandbox-resume-substitution-" + str(worker_already_completed),
    )
    ordinal = container.agent.append_v3_step(
        owner, run["id"], "sandbox.execute_python", "Run exact user code",
    )
    runtime = AgentRuntime(container, None)
    assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "executing"}
    original_execution = container.sandbox.list_executions(
        owner, container.agent.step_resource(run["id"], ordinal)["resource_id"],
    )[0]
    assert original_execution["source_sha256"] == hashlib.sha256(original.encode("utf-8")).hexdigest()
    if worker_already_completed:
        claimed = container.sandbox.claim_executions("sandbox-source-replay")[0]
        assert claimed["source"] == original
        completed = container.sandbox.complete_execution(
            "sandbox-source-replay", claimed["id"], completion_observation(),
        )
        assert completed["state"] == "succeeded"

    # Simulate an incompatible restored invocation (or corrupt replay) after
    # the original exact source was durably queued/possibly completed.
    with container.repository.sessions.begin() as db:
        invocation = db.scalar(select(ToolInvocation).where(
            ToolInvocation.run_id == run["id"],
            ToolInvocation.owner_id == owner,
        ))
        assert invocation is not None
        invocation.arguments = {"source": replacement}

    with pytest.raises(CoworkerError) as error:
        asyncio.run(runtime.execute_step(run["id"], ordinal))
    assert error.value.code == "sandbox_source_binding_mismatch"
    assert error.value.status_code == 409
    if worker_already_completed:
        # Bypass the earlier AgentRuntime poll to prove final ToolReceipt
        # enforcement independently checks the same exact source under DB lock.
        with pytest.raises(CoworkerError) as settlement:
            container.agent.finish_invocation(
                run["id"], ordinal, "sandbox_execution", completed["id"],
                {
                    "sandbox_state": "succeeded",
                    "sandbox_destroyed": True,
                    "stdout_sha256": completed["result"]["stdout_sha256"],
                    "stderr_sha256": completed["result"]["stderr_sha256"],
                },
            )
        assert settlement.value.code == "sandbox_source_binding_mismatch"
        assert settlement.value.status_code == 409
    assert [x["id"] for x in container.sandbox.list_executions(
        owner, container.agent.step_resource(run["id"], ordinal)["resource_id"],
    )] == [original_execution["id"]]
    with container.repository.sessions() as db:
        assert db.get(ToolReceipt, invocation.id) is None


def test_agent_sandbox_receipt_rejects_forged_stdout_and_preserves_verified_result(container):
    base = enable_sandbox(container)
    enabled = replace(base, agent_sandbox_tool_enabled=True)
    enabled.validate()
    container.settings = enabled
    container.repository.settings = enabled
    container.agent.settings = enabled
    container.sandbox.settings = enabled

    owner = account(container)
    source = "print(8)"
    run, _ = container.agent.create(
        owner,
        AgentRunCreate(goal="Execute my exact Python.\n\n```python\n" + source + "\n```"),
        "sandbox-forged-receipt",
    )
    ordinal = container.agent.append_v3_step(
        owner, run["id"], "sandbox.execute_python", "Run exact code",
    )
    runtime = AgentRuntime(container, None)
    assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "executing"}
    claimed = container.sandbox.claim_executions("sandbox-forged-receipt-worker")[0]
    completed = container.sandbox.complete_execution(
        "sandbox-forged-receipt-worker", claimed["id"], {
            **completion_observation(),
            "stdout": "8\n",
        },
    )
    assert completed["state"] == "succeeded"
    result = completed["result"]
    with pytest.raises(CoworkerError) as failure:
        container.agent.finish_invocation(
            run["id"], ordinal, "sandbox_execution", completed["id"], {
                "sandbox_state": "succeeded",
                "exit_code": 0,
                "sandbox_destroyed": True,
                "stdout_sha256": result["stdout_sha256"],
                "stderr_sha256": result["stderr_sha256"],
                "stdout_excerpt": "FAKE RESULT",  # Digest alone is not enough.
                "stderr_excerpt": "",
                "output_trust": "untrusted",
                "artifact_id": None,
                "artifact_sha256": None,
            },
        )
    assert failure.value.code == "sandbox_receipt_unverified"
    with container.repository.sessions() as db:
        invocation = db.scalar(select(ToolInvocation).where(ToolInvocation.run_id == run["id"]))
        assert db.get(ToolReceipt, invocation.id) is None

    # The actual verified worker output is eligible on the same execution;
    # rejecting a forged receipt must not poison an otherwise valid replay.
    assert asyncio.run(runtime.execute_step(run["id"], ordinal)) == {"status": "completed"}
    observed = container.agent.verified_observations(owner, run["id"])
    assert observed[0]["summary"]["stdout_excerpt"] == "8\n"


def test_agent_cancel_scrubs_prepared_planner_sandbox_source(container, signed_client):
    base = enable_sandbox(container)
    settings = replace(base, agent_sandbox_tool_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.agent.settings = settings
    container.sandbox.settings = settings

    owner = account(container)
    source = "print('cancel me')"
    goal = "Execute this exact code.\n\n```python\n" + source + "\n```"
    run, _ = container.agent.create(
        owner,
        AgentRunCreate(goal=goal, output_language="en"),
        "agent-sandbox-cancel",
    )

    class Planner:
        async def decide(self, *_args, **_kwargs):
            return AgentV3Decision(
                decision="next_step",
                tool="sandbox.execute_python",
                objective="Execute the user-provided code.",
            ), 10, 1, {
                "model": "synthetic-v3",
                "prompt_sha256": "e" * 64,
                "tool_schema_sha256": "f" * 64,
            }

    runtime = AgentRuntime(container, None, planner=Planner())
    assert asyncio.run(runtime.decide_v3(run["id"])) == {
        "decision": "next_step",
        "ordinal": 1,
    }
    assert asyncio.run(runtime.execute_step(run["id"], 1))["status"] == "executing"
    resource = container.agent.step_resource(run["id"], 1)
    assert resource["resource_type"] == "sandbox_session"
    executions = container.sandbox.list_executions(owner, resource["resource_id"])
    assert executions[0]["state"] == "prepared"

    # Roll back both execution authorities before cancellation. Cleanup must
    # still scrub the already-stored user source.
    rolled_back = replace(
        settings,
        code_execution_enabled=False,
        agent_sandbox_tool_enabled=False,
    )
    rolled_back.validate()
    container.settings = rolled_back
    container.repository.settings = rolled_back
    container.agent.settings = rolled_back
    container.sandbox.settings = rolled_back

    client, headers = signed_client
    response = client.post(
        f'/api/v1/agent-runs/{run["id"]}/cancel',
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"
    with container.repository.sessions() as db:
        session = db.get(SandboxSession, resource["resource_id"])
        stored = db.get(SandboxExecution, executions[0]["id"])
        assert session.state == "cancelled"
        assert stored.state == "cancelled"
        assert stored.request_spec == {"source_scrubbed": True}


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


@pytest.mark.parametrize("tamper_kind", [
    "same_length_source", "source_missing", "wrong_byte_count",
    "wrong_trust_label", "wrong_policy_version", "bad_utf8",
    "session_policy_drift", "session_identity_drift",
])
@pytest.mark.parametrize("recovery_claim", [False, True])
def test_sandbox_worker_claim_fails_closed_on_changed_persisted_source(
    container, tamper_kind, recovery_claim,
):
    """No new worker receives bytes that differ from the prepared source."""
    enable_sandbox(container)
    owner = account(container)
    session = create_session(
        container, owner, f"sandbox-claim-integrity-{tamper_kind}-{recovery_claim}",
    )
    source = "print(101)"
    prepared = container.sandbox.prepare_execution(
        owner, session["id"], SandboxExecutionCreate(source=source),
    )
    if recovery_claim:
        first = container.sandbox.claim_executions("sandbox-before-tamper")
        assert len(first) == 1 and first[0]["source"] == source
    with container.repository.sessions.begin() as db:
        execution = db.get(SandboxExecution, prepared["id"])
        spec = dict(execution.request_spec)
        if tamper_kind == "same_length_source":
            spec["source"] = "print(999)"
            assert len(spec["source"].encode("utf-8")) == len(source.encode("utf-8"))
        elif tamper_kind == "source_missing":
            spec.pop("source")
        elif tamper_kind == "wrong_byte_count":
            execution.source_bytes += 1
        elif tamper_kind == "wrong_trust_label":
            spec["source_trust"] = "reviewed_by_model"
        elif tamper_kind == "wrong_policy_version":
            spec["policy_version"] = "replaced-policy"
        elif tamper_kind == "bad_utf8":
            spec["source"] = "\ud800"
        elif tamper_kind == "session_policy_drift":
            live_session = db.get(SandboxSession, session["id"])
            changed_policy = dict(live_session.execution_policy)
            changed_policy["network"] = "open"
            live_session.execution_policy = changed_policy
        elif tamper_kind == "session_identity_drift":
            live_session = db.get(SandboxSession, session["id"])
            live_session.purpose = "interactive_artifact"
        execution.request_spec = spec
        if recovery_claim:
            execution.lease_until = utcnow() - timedelta(seconds=1)

    assert container.sandbox.claim_executions("sandbox-after-tamper") == []
    assert container.sandbox.claim_executions("sandbox-later") == []
    with container.repository.sessions() as db:
        execution = db.get(SandboxExecution, prepared["id"])
        owned_session = db.get(SandboxSession, session["id"])
        assert execution.state == "failed"
        assert execution.error_code == "sandbox_source_integrity_failed"
        assert execution.request_spec == {"source_scrubbed": True}
        assert execution.claimed_by is None
        assert execution.lease_until is None
        assert owned_session.state == "failed"
        assert owned_session.cleanup_state == ("required" if recovery_claim else "not_required")
    if recovery_claim:
        # A terminal session now sends an explicit stop signal to a prior
        # worker.  That is fail-closed even though the old worker no longer
        # owns a live lease; raising a 409 is reserved for an invalid claim
        # on an otherwise active session.
        stopped = container.sandbox.worker_control(
            "sandbox-before-tamper", prepared["id"],
        )
        assert stopped == {"action": "stop", "reason": "session_closed"}

        # A worker ignoring the stop signal must still be unable to publish
        # an apparently successful result or restore the scrubbed source.
        with pytest.raises(CoworkerError) as stale:
            container.sandbox.complete_execution(
                "sandbox-before-tamper",
                prepared["id"],
                {
                    "policy_version": "sandbox-control-v1",
                    "executor_contract": "bwrap-python311-v1",
                    "exit_code": 0,
                    "stdout": "101\n",
                    "stderr": "",
                    "elapsed_ms": 1,
                    "sandbox_destroyed": True,
                    "network_isolated": True,
                    "filesystem_isolated": True,
                    "environment_sanitized": True,
                },
            )
        assert stale.value.code in {"sandbox_worker_claim_invalid", "sandbox_session_closed"}
        with container.repository.sessions() as db:
            rejected = db.get(SandboxExecution, prepared["id"])
            closed = db.get(SandboxSession, session["id"])
            assert rejected.state == "failed"
            assert rejected.error_code == "sandbox_source_integrity_failed"
            assert rejected.result in ({}, None)
            assert rejected.request_spec == {"source_scrubbed": True}
            assert rejected.claimed_by is None
            assert rejected.lease_until is None
            assert closed.state == "failed"
            assert closed.cleanup_state == "required"


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
    cors_leak = client.get(
        f'/sandbox-preview/{manifest["id"]}?token={token}',
        headers=isolated_headers | {"Origin": "https://shuddho-web-editor.vercel.app"},
    )
    assert cors_leak.status_code == 400


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
            select(Artifact).where(
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


def test_preview_capability_is_sha_bound_tamper_evident_and_strictly_expires():
    secret = "preview-secret-0123456789abcdef0123456789abcdef"
    artifact_id = "11111111-1111-1111-1111-111111111111"
    digest = "a" * 64
    token = create_preview_token(secret, artifact_id, digest, 1060)
    assert verify_preview_token(
        secret, artifact_id, digest, token, now=1000, max_future_seconds=60
    ) == 1060
    with pytest.raises(CoworkerError) as tampered:
        verify_preview_token(
            secret, artifact_id, "b" * 64, token, now=1000, max_future_seconds=60
        )
    assert tampered.value.code == "sandbox_preview_invalid"
    with pytest.raises(CoworkerError) as expired:
        verify_preview_token(
            secret, artifact_id, digest, token, now=1060, max_future_seconds=60
        )
    assert expired.value.code == "sandbox_preview_expired"


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


@pytest.mark.parametrize("close_mode", ["expired", "cancelled"])
def test_late_sandbox_worker_completion_persists_terminal_failure(container, close_mode):
    """A rejected late receipt must durably revoke its claim and erase source."""
    enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner)
    prepared = container.sandbox.prepare_execution(
        owner, session["id"], SandboxExecutionCreate(source="print('private source')"),
    )
    claimed = container.sandbox.claim_executions("late-completion-worker")
    assert [item["id"] for item in claimed] == [prepared["id"]]

    # Reproduce a close between a valid worker claim and worker completion.
    # Do not call get()/list_executions() before inspecting the database:
    # their expiry scavenger would conceal rollback at the receipt boundary.
    with container.repository.sessions.begin() as db:
        stored_session = db.get(SandboxSession, session["id"])
        if close_mode == "expired":
            stored_session.expires_at = utcnow() - timedelta(seconds=1)
        else:
            # A cancellation request may be durable before state flips.
            stored_session.cancel_requested = True
            assert stored_session.state == "running"

    with pytest.raises(CoworkerError) as rejection:
        container.sandbox.complete_execution(
            "late-completion-worker", prepared["id"], completion_observation(),
        )
    assert rejection.value.code == "sandbox_session_closed"

    # The original implementation raised *inside* sessions.begin(), rolling
    # all of these state changes back and leaving the source retrievable.
    with container.repository.sessions() as db:
        execution = db.get(SandboxExecution, prepared["id"])
        stored_session = db.get(SandboxSession, session["id"])
        assert execution.state == ("failed" if close_mode == "expired" else "cancelled")
        assert execution.error_code == (
            "session_expired" if close_mode == "expired" else "session_cancelled"
        )
        assert execution.request_spec == {"source_scrubbed": True}
        assert execution.lease_until is None
        assert execution.claimed_by is None
        assert execution.finished_at is not None
        assert execution.result == {}
        assert stored_session.state == close_mode
        assert stored_session.cleanup_state == "required"
        assert stored_session.cancel_requested is True

    assert container.sandbox.claim_executions("another-worker") == []
    with pytest.raises(CoworkerError) as stale:
        container.sandbox.complete_execution(
            "late-completion-worker", prepared["id"], completion_observation(),
        )
    assert stale.value.code == "sandbox_worker_claim_invalid"


@pytest.mark.parametrize("worker_path", ["heartbeat", "completion"])
def test_terminal_session_failure_stops_other_claimed_sandbox_worker(container, worker_path):
    """A failed sibling execution must revoke the older worker's authority."""
    enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner, "terminal-sibling-" + worker_path)
    older = container.sandbox.prepare_execution(
        owner, session["id"], SandboxExecutionCreate(source="print('first')"),
    )
    first_claims = container.sandbox.claim_executions("first-worker")
    assert [item["id"] for item in first_claims] == [older["id"]]

    # One sandbox session can have multiple prepared executions. A tampered
    # second request terminates the owning session without cancelling the
    # already-running first execution's lease; check the *real* worker boundary.
    sibling = container.sandbox.prepare_execution(
        owner, session["id"], SandboxExecutionCreate(source="print('second')"),
    )
    with container.repository.sessions.begin() as db:
        row = db.get(SandboxExecution, sibling["id"])
        spec = dict(row.request_spec)
        spec["source"] = "print('tamper')"
        row.request_spec = spec

    assert container.sandbox.claim_executions("second-worker") == []
    with container.repository.sessions() as db:
        assert db.get(SandboxSession, session["id"]).state == "failed"
        first = db.get(SandboxExecution, older["id"])
        assert first.state == "running"
        assert first.claimed_by == "first-worker"

    if worker_path == "heartbeat":
        stopped = container.sandbox.worker_control("first-worker", older["id"])
        assert stopped == {"action": "stop", "reason": "session_closed"}
    else:
        with pytest.raises(CoworkerError) as rejected:
            container.sandbox.complete_execution(
                "first-worker", older["id"], completion_observation(),
            )
        assert rejected.value.code == "sandbox_session_closed"

    # Do not use the scavenging API before checking persisted state.
    with container.repository.sessions() as db:
        first = db.get(SandboxExecution, older["id"])
        second = db.get(SandboxExecution, sibling["id"])
        owned = db.get(SandboxSession, session["id"])
        assert owned.state == "failed"
        assert owned.cleanup_state == "required"
        assert first.state == "failed"
        assert first.error_code == "sandbox_session_closed"
        assert first.request_spec == {"source_scrubbed": True}
        assert first.claimed_by is None
        assert first.lease_until is None
        assert first.finished_at is not None
        assert first.result == {}
        assert second.error_code == "sandbox_source_integrity_failed"

    assert container.sandbox.claim_executions("third-worker") == []
    with pytest.raises(CoworkerError) as stale:
        container.sandbox.complete_execution(
            "first-worker", older["id"], completion_observation(),
        )
    assert stale.value.code == "sandbox_worker_claim_invalid"


def test_batched_sandbox_claim_does_not_reopen_failed_sibling_session(container):
    """A later selected row must not reset a failed session to running."""
    enable_sandbox(container)
    owner = account(container)
    session = create_session(container, owner, "batch-failed-sibling")
    first = container.sandbox.prepare_execution(
        owner, session["id"], SandboxExecutionCreate(source="print(101)"),
    )
    second = container.sandbox.prepare_execution(
        owner, session["id"], SandboxExecutionCreate(source="print(202)"),
    )
    with container.repository.sessions.begin() as db:
        row = db.get(SandboxExecution, first["id"])
        spec = dict(row.request_spec)
        spec["source"] = "print(999)"
        row.request_spec = spec

    # Both jobs are selected before the claim loop; the first is poisoned.
    # Without a per-row session-state recheck, the good second job runs
    # despite its shared session having been terminally failed.
    claims = container.sandbox.claim_executions("batch-worker", limit=2)
    assert not any(item["id"] in {first["id"], second["id"]} for item in claims)
    with container.repository.sessions() as db:
        failed = db.get(SandboxExecution, first["id"])
        skipped = db.get(SandboxExecution, second["id"])
        owned = db.get(SandboxSession, session["id"])
        assert owned.state == "failed"
        assert failed.error_code == "sandbox_source_integrity_failed"
        assert skipped.state == "failed"
        assert skipped.error_code == "sandbox_session_closed"
        assert skipped.request_spec == {"source_scrubbed": True}
        assert skipped.claimed_by is None
        assert skipped.lease_until is None

    assert container.sandbox.claim_executions("reclaim-worker", limit=2) == []
@pytest.mark.parametrize("control_response", [
    pytest.param(WorkerError("sandbox_worker_api_unavailable"), id="control-timeout"),
    pytest.param(WorkerError("http_500"), id="server-error"),
    pytest.param(WorkerError("sandbox_worker_unauthorized"), id="revoked-worker-token"),
    pytest.param({}, id="missing-action"),
    pytest.param({"action": "retry"}, id="unknown-action"),
    pytest.param({"action": "stop", "reason": "session_closed"}, id="explicit-stop"),
])
def test_sandbox_subprocess_stops_without_a_valid_control_heartbeat(
    container, monkeypatch, control_response,
):
    """Lost or malformed authorization must kill code, not extend runtime."""
    enable_sandbox(container)
    source = "print(1)\n"
    claim = {
        "id": str(uuid4()),
        "source": source,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_bytes": len(source.encode("utf-8")),
        "runtime": "python311",
        "purpose": "code_task",
        "policy": container.sandbox._policy(),
    }

    class FakeProcess:
        pid = 123456

        def __init__(self):
            self.polls = 0
            self.terminated = False

        def poll(self):
            self.polls += 1
            if self.polls > 4:
                pytest.fail("Untrusted code kept running without a valid heartbeat")
            return -9 if self.terminated else None

    process = FakeProcess()
    control_calls: list[str] = []
    terminations: list[FakeProcess] = []

    class FakeClient:
        def post(self, path, payload):
            control_calls.append(path)
            if isinstance(control_response, WorkerError):
                raise WorkerError(control_response.code)
            return control_response

    def fake_spawn(*args, **kwargs):
        return process

    def fake_terminate(running):
        terminations.append(running)
        running.terminated = True

    monkeypatch.setattr(sandbox_worker_module.subprocess, "Popen", fake_spawn)
    monkeypatch.setattr(sandbox_worker_module, "terminate_group", fake_terminate)

    with pytest.raises(WorkerError) as denied:
        sandbox_worker_module.execute_claim(
            FakeClient(), "sandbox-worker-heartbeat", claim, "/usr/bin/bwrap",
        )
    assert denied.value.code == "worker_interrupted"
    assert process.terminated is True
    assert terminations == [process]
    assert len(control_calls) == 1
    assert control_calls[0].endswith("/control")
    assert not any(path.endswith("/complete") for path in control_calls)

def test_sandbox_subprocess_accepts_explicit_control_continue_and_reports_result(
    container, monkeypatch,
):
    """A valid lease renewal preserves the bounded success path."""
    enable_sandbox(container)
    source = "print(1)\n"
    claim = {
        "id": str(uuid4()),
        "source": source,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_bytes": len(source.encode("utf-8")),
        "runtime": "python311",
        "purpose": "code_task",
        "policy": container.sandbox._policy(),
    }

    class FakeProcess:
        def __init__(self):
            self.polls = 0

        def poll(self):
            self.polls += 1
            return None if self.polls == 1 else 0

        def wait(self):
            return 0

    process = FakeProcess()
    completion: list[dict] = []
    calls: list[str] = []

    class FakeClient:
        def post(self, path, payload):
            calls.append(path)
            if path.endswith("/control"):
                return {"action": "continue", "lease_until": "2099-01-01T00:00:00+00:00"}
            if path.endswith("/complete"):
                completion.append(payload)
                return {"state": "succeeded"}
            pytest.fail("Unexpected worker request")

    monkeypatch.setattr(
        sandbox_worker_module.subprocess, "Popen",
        lambda *args, **kwargs: process,
    )
    sandbox_worker_module.execute_claim(
        FakeClient(), "sandbox-worker-heartbeat", claim, "/usr/bin/bwrap",
    )
    assert len(calls) == 2
    assert calls[0].endswith("/control")
    assert calls[1].endswith("/complete")
    assert completion[0]["exit_code"] == 0
    assert completion[0]["sandbox_destroyed"] is True
    assert completion[0]["network_isolated"] is True
