from __future__ import annotations

import json

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
    suite = {"manifest": {
        "suite_id": "pilot",
        "source_revision": "a" * 40,
        "files": {"development": {"sha256": "d" * 64}},
    }, "cases": cases}
    identity = {"schema_version": 1, "split": "development",
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
                "model_settings_sha256": "1" * 64,
                "behavior_sha256": ("2" if profile == "baseline" else "3") * 64,
                "prompt_sha256": ("4" if profile == "baseline" else "5") * 64,
                "tool_sha256": "6" * 64,
            },
            "results": [{
                "id": case["id"], "workflow": case["workflow"],
                "language": case["language"],
                "passed": True, "human_accepted": True, "safety_passed": True,
                "accepted_outcome_ref": "review:" + case["id"],
                "verified_artifact_refs": ["artifact:" + case["id"]],
                "input_tokens": 100, "output_tokens": 20,
                "model_time_ms": 100, "tool_time_ms": 50,
                "retry_count": 0, "cost_microusd": unit_cost,
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
