from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

REPORT_KEYS = {
    "schema_version",
    "release_id",
    "kind",
    "generated_at",
    "duration_seconds",
    "accounts",
    "offered_concurrency",
    "submitted",
    "completed",
    "failed",
    "rejected",
    "submit_p95_ms",
    "submit_p99_ms",
    "completion_p95_ms",
    "completion_p99_ms",
    "max_queue_age_seconds",
    "provider_samples",
    "provider_failed",
    "provider_p95_latency_ms",
    "total_tokens",
}
PLAN_KEYS = {
    "release_id",
    "final_stage",
    "freshness_minutes",
    "expected_peak_concurrency",
    "min_reserve_ratio",
    "simulated",
    "live_provider",
}
SIM_KEYS = {
    "min_accounts",
    "min_submitted",
    "min_success_rate",
    "max_rejection_rate",
    "max_submit_p95_ms",
    "max_submit_p99_ms",
    "max_completion_p95_ms",
    "max_completion_p99_ms",
    "max_queue_age_seconds",
}
LIVE_KEYS = {
    "min_accounts",
    "min_submitted",
    "min_success_rate",
    "max_rejection_rate",
    "max_completion_p95_ms",
    "max_completion_p99_ms",
    "max_provider_failure_rate",
    "max_provider_p95_latency_ms",
    "max_average_tokens_per_completed_task",
}


class CapacityQualificationError(RuntimeError):
    pass


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CapacityQualificationError(f"{label} must be an ISO-8601 timestamp.") from None
    if result.tzinfo is None:
        raise CapacityQualificationError(f"{label} must include a timezone.")
    return result.astimezone(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CapacityQualificationError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise CapacityQualificationError(f"{label} must contain a JSON object.")
    return value


def non_negative_number(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
        raise CapacityQualificationError(f"{label} must be a finite non-negative number.")
    return float(value)


def positive_int(value, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CapacityQualificationError(f"{label} must be a positive integer.")
    return value


def ratio(value, label: str) -> float:
    number = non_negative_number(value, label)
    if number > 1:
        raise CapacityQualificationError(f"{label} must be between 0 and 1.")
    return number


def load_plan(path: Path) -> dict:
    value = load_json(path, "capacity plan")
    if set(value) != PLAN_KEYS:
        raise CapacityQualificationError("Capacity plan must contain the exact documented top-level keys.")
    if not isinstance(value["release_id"], str) or not value["release_id"].strip():
        raise CapacityQualificationError("capacity plan release_id is required.")
    if not isinstance(value["final_stage"], str) or not value["final_stage"].strip():
        raise CapacityQualificationError("capacity plan final_stage is required.")
    positive_int(value["freshness_minutes"], "freshness_minutes")
    positive_int(value["expected_peak_concurrency"], "expected_peak_concurrency")
    reserve = non_negative_number(value["min_reserve_ratio"], "min_reserve_ratio")
    if reserve < 1:
        raise CapacityQualificationError("min_reserve_ratio must be at least 1.0.")
    if not isinstance(value["simulated"], dict) or set(value["simulated"]) != SIM_KEYS:
        raise CapacityQualificationError("Capacity plan simulated thresholds have an unexpected schema.")
    if not isinstance(value["live_provider"], dict) or set(value["live_provider"]) != LIVE_KEYS:
        raise CapacityQualificationError("Capacity plan live_provider thresholds have an unexpected schema.")

    for section_name, keys in (
        ("simulated", ("min_accounts", "min_submitted")),
        ("live_provider", ("min_accounts", "min_submitted")),
    ):
        section = value[section_name]
        for key in keys:
            positive_int(section[key], f"{section_name}.{key}")
        ratio(section["min_success_rate"], f"{section_name}.min_success_rate")
        ratio(section["max_rejection_rate"], f"{section_name}.max_rejection_rate")

    sim = value["simulated"]
    for key in (
        "max_submit_p95_ms",
        "max_submit_p99_ms",
        "max_completion_p95_ms",
        "max_completion_p99_ms",
        "max_queue_age_seconds",
    ):
        non_negative_number(sim[key], f"simulated.{key}")

    live = value["live_provider"]
    for key in (
        "max_completion_p95_ms",
        "max_completion_p99_ms",
        "max_provider_p95_latency_ms",
        "max_average_tokens_per_completed_task",
    ):
        non_negative_number(live[key], f"live_provider.{key}")
    ratio(live["max_provider_failure_rate"], "live_provider.max_provider_failure_rate")
    return value


def load_report(path: Path, kind: str, release_id: str) -> dict:
    value = load_json(path, f"{kind} capacity report")
    if set(value) != REPORT_KEYS:
        raise CapacityQualificationError(f"{kind} capacity report has an unexpected schema.")
    if value["schema_version"] != 1:
        raise CapacityQualificationError(f"{kind} capacity report schema_version must be 1.")
    if value["release_id"] != release_id:
        raise CapacityQualificationError(f"{kind} capacity report release_id does not match.")
    if value["kind"] != kind:
        raise CapacityQualificationError(f"{kind} capacity report kind does not match.")

    parse_time(str(value["generated_at"]), f"{kind}.generated_at")
    positive_int(value["duration_seconds"], f"{kind}.duration_seconds")
    positive_int(value["accounts"], f"{kind}.accounts")
    positive_int(value["offered_concurrency"], f"{kind}.offered_concurrency")
    positive_int(value["submitted"], f"{kind}.submitted")
    for key in ("completed", "failed", "rejected", "provider_samples", "provider_failed", "total_tokens"):
        if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 0:
            raise CapacityQualificationError(f"{kind}.{key} must be a non-negative integer.")
    for key in (
        "submit_p95_ms",
        "submit_p99_ms",
        "completion_p95_ms",
        "completion_p99_ms",
        "max_queue_age_seconds",
        "provider_p95_latency_ms",
    ):
        if value[key] is not None:
            non_negative_number(value[key], f"{kind}.{key}")
    if value["completed"] + value["failed"] + value["rejected"] > value["submitted"]:
        raise CapacityQualificationError(
            f"{kind} terminal/rejected counts cannot exceed submitted count."
        )
    if value["provider_failed"] > value["provider_samples"]:
        raise CapacityQualificationError(
            f"{kind} provider_failed cannot exceed provider_samples."
        )
    return value


def success_rate(report: dict) -> float:
    return report["completed"] / report["submitted"]


def rejection_rate(report: dict) -> float:
    return report["rejected"] / report["submitted"]


def provider_failure_rate(report: dict) -> float | None:
    if report["provider_samples"] == 0:
        return None
    return report["provider_failed"] / report["provider_samples"]


def average_tokens(report: dict) -> float | None:
    if report["completed"] == 0:
        return None
    return report["total_tokens"] / report["completed"]


def require_fresh(report: dict, *, freshness_minutes: int, now: datetime) -> None:
    generated = parse_time(str(report["generated_at"]), f"{report['kind']}.generated_at")
    age_minutes = (now - generated).total_seconds() / 60
    if age_minutes < -1:
        raise CapacityQualificationError(f"{report['kind']} capacity report is from the future.")
    if age_minutes > freshness_minutes:
        raise CapacityQualificationError(
            f"{report['kind']} capacity report is stale ({age_minutes:.1f} minutes old)."
        )


def validate_final_stage(progression: dict, plan: dict, release_id: str) -> None:
    if progression.get("release_id") != release_id:
        raise CapacityQualificationError("Progression evidence release_id does not match.")
    if progression.get("current_stage") != plan["final_stage"]:
        raise CapacityQualificationError(
            "Capacity qualification requires progression evidence for the configured final_stage."
        )
    if progression.get("next_stage") is not None:
        raise CapacityQualificationError(
            "Capacity qualification progression evidence must not name a next stage."
        )

    decision = progression.get("decision")
    reasons = progression.get("reasons")
    original_final_canary = decision == "HOLD" and reasons == ["final_stage_reached"]
    dynamic_requalification = (
        decision == "ELIGIBLE_FOR_REQUALIFICATION"
        and reasons == []
        and progression.get("stage_max_users") is not None
        and progression.get("epoch_start") is not None
    )
    if not (original_final_canary or dynamic_requalification):
        raise CapacityQualificationError(
            "Capacity qualification requires final_stage_reached for the original canary "
            "or an eligible post-scale observation epoch."
        )


def validate_operator_status(status: dict, release_id: str, *, not_before: datetime) -> None:
    if status.get("release_id") != release_id:
        raise CapacityQualificationError("Operator status release_id does not match.")
    if status.get("decision") != "CONTINUE_COHORT" or status.get("breaches") != []:
        raise CapacityQualificationError("Operator status must be CONTINUE_COHORT with zero breaches.")
    generated_at = status.get("generated_at")
    if not isinstance(generated_at, str):
        raise CapacityQualificationError("Operator status has no generated_at timestamp.")
    if parse_time(generated_at, "operator status generated_at") < not_before:
        raise CapacityQualificationError(
            "Operator status must be generated after both capacity reports."
        )


def evaluate_report(report: dict, thresholds: dict, *, kind: str, plan: dict) -> list[dict]:
    failures: list[dict] = []

    def fail(metric: str, actual, threshold, reason: str) -> None:
        failures.append({
            "report": kind,
            "metric": metric,
            "actual": actual,
            "threshold": threshold,
            "reason": reason,
        })

    if report["accounts"] < thresholds["min_accounts"]:
        fail("accounts", report["accounts"], thresholds["min_accounts"], "Too few distinct test accounts.")
    if report["submitted"] < thresholds["min_submitted"]:
        fail("submitted", report["submitted"], thresholds["min_submitted"], "Too few submitted tasks.")
    srate = success_rate(report)
    rrate = rejection_rate(report)
    if srate < thresholds["min_success_rate"]:
        fail("success_rate", round(srate, 6), thresholds["min_success_rate"], "Task success rate is below capacity qualification.")
    if rrate > thresholds["max_rejection_rate"]:
        fail("rejection_rate", round(rrate, 6), thresholds["max_rejection_rate"], "Task rejection rate exceeds capacity qualification.")

    required_concurrency = math.ceil(
        plan["expected_peak_concurrency"] * plan["min_reserve_ratio"]
    )
    if report["offered_concurrency"] < required_concurrency:
        fail(
            "offered_concurrency",
            report["offered_concurrency"],
            required_concurrency,
            "Load report does not demonstrate the required concurrency reserve.",
        )

    if kind == "simulated":
        for metric, key in (
            ("submit_p95_ms", "max_submit_p95_ms"),
            ("submit_p99_ms", "max_submit_p99_ms"),
            ("completion_p95_ms", "max_completion_p95_ms"),
            ("completion_p99_ms", "max_completion_p99_ms"),
            ("max_queue_age_seconds", "max_queue_age_seconds"),
        ):
            actual = report[metric]
            if actual is None or actual > thresholds[key]:
                fail(metric, actual, thresholds[key], f"{metric} exceeds simulated-load threshold.")
    else:
        for metric, key in (
            ("completion_p95_ms", "max_completion_p95_ms"),
            ("completion_p99_ms", "max_completion_p99_ms"),
        ):
            actual = report[metric]
            if actual is None or actual > thresholds[key]:
                fail(metric, actual, thresholds[key], f"{metric} exceeds live-provider threshold.")

        p_failure = provider_failure_rate(report)
        if p_failure is None:
            fail(
                "provider_failure_rate",
                None,
                thresholds["max_provider_failure_rate"],
                "Live-provider report has no measured provider samples.",
            )
        elif p_failure > thresholds["max_provider_failure_rate"]:
            fail(
                "provider_failure_rate",
                round(p_failure, 6),
                thresholds["max_provider_failure_rate"],
                "Live provider failure rate exceeds threshold.",
            )
        latency = report["provider_p95_latency_ms"]
        if latency is None or latency > thresholds["max_provider_p95_latency_ms"]:
            fail(
                "provider_p95_latency_ms",
                latency,
                thresholds["max_provider_p95_latency_ms"],
                "Live provider p95 latency exceeds threshold.",
            )
        avg_tokens = average_tokens(report)
        if avg_tokens is None or avg_tokens > thresholds["max_average_tokens_per_completed_task"]:
            fail(
                "average_tokens_per_completed_task",
                None if avg_tokens is None else round(avg_tokens, 2),
                thresholds["max_average_tokens_per_completed_task"],
                "Average live-provider token use exceeds threshold.",
            )
    return failures


def qualify(
    *,
    capacity_plan: dict,
    progression: dict,
    simulated: dict,
    live: dict,
    operator_status: dict,
    now: datetime | None = None,
) -> dict:
    release_id = capacity_plan["release_id"]
    validate_final_stage(progression, capacity_plan, release_id)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    require_fresh(simulated, freshness_minutes=capacity_plan["freshness_minutes"], now=now)
    require_fresh(live, freshness_minutes=capacity_plan["freshness_minutes"], now=now)
    simulated_time = parse_time(simulated["generated_at"], "simulated.generated_at")
    live_time = parse_time(live["generated_at"], "live_provider.generated_at")
    validate_operator_status(
        operator_status,
        release_id,
        not_before=max(simulated_time, live_time),
    )

    failures = (
        evaluate_report(
            simulated,
            capacity_plan["simulated"],
            kind="simulated",
            plan=capacity_plan,
        )
        + evaluate_report(
            live,
            capacity_plan["live_provider"],
            kind="live_provider",
            plan=capacity_plan,
        )
    )
    return {
        "decision": "ELIGIBLE_FOR_CAPACITY_REVIEW" if not failures else "CAPACITY_NOT_QUALIFIED",
        "generated_at": now.isoformat(),
        "release_id": release_id,
        "final_stage": capacity_plan["final_stage"],
        "expected_peak_concurrency": capacity_plan["expected_peak_concurrency"],
        "required_test_concurrency": math.ceil(
            capacity_plan["expected_peak_concurrency"] * capacity_plan["min_reserve_ratio"]
        ),
        "failures": failures,
        "summary": {
            "simulated": {
                "accounts": simulated["accounts"],
                "submitted": simulated["submitted"],
                "offered_concurrency": simulated["offered_concurrency"],
                "success_rate": round(success_rate(simulated), 6),
                "rejection_rate": round(rejection_rate(simulated), 6),
                "completion_p95_ms": simulated["completion_p95_ms"],
                "completion_p99_ms": simulated["completion_p99_ms"],
                "max_queue_age_seconds": simulated["max_queue_age_seconds"],
            },
            "live_provider": {
                "accounts": live["accounts"],
                "submitted": live["submitted"],
                "offered_concurrency": live["offered_concurrency"],
                "success_rate": round(success_rate(live), 6),
                "rejection_rate": round(rejection_rate(live), 6),
                "completion_p95_ms": live["completion_p95_ms"],
                "completion_p99_ms": live["completion_p99_ms"],
                "provider_failure_rate": (
                    None if provider_failure_rate(live) is None
                    else round(provider_failure_rate(live), 6)
                ),
                "provider_p95_latency_ms": live["provider_p95_latency_ms"],
                "average_tokens_per_completed_task": (
                    None if average_tokens(live) is None
                    else round(average_tokens(live), 2)
                ),
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Qualify measured Shuddho Coworker capacity after the final controlled cohort stage."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--progression", type=Path, required=True)
    parser.add_argument("--simulated-report", type=Path, required=True)
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--operator-status", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        capacity_plan = load_plan(args.plan)
        progression = load_json(args.progression, "canary progression")
        simulated = load_report(args.simulated_report, "simulated", capacity_plan["release_id"])
        live = load_report(args.live_report, "live_provider", capacity_plan["release_id"])
        status = load_json(args.operator_status, "operator status")
        result = qualify(
            capacity_plan=capacity_plan,
            progression=progression,
            simulated=simulated,
            live=live,
            operator_status=status,
        )
        result["artifact_sha256"] = {
            "capacity_plan": sha256_file(args.plan),
            "progression": sha256_file(args.progression),
            "simulated_report": sha256_file(args.simulated_report),
            "live_report": sha256_file(args.live_report),
            "operator_status": sha256_file(args.operator_status),
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "decision": result["decision"],
            "failures": len(result["failures"]),
        }, indent=2))
        if result["decision"] != "ELIGIBLE_FOR_CAPACITY_REVIEW":
            raise SystemExit("Capacity qualification failed.")
    except (CapacityQualificationError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
