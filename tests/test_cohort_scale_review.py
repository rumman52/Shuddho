from datetime import datetime, timezone

import pytest

from scripts.cohort_scale_review import (
    ScaleReviewError,
    evaluate_review,
    validate_capacity,
    validate_economics,
    validate_incident_restore,
    validate_operator_status,
    validate_quality,
)


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def plan():
    return {
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "current_max_users": 25,
        "max_growth_ratio": 2.0,
        "freshness_minutes": 1440,
        "min_quality_pass_rate": 1.0,
        "min_fact_recall": 1.0,
        "min_provider_headroom_ratio": 1.25,
        "min_budget_headroom_ratio": 1.15,
        "min_error_budget_remaining_ratio": 0.5,
    }


def review():
    return {
        "release_id": "coworker-cohort-001",
        "proposed_stage": "cohort-40",
        "proposed_max_users": 40,
        "projected_peak_concurrency": 12,
        "provider_concurrency_quota": 20,
        "estimated_monthly_cost_usd": 800,
        "approved_monthly_budget_usd": 1200,
        "error_budget_remaining_ratio": 0.8,
        "oncall_staffing_confirmed": True,
        "demand_reference": "demand-42",
        "provider_quota_reference": "quota-42",
        "budget_reference": "budget-42",
        "oncall_reference": "oncall-42",
        "change_reference": "change-42",
    }


def capacity():
    return {
        "decision": "ELIGIBLE_FOR_CAPACITY_REVIEW",
        "generated_at": "2026-09-22T11:20:00+00:00",
        "release_id": "coworker-cohort-001",
        "final_stage": "cohort-25",
        "failures": [],
    }


def quality():
    return {
        "mode": "live",
        "release_id": "coworker-cohort-001",
        "generated_at": "2026-09-22T11:30:00+00:00",
        "provider_model": "deepseek-flash",
        "source_revision": "1" * 40,
        "fixture_sha256": "a" * 64,
        "gate_decision": "PASS",
        "failures": [],
        "gate_failures": [],
        "pass_rate": 1.0,
        "required_fact_recall": 1.0,
    }




def economics():
    return {
        "schema_version": 1,
        "mode": "task_economics",
        "release_id": "coworker-cohort-001",
        "generated_at": "2026-09-22T11:35:00+00:00",
        "samples_generated_at": "2026-09-22T11:34:00+00:00",
        "source_revision": "1" * 40,
        "rollout_manifest_sha256": "b" * 64,
        "provider_policy_plan_sha256": "c" * 64,
        "pricing_plan_sha256": "d" * 64,
        "samples_sha256": "e" * 64,
        "completed_tasks": 4,
        "total_retries": 1,
        "category_coverage": {
            "model": True,
            "search": True,
            "sandbox": True,
            "render": True,
            "storage": True,
            "notification": True,
        },
        "category_cost_microusd": {
            "model": 4000,
            "search": 200,
            "sandbox": 50,
            "render": 80,
            "storage": 20,
            "notification": 12,
        },
        "average_cost_microusd": 1091,
        "p95_cost_microusd": 1400,
        "max_cost_microusd": 1400,
        "budget_microusd_per_completed_task": 2000,
        "gate_decision": "PASS",
        "failures": [],
    }


def incident_restore():
    return {
        "schema_version": 1,
        "mode": "incident_restore",
        "release_id": "coworker-cohort-001",
        "generated_at": "2026-09-22T11:37:00+00:00",
        "exercise_started_at": "2026-09-22T11:00:00+00:00",
        "exercise_completed_at": "2026-09-22T11:36:00+00:00",
        "source_revision": "1" * 40,
        "rollout_manifest_sha256": "b" * 64,
        "staging_evidence_sha256": "f" * 64,
        "review_sha256": "0" * 64,
        "checks": {
            "backup_restore": True,
            "temporal": True,
            "parallel_restart": True,
            "fan_in": True,
            "flag_rollback": True,
        },
        "rto_target_minutes": 60.0,
        "observed_restore_minutes": 36.0,
        "max_data_loss_seconds": 300.0,
        "observed_data_loss_seconds": 0.0,
        "references": {
            "incident": "incident-drill-001",
            "backup": "backup-001",
            "restore": "restore-001",
            "temporal_restart": "restart-001",
            "rollback": "rollback-001",
            "reviewer": "reviewer-001",
        },
        "gate_decision": "PASS",
        "failures": [],
    }


def operator():
    return {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T11:40:00+00:00",
        "breaches": [],
    }


def test_bounded_scale_review_qualifies_reviewed_growth():
    capacity_time = validate_capacity(capacity(), plan(), NOW)
    quality_time = validate_quality(quality(), plan(), NOW)
    economics_time = validate_economics(
        economics(),
        plan(),
        NOW,
        rollout_sha256="b" * 64,
        expected_source_revision="1" * 40,
    )
    incident_time = validate_incident_restore(
        incident_restore(),
        plan(),
        NOW,
        rollout_sha256="b" * 64,
        expected_source_revision="1" * 40,
    )
    validate_operator_status(
        operator(),
        plan(),
        not_before=max(
            capacity_time,
            quality_time,
            economics_time,
            incident_time,
        ),
        now=NOW,
    )
    result = evaluate_review(plan(), review())
    assert result["decision"] == "ELIGIBLE_FOR_BOUNDED_EXPANSION"
    assert result["max_allowed_next_users"] == 50
    assert result["failures"] == []


def test_bounded_scale_review_rejects_large_jump():
    value = review()
    value["proposed_max_users"] = 51
    result = evaluate_review(plan(), value)
    assert result["decision"] == "HOLD_AT_CURRENT_COHORT"
    assert any(item["metric"] == "proposed_max_users" for item in result["failures"])


def test_bounded_scale_review_requires_provider_headroom():
    value = review()
    value["provider_concurrency_quota"] = 14
    result = evaluate_review(plan(), value)
    assert result["decision"] == "HOLD_AT_CURRENT_COHORT"
    assert any(item["metric"] == "provider_concurrency_quota" for item in result["failures"])


def test_bounded_scale_review_requires_budget_and_oncall():
    value = review()
    value["approved_monthly_budget_usd"] = 850
    value["oncall_staffing_confirmed"] = False
    result = evaluate_review(plan(), value)
    names = {item["metric"] for item in result["failures"]}
    assert "approved_monthly_budget_usd" in names
    assert "oncall_staffing_confirmed" in names


def test_scale_review_rejects_offline_or_unbound_quality():
    value = quality()
    value["mode"] = "offline"
    with pytest.raises(ScaleReviewError, match="live quality"):
        validate_quality(value, plan(), NOW)

    value = quality()
    value["fixture_sha256"] = "not-a-hash"
    with pytest.raises(ScaleReviewError, match="fixture"):
        validate_quality(value, plan(), NOW)


def test_scale_review_requires_post_evidence_operator_health():
    value = operator()
    value["generated_at"] = "2026-09-22T11:25:00+00:00"
    with pytest.raises(ScaleReviewError, match="after capacity, quality, task economics and incident/restore"):
        validate_operator_status(
            value,
            plan(),
            not_before=datetime(2026, 9, 22, 11, 30, tzinfo=timezone.utc),
            now=NOW,
        )


def test_scale_review_rejects_stale_capacity():
    value = capacity()
    value["generated_at"] = "2026-09-20T11:20:00+00:00"
    with pytest.raises(ScaleReviewError, match="stale"):
        validate_capacity(value, plan(), NOW)


def test_scale_review_rejects_capacity_from_different_rollout():
    value = capacity()
    value["rollout_manifest_sha256"] = "a" * 64
    with pytest.raises(
        ScaleReviewError,
        match="does not bind the current rollout manifest",
    ):
        validate_capacity(
            value,
            plan(),
            NOW,
            rollout_sha256="b" * 64,
        )


def test_scale_review_output_carries_rollout_identity():
    result = evaluate_review(
        plan(),
        review(),
        rollout_manifest_sha256="c" * 64,
    )
    assert result["rollout_manifest_sha256"] == "c" * 64


def test_scale_review_rejects_quality_from_different_rollout():
    value = quality()
    value["rollout_manifest_sha256"] = "a" * 64
    with pytest.raises(
        ScaleReviewError,
        match="does not bind the current rollout manifest",
    ):
        validate_quality(
            value,
            plan(),
            NOW,
            rollout_sha256="b" * 64,
        )


def test_scale_review_accepts_rollout_bound_quality():
    value = quality()
    value["rollout_manifest_sha256"] = "b" * 64
    generated = validate_quality(
        value,
        plan(),
        NOW,
        rollout_sha256="b" * 64,
    )
    assert generated == datetime(2026, 9, 22, 11, 30, tzinfo=timezone.utc)



def test_scale_review_rejects_economics_from_different_rollout():
    value = economics()
    value["rollout_manifest_sha256"] = "a" * 64
    with pytest.raises(
        ScaleReviewError,
        match="does not bind the current rollout manifest",
    ):
        validate_economics(
            value,
            plan(),
            NOW,
            rollout_sha256="b" * 64,
            expected_source_revision="1" * 40,
        )


def test_scale_review_rejects_economics_from_different_source_revision():
    value = economics()
    with pytest.raises(ScaleReviewError, match="source revision"):
        validate_economics(
            value,
            plan(),
            NOW,
            rollout_sha256="b" * 64,
            expected_source_revision="2" * 40,
        )


def test_scale_review_requires_operator_health_after_economics():
    value = operator()
    value["generated_at"] = "2026-09-22T11:32:00+00:00"
    with pytest.raises(
        ScaleReviewError,
        match="after capacity, quality, task economics and incident/restore",
    ):
        validate_operator_status(
            value,
            plan(),
            not_before=datetime(2026, 9, 22, 11, 35, tzinfo=timezone.utc),
            now=NOW,
        )



def test_scale_review_rejects_stale_economics_samples_even_if_recompiled():
    value = economics()
    value["generated_at"] = "2026-09-22T11:50:00+00:00"
    value["samples_generated_at"] = "2026-09-20T11:34:00+00:00"
    with pytest.raises(ScaleReviewError, match="samples are stale"):
        validate_economics(
            value,
            plan(),
            NOW,
            rollout_sha256="b" * 64,
            expected_source_revision="1" * 40,
        )


def test_scale_review_rejects_incident_restore_from_different_source_revision():
    with pytest.raises(ScaleReviewError, match="source revision"):
        validate_incident_restore(
            incident_restore(),
            plan(),
            NOW,
            rollout_sha256="b" * 64,
            expected_source_revision="2" * 40,
        )


def test_scale_review_rejects_stale_incident_restore_exercise_even_if_recompiled():
    value = incident_restore()
    value["generated_at"] = "2026-09-22T11:50:00+00:00"
    value["exercise_started_at"] = "2026-09-20T10:00:00+00:00"
    value["exercise_completed_at"] = "2026-09-20T10:30:00+00:00"
    value["observed_restore_minutes"] = 30.0
    with pytest.raises(ScaleReviewError, match="exercise is stale"):
        validate_incident_restore(
            value,
            plan(),
            NOW,
            rollout_sha256="b" * 64,
            expected_source_revision="1" * 40,
        )
