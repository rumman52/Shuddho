from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from scripts.cohort_release_gate import load_rollout
from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.models import (
    Account,
    AgentRun,
    ExternalAction,
    ModelAttempt,
    Task,
    utcnow,
)
from services.coworker.provider_capacity import provider_capacity_snapshot

TASK_TERMINAL = {"completed", "failed", "cancelled", "needs_input"}
AGENT_TERMINAL = {"completed", "failed", "cancelled"}
ACTION_MEASURED = {"succeeded", "failed", "outcome_unknown"}
ACTION_ACTIVE = {"queued", "executing"}
MODEL_MEASURED = {"completed", "failed", "unknown"}

THRESHOLD_KEYS = {
    "window_minutes",
    "max_active_work_age_seconds",
    "min_task_samples",
    "max_task_failure_rate",
    "min_provider_samples",
    "max_provider_failure_rate",
    "max_model_p95_latency_ms",
    "max_window_tokens",
    "max_total_storage_bytes",
    "min_agent_samples",
    "max_agent_failure_rate",
    "min_research_samples",
    "max_research_failure_rate",
    "min_action_samples",
    "max_action_failure_rate",
    "max_action_outcome_unknown",
}


class CohortHealthError(RuntimeError):
    pass


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def percentile95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def age_seconds(now: datetime, created_at: datetime) -> int:
    return max(0, int((now - aware(created_at)).total_seconds()))


def load_thresholds(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != THRESHOLD_KEYS:
        raise CohortHealthError("Health thresholds must contain the exact documented key set.")
    integer_keys = {
        "window_minutes", "max_active_work_age_seconds", "min_task_samples",
        "min_provider_samples", "max_model_p95_latency_ms", "max_window_tokens",
        "max_total_storage_bytes", "min_agent_samples", "min_research_samples",
        "min_action_samples", "max_action_outcome_unknown",
    }
    rate_keys = {
        "max_task_failure_rate", "max_provider_failure_rate",
        "max_agent_failure_rate", "max_research_failure_rate",
        "max_action_failure_rate",
    }
    for key in integer_keys:
        if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 0:
            raise CohortHealthError(f"{key} must be a non-negative integer.")
    if value["window_minutes"] < 1:
        raise CohortHealthError("window_minutes must be at least 1.")
    for key in rate_keys:
        if not isinstance(value[key], (int, float)) or isinstance(value[key], bool) or not 0 <= float(value[key]) <= 1:
            raise CohortHealthError(f"{key} must be between 0 and 1.")
        value[key] = float(value[key])
    return value


def collect_snapshot(settings: Settings, *, window_minutes: int, now: datetime | None = None) -> dict:
    if not settings.cohort_enforced or not settings.cohort_account_ids:
        raise CohortHealthError("Cohort health collection requires backend cohort enforcement.")
    now = aware(now or utcnow())
    cutoff = now - timedelta(minutes=window_minutes)
    owners = sorted(settings.cohort_account_ids)
    sessions = session_factory(settings.database_url)
    engine = sessions.kw["bind"]
    try:
        with sessions() as db:
            active_tasks = list(db.scalars(select(Task).where(
                Task.owner_id.in_(owners),
                Task.state.not_in(TASK_TERMINAL),
            )).all())
            active_agents = list(db.scalars(select(AgentRun).where(
                AgentRun.owner_id.in_(owners),
                AgentRun.state.not_in(AGENT_TERMINAL),
            )).all())
            active_actions = list(db.scalars(select(ExternalAction).where(
                ExternalAction.owner_id.in_(owners),
                ExternalAction.state.in_(ACTION_ACTIVE),
            )).all())

            terminal_tasks = list(db.scalars(select(Task).where(
                Task.owner_id.in_(owners),
                Task.updated_at >= cutoff,
                Task.state.in_(TASK_TERMINAL),
            )).all())
            measured_tasks = [item for item in terminal_tasks if item.state != "cancelled"]
            task_completed = sum(item.state == "completed" for item in measured_tasks)
            task_failed = sum(item.state == "failed" for item in measured_tasks)
            task_needs_input = sum(item.state == "needs_input" for item in measured_tasks)

            research_tasks = [
                item for item in measured_tasks
                if item.workflow_version == "work_research_v1"
            ]
            research_failed = sum(item.state == "failed" for item in research_tasks)

            all_attempts = list(db.scalars(select(ModelAttempt).where(
                ModelAttempt.owner_id.in_(owners),
                ModelAttempt.created_at >= cutoff,
            )).all())
            attempts = [item for item in all_attempts if item.state in MODEL_MEASURED]
            provider_failed = sum(item.state in {"failed", "unknown"} for item in attempts)
            latencies = [int(item.latency_ms) for item in attempts if item.latency_ms is not None]
            # charged_tokens starts as the conservative reservation and is replaced
            # by actual usage only after a known provider result. Include reserved
            # attempts so in-flight spend cannot disappear from the stop gate.
            tokens = sum(int(item.charged_tokens) for item in all_attempts)
            reserved_attempts = sum(item.state == "reserved" for item in all_attempts)

            agent_runs = list(db.scalars(select(AgentRun).where(
                AgentRun.owner_id.in_(owners),
                AgentRun.updated_at >= cutoff,
                AgentRun.state.in_(AGENT_TERMINAL),
            )).all())
            measured_agents = [item for item in agent_runs if item.state != "cancelled"]
            agent_failed = sum(item.state == "failed" for item in measured_agents)

            actions = list(db.scalars(select(ExternalAction).where(
                ExternalAction.owner_id.in_(owners),
                ExternalAction.created_at >= cutoff,
                ExternalAction.state.in_(ACTION_MEASURED),
            )).all())
            action_failed = sum(item.state in {"failed", "outcome_unknown"} for item in actions)
            action_unknown = sum(item.state == "outcome_unknown" for item in actions)

            storage_bytes = db.scalar(select(func.coalesce(func.sum(Account.storage_bytes), 0)).where(
                Account.id.in_(owners)
            )) or 0

        with sessions.begin() as db:
            provider_capacity = provider_capacity_snapshot(db)

        active_created = (
            [item.created_at for item in active_tasks]
            + [item.created_at for item in active_agents]
            + [item.created_at for item in active_actions]
        )
        oldest_active_age = max((age_seconds(now, value) for value in active_created), default=0)
        return {
            "generated_at": now.isoformat(),
            "window_minutes": window_minutes,
            "cohort_members_configured": len(owners),
            "active": {
                "tasks": len(active_tasks),
                "agent_runs": len(active_agents),
                "provider_actions": len(active_actions),
                "oldest_work_age_seconds": oldest_active_age,
            },
            "tasks": {
                "samples": len(measured_tasks),
                "completed": task_completed,
                "failed": task_failed,
                "needs_input": task_needs_input,
                "success_rate": rate(task_completed, len(measured_tasks)),
                "failure_rate": rate(task_failed, len(measured_tasks)),
            },
            "provider": {
                "samples": len(attempts),
                "failed_or_unknown": provider_failed,
                "failure_rate": rate(provider_failed, len(attempts)),
                "p95_latency_ms": percentile95(latencies),
                "window_tokens": tokens,
                "reserved_attempts": reserved_attempts,
                "active_leases": provider_capacity["active_calls"],
                "reserved_lease_tokens": provider_capacity["reserved_tokens"],
                "oldest_lease_age_seconds": provider_capacity["oldest_lease_age_seconds"],
            },
            "agents": {
                "samples": len(measured_agents),
                "failed": agent_failed,
                "failure_rate": rate(agent_failed, len(measured_agents)),
            },
            "research": {
                "samples": len(research_tasks),
                "failed": research_failed,
                "failure_rate": rate(research_failed, len(research_tasks)),
            },
            "actions": {
                "samples": len(actions),
                "failed_or_unknown": action_failed,
                "outcome_unknown": action_unknown,
                "failure_rate": rate(action_failed, len(actions)),
            },
            "storage": {
                "total_bytes": int(storage_bytes),
            },
        }
    finally:
        engine.dispose()


def evaluate(snapshot: dict, rollout: dict, thresholds: dict) -> dict:
    failures: list[dict] = []
    capabilities = rollout.get("capabilities", {}) if isinstance(rollout, dict) else {}
    cohort = rollout.get("cohort", {}) if isinstance(rollout, dict) else {}

    def breach(metric: str, actual, threshold, reason: str) -> None:
        failures.append({
            "metric": metric,
            "actual": actual,
            "threshold": threshold,
            "reason": reason,
        })

    if snapshot["cohort_members_configured"] > int(cohort.get("max_users", 0) or 0):
        breach(
            "cohort_members_configured",
            snapshot["cohort_members_configured"],
            cohort.get("max_users"),
            "Configured backend cohort exceeds the approved rollout manifest.",
        )
    active_age = snapshot["active"]["oldest_work_age_seconds"]
    if active_age > thresholds["max_active_work_age_seconds"]:
        breach("active.oldest_work_age_seconds", active_age, thresholds["max_active_work_age_seconds"], "Active work is older than the rollout limit.")

    tasks = snapshot["tasks"]
    if tasks["samples"] >= thresholds["min_task_samples"] and tasks["failure_rate"] is not None and tasks["failure_rate"] > thresholds["max_task_failure_rate"]:
        breach("tasks.failure_rate", tasks["failure_rate"], thresholds["max_task_failure_rate"], "Task failure rate exceeded the rollout limit.")

    provider = snapshot["provider"]
    if provider["samples"] >= thresholds["min_provider_samples"] and provider["failure_rate"] is not None and provider["failure_rate"] > thresholds["max_provider_failure_rate"]:
        breach("provider.failure_rate", provider["failure_rate"], thresholds["max_provider_failure_rate"], "Model/provider failure rate exceeded the rollout limit.")
    if provider["p95_latency_ms"] is not None and provider["samples"] >= thresholds["min_provider_samples"] and provider["p95_latency_ms"] > thresholds["max_model_p95_latency_ms"]:
        breach("provider.p95_latency_ms", provider["p95_latency_ms"], thresholds["max_model_p95_latency_ms"], "Model p95 latency exceeded the rollout limit.")
    if provider["window_tokens"] > thresholds["max_window_tokens"]:
        breach("provider.window_tokens", provider["window_tokens"], thresholds["max_window_tokens"], "Window token allocation exceeded the rollout limit.")

    storage = snapshot["storage"]["total_bytes"]
    if storage > thresholds["max_total_storage_bytes"]:
        breach("storage.total_bytes", storage, thresholds["max_total_storage_bytes"], "Cohort storage exceeded the rollout limit.")

    if capabilities.get("agent_runtime") is True:
        agents = snapshot["agents"]
        if agents["samples"] >= thresholds["min_agent_samples"] and agents["failure_rate"] is not None and agents["failure_rate"] > thresholds["max_agent_failure_rate"]:
            breach("agents.failure_rate", agents["failure_rate"], thresholds["max_agent_failure_rate"], "Agent failure rate exceeded the rollout limit.")

    if capabilities.get("research") is True:
        research = snapshot["research"]
        if research["samples"] >= thresholds["min_research_samples"] and research["failure_rate"] is not None and research["failure_rate"] > thresholds["max_research_failure_rate"]:
            breach("research.failure_rate", research["failure_rate"], thresholds["max_research_failure_rate"], "Research task failure rate exceeded the rollout limit.")

    if capabilities.get("actions") is True:
        actions = snapshot["actions"]
        if actions["outcome_unknown"] > thresholds["max_action_outcome_unknown"]:
            breach("actions.outcome_unknown", actions["outcome_unknown"], thresholds["max_action_outcome_unknown"], "Consequential action outcomes are uncertain.")
        if actions["samples"] >= thresholds["min_action_samples"] and actions["failure_rate"] is not None and actions["failure_rate"] > thresholds["max_action_failure_rate"]:
            breach("actions.failure_rate", actions["failure_rate"], thresholds["max_action_failure_rate"], "Consequential action failure rate exceeded the rollout limit.")

    rollback = rollout.get("rollback", {}) if isinstance(rollout, dict) else {}
    return {
        "decision": "CONTINUE_COHORT" if not failures else "STOP_ROLLOUT",
        "release_id": rollout.get("release_id") if isinstance(rollout, dict) else None,
        "snapshot": snapshot,
        "breaches": failures,
        "rollback": rollback if failures else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Shuddho controlled-cohort production health and stop conditions.")
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--snapshot-output", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    settings = Settings.from_env()
    rollout = load_rollout(args.rollout)
    thresholds = load_thresholds(args.thresholds)
    snapshot = collect_snapshot(settings, window_minutes=thresholds["window_minutes"])
    result = evaluate(snapshot, rollout, thresholds)

    if args.snapshot_output:
        args.snapshot_output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if result["decision"] != "CONTINUE_COHORT":
        raise SystemExit("Cohort health gate says STOP_ROLLOUT.")


if __name__ == "__main__":
    main()
