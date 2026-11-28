from __future__ import annotations

import json

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for cohort observability tests")

from scripts.cohort_observability_export import atomic_write, operator_status, render_openmetrics


def result(*, decision="CONTINUE_COHORT", breaches=None):
    return {
        "decision": decision,
        "release_id": "coworker-cohort-001",
        "breaches": [] if breaches is None else breaches,
        "rollback": None if decision == "CONTINUE_COHORT" else {
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false"
        },
        "snapshot": {
            "generated_at": "2026-09-22T04:00:00+00:00",
            "window_minutes": 15,
            "cohort_members_configured": 10,
            "active": {
                "tasks": 1,
                "agent_runs": 2,
                "provider_actions": 0,
                "oldest_work_age_seconds": 42,
            },
            "tasks": {
                "samples": 10,
                "completed": 9,
                "failed": 1,
                "needs_input": 0,
                "success_rate": 0.9,
                "failure_rate": 0.1,
            },
            "provider": {
                "samples": 10,
                "failed_or_unknown": 1,
                "failure_rate": 0.1,
                "p95_latency_ms": 1234,
                "window_tokens": 50000,
                "reserved_attempts": 1,
            },
            "agents": {"samples": 5, "failed": 1, "failure_rate": 0.2},
            "research": {"samples": 0, "failed": 0, "failure_rate": None},
            "actions": {
                "samples": 0,
                "failed_or_unknown": 0,
                "outcome_unknown": 0,
                "failure_rate": None,
            },
            "storage": {"total_bytes": 123456},
        },
    }


def test_openmetrics_export_is_sanitized_and_complete():
    text = render_openmetrics(result())
    assert text.startswith("# HELP shuddho_coworker_cohort_continue")
    assert "shuddho_coworker_cohort_continue 1" in text
    assert "shuddho_coworker_cohort_stop 0" in text
    assert "shuddho_coworker_cohort_model_reserved_attempts 1" in text
    assert "shuddho_coworker_cohort_research_failure_ratio NaN" in text
    assert "shuddho_coworker_cohort_action_failure_ratio NaN" in text
    assert text.endswith("# EOF\n")
    assert "coworker-cohort-001" not in text
    assert "owner_id" not in text
    assert "account_id" not in text
    assert "subject" not in text.lower()
    assert "email" not in text.lower()
    assert "{" not in text  # No metric labels / user-derived dimensions.


def test_stop_decision_and_breach_count_are_exported():
    value = result(
        decision="STOP_ROLLOUT",
        breaches=[{
            "metric": "actions.outcome_unknown",
            "actual": 1,
            "threshold": 0,
            "reason": "Consequential action outcomes are uncertain.",
        }],
    )
    text = render_openmetrics(value)
    assert "shuddho_coworker_cohort_continue 0" in text
    assert "shuddho_coworker_cohort_stop 1" in text
    assert "shuddho_coworker_cohort_breaches 1" in text


def test_operator_status_contains_only_sanitized_decision_context():
    value = result(
        decision="STOP_ROLLOUT",
        breaches=[{
            "metric": "provider.failure_rate",
            "actual": 0.3,
            "threshold": 0.1,
            "reason": "Model/provider failure rate exceeded the rollout limit.",
        }],
    )
    status = operator_status(value)
    assert status["schema_version"] == 1
    assert status["decision"] == "STOP_ROLLOUT"
    assert status["release_id"] == "coworker-cohort-001"
    assert status["cohort_members_configured"] == 10
    assert status["breaches"][0]["metric"] == "provider.failure_rate"
    assert status["rollback"]["global_kill_switch"] == "SHUDDHO_COWORKER_ENABLED=false"
    encoded = json.dumps(status)
    assert "owner_id" not in encoded
    assert "subject" not in encoded
    assert "instruction" not in encoded


def test_atomic_write_replaces_existing_file(tmp_path):
    path = tmp_path / "metrics.prom"
    path.write_text("old\n", encoding="utf-8")
    atomic_write(path, "new\n")
    assert path.read_text(encoding="utf-8") == "new\n"
    assert list(tmp_path.iterdir()) == [path]


def test_new_observability_metrics_are_unknown_for_legacy_snapshot():
    text = render_openmetrics(result())
    assert "shuddho_coworker_cohort_task_dispatch_samples NaN\n" in text
    assert "shuddho_coworker_cohort_agent_dispatch_p95_ms NaN\n" in text
    assert "shuddho_coworker_queue_worker_fresh_running NaN\n" in text
    assert "shuddho_coworker_provider_active_leases NaN\n" in text


def test_dispatch_heartbeat_metrics_preserve_measured_zero_and_privacy():
    value = result()
    snapshot = value["snapshot"]
    snapshot["dispatch"] = {
        "tasks": {"admissions": 2, "samples": 1, "unobserved": 1, "invalid_clock": 0,
                  "p50_ms": 0, "p95_ms": 0, "private_id": "secret-task"},
        "agents": {"admissions": 0, "samples": 0, "unobserved": 0, "invalid_clock": 0,
                   "p50_ms": None, "p95_ms": None},
    }
    snapshot["workers"] = {
        "active_rows": 1, "fresh_running": 0, "stale": 1, "invalid_clock": 0,
        "starting": 0, "draining": 0, "oldest_valid_heartbeat_age_seconds": 16,
        "private_id": "secret-worker",
    }
    snapshot["provider"]["active_leases"] = 0
    text = render_openmetrics(value)
    assert "shuddho_coworker_cohort_task_dispatch_samples 1\n" in text
    assert "shuddho_coworker_cohort_task_dispatch_p95_ms 0\n" in text
    assert "shuddho_coworker_cohort_agent_dispatch_p95_ms NaN\n" in text
    assert "shuddho_coworker_queue_worker_fresh_running 0\n" in text
    assert "shuddho_coworker_queue_worker_stale 1\n" in text
    assert "shuddho_coworker_provider_active_leases 0\n" in text
    assert "secret-task" not in text and "secret-worker" not in text and "{" not in text


def test_terminal_agent_outcome_metrics_distinguish_unknown_and_zero():
    value = result()
    legacy = render_openmetrics(value)
    assert "shuddho_coworker_cohort_agents_blocked NaN\n" in legacy
    value["snapshot"]["agents"].update(completed=4, cancelled=0, needs_input=2, blocked=1)
    metrics = render_openmetrics(value)
    assert "shuddho_coworker_cohort_agents_completed 4\n" in metrics
    assert "shuddho_coworker_cohort_agents_cancelled 0\n" in metrics
    assert "shuddho_coworker_cohort_agents_needs_input 2\n" in metrics
    assert "shuddho_coworker_cohort_agents_blocked 1\n" in metrics
    assert "{" not in metrics
