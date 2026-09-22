from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

PLAN_KEYS = {
    "release_id",
    "current_stage",
    "current_max_users",
    "max_growth_ratio",
    "freshness_minutes",
    "min_quality_pass_rate",
    "min_fact_recall",
    "min_provider_headroom_ratio",
    "min_budget_headroom_ratio",
    "min_error_budget_remaining_ratio",
}
REVIEW_KEYS = {
    "release_id",
    "proposed_stage",
    "proposed_max_users",
    "projected_peak_concurrency",
    "provider_concurrency_quota",
    "estimated_monthly_cost_usd",
    "approved_monthly_budget_usd",
    "error_budget_remaining_ratio",
    "oncall_staffing_confirmed",
    "demand_reference",
    "provider_quota_reference",
    "budget_reference",
    "oncall_reference",
    "change_reference",
}


class ScaleReviewError(RuntimeError):
    pass


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ScaleReviewError(f"{label} must be an ISO-8601 timestamp.") from None
    if result.tzinfo is None:
        raise ScaleReviewError(f"{label} must include a timezone.")
    return result.astimezone(timezone.utc)


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ScaleReviewError(f"Could not read {label}: {type(error).__name__}") from None
    if not isinstance(value, dict):
        raise ScaleReviewError(f"{label} must contain a JSON object.")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def positive_number(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ScaleReviewError(f"{label} must be a positive finite number.")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ScaleReviewError(f"{label} must be a positive finite number.")
    return number


def ratio(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ScaleReviewError(f"{label} must be between 0 and 1.")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ScaleReviewError(f"{label} must be between 0 and 1.")
    return number


def positive_int(value, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ScaleReviewError(f"{label} must be a positive integer.")
    return value


def text_ref(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ScaleReviewError(f"{label} must be a non-empty reference up to 500 characters.")
    return value.strip()


def load_plan(path: Path) -> dict:
    value = load_json(path, "scale-review plan")
    if set(value) != PLAN_KEYS:
        raise ScaleReviewError("Scale-review plan has an unexpected schema.")
    text_ref(value["release_id"], "release_id")
    text_ref(value["current_stage"], "current_stage")
    positive_int(value["current_max_users"], "current_max_users")
    growth = positive_number(value["max_growth_ratio"], "max_growth_ratio")
    if growth <= 1:
        raise ScaleReviewError("max_growth_ratio must be greater than 1.0.")
    positive_int(value["freshness_minutes"], "freshness_minutes")
    ratio(value["min_quality_pass_rate"], "min_quality_pass_rate")
    ratio(value["min_fact_recall"], "min_fact_recall")
    if positive_number(value["min_provider_headroom_ratio"], "min_provider_headroom_ratio") < 1:
        raise ScaleReviewError("min_provider_headroom_ratio must be at least 1.0.")
    if positive_number(value["min_budget_headroom_ratio"], "min_budget_headroom_ratio") < 1:
        raise ScaleReviewError("min_budget_headroom_ratio must be at least 1.0.")
    ratio(value["min_error_budget_remaining_ratio"], "min_error_budget_remaining_ratio")
    return value


def load_review(path: Path, release_id: str) -> dict:
    value = load_json(path, "scale-review request")
    if set(value) != REVIEW_KEYS:
        raise ScaleReviewError("Scale-review request has an unexpected schema.")
    if value["release_id"] != release_id:
        raise ScaleReviewError("Scale-review request release_id does not match.")
    text_ref(value["proposed_stage"], "proposed_stage")
    positive_int(value["proposed_max_users"], "proposed_max_users")
    positive_number(value["projected_peak_concurrency"], "projected_peak_concurrency")
    positive_number(value["provider_concurrency_quota"], "provider_concurrency_quota")
    positive_number(value["estimated_monthly_cost_usd"], "estimated_monthly_cost_usd")
    positive_number(value["approved_monthly_budget_usd"], "approved_monthly_budget_usd")
    ratio(value["error_budget_remaining_ratio"], "error_budget_remaining_ratio")
    if not isinstance(value["oncall_staffing_confirmed"], bool):
        raise ScaleReviewError("oncall_staffing_confirmed must be boolean.")
    for key in (
        "demand_reference",
        "provider_quota_reference",
        "budget_reference",
        "oncall_reference",
        "change_reference",
    ):
        text_ref(value[key], key)
    return value


def require_fresh(value: dict, *, label: str, freshness_minutes: int, now: datetime) -> datetime:
    generated_at = value.get("generated_at")
    if not isinstance(generated_at, str):
        raise ScaleReviewError(f"{label} has no generated_at timestamp.")
    generated = parse_time(generated_at, f"{label}.generated_at")
    age_minutes = (now - generated).total_seconds() / 60
    if age_minutes < -1:
        raise ScaleReviewError(f"{label} is from the future.")
    if age_minutes > freshness_minutes:
        raise ScaleReviewError(f"{label} is stale ({age_minutes:.1f} minutes old).")
    return generated


def validate_capacity(value: dict, plan: dict, now: datetime) -> datetime:
    if value.get("release_id") != plan["release_id"]:
        raise ScaleReviewError("Capacity qualification release_id does not match.")
    if value.get("decision") != "ELIGIBLE_FOR_CAPACITY_REVIEW":
        raise ScaleReviewError("Capacity qualification is not eligible for review.")
    if value.get("final_stage") != plan["current_stage"]:
        raise ScaleReviewError("Capacity qualification final_stage does not match the current scale stage.")
    if value.get("failures") != []:
        raise ScaleReviewError("Capacity qualification contains failures.")
    return require_fresh(
        value,
        label="capacity qualification",
        freshness_minutes=plan["freshness_minutes"],
        now=now,
    )


def validate_quality(value: dict, plan: dict, now: datetime) -> datetime:
    if value.get("release_id") != plan["release_id"]:
        raise ScaleReviewError("Quality evaluation release_id does not match.")
    if value.get("mode") != "live":
        raise ScaleReviewError("Scale review requires a live quality evaluation.")
    if value.get("gate_decision") != "PASS" or value.get("failures") != [] or value.get("gate_failures") != []:
        raise ScaleReviewError("Live quality evaluation did not pass cleanly.")
    pass_rate = ratio(value.get("pass_rate"), "quality.pass_rate")
    fact_recall = ratio(value.get("required_fact_recall"), "quality.required_fact_recall")
    if pass_rate < plan["min_quality_pass_rate"]:
        raise ScaleReviewError("Live quality pass rate is below the scale-review threshold.")
    if fact_recall < plan["min_fact_recall"]:
        raise ScaleReviewError("Live quality fact recall is below the scale-review threshold.")
    fixture_hash = value.get("fixture_sha256")
    if not isinstance(fixture_hash, str) or len(fixture_hash) != 64 or any(c not in "0123456789abcdef" for c in fixture_hash):
        raise ScaleReviewError("Live quality evaluation must bind the evaluated fixture by SHA-256.")
    text_ref(value.get("provider_model"), "quality.provider_model")
    return require_fresh(
        value,
        label="quality evaluation",
        freshness_minutes=plan["freshness_minutes"],
        now=now,
    )


def validate_operator_status(value: dict, plan: dict, *, not_before: datetime, now: datetime) -> datetime:
    if value.get("release_id") != plan["release_id"]:
        raise ScaleReviewError("Operator status release_id does not match.")
    if value.get("decision") != "CONTINUE_COHORT" or value.get("breaches") != []:
        raise ScaleReviewError("Operator status must be CONTINUE_COHORT with zero breaches.")
    generated = require_fresh(
        value,
        label="operator status",
        freshness_minutes=plan["freshness_minutes"],
        now=now,
    )
    if generated < not_before:
        raise ScaleReviewError("Operator status must be generated after capacity and quality evidence.")
    return generated


def evaluate_review(plan: dict, review: dict) -> dict:
    failures = []

    def fail(metric: str, actual, threshold, reason: str) -> None:
        failures.append({
            "metric": metric,
            "actual": actual,
            "threshold": threshold,
            "reason": reason,
        })

    current_users = plan["current_max_users"]
    proposed_users = review["proposed_max_users"]
    max_next_users = math.floor(current_users * plan["max_growth_ratio"])
    if proposed_users <= current_users:
        fail("proposed_max_users", proposed_users, f">{current_users}", "Proposed cohort must be larger than the current cohort.")
    if proposed_users > max_next_users:
        fail("proposed_max_users", proposed_users, max_next_users, "Proposed cohort exceeds the reviewed maximum growth ratio.")
    if review["proposed_stage"] == plan["current_stage"]:
        fail("proposed_stage", review["proposed_stage"], "new stage", "Proposed stage must differ from the current stage.")

    required_provider_quota = math.ceil(
        review["projected_peak_concurrency"] * plan["min_provider_headroom_ratio"]
    )
    if review["provider_concurrency_quota"] < required_provider_quota:
        fail(
            "provider_concurrency_quota",
            review["provider_concurrency_quota"],
            required_provider_quota,
            "Provider concurrency quota lacks the required projected-demand headroom.",
        )

    required_budget = round(
        review["estimated_monthly_cost_usd"] * plan["min_budget_headroom_ratio"], 2
    )
    if review["approved_monthly_budget_usd"] < required_budget:
        fail(
            "approved_monthly_budget_usd",
            review["approved_monthly_budget_usd"],
            required_budget,
            "Approved monthly budget lacks the required cost headroom.",
        )

    if review["error_budget_remaining_ratio"] < plan["min_error_budget_remaining_ratio"]:
        fail(
            "error_budget_remaining_ratio",
            review["error_budget_remaining_ratio"],
            plan["min_error_budget_remaining_ratio"],
            "Remaining reliability error budget is below the scale-review floor.",
        )
    if not review["oncall_staffing_confirmed"]:
        fail(
            "oncall_staffing_confirmed",
            False,
            True,
            "Expansion requires confirmed operational staffing.",
        )

    return {
        "decision": "ELIGIBLE_FOR_BOUNDED_EXPANSION" if not failures else "HOLD_AT_CURRENT_COHORT",
        "release_id": plan["release_id"],
        "current_stage": plan["current_stage"],
        "current_max_users": current_users,
        "proposed_stage": review["proposed_stage"],
        "proposed_max_users": proposed_users,
        "max_allowed_next_users": max_next_users,
        "required_provider_concurrency_quota": required_provider_quota,
        "required_monthly_budget_usd": required_budget,
        "failures": failures,
        "references": {
            key: review[key]
            for key in (
                "demand_reference",
                "provider_quota_reference",
                "budget_reference",
                "oncall_reference",
                "change_reference",
            )
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review a human-proposed next Shuddho Coworker cohort after the 25-user capacity and quality gates."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--capacity-qualification", type=Path, required=True)
    parser.add_argument("--quality-eval", type=Path, required=True)
    parser.add_argument("--operator-status", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        plan = load_plan(args.plan)
        review = load_review(args.review, plan["release_id"])
        capacity = load_json(args.capacity_qualification, "capacity qualification")
        quality = load_json(args.quality_eval, "quality evaluation")
        operator = load_json(args.operator_status, "operator status")
        now = datetime.now(timezone.utc)
        capacity_time = validate_capacity(capacity, plan, now)
        quality_time = validate_quality(quality, plan, now)
        operator_time = validate_operator_status(
            operator,
            plan,
            not_before=max(capacity_time, quality_time),
            now=now,
        )
        result = evaluate_review(plan, review)
        result["generated_at"] = now.isoformat()
        result["operator_status_generated_at"] = operator_time.isoformat()
        result["artifact_sha256"] = {
            "plan": sha256_file(args.plan),
            "review": sha256_file(args.review),
            "capacity_qualification": sha256_file(args.capacity_qualification),
            "quality_eval": sha256_file(args.quality_eval),
            "operator_status": sha256_file(args.operator_status),
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "decision": result["decision"],
            "failures": len(result["failures"]),
        }, indent=2))
        if result["decision"] != "ELIGIBLE_FOR_BOUNDED_EXPANSION":
            raise SystemExit("Bounded cohort scale review did not qualify.")
    except (ScaleReviewError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
