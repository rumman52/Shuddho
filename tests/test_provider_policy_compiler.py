from scripts.provider_policy_compiler import compile_policy


def plan():
    return {
        "release_id": "coworker-cohort-001",
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
    }


def decision():
    return {
        "decision": "ELIGIBLE_FOR_BOUNDED_EXPANSION",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "proposed_stage": "cohort-40",
        "proposed_max_users": 40,
        "failures": [],
        "artifact_sha256": {"review": "a" * 64, "capacity_qualification": "b" * 64},
    }


def review():
    return {
        "release_id": "coworker-cohort-001",
        "proposed_stage": "cohort-40",
        "proposed_max_users": 40,
        "projected_peak_concurrency": 8,
        "provider_concurrency_quota": 20,
        "estimated_monthly_cost_usd": 150,
        "approved_monthly_budget_usd": 300,
    }


def capacity():
    return {
        "decision": "ELIGIBLE_FOR_CAPACITY_REVIEW",
        "release_id": "coworker-cohort-001",
        "final_stage": "cohort-25",
        "failures": [],
        "summary": {
            "live_provider": {
                "offered_concurrency": 15,
                "average_tokens_per_completed_task": 6000,
            }
        },
    }


def test_policy_compiler_proposes_bounded_measured_policy():
    value = compile_policy(plan(), decision(), review(), capacity())
    assert value["decision"] == "ELIGIBLE_FOR_POLICY_REVIEW"
    assert value["proposed_policy"]["provider_max_concurrent_calls"] == 12
    assert value["proposed_policy"]["provider_max_concurrent_per_workspace"] == 3
    assert value["proposed_policy"]["provider_max_reserved_tokens"] == 1200000
    assert value["proposed_policy"]["provider_daily_token_budget"] == 7500000
    assert value["proposed_policy"]["daily_token_budget"] == 375000
    assert value["environment"]["SHUDDHO_PROVIDER_MAX_CONCURRENT_CALLS"] == "12"


def test_policy_compiler_holds_when_budget_cannot_cover_reviewed_demand():
    r = review()
    r["estimated_monthly_cost_usd"] = 290
    value = compile_policy(plan(), decision(), r, capacity())
    assert value["decision"] == "HOLD_CURRENT_POLICY"
    assert any(item["metric"] == "estimated_monthly_cost_usd" for item in value["failures"])


def test_policy_compiler_holds_when_quota_cannot_meet_demand_headroom():
    r = review()
    r["projected_peak_concurrency"] = 12
    r["provider_concurrency_quota"] = 12
    value = compile_policy(plan(), decision(), r, capacity())
    assert value["decision"] == "HOLD_CURRENT_POLICY"
    assert any(item["metric"] == "provider_max_concurrent_calls" for item in value["failures"])


def test_policy_compiler_never_jumps_past_growth_bound():
    p = plan()
    r = review()
    r["provider_concurrency_quota"] = 100
    c = capacity()
    c["summary"]["live_provider"]["offered_concurrency"] = 100
    value = compile_policy(p, decision(), r, c)
    assert value["proposed_policy"]["provider_max_concurrent_calls"] <= 12


def test_policy_compiler_preserves_workspace_fairness():
    p = plan()
    p["max_workspace_concurrency_share"] = 0.2
    value = compile_policy(p, decision(), review(), capacity())
    assert value["proposed_policy"]["provider_max_concurrent_per_workspace"] <= 3
    assert value["proposed_policy"]["daily_token_budget"] <= (
        value["proposed_policy"]["provider_daily_token_budget"] * 0.05
    )
