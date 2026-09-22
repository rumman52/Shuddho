from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for rollback tests")
pytest.importorskip("temporalio", reason="Install the coworker extra for rollback tests")

from scripts import staging_flag_rollback as rollback


def settings(**overrides):
    value = dict(
        agent_runtime_enabled=True,
        agent_dependency_graph_enabled=True,
        agent_parallel_execution_enabled=True,
        work_services_enabled=True,
    )
    value.update(overrides)
    return SimpleNamespace(**value)


def test_prepare_requires_parallel_v2_flags():
    rollback.require_prepare_flags(settings())
    with pytest.raises(rollback.RollbackFailure, match="parallel execution"):
        rollback.require_prepare_flags(settings(agent_parallel_execution_enabled=False))
    with pytest.raises(rollback.RollbackFailure, match="dependency graph"):
        rollback.require_prepare_flags(settings(agent_dependency_graph_enabled=False))


def test_verify_requires_parallel_flag_off_but_runtime_on():
    rollback.require_verify_flags(settings(agent_parallel_execution_enabled=False))
    with pytest.raises(rollback.RollbackFailure, match="requires SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false"):
        rollback.require_verify_flags(settings(agent_parallel_execution_enabled=True))
    with pytest.raises(rollback.RollbackFailure, match="must remain true"):
        rollback.require_verify_flags(settings(agent_parallel_execution_enabled=False, agent_runtime_enabled=False))


def test_workflow_type_reads_temporal_visibility_string():
    class Client:
        def list_workflows(self, query):
            assert 'WorkflowId = "shuddho-agent-123"' == query
            async def rows():
                yield SimpleNamespace(workflow_type="shuddho_agent_run_v2")
            return rows()

    assert asyncio.run(rollback.workflow_type(Client(), "shuddho-agent-123")) == "shuddho_agent_run_v2"


def test_workflow_type_accepts_named_workflow_type_object():
    class Client:
        def list_workflows(self, query):
            async def rows():
                yield SimpleNamespace(workflow_type=SimpleNamespace(name="shuddho_agent_run_v1"))
            return rows()

    assert asyncio.run(rollback.workflow_type(Client(), "shuddho-agent-456")) == "shuddho_agent_run_v1"


def test_workflow_type_fails_closed_when_visibility_missing():
    class Client:
        def list_workflows(self, query):
            async def rows():
                if False:
                    yield None
            return rows()

    with pytest.raises(rollback.RollbackFailure, match="did not return a workflow type"):
        asyncio.run(rollback.workflow_type(Client(), "missing"))


def test_simple_plan_is_one_non_consequential_document_task():
    plan = rollback.simple_plan()
    assert len(plan) == 1
    assert plan[0].tool == "document.create"
    assert plan[0].arguments["document_ids"] == []
