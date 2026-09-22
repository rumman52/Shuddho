from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


PLAN_KEYS = {
    "release_id",
    "max_growth_ratio",
    "runtime_quota_headroom_ratio",
    "demand_headroom_ratio",
    "max_workspace_concurrency_share",
    "max_workspace_daily_token_share",
    "max_budget_utilization_ratio",
    "blended_token_cost_usd_per_million",
    "days_per_month",
    "task_token_budget",
    "planner_call_token_budget",
    "model_timeout_seconds",
    "lease_margin_seconds",
    "current",
}
CURRENT_KEYS = {
    "provider_max_concurrent_calls",
    "provider_max_concurrent_per_workspace",
    "provider_max_reserved_tokens",
    "provider_max_reserved_tokens_per_workspace",
    "provider_daily_token_budget",
    "daily_token_budget",
    "provider_lease_seconds",
}


class ProviderPolicyError(RuntimeError):
    pass


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProviderPolicyError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise ProviderPolicyError(f"{label} must contain a JSON object.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def positive_number(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ProviderPolicyError(f"{label} must be a positive finite number.")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ProviderPolicyError(f"{label} must be a positive finite number.")
    return result


def positive_int(value, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProviderPolicyError(f"{label} must be a positive integer.")
    return value


def fraction(value, label: str) -> float:
    result = positive_number(value, label)
    if result > 1:
        raise ProviderPolicyError(f"{label} must be at most 1.0.")
    return result


def load_plan(path: Path) -> dict:
    value = load_json(path, "provider policy plan")
    if set(value) != PLAN_KEYS:
        raise ProviderPolicyError("Provider policy plan has an unexpected schema.")
    if not isinstance(value["release_id"], str) or not value["release_id"].strip():
        raise ProviderPolicyError("release_id is required.")
    if positive_number(value["max_growth_ratio"], "max_growth_ratio") <= 1:
        raise ProviderPolicyError("max_growth_ratio must be greater than 1.0.")
    if positive_number(value["runtime_quota_headroom_ratio"], "runtime_quota_headroom_ratio") < 1:
        raise ProviderPolicyError("runtime_quota_headroom_ratio must be at least 1.0.")
    if positive_number(value["demand_headroom_ratio"], "demand_headroom_ratio") < 1:
        raise ProviderPolicyError("demand_headroom_ratio must be at least 1.0.")
    fraction(value["max_workspace_concurrency_share"], "max_workspace_concurrency_share")
    fraction(value["max_workspace_daily_token_share"], "max_workspace_daily_token_share")
    fraction(value["max_budget_utilization_ratio"], "max_budget_utilization_ratio")
    positive_number(
        value["blended_token_cost_usd_per_million"],
        "blended_token_cost_usd_per_million",
    )
    positive_int(value["days_per_month"], "days_per_month")
    positive_int(value["task_token_budget"], "task_token_budget")
    positive_int(value["planner_call_token_budget"], "planner_call_token_budget")
    positive_int(value["model_timeout_seconds"], "model_timeout_seconds")
    positive_int(value["lease_margin_seconds"], "lease_margin_seconds")
    current = value["current"]
    if not isinstance(current, dict) or set(current) != CURRENT_KEYS:
        raise ProviderPolicyError("current provider policy has an unexpected schema.")
    for key in CURRENT_KEYS:
        positive_int(current[key], f"current.{key}")
    return value


def validate_inputs(plan: dict, decision: dict, review: dict, capacity: dict) -> None:
    release_id = plan["release_id"]
    for label, value in (
        ("scale decision", decision),
        ("scale review request", review),
        ("capacity qualification", capacity),
    ):
        if value.get("release_id") != release_id:
            raise ProviderPolicyError(f"{label} release_id does not match.")

    if decision.get("decision") != "ELIGIBLE_FOR_BOUNDED_EXPANSION":
        raise ProviderPolicyError("Scale decision is not eligible for bounded expansion.")
    if decision.get("failures") != []:
        raise ProviderPolicyError("Scale decision contains failures.")
    if capacity.get("decision") != "ELIGIBLE_FOR_CAPACITY_REVIEW":
        raise ProviderPolicyError("Capacity qualification is not eligible for review.")
    if capacity.get("failures") != []:
        raise ProviderPolicyError("Capacity qualification contains failures.")
    if capacity.get("final_stage") != decision.get("current_stage"):
        raise ProviderPolicyError(
            "Capacity qualification does not describe the scale decision's current stage."
        )

    if review.get("proposed_stage") != decision.get("proposed_stage"):
        raise ProviderPolicyError("Scale review proposed_stage does not match the decision.")
    if review.get("proposed_max_users") != decision.get("proposed_max_users"):
        raise ProviderPolicyError("Scale review proposed_max_users does not match the decision.")

    bound = decision.get("artifact_sha256")
    if not isinstance(bound, dict):
        raise ProviderPolicyError("Scale decision is missing artifact hashes.")


def compile_policy(plan: dict, decision: dict, review: dict, capacity: dict) -> dict:
    validate_inputs(plan, decision, review, capacity)

    current = plan["current"]
    projected = positive_number(
        review.get("projected_peak_concurrency"),
        "review.projected_peak_concurrency",
    )
    provider_quota = positive_number(
        review.get("provider_concurrency_quota"),
        "review.provider_concurrency_quota",
    )
    estimated_cost = positive_number(
        review.get("estimated_monthly_cost_usd"),
        "review.estimated_monthly_cost_usd",
    )
    approved_budget = positive_number(
        review.get("approved_monthly_budget_usd"),
        "review.approved_monthly_budget_usd",
    )
    proposed_users = positive_int(
        decision.get("proposed_max_users"),
        "decision.proposed_max_users",
    )

    summary = capacity.get("summary")
    live = summary.get("live_provider") if isinstance(summary, dict) else None
    if not isinstance(live, dict):
        raise ProviderPolicyError("Capacity qualification has no live-provider summary.")
    tested_concurrency = positive_int(
        live.get("offered_concurrency"),
        "capacity.live_provider.offered_concurrency",
    )
    measured_average_tokens = positive_number(
        live.get("average_tokens_per_completed_task"),
        "capacity.live_provider.average_tokens_per_completed_task",
    )

    failures = []

    def fail(metric: str, actual, threshold, reason: str) -> None:
        failures.append({
            "metric": metric,
            "actual": actual,
            "threshold": threshold,
            "reason": reason,
        })

    budget_ceiling = approved_budget * plan["max_budget_utilization_ratio"]
    if estimated_cost > budget_ceiling:
        fail(
            "estimated_monthly_cost_usd",
            estimated_cost,
            round(budget_ceiling, 2),
            "Estimated monthly cost exceeds the runtime policy's approved budget utilization ceiling.",
        )

    demand_floor = math.ceil(projected * plan["demand_headroom_ratio"])
    quota_ceiling = math.floor(provider_quota / plan["runtime_quota_headroom_ratio"])
    concurrency_growth_ceiling = math.floor(
        current["provider_max_concurrent_calls"] * plan["max_growth_ratio"]
    )
    max_call_reservation = max(
        plan["task_token_budget"],
        plan["planner_call_token_budget"],
    )
    reserve_growth_ceiling = math.floor(
        current["provider_max_reserved_tokens"] * plan["max_growth_ratio"]
    )
    reserve_concurrency_ceiling = reserve_growth_ceiling // max_call_reservation

    target_concurrency = min(
        tested_concurrency,
        quota_ceiling,
        concurrency_growth_ceiling,
        reserve_concurrency_ceiling,
    )
    if target_concurrency < demand_floor:
        fail(
            "provider_max_concurrent_calls",
            target_concurrency,
            demand_floor,
            "Measured/tested/provider-budget bounds cannot provide the required demand headroom.",
        )

    target_concurrency = max(1, target_concurrency)
    workspace_concurrency = max(
        1,
        min(
            target_concurrency,
            math.ceil(
                target_concurrency * plan["max_workspace_concurrency_share"]
            ),
            math.floor(
                current["provider_max_concurrent_per_workspace"]
                * plan["max_growth_ratio"]
            ),
        ),
    )

    global_reserved = target_concurrency * max_call_reservation
    workspace_reserved = workspace_concurrency * max_call_reservation

    token_price = plan["blended_token_cost_usd_per_million"]
    estimated_daily_tokens = math.ceil(
        estimated_cost / token_price * 1_000_000 / plan["days_per_month"]
    )
    budget_daily_token_ceiling = math.floor(
        approved_budget
        * plan["max_budget_utilization_ratio"]
        / token_price
        * 1_000_000
        / plan["days_per_month"]
    )
    daily_growth_ceiling = math.floor(
        current["provider_daily_token_budget"] * plan["max_growth_ratio"]
    )
    provider_daily_budget = min(
        budget_daily_token_ceiling,
        daily_growth_ceiling,
    )
    if provider_daily_budget < estimated_daily_tokens:
        fail(
            "provider_daily_token_budget",
            provider_daily_budget,
            estimated_daily_tokens,
            "The bounded daily provider-token budget cannot cover the reviewed monthly demand estimate.",
        )

    workspace_daily_budget = max(
        1,
        min(
            math.floor(
                provider_daily_budget
                * plan["max_workspace_daily_token_share"]
            ),
            math.floor(
                current["daily_token_budget"] * plan["max_growth_ratio"]
            ),
        ),
    )
    fair_average_daily = max(1, provider_daily_budget // proposed_users)
    if workspace_daily_budget < fair_average_daily:
        fail(
            "daily_token_budget",
            workspace_daily_budget,
            fair_average_daily,
            "Per-workspace daily budget would be below the average fair share of the reviewed stage.",
        )

    lease_seconds = max(
        current["provider_lease_seconds"],
        plan["model_timeout_seconds"] + plan["lease_margin_seconds"],
    )

    proposed = {
        "provider_max_concurrent_calls": target_concurrency,
        "provider_max_concurrent_per_workspace": workspace_concurrency,
        "provider_max_reserved_tokens": global_reserved,
        "provider_max_reserved_tokens_per_workspace": workspace_reserved,
        "provider_daily_token_budget": provider_daily_budget,
        "daily_token_budget": workspace_daily_budget,
        "provider_lease_seconds": lease_seconds,
    }
    lower = [key for key in proposed if proposed[key] < current[key]]
    higher = [key for key in proposed if proposed[key] > current[key]]
    direction = "reduce" if lower else "increase" if higher else "hold"

    return {
        "decision": (
            "ELIGIBLE_FOR_POLICY_REVIEW" if not failures
            else "HOLD_CURRENT_POLICY"
        ),
        "release_id": plan["release_id"],
        "current_stage": decision["current_stage"],
        "proposed_stage": decision["proposed_stage"],
        "proposed_max_users": proposed_users,
        "direction": direction,
        "failures": failures,
        "evidence": {
            "projected_peak_concurrency": projected,
            "tested_live_concurrency": tested_concurrency,
            "provider_concurrency_quota": provider_quota,
            "measured_average_tokens_per_task": measured_average_tokens,
            "estimated_monthly_cost_usd": estimated_cost,
            "approved_monthly_budget_usd": approved_budget,
            "budget_utilization_ceiling_usd": round(budget_ceiling, 2),
            "estimated_daily_tokens": estimated_daily_tokens,
            "budget_daily_token_ceiling": budget_daily_token_ceiling,
        },
        "current_policy": current,
        "proposed_policy": proposed,
        "environment": {
            "SHUDDHO_PROVIDER_MAX_CONCURRENT_CALLS": str(
                proposed["provider_max_concurrent_calls"]
            ),
            "SHUDDHO_PROVIDER_MAX_CONCURRENT_PER_WORKSPACE": str(
                proposed["provider_max_concurrent_per_workspace"]
            ),
            "SHUDDHO_PROVIDER_MAX_RESERVED_TOKENS": str(
                proposed["provider_max_reserved_tokens"]
            ),
            "SHUDDHO_PROVIDER_MAX_RESERVED_TOKENS_PER_WORKSPACE": str(
                proposed["provider_max_reserved_tokens_per_workspace"]
            ),
            "SHUDDHO_PROVIDER_DAILY_TOKEN_BUDGET": str(
                proposed["provider_daily_token_budget"]
            ),
            "SHUDDHO_COWORKER_DAILY_TOKENS": str(
                proposed["daily_token_budget"]
            ),
            "SHUDDHO_PROVIDER_LEASE_SECONDS": str(
                proposed["provider_lease_seconds"]
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile a bounded Shuddho provider quota/cost policy from measured scale evidence."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--scale-decision", type=Path, required=True)
    parser.add_argument("--scale-review", type=Path, required=True)
    parser.add_argument("--capacity-qualification", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        plan = load_plan(args.plan)
        decision = load_json(args.scale_decision, "scale decision")
        review = load_json(args.scale_review, "scale review request")
        capacity = load_json(
            args.capacity_qualification,
            "capacity qualification",
        )
        validate_inputs(plan, decision, review, capacity)
        bound = decision["artifact_sha256"]
        if bound.get("review") != sha256_file(args.scale_review):
            raise ProviderPolicyError(
                "Scale decision does not bind this scale-review request."
            )
        if bound.get("capacity_qualification") != sha256_file(
            args.capacity_qualification
        ):
            raise ProviderPolicyError(
                "Scale decision does not bind this capacity qualification."
            )
        result = compile_policy(plan, decision, review, capacity)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["artifact_sha256"] = {
            "plan": sha256_file(args.plan),
            "scale_decision": sha256_file(args.scale_decision),
            "scale_review": sha256_file(args.scale_review),
            "capacity_qualification": sha256_file(
                args.capacity_qualification
            ),
        }
        args.output.write_text(
            json.dumps(result, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "written": str(args.output),
            "decision": result["decision"],
            "direction": result["direction"],
            "failures": len(result["failures"]),
        }, indent=2))
        if result["decision"] != "ELIGIBLE_FOR_POLICY_REVIEW":
            raise SystemExit("Provider policy is not eligible for deployment review.")
    except (ProviderPolicyError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
