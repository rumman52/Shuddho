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
        "model_latency_ms": [25],
        "tool_latency_ms": [10],
    }], [], settings)
    text = render_openmetrics({"dashboard": dashboard})

    assert "shuddho_core_agent_model_latency_p50_ms 25" in text
    assert "shuddho_core_agent_tool_latency_p95_ms 10" in text
    assert "shuddho_core_agent_retry_rate 0" in text
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


def test_day8_missing_cost_or_token_direction_blocks_choice_without_invented_savings():
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][0]["input_tokens"] = None
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["status"] == "BLOCKED"
    assert comparison["selected_least_cost_qualified_profile"] is None
    assert comparison["measured_cost_savings_microusd"] is None
    assert comparison["profile_summaries"]["bounded_context_compact_observations"]["total_cost_microusd"] is None
    assert comparison["freeze"] is None


def test_day8_does_not_claim_quality_retention_when_one_language_cell_regresses():
    suite, baseline, candidate = _day8_fixture()
    candidate["results"][0]["human_accepted"] = False
    candidate["results"][1]["human_accepted"] = False
    comparison = compare_day8_development(baseline, candidate, suite)
    assert comparison["status"] == "BLOCKED"
    assert comparison["candidate_quality_retained"] is False
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
