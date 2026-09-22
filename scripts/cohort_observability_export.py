from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from scripts.cohort_health_gate import collect_snapshot, evaluate, load_thresholds
from scripts.cohort_release_gate import load_rollout
from services.coworker.config import Settings


class CohortObservabilityError(RuntimeError):
    pass


def metric_value(value) -> str:
    if value is None:
        return "NaN"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, ".12g")
    raise CohortObservabilityError(f"Unsupported metric value type: {type(value).__name__}")


def sample(name: str, help_text: str, value, metric_type: str = "gauge") -> list[str]:
    return [
        f"# HELP {name} {help_text}",
        f"# TYPE {name} {metric_type}",
        f"{name} {metric_value(value)}",
    ]


def render_openmetrics(result: dict) -> str:
    snapshot = result["snapshot"]
    generated = datetime.fromisoformat(snapshot["generated_at"].replace("Z", "+00:00"))
    lines: list[str] = []
    add = lines.extend

    add(sample(
        "shuddho_coworker_cohort_continue",
        "1 when the current controlled cohort health decision is CONTINUE_COHORT, else 0.",
        result["decision"] == "CONTINUE_COHORT",
    ))
    add(sample(
        "shuddho_coworker_cohort_stop",
        "1 when the current controlled cohort health decision is STOP_ROLLOUT, else 0.",
        result["decision"] == "STOP_ROLLOUT",
    ))
    add(sample(
        "shuddho_coworker_cohort_breaches",
        "Number of currently breached controlled-cohort stop conditions.",
        len(result["breaches"]),
    ))
    add(sample(
        "shuddho_coworker_cohort_snapshot_timestamp_seconds",
        "Unix timestamp when the controlled-cohort health snapshot was generated.",
        int(generated.timestamp()),
    ))
    add(sample(
        "shuddho_coworker_cohort_window_minutes",
        "Observation window used for the controlled-cohort health snapshot.",
        snapshot["window_minutes"],
    ))
    add(sample(
        "shuddho_coworker_cohort_members_configured",
        "Number of backend-enforced controlled-cohort members.",
        snapshot["cohort_members_configured"],
    ))

    active = snapshot["active"]
    add(sample("shuddho_coworker_cohort_active_tasks", "Number of active Coworker tasks.", active["tasks"]))
    add(sample("shuddho_coworker_cohort_active_agent_runs", "Number of active Agent runs.", active["agent_runs"]))
    add(sample("shuddho_coworker_cohort_active_provider_actions", "Number of active consequential provider actions.", active["provider_actions"]))
    add(sample("shuddho_coworker_cohort_oldest_active_work_age_seconds", "Age in seconds of the oldest active task, Agent run, or provider action.", active["oldest_work_age_seconds"]))

    tasks = snapshot["tasks"]
    add(sample("shuddho_coworker_cohort_task_samples", "Measured terminal task samples in the current observation window.", tasks["samples"]))
    add(sample("shuddho_coworker_cohort_tasks_completed", "Completed task count in the current observation window.", tasks["completed"]))
    add(sample("shuddho_coworker_cohort_tasks_failed", "Failed task count in the current observation window.", tasks["failed"]))
    add(sample("shuddho_coworker_cohort_tasks_needs_input", "Needs-input task count in the current observation window.", tasks["needs_input"]))
    add(sample("shuddho_coworker_cohort_task_success_ratio", "Task success ratio in the current observation window.", tasks["success_rate"]))
    add(sample("shuddho_coworker_cohort_task_failure_ratio", "Task failure ratio in the current observation window.", tasks["failure_rate"]))

    provider = snapshot["provider"]
    add(sample("shuddho_coworker_cohort_model_samples", "Measured model/provider attempts in the current observation window.", provider["samples"]))
    add(sample("shuddho_coworker_cohort_model_failed_or_unknown", "Failed or unknown-outcome model/provider attempts in the current observation window.", provider["failed_or_unknown"]))
    add(sample("shuddho_coworker_cohort_model_failure_ratio", "Model/provider failed-or-unknown ratio in the current observation window.", provider["failure_rate"]))
    add(sample("shuddho_coworker_cohort_model_p95_latency_ms", "Observed p95 model/provider latency in milliseconds.", provider["p95_latency_ms"]))
    add(sample("shuddho_coworker_cohort_model_window_tokens", "Conservatively accounted model tokens in the current observation window, including in-flight reservations.", provider["window_tokens"]))
    add(sample("shuddho_coworker_provider_active_leases", "Active shared provider-capacity leases across Coworker workers.", provider.get("active_leases", 0)))
    add(sample("shuddho_coworker_provider_reserved_lease_tokens", "Tokens reserved by active shared provider-capacity leases.", provider.get("reserved_lease_tokens", 0)))
    add(sample("shuddho_coworker_provider_oldest_lease_age_seconds", "Age in seconds of the oldest active provider-capacity lease.", provider.get("oldest_lease_age_seconds", 0)))
    add(sample("shuddho_coworker_cohort_model_reserved_attempts", "In-flight reserved model attempts in the current observation window.", provider["reserved_attempts"]))

    agents = snapshot["agents"]
    add(sample("shuddho_coworker_cohort_agent_samples", "Measured terminal Agent runs in the current observation window.", agents["samples"]))
    add(sample("shuddho_coworker_cohort_agents_failed", "Failed Agent runs in the current observation window.", agents["failed"]))
    add(sample("shuddho_coworker_cohort_agent_failure_ratio", "Agent failure ratio in the current observation window.", agents["failure_rate"]))

    research = snapshot["research"]
    add(sample("shuddho_coworker_cohort_research_samples", "Measured Research tasks in the current observation window.", research["samples"]))
    add(sample("shuddho_coworker_cohort_research_failed", "Failed Research tasks in the current observation window.", research["failed"]))
    add(sample("shuddho_coworker_cohort_research_failure_ratio", "Research task failure ratio in the current observation window.", research["failure_rate"]))

    actions = snapshot["actions"]
    add(sample("shuddho_coworker_cohort_action_samples", "Measured consequential actions in the current observation window.", actions["samples"]))
    add(sample("shuddho_coworker_cohort_actions_failed_or_unknown", "Failed or unknown-outcome consequential actions in the current observation window.", actions["failed_or_unknown"]))
    add(sample("shuddho_coworker_cohort_actions_outcome_unknown", "Consequential actions with uncertain provider outcome in the current observation window.", actions["outcome_unknown"]))
    add(sample("shuddho_coworker_cohort_action_failure_ratio", "Consequential action failed-or-unknown ratio in the current observation window.", actions["failure_rate"]))

    add(sample("shuddho_coworker_cohort_storage_bytes", "Total Coworker storage bytes held by configured cohort accounts.", snapshot["storage"]["total_bytes"]))
    lines.append("# EOF")
    return "\n".join(lines) + "\n"


def operator_status(result: dict) -> dict:
    snapshot = result["snapshot"]
    return {
        "schema_version": 1,
        "decision": result["decision"],
        "release_id": result.get("release_id"),
        "generated_at": snapshot["generated_at"],
        "window_minutes": snapshot["window_minutes"],
        "cohort_members_configured": snapshot["cohort_members_configured"],
        "breaches": [
            {
                "metric": item["metric"],
                "actual": item["actual"],
                "threshold": item["threshold"],
                "reason": item["reason"],
            }
            for item in result["breaches"]
        ],
        "rollback": result.get("rollback"),
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export sanitized controlled-cohort health metrics and operator status."
    )
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    parser.add_argument("--prom-output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()

    settings = Settings.from_env()
    rollout = load_rollout(args.rollout)
    thresholds = load_thresholds(args.thresholds)
    snapshot = collect_snapshot(settings, window_minutes=thresholds["window_minutes"])
    result = evaluate(snapshot, rollout, thresholds)

    atomic_write(args.prom_output, render_openmetrics(result))
    atomic_write(args.status_output, json.dumps(operator_status(result), indent=2) + "\n")
    print(json.dumps({
        "decision": result["decision"],
        "prom_output": str(args.prom_output),
        "status_output": str(args.status_output),
        "breaches": len(result["breaches"]),
    }, indent=2))
    if result["decision"] != "CONTINUE_COHORT":
        raise SystemExit("Cohort observability export says STOP_ROLLOUT.")


if __name__ == "__main__":
    main()
