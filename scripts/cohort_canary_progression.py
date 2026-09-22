from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.cohort_release_gate import load_rollout


class CanaryProgressionError(RuntimeError):
    pass


PLAN_KEYS = {"release_id", "max_gap_minutes", "stale_after_minutes", "stages"}
STAGE_KEYS = {
    "name",
    "min_members",
    "max_users",
    "min_healthy_windows",
    "min_observation_minutes",
    "min_task_samples",
    "min_provider_samples",
    "min_agent_samples",
    "min_research_samples",
    "min_action_samples",
}


def parse_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CanaryProgressionError(f"Invalid ISO-8601 timestamp: {value!r}") from None
    if result.tzinfo is None:
        raise CanaryProgressionError("Canary timestamps must include a timezone.")
    return result.astimezone(timezone.utc)


def load_plan(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != PLAN_KEYS:
        raise CanaryProgressionError("Canary plan must contain the exact documented top-level keys.")
    if not isinstance(value["release_id"], str) or not value["release_id"].strip():
        raise CanaryProgressionError("Canary plan release_id is required.")
    for key in ("max_gap_minutes", "stale_after_minutes"):
        if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 1:
            raise CanaryProgressionError(f"{key} must be a positive integer.")
    stages = value["stages"]
    if not isinstance(stages, list) or not stages:
        raise CanaryProgressionError("Canary plan requires at least one stage.")
    names: set[str] = set()
    previous_max = 0
    for stage in stages:
        if not isinstance(stage, dict) or set(stage) != STAGE_KEYS:
            raise CanaryProgressionError("Every canary stage must contain the exact documented key set.")
        name = stage["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise CanaryProgressionError("Canary stage names must be unique non-empty strings.")
        names.add(name)
        for key in STAGE_KEYS - {"name"}:
            if not isinstance(stage[key], int) or isinstance(stage[key], bool) or stage[key] < 0:
                raise CanaryProgressionError(f"{name}.{key} must be a non-negative integer.")
        if stage["min_members"] < 1 or stage["max_users"] < 1:
            raise CanaryProgressionError(f"{name} member bounds must be positive.")
        if stage["min_members"] > stage["max_users"]:
            raise CanaryProgressionError(f"{name}.min_members cannot exceed max_users.")
        if stage["max_users"] <= previous_max:
            raise CanaryProgressionError("Canary stage max_users must increase strictly.")
        if stage["min_healthy_windows"] < 1 or stage["min_observation_minutes"] < 1:
            raise CanaryProgressionError(f"{name} requires positive health-window and observation minimums.")
        previous_max = stage["max_users"]
    return value


def load_history(directory: Path) -> list[dict]:
    rows: list[dict] = []
    if not directory.is_dir():
        raise CanaryProgressionError("Health history path must be a directory.")
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CanaryProgressionError(f"Could not read health history file {path.name}: {type(error).__name__}") from None
        if not isinstance(value, dict):
            raise CanaryProgressionError(f"Health history file {path.name} must contain a JSON object.")
        snapshot = value.get("snapshot")
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("generated_at"), str):
            raise CanaryProgressionError(f"Health history file {path.name} has no valid snapshot timestamp.")
        rows.append(value)
    if not rows:
        raise CanaryProgressionError("Health history directory contains no JSON decisions.")
    rows.sort(key=lambda item: parse_time(item["snapshot"]["generated_at"]))
    timestamps = [parse_time(item["snapshot"]["generated_at"]) for item in rows]
    if len(timestamps) != len(set(timestamps)):
        raise CanaryProgressionError("Health history contains duplicate snapshot timestamps.")
    return rows


def _stage(plan: dict, name: str) -> tuple[int, dict]:
    for index, stage in enumerate(plan["stages"]):
        if stage["name"] == name:
            return index, stage
    raise CanaryProgressionError(f"Unknown canary stage: {name}")


def _samples(history: list[dict], key: str) -> int:
    return sum(int(item["snapshot"][key]["samples"]) for item in history)


def evaluate_progression(
    history: list[dict],
    rollout: dict,
    plan: dict,
    *,
    current_stage: str,
    now: datetime | None = None,
) -> dict:
    if rollout.get("release_id") != plan["release_id"]:
        raise CanaryProgressionError("Rollout manifest and canary plan release_id do not match.")
    stage_index, stage = _stage(plan, current_stage)
    rollout_max = rollout.get("cohort", {}).get("max_users") if isinstance(rollout.get("cohort"), dict) else None
    if not isinstance(rollout_max, int) or isinstance(rollout_max, bool):
        raise CanaryProgressionError("Rollout manifest cohort.max_users is invalid.")
    if plan["stages"][-1]["max_users"] > rollout_max:
        raise CanaryProgressionError("Canary plan exceeds the approved rollout manifest cohort maximum.")

    release_id = rollout["release_id"]
    relevant: list[dict] = []
    for item in history:
        if item.get("release_id") != release_id:
            raise CanaryProgressionError("Health history contains a different release_id.")
        snapshot = item["snapshot"]
        members = snapshot.get("cohort_members_configured")
        if not isinstance(members, int) or isinstance(members, bool):
            raise CanaryProgressionError("Health history contains an invalid cohort member count.")
        if members > stage["max_users"]:
            return {
                "decision": "STOP_ROLLOUT",
                "release_id": release_id,
                "current_stage": current_stage,
                "next_stage": None,
                "reasons": ["configured_members_exceed_current_stage"],
                "summary": {"configured_members": members},
                "rollback": rollout.get("rollback"),
            }
        if members >= stage["min_members"]:
            relevant.append(item)

    if not relevant:
        return {
            "decision": "HOLD",
            "release_id": release_id,
            "current_stage": current_stage,
            "next_stage": plan["stages"][stage_index + 1]["name"] if stage_index + 1 < len(plan["stages"]) else None,
            "reasons": ["stage_not_fully_enrolled"],
            "summary": {"healthy_windows": 0, "configured_members": history[-1]["snapshot"]["cohort_members_configured"]},
            "rollback": None,
        }

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    times = [parse_time(item["snapshot"]["generated_at"]) for item in relevant]
    latest_age_minutes = (now - times[-1]).total_seconds() / 60
    if latest_age_minutes < -1:
        raise CanaryProgressionError("Latest health snapshot is in the future.")
    if latest_age_minutes > plan["stale_after_minutes"]:
        return {
            "decision": "STOP_ROLLOUT",
            "release_id": release_id,
            "current_stage": current_stage,
            "next_stage": None,
            "reasons": ["latest_health_snapshot_stale"],
            "summary": {"latest_age_minutes": round(latest_age_minutes, 2)},
            "rollback": rollout.get("rollback"),
        }

    stop_rows = [item for item in relevant if item.get("decision") == "STOP_ROLLOUT"]
    if stop_rows:
        return {
            "decision": "STOP_ROLLOUT",
            "release_id": release_id,
            "current_stage": current_stage,
            "next_stage": None,
            "reasons": ["health_history_contains_stop"],
            "summary": {
                "stop_windows": len(stop_rows),
                "latest_stop_at": stop_rows[-1]["snapshot"]["generated_at"],
            },
            "rollback": rollout.get("rollback"),
        }
    if any(item.get("decision") != "CONTINUE_COHORT" for item in relevant):
        raise CanaryProgressionError("Health history contains an unknown decision value.")

    gaps = [
        (times[index] - times[index - 1]).total_seconds() / 60
        for index in range(1, len(times))
    ]
    max_gap = max(gaps, default=0)
    observation_minutes = max(0, (times[-1] - times[0]).total_seconds() / 60)
    latest_members = relevant[-1]["snapshot"]["cohort_members_configured"]

    summary = {
        "configured_members": latest_members,
        "healthy_windows": len(relevant),
        "observation_minutes": round(observation_minutes, 2),
        "max_gap_minutes": round(max_gap, 2),
        "task_samples": _samples(relevant, "tasks"),
        "provider_samples": _samples(relevant, "provider"),
        "agent_samples": _samples(relevant, "agents"),
        "research_samples": _samples(relevant, "research"),
        "action_samples": _samples(relevant, "actions"),
    }
    reasons: list[str] = []
    if latest_members < stage["min_members"]:
        reasons.append("stage_not_fully_enrolled")
    if len(relevant) < stage["min_healthy_windows"]:
        reasons.append("insufficient_healthy_windows")
    if observation_minutes < stage["min_observation_minutes"]:
        reasons.append("insufficient_observation_time")
    if max_gap > plan["max_gap_minutes"]:
        reasons.append("monitoring_gap")
    for key, summary_key in (
        ("min_task_samples", "task_samples"),
        ("min_provider_samples", "provider_samples"),
        ("min_agent_samples", "agent_samples"),
        ("min_research_samples", "research_samples"),
        ("min_action_samples", "action_samples"),
    ):
        if summary[summary_key] < stage[key]:
            reasons.append("insufficient_" + summary_key)

    next_stage = plan["stages"][stage_index + 1]["name"] if stage_index + 1 < len(plan["stages"]) else None
    if reasons:
        decision = "HOLD"
    elif next_stage is None:
        decision = "HOLD"
        reasons = ["final_stage_reached"]
    else:
        decision = "ELIGIBLE_FOR_EXPANSION"

    return {
        "decision": decision,
        "release_id": release_id,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "reasons": reasons,
        "summary": summary,
        "rollback": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate sustained health before controlled Coworker cohort expansion.")
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--current-stage", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = evaluate_progression(
        load_history(args.history_dir),
        load_rollout(args.rollout),
        load_plan(args.plan),
        current_stage=args.current_stage,
    )
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if result["decision"] == "STOP_ROLLOUT":
        raise SystemExit("Canary progression says STOP_ROLLOUT.")
    if result["decision"] != "ELIGIBLE_FOR_EXPANSION":
        raise SystemExit("Canary progression is HOLD.")


if __name__ == "__main__":
    main()
