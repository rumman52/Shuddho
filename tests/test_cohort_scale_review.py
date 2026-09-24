from datetime import datetime, timezone

import pytest

from scripts.cohort_scale_review import (
    ScaleReviewError,
    evaluate_review,
    validate_capacity,
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
    validate_operator_status(
        operator(),
        plan(),
        not_before=max(capacity_time, quality_time),
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
    with pytest.raises(ScaleReviewError, match="after capacity and quality"):
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
