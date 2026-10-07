from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for Agent economics tests")

from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.errors import CoworkerError
from services.coworker.migrate import upgrade
from services.coworker.schemas import TaskCreate
from scripts.core_agent_observability import aggregate, collect_snapshot, render_openmetrics

ISSUER = "https://identity.example.test/auth/v1"


def make_container(tmp_path, **overrides):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'phase10.sqlite3'}",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        agent_runtime_enabled=True,
        agent_runtime_v3_enabled=True,
        intelligent_planner_enabled=True,
        **overrides,
    )
    settings.validate()
    upgrade(settings.database_url)
    value = Container.create(settings)
    return value


def owner(container, subject="phase10"):
    return container.repository.ensure_account(
        Principal(ISSUER, subject, 4102444800)
    )["account_id"]


def create_run(container, account_id, key="phase10-run"):
    return container.agent.create(
        account_id,
        AgentRunCreate(goal="Prepare a bounded project document.", output_language="en"),
        key,
    )[0]


def test_total_model_call_budget_spans_planner_and_child_tasks(tmp_path):
    container = make_container(
        tmp_path,
        max_agent_model_calls_per_run=1,
        max_agent_v3_planner_calls=1,
        agent_v3_planner_token_budget=1000,
        max_agent_tokens_per_run=1000,
    )
    account_id = owner(container)
    run = create_run(container, account_id)
    reservation = container.agent.reserve_planner(run["id"], 10)
    assert reservation["call"] == 1

    task, _ = container.repository.create_task(
        account_id,
        TaskCreate(instruction="Draft the bounded output.", output_language="en"),
        "phase10-child-task",
        enqueue=False,
        agent_run_id=run["id"],
        agent_step_id=None,
    )
    with pytest.raises(CoworkerError) as error:
        container.repository.reserve_model(task["id"], 10)
    assert error.value.code == "agent_model_call_limit"
    assert error.value.status_code == 429


def test_cost_budget_is_fail_closed_before_provider_call(tmp_path):
    container = make_container(
        tmp_path,
        agent_v3_planner_cost_microusd_per_1k_tokens=1000,
        max_agent_cost_microusd_per_run=5,
        agent_v3_planner_token_budget=100,
        max_agent_tokens_per_run=100,
    )
    account_id = owner(container, "cost")
    run = create_run(container, account_id, "phase10-cost")
    with pytest.raises(CoworkerError) as error:
        container.agent.reserve_planner(run["id"], 6)
    assert error.value.code == "agent_cost_limit"
    assert error.value.status_code == 402


def test_tool_budget_is_exposed_by_runtime_v3(tmp_path):
    container = make_container(tmp_path, max_agent_tool_calls_per_run=1)
    account_id = owner(container, "tools")
    run = create_run(container, account_id, "phase10-tools")
    remaining = container.agent.v3_remaining_budget(run["id"])
    assert remaining["tool_steps_remaining"] == 1


def test_observability_record_has_required_phase10_fields(tmp_path):
    container = make_container(tmp_path)
    account_id = owner(container, "observe")
    run = create_run(container, account_id, "phase10-observe")
    snapshot = collect_snapshot(container.settings, window_minutes=60)
    record = next(item for item in snapshot["records"] if item["run_id"] == run["id"])
    required = {
        "run_id", "model", "tokens", "latency_ms", "tool_calls",
        "tool_latency_ms_total", "retries", "routing_decision", "approval_waits",
        "provider_failures", "cost_microusd", "completion_state",
    }
    assert required <= set(record)
    assert record["routing_decision"] == "agent_run"
    assert snapshot["dashboard"]["budgets"]["max_runtime_seconds"] == 1800


def test_dashboard_covers_reliability_economics_and_transaction_unknown():
    settings = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
    )
    records = [
        {
            "completion_state": "completed", "tool_calls": 2, "tool_failures": 0,
            "model_calls": 2, "model_failures": 0, "latency_ms": 100,
            "tokens": 500, "cost_microusd": 20, "duplicate_attempts": 0,
            "outcome_unknown": 0, "abandoned": False, "provider_failures": 0,
        },
        {
            "completion_state": "failed", "tool_calls": 1, "tool_failures": 1,
            "model_calls": 1, "model_failures": 1, "latency_ms": 300,
            "tokens": 700, "cost_microusd": 40, "duplicate_attempts": 1,
            "outcome_unknown": 1, "abandoned": True, "provider_failures": 2,
        },
    ]
    transactions = [
        SimpleNamespace(state="confirmed"),
        SimpleNamespace(state="outcome_unknown"),
    ]
    dashboard = aggregate(records, transactions, settings)
    assert dashboard["runs"]["success_rate"] == 0.5
    assert dashboard["runs"]["p50_latency_ms"] == 100
    assert dashboard["runs"]["p95_latency_ms"] == 300
    assert dashboard["runs"]["p99_latency_ms"] == 300
    assert dashboard["runs"]["average_steps"] == 1.5
    assert dashboard["runs"]["token_consumption"] == 1200
    assert dashboard["runs"]["average_cost_microusd"] == 30
    assert dashboard["tools"]["failure_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert dashboard["models"]["failure_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert dashboard["transactions"]["outcome_unknown"] == 1


def test_openmetrics_is_label_free_and_exports_transaction_unknown():
    settings = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
    )
    dashboard = aggregate([], [SimpleNamespace(state="outcome_unknown")], settings)
    text = render_openmetrics({"dashboard": dashboard})
    assert "shuddho_core_agent_run_success_ratio NaN" in text
    assert "shuddho_transactions_outcome_unknown 1" in text
    assert "{" not in text
    assert "run_id" not in text
    assert text.endswith("# EOF\n")


def test_invalid_phase10_budget_configuration_is_rejected():
    base = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
    )
    with pytest.raises(ValueError, match="hard Core Agent ceiling"):
        replace(base, max_agent_tool_calls_per_run=9).validate()
    with pytest.raises(ValueError, match="MAX_MODEL_CALLS_PER_RUN"):
        replace(base, max_agent_model_calls_per_run=3, max_agent_v3_planner_calls=4).validate()
    with pytest.raises(ValueError, match="MAX_TOKENS_PER_RUN"):
        replace(base, max_agent_tokens_per_run=20000, agent_v3_planner_token_budget=24000).validate()
