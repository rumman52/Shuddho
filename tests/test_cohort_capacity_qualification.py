from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.cohort_capacity_qualification import (
    CapacityQualificationError,
    evaluate_report,
    qualify,
)


def plan():
    return {
        "release_id": "coworker-cohort-001",
        "final_stage": "cohort-25",
        "freshness_minutes": 120,
        "expected_peak_concurrency": 10,
        "min_reserve_ratio": 1.5,
        "simulated": {
            "min_accounts": 10,
            "min_submitted": 200,
            "min_success_rate": 0.99,
            "max_rejection_rate": 0.01,
            "max_submit_p95_ms": 500,
            "max_submit_p99_ms": 1000,
            "max_completion_p95_ms": 15000,
            "max_completion_p99_ms": 30000,
            "max_queue_age_seconds": 30,
        },
        "live_provider": {
            "min_accounts": 5,
            "min_submitted": 20,
            "min_success_rate": 0.95,
            "max_rejection_rate": 0.05,
            "max_completion_p95_ms": 120000,
            "max_completion_p99_ms": 180000,
            "max_provider_failure_rate": 0.05,
            "max_provider_p95_latency_ms": 90000,
            "max_average_tokens_per_completed_task": 20000,
        },
    }


def report(kind):
    base = {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "kind": kind,
        "generated_at": "2026-09-22T08:30:00+00:00",
        "duration_seconds": 600,
        "accounts": 10 if kind == "simulated" else 5,
        "offered_concurrency": 15,
        "submitted": 200 if kind == "simulated" else 20,
        "completed": 200 if kind == "simulated" else 20,
        "failed": 0,
        "rejected": 0,
        "submit_p95_ms": 120,
        "submit_p99_ms": 250,
        "completion_p95_ms": 8000 if kind == "simulated" else 60000,
        "completion_p99_ms": 12000 if kind == "simulated" else 90000,
        "max_queue_age_seconds": 4,
        "provider_samples": 0 if kind == "simulated" else 20,
        "provider_failed": 0,
        "provider_p95_latency_ms": None if kind == "simulated" else 30000,
        "total_tokens": 0 if kind == "simulated" else 120000,
    }
    return base


def progression():
    return {
        "decision": "HOLD",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "next_stage": None,
        "reasons": ["final_stage_reached"],
    }


def status():
    return {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T08:40:00+00:00",
        "breaches": [],
    }


def test_capacity_gate_qualifies_measured_reserve():
    value = qualify(
        capacity_plan=plan(),
        progression=progression(),
        simulated=report("simulated"),
        live=report("live_provider"),
        operator_status=status(),
        now=datetime(2026, 9, 22, 8, 45, tzinfo=timezone.utc),
    )
    assert value["decision"] == "ELIGIBLE_FOR_CAPACITY_REVIEW"
    assert value["required_test_concurrency"] == 15
    assert value["failures"] == []
    assert value["generated_at"] == "2026-09-22T08:45:00+00:00"


def test_capacity_gate_requires_final_stage_to_be_fully_earned():
    value = progression()
    value["reasons"] = ["insufficient_provider_samples"]
    with pytest.raises(CapacityQualificationError, match="final_stage_reached"):
        qualify(
            capacity_plan=plan(),
            progression=value,
            simulated=report("simulated"),
            live=report("live_provider"),
            operator_status=status(),
            now=datetime(2026, 9, 22, 8, 45, tzinfo=timezone.utc),
        )


def test_capacity_gate_requires_reserve_concurrency():
    simulated = report("simulated")
    simulated["offered_concurrency"] = 14
    failures = evaluate_report(
        simulated,
        plan()["simulated"],
        kind="simulated",
        plan=plan(),
    )
    assert any(item["metric"] == "offered_concurrency" for item in failures)


def test_live_capacity_requires_provider_measurements():
    live = report("live_provider")
    live["provider_samples"] = 0
    live["provider_p95_latency_ms"] = None
    failures = evaluate_report(
        live,
        plan()["live_provider"],
        kind="live_provider",
        plan=plan(),
    )
    names = {item["metric"] for item in failures}
    assert "provider_failure_rate" in names
    assert "provider_p95_latency_ms" in names


def test_live_capacity_rejects_excessive_token_cost():
    live = report("live_provider")
    live["total_tokens"] = 500000
    failures = evaluate_report(
        live,
        plan()["live_provider"],
        kind="live_provider",
        plan=plan(),
    )
    assert any(item["metric"] == "average_tokens_per_completed_task" for item in failures)


def test_capacity_gate_requires_fresh_post_report_health():
    operator = status()
    operator["generated_at"] = "2026-09-22T08:20:00+00:00"
    with pytest.raises(CapacityQualificationError, match="after both capacity reports"):
        qualify(
            capacity_plan=plan(),
            progression=progression(),
            simulated=report("simulated"),
            live=report("live_provider"),
            operator_status=operator,
            now=datetime(2026, 9, 22, 8, 45, tzinfo=timezone.utc),
        )


def test_capacity_gate_rejects_stale_reports():
    with pytest.raises(CapacityQualificationError, match="stale"):
        qualify(
            capacity_plan=plan(),
            progression=progression(),
            simulated=report("simulated"),
            live=report("live_provider"),
            operator_status=status(),
            now=datetime(2026, 9, 22, 11, 0, tzinfo=timezone.utc),
        )


def test_capacity_gate_accepts_dynamic_post_scale_requalification():
    dynamic_plan = plan()
    dynamic_plan["final_stage"] = "cohort-40"
    progression_value = {
        "decision": "ELIGIBLE_FOR_REQUALIFICATION",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-40",
        "next_stage": None,
        "stage_max_users": 40,
        "epoch_start": "2026-09-22T08:00:00+00:00",
        "reasons": [],
    }
    value = qualify(
        capacity_plan=dynamic_plan,
        progression=progression_value,
        simulated=report("simulated"),
        live=report("live_provider"),
        operator_status=status(),
        now=datetime(2026, 9, 22, 8, 45, tzinfo=timezone.utc),
    )
    assert value["decision"] == "ELIGIBLE_FOR_CAPACITY_REVIEW"
    assert value["final_stage"] == "cohort-40"


def test_capacity_gate_rejects_unearned_dynamic_stage():
    dynamic_plan = plan()
    dynamic_plan["final_stage"] = "cohort-40"
    progression_value = {
        "decision": "HOLD",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-40",
        "next_stage": None,
        "stage_max_users": 40,
        "epoch_start": "2026-09-22T08:00:00+00:00",
        "reasons": ["insufficient_healthy_windows"],
    }
    with pytest.raises(CapacityQualificationError, match="post-scale observation"):
        qualify(
            capacity_plan=dynamic_plan,
            progression=progression_value,
            simulated=report("simulated"),
            live=report("live_provider"),
            operator_status=status(),
            now=datetime(2026, 9, 22, 8, 45, tzinfo=timezone.utc),
        )
