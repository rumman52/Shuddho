from __future__ import annotations

import json

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
