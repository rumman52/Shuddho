from __future__ import annotations

import json
import hashlib

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for Agent economics tests")

from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.errors import CoworkerError
from services.coworker.models import AgentDecision, AgentRun
from services.coworker.migrate import upgrade
from services.coworker.schemas import TaskCreate
from scripts.core_agent_observability import aggregate, collect_snapshot, compare_day8_development, estimated_cost_microusd, main, render_openmetrics

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
        TaskCreate(
            instruction="Draft the bounded output.",
            notes="Phase 10 bounded child model budget test.",
            output_language="en",
        ),
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

def test_dashboard_reports_model_tool_latency_and_retry_rate():
    settings = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
    )
    records = [{
        "completion_state": "completed",
        "tool_calls": 2,
        "tool_failures": 0,
        "model_calls": 3,
        "model_failures": 0,
        "latency_ms": 500,
        "tokens": 900,
        "cost_microusd": 30,
        "duplicate_attempts": 0,
        "outcome_unknown": 0,
        "abandoned": False,
        "provider_failures": 0,
        "retries": 1,
        "dispatch_retries": 3,
        "token_direction_breakdown_available": True,
        "input_tokens": 100,
        "output_tokens": 200,
        "model_latency_ms": [100, 200, 300],
        "tool_latency_ms": [20, 40],
    }]
    dashboard = aggregate(records, [], settings)

    assert dashboard["models"]["p50_latency_ms"] == 200
    assert dashboard["models"]["p95_latency_ms"] == 300
    assert dashboard["models"]["p99_latency_ms"] == 300
    assert dashboard["tools"]["p50_latency_ms"] == 20
    assert dashboard["tools"]["p95_latency_ms"] == 40
    assert dashboard["runs"]["retry_rate"] == pytest.approx(1 / 5, abs=1e-6)
    assert dashboard["runs"]["dispatch_retry_attempts"] == 3
    assert dashboard["runs"]["input_token_consumption"] == 100
    assert dashboard["runs"]["output_token_consumption"] == 200
    assert dashboard["runs"]["token_direction_coverage"] == 1.0

def test_unpriced_model_usage_is_not_reported_as_zero_cost():
    settings = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        agent_v3_planner_cost_microusd_per_1k_tokens=0,
    )
    assert estimated_cost_microusd(1000, settings) is None

def test_openmetrics_exports_latency_and_retry_metrics_without_labels():
    settings = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
    )
    dashboard = aggregate([{
        "completion_state": "completed",
        "tool_calls": 1,
        "tool_failures": 0,
        "model_calls": 1,
        "model_failures": 0,
        "latency_ms": 100,
        "tokens": 100,
        "cost_microusd": 10,
        "duplicate_attempts": 0,
        "outcome_unknown": 0,
        "abandoned": False,
        "provider_failures": 0,
        "retries": 0,
        "dispatch_retries": 2,
        "token_direction_breakdown_available": True,
        "input_tokens": 30,
        "output_tokens": 70,
        "model_latency_ms": [25],
        "tool_latency_ms": [10],
    }], [], settings)
    text = render_openmetrics({"dashboard": dashboard})

    assert "shuddho_core_agent_model_latency_p50_ms 25" in text
    assert "shuddho_core_agent_tool_latency_p95_ms 10" in text
    assert "shuddho_core_agent_retry_rate 0" in text
    assert "shuddho_core_agent_dispatch_retry_attempts 2" in text
    assert "shuddho_core_agent_input_token_consumption 30" in text
    assert "shuddho_core_agent_output_token_consumption 70" in text
    assert "shuddho_core_agent_token_direction_coverage 1" in text
    assert "{" not in text
    assert "run_id" not in text

def test_unknown_cost_rate_propagates_as_unavailable_not_zero():
    settings = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        agent_v3_planner_cost_microusd_per_1k_tokens=0,
    )
    dashboard = aggregate([{
        "completion_state": "completed",
        "tool_calls": 0,
        "tool_failures": 0,
        "model_calls": 1,
        "model_failures": 0,
        "latency_ms": 100,
        "tokens": 500,
        "cost_microusd": None,
        "duplicate_attempts": 0,
        "outcome_unknown": 0,
        "abandoned": False,
        "provider_failures": 0,
        "retries": 0,
        "model_latency_ms": [50],
        "tool_latency_ms": [],
    }], [], settings)

    assert dashboard["runs"]["cost_estimate_complete"] is False
    assert dashboard["runs"]["total_cost_microusd"] is None
    assert dashboard["runs"]["average_cost_microusd"] is None
    text = render_openmetrics({"dashboard": dashboard})
    assert "shuddho_core_agent_average_cost_microusd NaN" in text

def test_snapshot_includes_persisted_planner_inference_latency(tmp_path):
    container = make_container(
        tmp_path,
        agent_v3_planner_cost_microusd_per_1k_tokens=1000,
    )
    account_id = owner(container, "planner-latency")
    run = create_run(container, account_id, "planner-latency-run")
    now = datetime.now(timezone.utc)
    with container.repository.sessions.begin() as db:
        saved_run = db.get(AgentRun, run["id"])
        saved_run.state = "completed"
        saved_run.planner_calls = 1
        saved_run.planner_tokens = 10
        saved_run.planner_actual_tokens = 10
        saved_run.planner_cost_microusd = 10
        saved_run.updated_at = now
        db.add(AgentDecision(
            run_id=run["id"],
            sequence=1,
            owner_id=account_id,
            planner_call=1,
            decision_type="next_step",
            payload={"decision": "next_step", "tool": "document.create", "objective": "Create a report."},
            model="test-model",
            prompt_sha256="a" * 64,
            tool_schema_sha256="b" * 64,
            observation_count=0,
            total_tokens=10,
            cost_microusd=10,
            latency_ms=37,
        ))

    snapshot = collect_snapshot(container.settings, now=now)
    record = snapshot["records"][0]

    assert record["model_latency_ms"] == [37]
    assert record["model_latency_ms_p50"] == 37
    assert record["model_latency_coverage"] == 1.0
    assert snapshot["dashboard"]["models"]["p95_latency_ms"] == 37

def test_v3_planner_preserves_provider_token_directions():
    import asyncio
    import httpx

    from services.coworker.agent_planning_model import DeepSeekAgentPlanner, PlannerFailure

    settings = Settings(
        database_url="sqlite://",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        deepseek_api_key="test-only-placeholder",
    )
    response_body = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({"decision": "wait", "wait_seconds": 1})},
        }],
        "usage": {"total_tokens": 50, "prompt_tokens": 30, "completion_tokens": 20},
    }
    planner = DeepSeekAgentPlanner(
        settings,
        httpx.MockTransport(lambda _: httpx.Response(200, json=response_body)),
    )
    decision, total, _latency, evidence = asyncio.run(planner.decide(
        "Prepare a bounded project report.",
        [],
        [],
        remaining_budget={},
        dependencies={},
    ))
    assert decision.decision == "wait"
    assert total == 50
    assert evidence["input_tokens"] == 30
    assert evidence["output_tokens"] == 20

    invalid_body = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({"decision": "next_step"})},
        }],
        "usage": {"total_tokens": 50, "prompt_tokens": 30, "completion_tokens": 20},
    }
    invalid = DeepSeekAgentPlanner(
        settings,
        httpx.MockTransport(lambda _: httpx.Response(200, json=invalid_body)),
    )
    with pytest.raises(PlannerFailure) as failure:
        asyncio.run(invalid.decide(
            "Prepare a bounded project report.",
            [],
            [],
            remaining_budget={},
            dependencies={},
        ))
    assert failure.value.input_tokens == 30
    assert failure.value.output_tokens == 20

def test_snapshot_directional_usage_sums_complete_calls(tmp_path):
    container = make_container(tmp_path)
    account_id = owner(container, "token-directions")
    run = create_run(container, account_id, "token-directions-run")

    planner = container.agent.reserve_planner(run["id"], 100)
    container.agent.settle_planner_capacity(
        run["id"], planner["call"], 50,
        input_tokens=30, output_tokens=20,
    )
    task, _ = container.repository.create_task(
        account_id,
        TaskCreate(
            instruction="Draft the bounded output.",
            notes="Directional usage persistence test.",
            output_language="en",
        ),
        "token-directions-child",
        enqueue=False,
        agent_run_id=run["id"],
        agent_step_id=None,
    )
    attempt = container.repository.reserve_model(task["id"], 100)
    container.repository.settle_model(
        task["id"], attempt, 40, 12, "completed",
        input_tokens=25, output_tokens=15,
    )

    snapshot = collect_snapshot(container.settings)
    record = next(item for item in snapshot["records"] if item["run_id"] == run["id"])
    assert record["input_tokens"] == 55
    assert record["output_tokens"] == 35
    assert record["token_direction_breakdown_available"] is True
    assert record["token_direction_missing_components"] == []

def test_snapshot_missing_planner_tokens_stay_unknown(tmp_path):
    container = make_container(tmp_path)
    account_id = owner(container, "token-directions-missing")
    run = create_run(container, account_id, "token-directions-missing-run")
    planner = container.agent.reserve_planner(run["id"], 100)
    container.agent.settle_planner_capacity(
        run["id"], planner["call"], 50,
        input_tokens=30, output_tokens=None,
    )

    snapshot = collect_snapshot(container.settings)
    record = next(item for item in snapshot["records"] if item["run_id"] == run["id"])
    assert record["input_tokens"] is None
    assert record["output_tokens"] is None
    assert record["token_direction_breakdown_available"] is False
    assert record["token_direction_missing_components"] == ["planner"]

def test_snapshot_missing_child_tokens_stay_unknown(tmp_path):
    container = make_container(tmp_path)
    account_id = owner(container, "child-token-directions-missing")
    run = create_run(container, account_id, "child-token-directions-missing-run")
    task, _ = container.repository.create_task(
        account_id,
        TaskCreate(
            instruction="Draft the bounded output.",
            notes="Missing child usage test.",
            output_language="en",
        ),
        "child-token-directions-missing-task",
        enqueue=False,
        agent_run_id=run["id"],
        agent_step_id=None,
    )
    attempt = container.repository.reserve_model(task["id"], 100)
    container.repository.settle_model(task["id"], attempt, 40, 12, "completed")

    snapshot = collect_snapshot(container.settings)
    record = next(item for item in snapshot["records"] if item["run_id"] == run["id"])
    assert record["input_tokens"] is None
    assert record["output_tokens"] is None
    assert record["token_direction_breakdown_available"] is False
    assert record["token_direction_missing_components"] == ["child_model_attempts"]

def _day8_fixture():
    """Four ten-task development cells and independently referenced outcomes."""
    cases = []
    for workflow in ("research_brief", "project_report_email"):
        for language in ("bn", "en"):
            for index in range(10):
                cases.append({
                    "id": f"{workflow}-{language}-{index}",
                    "workflow": workflow, "language": language,
                    "split": "development",
                })
    # A synthetic immutable source snapshot per case; no source text or
    # provider token enters this unit-test fixture.
    for case in cases:
        case["_source"] = {
            "sha256": hashlib.sha256(("frozen-source:" + case["id"]).encode()).hexdigest(),
        }
    suite = {"manifest": {
        "suite_id": "pilot",
        "source_revision": "a" * 40,
        "files": {"development": {"sha256": "d" * 64}},
    }, "cases": cases}
    identity = {"schema_version": 2, "split": "development",
                "suite_id": "pilot", "source_revision": "a" * 40,
                "case_file_sha256": "d" * 64,
                "generation_identity_verified": True,
                "receipts_independently_verified": True,
                "provider_usage_receipt_sha256": "e" * 64,
                "review_ledger_sha256": "f" * 64}
    def make(profile, unit_cost):
        return {
            **identity,
            "configuration": {
                "profile": profile,
                "provider": "deepseek",
                "model": "deepseek-flash",
                "time_limit_seconds": 60,
                "model_settings_sha256": "1" * 64,
                "behavior_sha256": ("2" if profile == "baseline" else "3") * 64,
                "prompt_sha256": ("4" if profile == "baseline" else "5") * 64,
                "tool_sha256": "6" * 64,
                "schema_sha256": "7" * 64,
                "flags_sha256": "8" * 64,
                "budgets_sha256": "9" * 64,
                "prompt_template_sha256": "0" * 64,
            },
            "evaluation_policy": {
                "approved_p95_end_to_end_latency_ms": 1000,
                "approved_max_cost_microusd_per_accepted_output": 1000,
                "quality_rubric_sha256": "a" * 64,
                "pricing_assumptions_sha256": "b" * 64,
                "owner_approval_receipt_sha256": "c" * 64,
            },
            "reruns": [],
            "results": [{
                "execution_kind": "first_run", "attempt_number": 1,
                "id": case["id"], "workflow": case["workflow"],
                "language": case["language"],
                "case_input_sha256": hashlib.sha256(json.dumps(
                    {key: value for key, value in case.items() if key != "_source"},
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")).hexdigest(),
                "source_snapshot_sha256": case["_source"]["sha256"],
                "passed": True, "human_accepted": True, "safety_passed": True,
                # The 80 synthetic accepted outputs have separate custody
                # in each arm, even if generated content is byte-identical.
                "accepted_outcome_ref": f"review:{profile}:" + case["id"],
                "verified_artifact_refs": [f"artifact:{profile}:" + case["id"]],
                "input_tokens": 100, "output_tokens": 20,
                "model_time_ms": 100, "tool_time_ms": 50,
                "retry_count": 0, "cost_microusd": unit_cost,
                "run_id": f"synthetic:{profile}:{case['id']}",
                "provider_usage_case_receipt_sha256": hashlib.sha256(
                    (profile + case["id"] + ":usage").encode()
                ).hexdigest(),
                "output_sha256": hashlib.sha256(
                    (profile + case["id"] + ":output").encode()
                ).hexdigest(),
                "end_to_end_latency_ms": 300,
                "retry_breakdown": {"model": 0, "tool": 0, "dispatch": 0},
                "failure_breakdown": {"provider": 0, "model": 0, "tool": 0},
                "cost_components_microusd": {
                    "provider": unit_cost, "tools": 0, "compute": 0,
                    "storage": 0, "other": 0,
                },
            } for case in cases],
        }
    return suite, make("baseline", 20), make("bounded_context_compact_observations", 15)

def test_day8_selects_measured_least_cost_profile_with_receipts_and_freeze_hashes():
    suite, baseline, candidate = _day8_fixture()
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["status"] == "FROZEN_FOR_DAY9"
    assert comparison["measured_cost_savings_microusd"] == 200
    assert comparison["selected_least_cost_qualified_profile"] == "bounded_context_compact_observations"
    assert comparison["freeze"]["promotion_authorized"] is False
    assert len(comparison["freeze"]["freeze_sha256"]) == 64
    assert comparison["profile_summaries"]["baseline"]["total_input_tokens"] == 4000
    assert comparison["profile_summaries"]["bounded_context_compact_observations"]["total_model_time_ms"] == 4000
    assert len(comparison["per_task_comparison"]) == 40
    first = comparison["per_task_comparison"][0]
    assert first["baseline"]["input_tokens"] == 100
    assert first["baseline"]["output_tokens"] == 20
    assert first["baseline"]["measured_model_tool_time_ms"] == 150
    assert first["baseline"]["accepted_outcome_ref"].startswith("review:")
    assert first["measured_cost_savings_microusd"] == 5

def test_day8_missing_cost_or_token_direction_blocks_choice_without_invented_savings():
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][0]["input_tokens"] = None
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["status"] == "BLOCKED"
    assert comparison["selected_least_cost_qualified_profile"] is None
    assert comparison["measured_cost_savings_microusd"] is None
    assert comparison["profile_summaries"]["bounded_context_compact_observations"]["total_cost_microusd"] is None
    assert any(item["bounded_context_compact_observations"]["input_tokens"] is None
               for item in comparison["per_task_comparison"])
    assert comparison["freeze"] is None

def test_day8_does_not_claim_quality_retention_when_one_language_cell_regresses():
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][0]["human_accepted"] = False
    candidate["results"][1]["human_accepted"] = False
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["status"] == "FROZEN_FOR_DAY9"
    assert comparison["selected_least_cost_qualified_profile"] == "baseline"
    assert comparison["candidate_quality_retained"] is False
    assert comparison["candidate_exclusion_reason"] == "quality_regression_vs_baseline"
    assert comparison["measured_cost_savings_microusd"] is None
    assert comparison["profile_summaries"]["bounded_context_compact_observations"]["by_cell"]["research_brief/bn"] == 8

def test_day8_rejects_unpaired_model_setting_and_unreferenced_accepted_outcome():
    suite, baseline, candidate = _day8_fixture()
    candidate["configuration"]["model_settings_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="preserve provider, model, parameters and tool surface"):
        compare_day8_development(baseline, candidate, suite)
    candidate["configuration"]["model_settings_sha256"] = baseline["configuration"]["model_settings_sha256"]
    candidate["results"][0]["verified_artifact_refs"] = []
    with pytest.raises(ValueError, match="accepted outcome lacks valid artifact"):
        compare_day8_development(baseline, candidate, suite)

def test_day8_missing_independent_receipt_verification_blocks_freeze():
    suite, baseline, candidate = _day8_fixture()
    candidate["receipts_independently_verified"] = False
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert any("independently verified" in blocker for blocker in result["blockers"])

def test_day8_operator_snapshot_does_not_infer_split_tokens_or_accepted_artifacts(tmp_path):
    container = make_container(tmp_path)
    account_id = owner(container, "day8")
    run = create_run(container, account_id, "day8-run")
    snapshot = collect_snapshot(container.settings)
    record = next(record for record in snapshot["records"] if record["run_id"] == run["id"])
    assert record["input_tokens"] is None
    assert record["output_tokens"] is None
    assert record["token_direction_breakdown_available"] is False
    assert record["verified_artifact_references"] == []
    assert record["accepted_outcome_references"] == []
    assert "{" not in render_openmetrics(snapshot)

def test_day8_cli_exit_code_fails_on_blocked_comparison(tmp_path, monkeypatch):
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][0]["cost_microusd"] = None
    baseline_file = tmp_path / "baseline.json"
    candidate_file = tmp_path / "candidate.json"
    report_file = tmp_path / "comparison.json"
    baseline_file.write_text(json.dumps(baseline), encoding="utf-8")
    candidate_file.write_text(json.dumps(candidate), encoding="utf-8")
    monkeypatch.setattr("scripts.pilot_workflow_eval.load_suite", lambda: suite)
    monkeypatch.setattr("sys.argv", [
        "core_agent_observability",
        "--day8-baseline", str(baseline_file),
        "--day8-candidate", str(candidate_file),
        "--day8-report", str(report_file),
    ])
    assert main() == 1
    assert json.loads(report_file.read_text(encoding="utf-8"))["status"] == "BLOCKED"

def test_day8_allows_nonaccepted_failed_tasks_to_lack_verified_artifacts():
    suite, baseline, candidate = _day8_fixture()
    for report in (baseline, candidate):
        for row in report["results"]:
            if row["id"].endswith("-9"):
                row["passed"] = False
                row["human_accepted"] = False
                row["verified_artifact_refs"] = []
                row["accepted_outcome_ref"] = None
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["status"] == "FROZEN_FOR_DAY9"
    assert comparison["profile_summaries"]["baseline"]["human_accepted"] == 36

def test_day8_does_not_trade_away_a_previously_accepted_task_for_another():
    """Per-cell totals cannot hide a regression on a matched frozen task."""
    suite, baseline, candidate = _day8_fixture()
    # Both runs still pass 39/40 and the same 9/10 cell gate.
    baseline["results"][0]["human_accepted"] = False
    baseline["results"][0]["verified_artifact_refs"] = []
    baseline["results"][0]["accepted_outcome_ref"] = None
    candidate["results"][1]["human_accepted"] = False
    candidate["results"][1]["verified_artifact_refs"] = []
    candidate["results"][1]["accepted_outcome_ref"] = None

    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["profile_summaries"]["baseline"]["human_accepted"] == 39
    assert comparison["profile_summaries"]["bounded_context_compact_observations"]["human_accepted"] == 39
    assert comparison["candidate_quality_retained"] is False
    assert comparison["selected_least_cost_qualified_profile"] == "baseline"
    assert comparison["measured_cost_savings_microusd"] is None

def test_day8_rejects_reused_artifact_receipt_between_distinct_tasks():
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][1]["verified_artifact_refs"] = candidate["results"][0]["verified_artifact_refs"]
    with pytest.raises(ValueError, match="reused artifact reference"):
        compare_day8_development(baseline, candidate, suite)


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "model_time_ms"])
def test_day8_rejects_zero_model_usage_for_accepted_output(field):
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][0][field] = 0
    with pytest.raises(ValueError, match="accepted outcome has zero"):
        compare_day8_development(baseline, candidate, suite)

def test_day8_unsafe_candidate_does_not_claim_qualified_savings():
    """Safety failure can coexist with retained 39/40 accepted tasks."""
    suite, baseline, candidate = _day8_fixture()
    for report in (baseline, candidate):
        report["results"][0]["human_accepted"] = False
        report["results"][0]["verified_artifact_refs"] = []
        report["results"][0]["accepted_outcome_ref"] = None
    candidate["results"][0]["safety_passed"] = False
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["candidate_quality_retained"] is True
    assert comparison["profile_summaries"]["baseline"]["quality_gate_passed"] is True
    assert comparison["profile_summaries"]["bounded_context_compact_observations"]["quality_gate_passed"] is False
    assert comparison["selected_least_cost_qualified_profile"] == "baseline"
    assert comparison["candidate_exclusion_reason"] == "failed_quality_or_safety_gate"
    assert comparison["measured_cost_savings_microusd"] is None
    assert all(row["measured_cost_savings_microusd"] is None for row in comparison["per_task_comparison"])

def test_day8_rejects_reused_human_review_receipt_between_tasks():
    """An acceptance receipt must identify one specific reviewed outcome."""
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][1]["accepted_outcome_ref"] = candidate["results"][0]["accepted_outcome_ref"]
    with pytest.raises(ValueError, match="reused accepted outcome reference"):
        compare_day8_development(baseline, candidate, suite)



def _day8_complete_measurement_fixture():
    """Synthetic only: inputs exercise validation, not operated provider receipts."""
    suite, baseline, candidate = _day8_fixture()
    for report in (baseline, candidate):
        report["configuration"].update({
            "schema_sha256": "7" * 64,
            "flags_sha256": "8" * 64,
            "budgets_sha256": "9" * 64,
        })
        report["evaluation_policy"] = {
            "approved_p95_end_to_end_latency_ms": 1000,
            "approved_max_cost_microusd_per_accepted_output": 1000,
            "quality_rubric_sha256": "a" * 64,
            "pricing_assumptions_sha256": "b" * 64,
            "owner_approval_receipt_sha256": "c" * 64,
        }
        for row in report["results"]:
            row["end_to_end_latency_ms"] = 300
            row["retry_breakdown"] = {"model": 0, "tool": 0, "dispatch": 0}
            row["failure_breakdown"] = {"provider": 0, "model": 0, "tool": 0}
            row["cost_components_microusd"] = {
                "provider": row["cost_microusd"],
                "tools": 0,
                "compute": 0,
                "storage": 0,
                "other": 0,
            }
    return suite, baseline, candidate


def test_day8_no_freeze_on_missing_end_to_end_latency():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["end_to_end_latency_ms"] = None
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert any("latency" in item for item in result["blockers"])
    assert result["profile_summaries"]["bounded_context_compact_observations"]["p95_end_to_end_latency_ms"] is None


def test_day8_slower_cheaper_candidate_loses_approved_latency_gate():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    for row in candidate["results"]:
        row["end_to_end_latency_ms"] = 1200
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "FROZEN_FOR_DAY9"
    assert result["selected_least_cost_qualified_profile"] == "baseline"
    assert result["profile_summaries"]["bounded_context_compact_observations"]["p95_end_to_end_latency_ms"] == 1200
    assert result["candidate_exclusion_reason"] == "latency_slo_breached"
    assert result["measured_cost_savings_microusd"] is None


def test_day8_selects_cost_per_accepted_output_not_lower_raw_cohort_spend():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    for row in baseline["results"]:
        if row["id"].endswith("-0"):
            row["human_accepted"] = False
            row["verified_artifact_refs"] = []
            row["accepted_outcome_ref"] = None
    for row in candidate["results"]:
        row["cost_microusd"] = 21
        row["cost_components_microusd"]["provider"] = 21
    result = compare_day8_development(baseline, candidate, suite)
    assert result["profile_summaries"]["baseline"]["human_accepted"] == 36
    assert result["profile_summaries"]["baseline"]["total_cost_microusd"] == 800
    assert result["profile_summaries"]["bounded_context_compact_observations"]["total_cost_microusd"] == 840
    assert result["profile_summaries"]["baseline"]["cost_microusd_per_accepted_output"] == pytest.approx(800 / 36, abs=.01)
    assert result["selected_least_cost_qualified_profile"] == "bounded_context_compact_observations"


def test_day8_rejects_unpaired_price_policy_and_invalid_all_in_components():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["evaluation_policy"]["pricing_assumptions_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="decision policy"):
        compare_day8_development(baseline, candidate, suite)
    candidate["evaluation_policy"] = baseline["evaluation_policy"].copy()
    candidate["results"][0]["cost_components_microusd"]["provider"] = 0
    with pytest.raises(ValueError, match="cost components"):
        compare_day8_development(baseline, candidate, suite)


def test_day8_emits_paired_cell_denominators_and_failure_retry_types():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["retry_count"] = 1
    candidate["results"][0]["retry_breakdown"]["model"] = 1
    candidate["results"][0]["failure_breakdown"]["provider"] = 1
    result = compare_day8_development(baseline, candidate, suite)
    cell = result["profile_summaries"]["bounded_context_compact_observations"]["cell_metrics"]["research_brief/bn"]
    assert cell["cases"] == 10
    assert cell["accepted"] == 10
    assert cell["p50_end_to_end_latency_ms"] == 300
    assert cell["p95_end_to_end_latency_ms"] == 300
    assert cell["retries_by_type"] == {"model": 1, "tool": 0, "dispatch": 0}
    assert cell["failures_by_type"] == {"provider": 1, "model": 0, "tool": 0}
    assert cell["cost_microusd_per_accepted_output"] == 15
    first = next(r for r in result["per_task_comparison"] if r["id"] == candidate["results"][0]["id"])
    assert first["bounded_context_compact_observations"]["end_to_end_latency_ms"] == 300
    assert first["bounded_context_compact_observations"]["retry_breakdown"]["model"] == 1


def test_day8_rejects_incomplete_or_inconsistent_retry_accounting():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    del candidate["results"][0]["retry_breakdown"]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    candidate["results"][0]["retry_breakdown"] = {"model": 1, "tool": 0, "dispatch": 0}
    with pytest.raises(ValueError, match="retry breakdown"):
        compare_day8_development(baseline, candidate, suite)


def test_day8_freeze_manifest_pins_policy_schema_flags_budgets_and_code():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "FROZEN_FOR_DAY9"
    freeze = result["freeze"]
    assert freeze["evaluation_policy"] == baseline["evaluation_policy"]
    assert freeze["configuration"]["schema_sha256"] == "7" * 64
    assert freeze["configuration"]["flags_sha256"] == "8" * 64
    assert freeze["configuration"]["budgets_sha256"] == "9" * 64
    assert "services/coworker/models.py" in freeze["source_file_sha256"]


def test_day8_unapproved_or_missing_pricing_policy_cannot_freeze():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    del candidate["evaluation_policy"]["owner_approval_receipt_sha256"]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None



def test_day8_incomplete_legacy_v1_identity_blocks_without_crashing():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    del candidate["configuration"]["flags_sha256"]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert any("configuration" in blocker for blocker in result["blockers"])


def test_day8_missing_or_reused_case_run_identity_cannot_freeze():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["run_id"] = None
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    candidate["results"][0]["run_id"] = candidate["results"][1]["run_id"]
    with pytest.raises(ValueError, match="reused run identity"):
        compare_day8_development(baseline, candidate, suite)



def _day8_cross_arm_distinct_accepted_references(candidate):
    """Make otherwise independent synthetic arm receipts, including reviews."""
    for row in candidate["results"]:
        row["accepted_outcome_ref"] = "review:bounded:" + row["id"]
        row["verified_artifact_refs"] = ["artifact:bounded:" + row["id"]]


@pytest.mark.parametrize("evidence", ["verified_artifact_refs", "accepted_outcome_ref"])
@pytest.mark.parametrize("attempt", ["first_run", "rerun"])
def test_day8_rejects_cross_arm_reuse_of_accepted_evidence(evidence, attempt):
    """An accepted baseline review/artifact cannot stand in for another arm."""
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    _day8_cross_arm_distinct_accepted_references(candidate)
    primary = baseline["results"][0]
    if attempt == "first_run":
        reused = candidate["results"][0]
    else:
        reused = _day8_synthetic_rerun(candidate, cost=0)
        reused["passed"] = True
        reused["human_accepted"] = True
        reused["output_sha256"] = hashlib.sha256(b"independent-rerun").hexdigest()
        reused["accepted_outcome_ref"] = "review:bounded:rerun:unique"
        reused["verified_artifact_refs"] = ["artifact:bounded:rerun:unique"]
        candidate["reruns"].append(reused)
    reused[evidence] = primary[evidence]
    reason = (
        "reused accepted artifact reference across profiles"
        if evidence == "verified_artifact_refs"
        else "reused accepted outcome reference across profiles"
    )
    with pytest.raises(ValueError, match=reason):
        compare_day8_development(baseline, candidate, suite)


def test_day8_independent_accepted_receipts_allow_same_output_content_digest():
    """Equal generated bytes do not imply sharing an artifact/review receipt."""
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    _day8_cross_arm_distinct_accepted_references(candidate)
    candidate["results"][0]["output_sha256"] = baseline["results"][0]["output_sha256"]
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["selected_least_cost_qualified_profile"] == "bounded_context_compact_observations"
    assert comparison["status"] == "FROZEN_FOR_DAY9"


def test_day8_cross_profile_runs_cannot_use_same_generation_identity():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["run_id"] = baseline["results"][0]["run_id"]
    with pytest.raises(ValueError, match="reused run identity across profiles"):
        compare_day8_development(baseline, candidate, suite)


def test_day8_case_usage_receipt_hash_cannot_be_omitted_or_reused():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["provider_usage_case_receipt_sha256"] = None
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    candidate["results"][0]["provider_usage_case_receipt_sha256"] = (
        candidate["results"][1]["provider_usage_case_receipt_sha256"]
    )
    with pytest.raises(ValueError, match="reused provider usage receipt"):
        compare_day8_development(baseline, candidate, suite)


def test_day8_shared_prompt_template_is_pinned_while_generated_prompts_may_vary():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["configuration"]["prompt_template_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="paired context experiment"):
        compare_day8_development(baseline, candidate, suite)



def test_day8_rejects_private_config_fields_before_freeze_output():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    secret = "synthetic-private@example.invalid fake-token-ONLY-FOR-TEST"
    baseline["configuration"]["raw_prompt_and_token"] = secret
    with pytest.raises(ValueError, match="unexpected configuration property") as exc:
        compare_day8_development(baseline, candidate, suite)
    assert secret not in str(exc.value)


def test_day8_rejects_different_task_time_budgets():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["configuration"]["time_limit_seconds"] = 120
    with pytest.raises(ValueError, match="same time limit"):
        compare_day8_development(baseline, candidate, suite)


@pytest.mark.parametrize("bad_limit", [None, 0, True, 3601, "60"])
def test_day8_missing_or_invalid_time_limit_blocks_freeze(bad_limit):
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["configuration"]["time_limit_seconds"] = bad_limit
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert any("time limit" in blocker for blocker in result["blockers"])


@pytest.mark.parametrize("missing_control", [
    "candidate_time_limit", "shared_flags_fingerprint", "shared_budgets_fingerprint",
])
def test_day8_unqualified_comparison_controls_never_claim_cost_savings(missing_control):
    """Arithmetic deltas cannot qualify as savings without matched controls."""
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    if missing_control == "candidate_time_limit":
        del candidate["configuration"]["time_limit_seconds"]
    elif missing_control == "shared_flags_fingerprint":
        del candidate["configuration"]["flags_sha256"]
    else:
        del candidate["configuration"]["budgets_sha256"]

    report = compare_day8_development(baseline, candidate, suite)
    # The provider usage and reviewer evidence remain complete and the raw
    # observed cost difference still exists; the experiment isn't eligible.
    assert report["status"] == "BLOCKED"
    assert report["selected_least_cost_qualified_profile"] is None
    assert report["freeze"] is None
    assert report["profile_summaries"]["baseline"]["total_cost_microusd"] == 800
    assert report["profile_summaries"]["bounded_context_compact_observations"][
        "total_cost_microusd"
    ] == 600
    assert report["measured_cost_savings_microusd"] is None
    assert all(
        row["measured_cost_savings_microusd"] is None
        for row in report["per_task_comparison"]
    )
    # Raw matched costs must remain visible as measurements, not qualified
    # savings; the withheld claim cannot erase available provider receipts.
    assert all(
        row["paired_measured_deltas_candidate_minus_baseline"]["cost_microusd"] == -5
        for row in report["per_task_comparison"]
    )


def test_day8_legacy_missing_time_limits_never_freezes():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    del baseline["configuration"]["time_limit_seconds"]
    del candidate["configuration"]["time_limit_seconds"]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None


def test_day8_rejects_reused_usage_receipt_across_baseline_and_candidate():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["provider_usage_case_receipt_sha256"] = (
        baseline["results"][0]["provider_usage_case_receipt_sha256"]
    )
    with pytest.raises(ValueError, match="reused provider usage receipt across profiles"):
        compare_day8_development(baseline, candidate, suite)


def _day8_synthetic_rerun(report, *, cost=500):
    """A separate synthetic attempt, never a replacement for its first-run row."""
    first = report["results"][0]
    return {
        **first,
        "execution_kind": "rerun",
        "attempt_number": 2,
        "rerun_of_run_id": first["run_id"],
        "run_id": f"{first['run_id']}:rerun-2",
        "provider_usage_case_receipt_sha256": hashlib.sha256(
            f"{first['run_id']}:rerun-2:usage".encode(),
        ).hexdigest(),
        "output_sha256": None,
        "passed": False,
        "human_accepted": False,
        "verified_artifact_refs": [],
        "accepted_outcome_ref": None,
        "cost_microusd": cost,
        "cost_components_microusd": {
            "provider": cost, "tools": 0, "compute": 0, "storage": 0, "other": 0,
        },
    }


def test_day8_rerun_cost_changes_least_cost_profile_without_changing_first_run_quality():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["reruns"].append(_day8_synthetic_rerun(candidate, cost=500))
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "FROZEN_FOR_DAY9"
    assert result["profile_summaries"]["baseline"]["total_cost_microusd"] == 800
    assert result["profile_summaries"]["bounded_context_compact_observations"]["total_cost_microusd"] == 1100
    assert result["profile_summaries"]["bounded_context_compact_observations"]["human_accepted"] == 40
    assert result["profile_summaries"]["bounded_context_compact_observations"]["rerun_attempts"] == 1
    assert result["selected_least_cost_qualified_profile"] == "baseline"
    assert result["measured_cost_savings_microusd"] == -300
    row = next(item for item in result["per_task_comparison"]
               if item["id"] == candidate["results"][0]["id"])
    assert row["bounded_context_compact_observations"]["all_attempts_cost_microusd"] == 515
    assert row["measured_cost_savings_microusd"] == -495



def test_day8_unsafe_candidate_rerun_cannot_make_cheapest_profile_eligible():
    """All observed attempts, not only the 40 first runs, must pass safety."""
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    unsafe = _day8_synthetic_rerun(candidate, cost=0)
    unsafe["safety_passed"] = False
    candidate["reruns"].append(unsafe)
    report = compare_day8_development(baseline, candidate, suite)

    bounded = report["profile_summaries"]["bounded_context_compact_observations"]
    assert bounded["human_accepted"] == 40  # fixed first-run denominator
    assert bounded["rerun_attempts"] == 1
    assert bounded["unsafe_attempts"] == 1
    assert bounded["safety_assessed_attempts"] == 41
    case_row = next(
        case for case in report["per_task_comparison"]
        if case["id"] == candidate["results"][0]["id"]
    )
    assert case_row["bounded_context_compact_observations"]["unsafe_rerun_attempts"] == 1
    assert bounded["safety_gate_passed"] is False
    assert bounded["quality_gate_passed"] is False
    assert report["selected_least_cost_qualified_profile"] == "baseline"
    assert report["candidate_exclusion_reason"] == "failed_quality_or_safety_gate"
    assert report["measured_cost_savings_microusd"] is None


def test_day8_safe_candidate_may_be_selected_when_baseline_has_unsafe_rerun():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    unsafe = _day8_synthetic_rerun(baseline, cost=0)
    unsafe["safety_passed"] = False
    baseline["reruns"].append(unsafe)
    report = compare_day8_development(baseline, candidate, suite)

    assert report["profile_summaries"]["baseline"]["unsafe_attempts"] == 1
    assert report["profile_summaries"]["baseline"]["safety_gate_passed"] is False
    assert report["profile_summaries"]["bounded_context_compact_observations"]["safety_gate_passed"] is True
    assert report["selected_least_cost_qualified_profile"] == "bounded_context_compact_observations"
    # A failed baseline safety gate must never be described as qualified savings.
    assert report["measured_cost_savings_microusd"] is None


def test_day8_both_profiles_with_unsafe_reruns_cannot_freeze():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    for profile in (baseline, candidate):
        unsafe = _day8_synthetic_rerun(profile, cost=0)
        unsafe["safety_passed"] = False
        profile["reruns"].append(unsafe)
    report = compare_day8_development(baseline, candidate, suite)

    assert report["status"] == "BLOCKED"
    assert report["freeze"] is None
    assert report["selected_least_cost_qualified_profile"] is None
    assert all(
        report["profile_summaries"][name]["safety_gate_passed"] is False
        for name in ("baseline", "bounded_context_compact_observations")
    )
    assert any("safety" in reason for reason in report["blockers"])


def test_day8_missing_rerun_safety_assessment_cannot_be_treated_as_safe():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    unassessed = _day8_synthetic_rerun(candidate, cost=0)
    del unassessed["safety_passed"]
    candidate["reruns"].append(unassessed)
    report = compare_day8_development(baseline, candidate, suite)

    bounded = report["profile_summaries"]["bounded_context_compact_observations"]
    assert bounded["rerun_attempts"] == 1
    assert bounded["unsafe_attempts"] == 0  # unknown is not an observed unsafe output
    assert bounded["safety_assessed_attempts"] == 40
    assert bounded["safety_gate_passed"] is False
    assert report["status"] == "BLOCKED"
    assert report["freeze"] is None
    assert any("attempt provenance" in reason or "missing run/output" in reason
               for reason in report["blockers"])

def test_day8_missing_rerun_cost_or_attempt_provenance_blocks_freeze():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["reruns"].append(_day8_synthetic_rerun(candidate))
    candidate["reruns"][0]["cost_microusd"] = None
    candidate["reruns"][0]["cost_components_microusd"] = None
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert result["profile_summaries"]["bounded_context_compact_observations"]["total_cost_microusd"] is None

    candidate["reruns"] = []
    del candidate["reruns"]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert any("attempt provenance" in blocker for blocker in result["blockers"])


def test_day8_legacy_v1_without_explicit_attempts_never_freezes():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    for report in (baseline, candidate):
        report["schema_version"] = 1
        del report["reruns"]
        for first in report["results"]:
            del first["execution_kind"]
            del first["attempt_number"]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert any("attempt provenance" in blocker for blocker in result["blockers"])


@pytest.mark.parametrize("reused_identity", ["run", "usage"])
def test_day8_rejects_cross_profile_rerun_identity_reuse(reused_identity):
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    rerun = _day8_synthetic_rerun(candidate)
    if reused_identity == "run":
        rerun["run_id"] = baseline["results"][0]["run_id"]
        error = "reused run identity across profiles"
    else:
        rerun["provider_usage_case_receipt_sha256"] = baseline["results"][0][
            "provider_usage_case_receipt_sha256"
        ]
        error = "reused provider usage receipt across profiles"
    candidate["reruns"].append(rerun)
    with pytest.raises(ValueError, match=error):
        compare_day8_development(baseline, candidate, suite)


def _with_day8_cost_ceiling(baseline, candidate, ceiling_microusd):
    for report in (baseline, candidate):
        report["evaluation_policy"]["approved_max_cost_microusd_per_accepted_output"] = ceiling_microusd


def test_day8_legacy_policy_without_approved_cost_ceiling_cannot_freeze():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    for report in (baseline, candidate):
        del report["evaluation_policy"]["approved_max_cost_microusd_per_accepted_output"]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert result["profile_summaries"]["baseline"]["total_cost_microusd"] == 800
    assert any("cost ceiling" in reason for reason in result["blockers"])


def test_day8_candidate_at_exact_cost_ceiling_qualifies_even_when_baseline_exceeds():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    _with_day8_cost_ceiling(baseline, candidate, 15)
    report = compare_day8_development(baseline, candidate, suite)
    assert report["status"] == "FROZEN_FOR_DAY9"
    assert report["selected_least_cost_qualified_profile"] == "bounded_context_compact_observations"
    assert report["profile_summaries"]["baseline"]["cost_gate_passed"] is False
    assert report["profile_summaries"]["bounded_context_compact_observations"]["cost_gate_passed"] is True
    assert report["profile_summaries"]["bounded_context_compact_observations"][
        "approved_cost_ceiling_microusd_per_accepted_output"
    ] == 15
    assert report["freeze"]["evaluation_policy"]["approved_max_cost_microusd_per_accepted_output"] == 15


def test_day8_one_extra_rerun_microdollar_exceeds_exact_accepted_output_ceiling():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    _with_day8_cost_ceiling(baseline, candidate, 15)
    candidate["reruns"].append(_day8_synthetic_rerun(candidate, cost=1))
    report = compare_day8_development(baseline, candidate, suite)
    assert report["status"] == "BLOCKED"
    assert report["freeze"] is None
    assert report["profile_summaries"]["bounded_context_compact_observations"]["total_cost_microusd"] == 601
    assert report["profile_summaries"]["bounded_context_compact_observations"]["cost_gate_passed"] is False
    assert any("cost ceiling" in reason for reason in report["blockers"])


def test_day8_over_budget_but_cheaper_candidate_does_not_claim_qualified_savings():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    _with_day8_cost_ceiling(baseline, candidate, 14)
    report = compare_day8_development(baseline, candidate, suite)
    assert report["status"] == "BLOCKED"
    assert report["measured_cost_savings_microusd"] is None
    assert report["profile_summaries"]["baseline"]["cost_microusd_per_accepted_output"] == 20
    assert report["profile_summaries"]["bounded_context_compact_observations"][
        "cost_microusd_per_accepted_output"
    ] == 15
    assert report["per_task_comparison"][0]["paired_measured_deltas_candidate_minus_baseline"][
        "cost_microusd"
    ] == -5
    assert all(r["measured_cost_savings_microusd"] is None
               for r in report["per_task_comparison"])
    assert any("cost ceiling" in reason for reason in report["blockers"])


def test_day8_over_budget_candidate_falls_back_to_eligible_baseline():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    _with_day8_cost_ceiling(baseline, candidate, 20)
    candidate["reruns"].append(_day8_synthetic_rerun(candidate, cost=500))
    report = compare_day8_development(baseline, candidate, suite)
    assert report["status"] == "FROZEN_FOR_DAY9"
    assert report["selected_least_cost_qualified_profile"] == "baseline"
    assert report["profile_summaries"]["baseline"]["cost_gate_passed"] is True
    assert report["profile_summaries"]["bounded_context_compact_observations"]["cost_gate_passed"] is False
    assert report["measured_cost_savings_microusd"] is None


@pytest.mark.parametrize("invalid", [None, 0, -1, True, 15.0, "15"])
def test_day8_invalid_owner_cost_ceiling_cannot_freeze(invalid):
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    _with_day8_cost_ceiling(baseline, candidate, 20)
    candidate["evaluation_policy"]["approved_max_cost_microusd_per_accepted_output"] = invalid
    report = compare_day8_development(baseline, candidate, suite)
    assert report["status"] == "BLOCKED"
    assert report["freeze"] is None
    assert report["measured_cost_savings_microusd"] is None


def test_day8_rejects_41_manifest_development_entries_with_one_duplicate_id():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    suite["cases"].append(dict(suite["cases"][0]))
    with pytest.raises(ValueError, match="exactly 40 distinct frozen development cases"):
        compare_day8_development(baseline, candidate, suite)


@pytest.mark.parametrize("field", ["case_input_sha256", "source_snapshot_sha256"])
def test_day8_rejects_first_run_different_from_frozen_case_or_source(field):
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0][field] = "0" * 64
    with pytest.raises(ValueError, match="frozen .* digest mismatch"):
        compare_day8_development(baseline, candidate, suite)


@pytest.mark.parametrize("field", ["case_input_sha256", "source_snapshot_sha256"])
def test_day8_missing_first_run_case_source_binding_blocks_freeze(field):
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    del candidate["results"][0][field]
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert result["measured_cost_savings_microusd"] is None
    assert any("case input/source" in reason for reason in result["blockers"])
    assert result["profile_summaries"]["baseline"]["total_cost_microusd"] == 800


@pytest.mark.parametrize("field", ["case_input_sha256", "source_snapshot_sha256"])
def test_day8_rejects_rerun_with_wrong_frozen_case_source_binding(field):
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    rerun = _day8_synthetic_rerun(candidate, cost=1)
    rerun[field] = "0" * 64
    candidate["reruns"].append(rerun)
    with pytest.raises(ValueError, match="frozen .* digest mismatch"):
        compare_day8_development(baseline, candidate, suite)


@pytest.mark.parametrize("field", ["case_input_sha256", "source_snapshot_sha256"])
def test_day8_missing_rerun_case_source_binding_blocks_freeze(field):
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    rerun = _day8_synthetic_rerun(candidate, cost=1)
    del rerun[field]
    candidate["reruns"].append(rerun)
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert any("case input/source" in reason for reason in result["blockers"])


def test_day8_source_snapshot_is_not_accepted_without_suite_source_digest():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    del suite["cases"][0]["_source"]
    with pytest.raises(ValueError, match="source snapshot digest"):
        compare_day8_development(baseline, candidate, suite)

def test_day8_one_first_run_over_hard_deadline_excludes_cheaper_profile():
    """p95 may look green while one accepted attempt exceeds its task deadline."""
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["end_to_end_latency_ms"] = 60_001  # 60-second fixed limit
    result = compare_day8_development(baseline, candidate, suite)
    bounded = result["profile_summaries"]["bounded_context_compact_observations"]
    assert bounded["human_accepted"] == 40
    assert bounded["latency_gate_passed"] is True  # one outlier is below p95
    assert bounded["deadline_evaluated_attempts"] == 40
    assert bounded["deadline_overrun_attempts"] == 1
    assert bounded["deadline_gate_passed"] is False
    matched = next(
        row for row in result["per_task_comparison"]
        if row["id"] == candidate["results"][0]["id"]
    )
    assert matched["bounded_context_compact_observations"]["deadline_overrun_attempts"] == 1
    assert matched["baseline"]["deadline_overrun_attempts"] == 0
    assert result["selected_least_cost_qualified_profile"] == "baseline"
    assert result["candidate_exclusion_reason"] == "execution_deadline_breached"
    assert result["measured_cost_savings_microusd"] is None


def test_day8_failed_rerun_beyond_fixed_deadline_disqualifies_profile():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    rerun = _day8_synthetic_rerun(candidate, cost=0)
    rerun["end_to_end_latency_ms"] = 60_001
    candidate["reruns"].append(rerun)
    result = compare_day8_development(baseline, candidate, suite)
    bounded = result["profile_summaries"]["bounded_context_compact_observations"]
    assert bounded["human_accepted"] == 40  # rerun does not expand denominator
    assert bounded["rerun_attempts"] == 1
    assert bounded["latency_gate_passed"] is True
    assert bounded["deadline_evaluated_attempts"] == 41
    assert bounded["deadline_overrun_attempts"] == 1
    assert bounded["deadline_gate_passed"] is False
    assert result["selected_least_cost_qualified_profile"] == "baseline"
    assert result["measured_cost_savings_microusd"] is None


def test_day8_both_profiles_with_measured_deadline_overruns_cannot_freeze():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    for report in (baseline, candidate):
        report["results"][0]["end_to_end_latency_ms"] = 60_001
    result = compare_day8_development(baseline, candidate, suite)
    assert result["status"] == "BLOCKED"
    assert result["freeze"] is None
    assert result["selected_least_cost_qualified_profile"] is None
    assert any("execution deadline" in reason for reason in result["blockers"])


def test_day8_measured_exact_deadline_is_allowed():
    suite, baseline, candidate = _day8_complete_measurement_fixture()
    candidate["results"][0]["end_to_end_latency_ms"] = 60_000
    result = compare_day8_development(baseline, candidate, suite)
    bounded = result["profile_summaries"]["bounded_context_compact_observations"]
    assert bounded["deadline_evaluated_attempts"] == 40
    assert bounded["deadline_overrun_attempts"] == 0
    assert bounded["deadline_gate_passed"] is True
    assert result["selected_least_cost_qualified_profile"] == "bounded_context_compact_observations"



@pytest.mark.parametrize("raw", [b'{"cost":1e999}', b'{"cost":-1e999}', b'{"cost":NaN}', b'{"cost":1,"cost":2}', b'[]'])
def test_day8_input_rejects_ambiguous_or_nonfinite_json(tmp_path, raw):
    from scripts.core_agent_observability import _read_day8_input
    path = tmp_path / "receipt.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        _read_day8_input(path)


def test_day8_input_does_not_reopen_checked_path(tmp_path, monkeypatch):
    from pathlib import Path
    from scripts.core_agent_observability import _read_day8_input
    path = tmp_path / "receipt.json"
    path.write_text('{"cost":1}', encoding="utf-8")
    replacement = tmp_path / "replacement.json"
    replacement.write_text('{"cost":2}', encoding="utf-8")
    original_stat = Path.stat
    swapped = False

    def swap_after_stat(self, *args, **kwargs):
        nonlocal swapped
        result = original_stat(self, *args, **kwargs)
        if self == path and kwargs.get("follow_symlinks", True) and not swapped:
            swapped = True
            path.unlink()
            path.symlink_to(replacement)
        return result

    monkeypatch.setattr(Path, "stat", swap_after_stat)
    assert _read_day8_input(path) == {"cost": 1}


def test_day8_input_preserves_two_megabyte_limit(tmp_path):
    from scripts.core_agent_observability import _read_day8_input
    path = tmp_path / "receipt.json"
    path.write_bytes(b'{}' + b' ' * 1_999_998)
    assert _read_day8_input(path) == {}
    with path.open("ab") as stream:
        stream.write(b' ')
    with pytest.raises(ValueError):
        _read_day8_input(path)
