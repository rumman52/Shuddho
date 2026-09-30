from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.task_economics_evidence import (
    TaskEconomicsEvidenceError,
    compile_task_economics_evidence,
    sha256_file,
    validate_task_economics_evidence,
)


RELEASE_ID = "coworker-cohort-001"
REVISION = "1" * 40


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def rollout(tmp_path):
    return write_json(tmp_path / "rollout.json", {
        "release_id": RELEASE_ID,
        "capabilities": {},
    })


def provider_policy(tmp_path):
    return write_json(tmp_path / "provider-policy.json", {
        "release_id": RELEASE_ID,
        "max_growth_ratio": 1.5,
        "runtime_quota_headroom_ratio": 1.25,
        "demand_headroom_ratio": 1.1,
        "max_workspace_concurrency_share": 0.25,
        "max_workspace_daily_token_share": 0.05,
        "max_budget_utilization_ratio": 0.8,
        "blended_token_cost_usd_per_million": 1.0,
        "days_per_month": 30,
        "task_token_budget": 100000,
        "planner_call_token_budget": 8000,
        "model_timeout_seconds": 90,
        "lease_margin_seconds": 30,
        "current": {
            "provider_max_concurrent_calls": 8,
            "provider_max_concurrent_per_workspace": 2,
            "provider_max_reserved_tokens": 800000,
            "provider_max_reserved_tokens_per_workspace": 200000,
            "provider_daily_token_budget": 5000000,
            "daily_token_budget": 500000,
            "provider_lease_seconds": 120,
        },
    })


def pricing(tmp_path, *, budget=5000):
    return write_json(tmp_path / "pricing.json", {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "min_completed_tasks": 2,
        "max_cost_microusd_per_completed_task": budget,
        "search_microusd_per_credit": 100,
        "sandbox_microusd_per_second": 2,
        "render_microusd_per_operation": 10,
        "storage_microusd_per_gib_hour": 5,
        "notification_microusd_per_attempt": 3,
        "review_reference": "cost-review-42",
    })


def samples(tmp_path, *, revision=REVISION, second_notification_attempts=2):
    now = datetime.now(timezone.utc) - timedelta(minutes=2)
    return write_json(tmp_path / "samples.json", {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "source_revision": revision,
        "generated_at": now.isoformat(),
        "tasks": [
            {
                "task_reference": "task-redacted-001",
                "task_kind": "research_report",
                "language": "bn",
                "state": "completed",
                "usage": {
                    "model_tokens": 1000,
                    "search_credits": 1,
                    "sandbox_milliseconds": 0,
                    "render_operations": 2,
                    "storage_byte_hours": 1073741824,
                    "notification_attempts": 1,
                    "retry_count": 0,
                },
            },
            {
                "task_reference": "task-redacted-002",
                "task_kind": "sandbox_analysis",
                "language": "en",
                "state": "completed",
                "usage": {
                    "model_tokens": 2000,
                    "search_credits": 0,
                    "sandbox_milliseconds": 2500,
                    "render_operations": 1,
                    "storage_byte_hours": 536870912,
                    "notification_attempts": second_notification_attempts,
                    "retry_count": 2,
                },
            },
        ],
    })


def compile_value(tmp_path, *, budget=5000, second_notification_attempts=2):
    return compile_task_economics_evidence(
        rollout_path=rollout(tmp_path),
        provider_policy_plan_path=provider_policy(tmp_path),
        pricing_plan_path=pricing(tmp_path, budget=budget),
        samples_path=samples(
            tmp_path,
            second_notification_attempts=second_notification_attempts,
        ),
    )


def test_task_economics_compiles_all_categories_and_retries(tmp_path):
    value = compile_value(tmp_path)
    assert value["gate_decision"] == "PASS"
    assert value["completed_tasks"] == 2
    assert value["total_retries"] == 2
    assert value["category_coverage"] == {
        "model": True,
        "search": True,
        "sandbox": True,
        "render": True,
        "storage": True,
        "notification": True,
    }
    assert value["category_cost_microusd"]["model"] == 3000
    assert value["category_cost_microusd"]["search"] == 100
    assert value["category_cost_microusd"]["sandbox"] == 5
    assert value["category_cost_microusd"]["render"] == 30
    assert value["category_cost_microusd"]["storage"] == 8
    assert value["category_cost_microusd"]["notification"] == 9
    assert value["max_cost_microusd"] <= value["budget_microusd_per_completed_task"]


def test_task_economics_rejects_missing_required_category(tmp_path):
    sample_path = samples(tmp_path, second_notification_attempts=0)
    value = json.loads(sample_path.read_text(encoding="utf-8"))
    value["tasks"][0]["usage"]["notification_attempts"] = 0
    write_json(sample_path, value)
    with pytest.raises(TaskEconomicsEvidenceError, match="notification"):
        compile_task_economics_evidence(
            rollout_path=rollout(tmp_path),
            provider_policy_plan_path=provider_policy(tmp_path),
            pricing_plan_path=pricing(tmp_path),
            samples_path=sample_path,
        )


def test_task_economics_rejects_any_over_budget_task(tmp_path):
    with pytest.raises(TaskEconomicsEvidenceError, match="exceeds the reviewed per-task budget"):
        compile_value(tmp_path, budget=1000)


def test_task_economics_rejects_duplicate_task_reference(tmp_path):
    sample_path = samples(tmp_path)
    value = json.loads(sample_path.read_text(encoding="utf-8"))
    value["tasks"][1]["task_reference"] = value["tasks"][0]["task_reference"]
    write_json(sample_path, value)
    with pytest.raises(TaskEconomicsEvidenceError, match="must be unique"):
        compile_task_economics_evidence(
            rollout_path=rollout(tmp_path),
            provider_policy_plan_path=provider_policy(tmp_path),
            pricing_plan_path=pricing(tmp_path),
            samples_path=sample_path,
        )


def test_task_economics_rejects_non_completed_samples(tmp_path):
    sample_path = samples(tmp_path)
    value = json.loads(sample_path.read_text(encoding="utf-8"))
    value["tasks"][0]["state"] = "failed"
    write_json(sample_path, value)
    with pytest.raises(TaskEconomicsEvidenceError, match="only completed tasks"):
        compile_task_economics_evidence(
            rollout_path=rollout(tmp_path),
            provider_policy_plan_path=provider_policy(tmp_path),
            pricing_plan_path=pricing(tmp_path),
            samples_path=sample_path,
        )


def test_task_economics_binds_rollout_source_and_inputs(tmp_path):
    rollout_path = rollout(tmp_path)
    provider_path = provider_policy(tmp_path)
    pricing_path = pricing(tmp_path)
    samples_path = samples(tmp_path)
    value = compile_task_economics_evidence(
        rollout_path=rollout_path,
        provider_policy_plan_path=provider_path,
        pricing_plan_path=pricing_path,
        samples_path=samples_path,
    )
    assert value["rollout_manifest_sha256"] == sha256_file(rollout_path)
    assert value["provider_policy_plan_sha256"] == sha256_file(provider_path)
    assert value["pricing_plan_sha256"] == sha256_file(pricing_path)
    assert value["samples_sha256"] == sha256_file(samples_path)
    assert value["source_revision"] == REVISION

    validate_task_economics_evidence(
        value,
        release_id=RELEASE_ID,
        rollout_sha256=sha256_file(rollout_path),
        expected_source_revision=REVISION,
    )

    with pytest.raises(TaskEconomicsEvidenceError, match="current rollout"):
        validate_task_economics_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256="f" * 64,
            expected_source_revision=REVISION,
        )
    with pytest.raises(TaskEconomicsEvidenceError, match="source revision"):
        validate_task_economics_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256=sha256_file(rollout_path),
            expected_source_revision="2" * 40,
        )


def test_task_economics_rejects_tampered_budget_summary(tmp_path):
    value = compile_value(tmp_path)
    value["budget_microusd_per_completed_task"] = value["max_cost_microusd"] - 1
    with pytest.raises(TaskEconomicsEvidenceError, match="maximum cost exceeds"):
        validate_task_economics_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256=value["rollout_manifest_sha256"],
            expected_source_revision=REVISION,
        )


def test_task_economics_rejects_future_evidence(tmp_path):
    value = compile_value(tmp_path)
    value["generated_at"] = (
        datetime.now(timezone.utc) + timedelta(minutes=10)
    ).isoformat()
    with pytest.raises(TaskEconomicsEvidenceError, match="future"):
        validate_task_economics_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256=value["rollout_manifest_sha256"],
            expected_source_revision=REVISION,
        )
