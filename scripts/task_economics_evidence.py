from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path

from scripts.provider_policy_compiler import ProviderPolicyError, load_plan as load_provider_policy_plan


class TaskEconomicsEvidenceError(RuntimeError):
    pass


MAX_CLOCK_SKEW = timedelta(minutes=5)
GIB = Decimal(1024 ** 3)
CATEGORY_KEYS = (
    "model",
    "search",
    "sandbox",
    "render",
    "storage",
    "notification",
)
USAGE_KEYS = {
    "model_tokens",
    "search_credits",
    "sandbox_milliseconds",
    "render_operations",
    "storage_byte_hours",
    "notification_attempts",
    "retry_count",
}
PRICING_KEYS = {
    "schema_version",
    "release_id",
    "min_completed_tasks",
    "max_cost_microusd_per_completed_task",
    "search_microusd_per_credit",
    "sandbox_microusd_per_second",
    "render_microusd_per_operation",
    "storage_microusd_per_gib_hour",
    "notification_microusd_per_attempt",
    "review_reference",
}
SAMPLES_KEYS = {
    "schema_version",
    "release_id",
    "source_revision",
    "generated_at",
    "tasks",
}
TASK_KEYS = {
    "task_reference",
    "task_kind",
    "language",
    "state",
    "usage",
}
EVIDENCE_KEYS = {
    "schema_version",
    "mode",
    "release_id",
    "generated_at",
    "samples_generated_at",
    "source_revision",
    "rollout_manifest_sha256",
    "provider_policy_plan_sha256",
    "pricing_plan_sha256",
    "samples_sha256",
    "completed_tasks",
    "total_retries",
    "category_coverage",
    "category_cost_microusd",
    "average_cost_microusd",
    "p95_cost_microusd",
    "max_cost_microusd",
    "budget_microusd_per_completed_task",
    "gate_decision",
    "failures",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TaskEconomicsEvidenceError(f"Unable to read {label}: {error}") from None
    if not isinstance(value, dict):
        raise TaskEconomicsEvidenceError(f"{label} must be a JSON object.")
    return value


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise TaskEconomicsEvidenceError(f"{label} must be an ISO-8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TaskEconomicsEvidenceError(f"{label} must be an ISO-8601 timestamp.") from None
    if parsed.tzinfo is None:
        raise TaskEconomicsEvidenceError(f"{label} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def reject_future(value: datetime, label: str, *, now: datetime | None = None) -> None:
    reference = now or datetime.now(timezone.utc)
    if value > reference + MAX_CLOCK_SKEW:
        raise TaskEconomicsEvidenceError(f"{label} is too far in the future.")


def require_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TaskEconomicsEvidenceError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def require_revision(value: object, label: str = "source_revision") -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TaskEconomicsEvidenceError(f"{label} must be a full 40-character commit SHA.")
    return value


def text_ref(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise TaskEconomicsEvidenceError(f"{label} must be a non-empty reference up to 500 characters.")
    return value.strip()


def non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TaskEconomicsEvidenceError(f"{label} must be a non-negative integer.")
    return value


def positive_int(value: object, label: str) -> int:
    result = non_negative_int(value, label)
    if result < 1:
        raise TaskEconomicsEvidenceError(f"{label} must be at least 1.")
    return result


def decimal_number(value: object, label: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise TaskEconomicsEvidenceError(f"{label} must be numeric.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise TaskEconomicsEvidenceError(f"{label} must be numeric.") from None
    if not number.is_finite() or number < 0 or (positive and number <= 0):
        qualifier = "positive" if positive else "non-negative"
        raise TaskEconomicsEvidenceError(f"{label} must be a finite {qualifier} number.")
    return number


def ceil_microusd(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def percentile95(values: list[int]) -> int:
    ordered = sorted(values)
    rank = max(1, math.ceil(len(ordered) * 0.95))
    return ordered[rank - 1]


def load_pricing(path: Path, release_id: str) -> dict:
    value = load_json(path, "task economics pricing plan")
    if set(value) != PRICING_KEYS:
        raise TaskEconomicsEvidenceError(
            "Task economics pricing plan has an unexpected schema."
        )
    if value["schema_version"] != 1:
        raise TaskEconomicsEvidenceError(
            "Task economics pricing plan schema_version must be 1."
        )
    if value["release_id"] != release_id:
        raise TaskEconomicsEvidenceError(
            "Task economics pricing plan release_id does not match."
        )
    positive_int(value["min_completed_tasks"], "pricing.min_completed_tasks")
    positive_int(
        value["max_cost_microusd_per_completed_task"],
        "pricing.max_cost_microusd_per_completed_task",
    )
    for key in (
        "search_microusd_per_credit",
        "sandbox_microusd_per_second",
        "render_microusd_per_operation",
        "storage_microusd_per_gib_hour",
        "notification_microusd_per_attempt",
    ):
        non_negative_int(value[key], f"pricing.{key}")
    text_ref(value["review_reference"], "pricing.review_reference")
    return value


def load_samples(
    path: Path,
    release_id: str,
    *,
    min_completed_tasks: int,
    now: datetime,
) -> tuple[dict, datetime]:
    value = load_json(path, "task economics samples")
    if set(value) != SAMPLES_KEYS:
        raise TaskEconomicsEvidenceError(
            "Task economics samples have an unexpected schema."
        )
    if value["schema_version"] != 1:
        raise TaskEconomicsEvidenceError(
            "Task economics samples schema_version must be 1."
        )
    if value["release_id"] != release_id:
        raise TaskEconomicsEvidenceError(
            "Task economics samples release_id does not match."
        )
    require_revision(value["source_revision"])
    generated = parse_time(value["generated_at"], "samples.generated_at")
    reject_future(generated, "samples.generated_at", now=now)
    tasks = value["tasks"]
    if not isinstance(tasks, list) or len(tasks) < min_completed_tasks:
        raise TaskEconomicsEvidenceError(
            f"Task economics requires at least {min_completed_tasks} completed samples."
        )
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or set(task) != TASK_KEYS:
            raise TaskEconomicsEvidenceError(
                f"samples.tasks[{index}] has an unexpected schema."
            )
        reference = text_ref(task["task_reference"], f"samples.tasks[{index}].task_reference")
        if reference in seen:
            raise TaskEconomicsEvidenceError("Task economics task references must be unique.")
        seen.add(reference)
        text_ref(task["task_kind"], f"samples.tasks[{index}].task_kind")
        text_ref(task["language"], f"samples.tasks[{index}].language")
        if task["state"] != "completed":
            raise TaskEconomicsEvidenceError(
                "Task economics samples may include only completed tasks."
            )
        usage = task["usage"]
        if not isinstance(usage, dict) or set(usage) != USAGE_KEYS:
            raise TaskEconomicsEvidenceError(
                f"samples.tasks[{index}].usage has an unexpected schema."
            )
        for key in USAGE_KEYS:
            non_negative_int(usage[key], f"samples.tasks[{index}].usage.{key}")
    return value, generated


def task_costs(
    usage: dict,
    *,
    model_microusd_per_token: Decimal,
    pricing: dict,
) -> dict[str, int]:
    return {
        "model": ceil_microusd(
            Decimal(usage["model_tokens"]) * model_microusd_per_token
        ),
        "search": ceil_microusd(
            Decimal(usage["search_credits"]) * Decimal(pricing["search_microusd_per_credit"])
        ),
        "sandbox": ceil_microusd(
            Decimal(usage["sandbox_milliseconds"])
            * Decimal(pricing["sandbox_microusd_per_second"])
            / Decimal(1000)
        ),
        "render": ceil_microusd(
            Decimal(usage["render_operations"]) * Decimal(pricing["render_microusd_per_operation"])
        ),
        "storage": ceil_microusd(
            Decimal(usage["storage_byte_hours"])
            * Decimal(pricing["storage_microusd_per_gib_hour"])
            / GIB
        ),
        "notification": ceil_microusd(
            Decimal(usage["notification_attempts"])
            * Decimal(pricing["notification_microusd_per_attempt"])
        ),
    }


def compile_task_economics_evidence(
    *,
    rollout_path: Path,
    provider_policy_plan_path: Path,
    pricing_plan_path: Path,
    samples_path: Path,
) -> dict:
    now = datetime.now(timezone.utc)
    rollout = load_json(rollout_path, "rollout manifest")
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise TaskEconomicsEvidenceError("Rollout manifest release_id is required.")

    try:
        provider_plan = load_provider_policy_plan(provider_policy_plan_path)
    except (ProviderPolicyError, OSError, ValueError) as error:
        raise TaskEconomicsEvidenceError(str(error)) from None
    if provider_plan["release_id"] != release_id:
        raise TaskEconomicsEvidenceError(
            "Provider policy plan release_id does not match the rollout."
        )
    model_rate = decimal_number(
        provider_plan["blended_token_cost_usd_per_million"],
        "provider_policy.blended_token_cost_usd_per_million",
        positive=True,
    )
    # USD per million tokens is numerically equal to micro-USD per token.
    model_microusd_per_token = model_rate

    pricing = load_pricing(pricing_plan_path, release_id)
    samples, samples_generated = load_samples(
        samples_path,
        release_id,
        min_completed_tasks=pricing["min_completed_tasks"],
        now=now,
    )

    totals = {key: 0 for key in CATEGORY_KEYS}
    coverage = {key: False for key in CATEGORY_KEYS}
    costs: list[int] = []
    retries = 0
    budget = pricing["max_cost_microusd_per_completed_task"]

    for task in samples["tasks"]:
        usage = task["usage"]
        coverage["model"] = coverage["model"] or usage["model_tokens"] > 0
        coverage["search"] = coverage["search"] or usage["search_credits"] > 0
        coverage["sandbox"] = coverage["sandbox"] or usage["sandbox_milliseconds"] > 0
        coverage["render"] = coverage["render"] or usage["render_operations"] > 0
        coverage["storage"] = coverage["storage"] or usage["storage_byte_hours"] > 0
        coverage["notification"] = coverage["notification"] or usage["notification_attempts"] > 0
        retries += usage["retry_count"]

        categories = task_costs(
            usage,
            model_microusd_per_token=model_microusd_per_token,
            pricing=pricing,
        )
        for key, value in categories.items():
            totals[key] += value
        task_total = sum(categories.values())
        if task_total > budget:
            raise TaskEconomicsEvidenceError(
                f"Task economics sample {task['task_reference']} exceeds the reviewed per-task budget."
            )
        costs.append(task_total)

    missing = [key for key, present in coverage.items() if not present]
    if missing:
        raise TaskEconomicsEvidenceError(
            "Task economics samples do not cover every required cost category: "
            + ", ".join(missing)
            + "."
        )

    average = ceil_microusd(Decimal(sum(costs)) / Decimal(len(costs)))
    return {
        "schema_version": 1,
        "mode": "task_economics",
        "release_id": release_id,
        "generated_at": now.isoformat(),
        "samples_generated_at": samples_generated.isoformat(),
        "source_revision": require_revision(samples["source_revision"]),
        "rollout_manifest_sha256": sha256_file(rollout_path),
        "provider_policy_plan_sha256": sha256_file(provider_policy_plan_path),
        "pricing_plan_sha256": sha256_file(pricing_plan_path),
        "samples_sha256": sha256_file(samples_path),
        "completed_tasks": len(costs),
        "total_retries": retries,
        "category_coverage": coverage,
        "category_cost_microusd": totals,
        "average_cost_microusd": average,
        "p95_cost_microusd": percentile95(costs),
        "max_cost_microusd": max(costs),
        "budget_microusd_per_completed_task": budget,
        "gate_decision": "PASS",
        "failures": [],
    }


def validate_task_economics_evidence(
    value: dict,
    *,
    release_id: str,
    rollout_sha256: str,
    expected_source_revision: str | None = None,
) -> datetime:
    if not isinstance(value, dict) or set(value) != EVIDENCE_KEYS:
        raise TaskEconomicsEvidenceError(
            "Task economics evidence has an unexpected schema."
        )
    if value["schema_version"] != 1 or value["mode"] != "task_economics":
        raise TaskEconomicsEvidenceError(
            "Task economics evidence has an unsupported schema or mode."
        )
    if value["release_id"] != release_id:
        raise TaskEconomicsEvidenceError(
            "Task economics evidence release_id does not match."
        )
    require_sha256(rollout_sha256, "Expected rollout manifest SHA-256")
    if value["rollout_manifest_sha256"] != rollout_sha256:
        raise TaskEconomicsEvidenceError(
            "Task economics evidence does not bind the current rollout manifest."
        )
    revision = require_revision(value["source_revision"])
    if expected_source_revision is not None and revision != require_revision(
        expected_source_revision, "expected_source_revision"
    ):
        raise TaskEconomicsEvidenceError(
            "Task economics source revision does not match the live quality evidence."
        )
    for key in (
        "provider_policy_plan_sha256",
        "pricing_plan_sha256",
        "samples_sha256",
    ):
        require_sha256(value[key], f"economics.{key}")
    positive_int(value["completed_tasks"], "economics.completed_tasks")
    non_negative_int(value["total_retries"], "economics.total_retries")
    if (
        not isinstance(value["category_coverage"], dict)
        or set(value["category_coverage"]) != set(CATEGORY_KEYS)
        or any(item is not True for item in value["category_coverage"].values())
    ):
        raise TaskEconomicsEvidenceError(
            "Task economics evidence must cover every required cost category."
        )
    if (
        not isinstance(value["category_cost_microusd"], dict)
        or set(value["category_cost_microusd"]) != set(CATEGORY_KEYS)
    ):
        raise TaskEconomicsEvidenceError(
            "Task economics category cost summary has an unexpected schema."
        )
    for key in CATEGORY_KEYS:
        non_negative_int(
            value["category_cost_microusd"][key],
            f"economics.category_cost_microusd.{key}",
        )
    for key in (
        "average_cost_microusd",
        "p95_cost_microusd",
        "max_cost_microusd",
        "budget_microusd_per_completed_task",
    ):
        positive_int(value[key], f"economics.{key}")
    if value["max_cost_microusd"] > value["budget_microusd_per_completed_task"]:
        raise TaskEconomicsEvidenceError(
            "Task economics maximum cost exceeds the reviewed per-task budget."
        )
    if value["average_cost_microusd"] > value["max_cost_microusd"]:
        raise TaskEconomicsEvidenceError(
            "Task economics average cost cannot exceed the maximum cost."
        )
    if value["p95_cost_microusd"] > value["max_cost_microusd"]:
        raise TaskEconomicsEvidenceError(
            "Task economics p95 cost cannot exceed the maximum cost."
        )
    if value["gate_decision"] != "PASS" or value["failures"] != []:
        raise TaskEconomicsEvidenceError(
            "Task economics evidence did not pass cleanly."
        )
    generated = parse_time(value["generated_at"], "economics.generated_at")
    samples_generated = parse_time(
        value["samples_generated_at"],
        "economics.samples_generated_at",
    )
    reject_future(generated, "economics.generated_at")
    reject_future(samples_generated, "economics.samples_generated_at")
    if samples_generated > generated + MAX_CLOCK_SKEW:
        raise TaskEconomicsEvidenceError(
            "Task economics samples cannot be newer than the compiled evidence."
        )
    return samples_generated


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile rollout-bound PA-11 task-economics evidence from reviewed "
            "pricing and measured completed-task resource usage."
        )
    )
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--provider-policy-plan", type=Path, required=True)
    parser.add_argument("--pricing-plan", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compile_task_economics_evidence(
            rollout_path=args.rollout,
            provider_policy_plan_path=args.provider_policy_plan,
            pricing_plan_path=args.pricing_plan,
            samples_path=args.samples,
        )
    except TaskEconomicsEvidenceError as error:
        raise SystemExit(str(error)) from None
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
