from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from scripts.cohort_canary_progression import load_history, parse_time
from scripts.cohort_release_ledger import file_sha256, ledger_key, read_entries, verify_entries


class PostScaleObservationError(RuntimeError):
    pass


PLAN_KEYS = {
    "release_id",
    "max_gap_minutes",
    "stale_after_minutes",
    "min_enrollment_ratio",
    "min_healthy_windows",
    "min_observation_minutes",
    "min_task_samples",
    "min_provider_samples",
    "min_agent_samples",
    "min_research_samples",
    "min_action_samples",
}


def load_plan(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PostScaleObservationError(
            f"Could not read post-scale observation plan: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict) or set(value) != PLAN_KEYS:
        raise PostScaleObservationError(
            "Post-scale observation plan has an unexpected schema."
        )
    if not isinstance(value["release_id"], str) or not value["release_id"].strip():
        raise PostScaleObservationError("release_id is required.")
    for key in (
        "max_gap_minutes",
        "stale_after_minutes",
        "min_healthy_windows",
        "min_observation_minutes",
        "min_task_samples",
        "min_provider_samples",
        "min_agent_samples",
        "min_research_samples",
        "min_action_samples",
    ):
        if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] < 0:
            raise PostScaleObservationError(f"{key} must be a non-negative integer.")
    if value["max_gap_minutes"] < 1 or value["stale_after_minutes"] < 1:
        raise PostScaleObservationError(
            "max_gap_minutes and stale_after_minutes must be positive."
        )
    if value["min_healthy_windows"] < 1 or value["min_observation_minutes"] < 1:
        raise PostScaleObservationError(
            "Post-scale observation requires positive window and duration minimums."
        )
    ratio = value["min_enrollment_ratio"]
    if (
        not isinstance(ratio, (int, float))
        or isinstance(ratio, bool)
        or not math.isfinite(float(ratio))
        or not 0 < float(ratio) <= 1
    ):
        raise PostScaleObservationError(
            "min_enrollment_ratio must be greater than 0 and at most 1."
        )
    return value


def load_activation(path: Path, release_id: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PostScaleObservationError(
            f"Could not read scale activation: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise PostScaleObservationError("Scale activation must contain a JSON object.")
    if value.get("status") != "bounded_expansion_verified":
        raise PostScaleObservationError("Scale activation has not been verified.")
    if value.get("release_id") != release_id:
        raise PostScaleObservationError("Scale activation release_id does not match.")
    for key in ("current_stage", "proposed_stage"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise PostScaleObservationError(f"Scale activation {key} is required.")
    current_max = value.get("current_max_users")
    proposed_max = value.get("proposed_max_users")
    configured_max = value.get("configured_max_users")
    configured_members = value.get("configured_members")
    for key, number in (
        ("current_max_users", current_max),
        ("proposed_max_users", proposed_max),
        ("configured_max_users", configured_max),
        ("configured_members", configured_members),
    ):
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise PostScaleObservationError(
                f"Scale activation {key} must be a positive integer."
            )
    if proposed_max <= current_max:
        raise PostScaleObservationError(
            "Scale activation proposed maximum must exceed the prior maximum."
        )
    if configured_max != proposed_max:
        raise PostScaleObservationError(
            "Scale activation configured maximum does not match the reviewed maximum."
        )
    if not current_max < configured_members <= proposed_max:
        raise PostScaleObservationError(
            "Scale activation configured membership is outside the reviewed expansion bounds."
        )
    verified_at = value.get("verified_at")
    if not isinstance(verified_at, str):
        raise PostScaleObservationError("Scale activation has no verified_at timestamp.")
    parse_time(verified_at)
    return value


def activation_epoch(
    activation_path: Path,
    ledger_path: Path,
    *,
    activation: dict,
) -> datetime:
    try:
        entries = read_entries(ledger_path)
        state = verify_entries(entries, ledger_key())
    except Exception as error:
        raise PostScaleObservationError(
            f"Release ledger verification failed: {error}"
        ) from None
    release_id = activation["release_id"]
    if state.get("release_id") != release_id:
        raise PostScaleObservationError(
            "Release ledger release_id does not match the scale activation."
        )
    matches = [
        item
        for item in entries
        if item.get("schema_version") == 4
        and item.get("event_type") == "bounded_expansion_verified"
        and item.get("current_stage") == activation["current_stage"]
        and item.get("next_stage") == activation["proposed_stage"]
    ]
    if len(matches) != 1:
        raise PostScaleObservationError(
            "Release ledger must contain exactly one matching bounded_expansion_verified event."
        )
    entry = matches[0]
    artifacts = entry.get("artifact_sha256")
    if (
        not isinstance(artifacts, dict)
        or artifacts.get("scale_activation") != file_sha256(activation_path)
    ):
        raise PostScaleObservationError(
            "Release ledger does not bind this scale-activation artifact."
        )
    if entry.get("change_reference") != activation.get("change_reference"):
        raise PostScaleObservationError(
            "Release ledger change reference does not match the activation artifact."
        )
    created_at = entry.get("created_at")
    if not isinstance(created_at, str):
        raise PostScaleObservationError(
            "Scale activation ledger entry has no created_at timestamp."
        )
    return max(parse_time(activation["verified_at"]), parse_time(created_at))


def sample_sum(history: list[dict], key: str) -> int:
    total = 0
    for item in history:
        snapshot = item.get("snapshot")
        metric = snapshot.get(key) if isinstance(snapshot, dict) else None
        samples = metric.get("samples") if isinstance(metric, dict) else None
        if not isinstance(samples, int) or isinstance(samples, bool) or samples < 0:
            raise PostScaleObservationError(
                f"Health history contains invalid {key}.samples."
            )
        total += samples
    return total


def evaluate_observation(
    history: list[dict],
    activation: dict,
    plan: dict,
    *,
    epoch_start: datetime,
    now: datetime | None = None,
) -> dict:
    if activation["release_id"] != plan["release_id"]:
        raise PostScaleObservationError(
            "Observation plan and scale activation release_id do not match."
        )
    release_id = activation["release_id"]
    stage = activation["proposed_stage"]
    stage_max = activation["proposed_max_users"]
    epoch_start = epoch_start.astimezone(timezone.utc)

    post = [
        item
        for item in history
        if parse_time(item["snapshot"]["generated_at"]) > epoch_start
    ]
    base = {
        "release_id": release_id,
        "current_stage": stage,
        "next_stage": None,
        "stage_max_users": stage_max,
        "epoch_start": epoch_start.isoformat(),
    }
    if not post:
        return {
            **base,
            "decision": "HOLD",
            "generated_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
            "reasons": ["no_post_scale_health"],
            "summary": {"healthy_windows": 0},
        }

    for item in post:
        if item.get("release_id") != release_id:
            raise PostScaleObservationError(
                "Health history contains a different release_id."
            )
        snapshot = item.get("snapshot")
        members = snapshot.get("cohort_members_configured") if isinstance(snapshot, dict) else None
        if not isinstance(members, int) or isinstance(members, bool) or members < 1:
            raise PostScaleObservationError(
                "Health history contains an invalid cohort member count."
            )
        if members > stage_max:
            return {
                **base,
                "decision": "STOP_ROLLOUT",
                "generated_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
                "reasons": ["configured_members_exceed_reviewed_stage"],
                "summary": {"configured_members": members},
            }

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    latest = post[-1]
    latest_time = parse_time(latest["snapshot"]["generated_at"])
    age_minutes = (now - latest_time).total_seconds() / 60
    if age_minutes < -1:
        raise PostScaleObservationError("Latest health snapshot is in the future.")
    if age_minutes > plan["stale_after_minutes"]:
        return {
            **base,
            "decision": "STOP_ROLLOUT",
            "generated_at": now.isoformat(),
            "reasons": ["latest_health_snapshot_stale"],
            "summary": {"latest_age_minutes": round(age_minutes, 2)},
        }

    stop_rows = [item for item in post if item.get("decision") == "STOP_ROLLOUT"]
    if stop_rows:
        return {
            **base,
            "decision": "STOP_ROLLOUT",
            "generated_at": now.isoformat(),
            "reasons": ["post_scale_health_contains_stop"],
            "summary": {
                "stop_windows": len(stop_rows),
                "latest_stop_at": stop_rows[-1]["snapshot"]["generated_at"],
            },
        }
    if any(item.get("decision") != "CONTINUE_COHORT" for item in post):
        raise PostScaleObservationError(
            "Health history contains an unknown decision value."
        )

    min_members = max(
        activation["current_max_users"] + 1,
        math.ceil(stage_max * float(plan["min_enrollment_ratio"])),
    )
    latest_members = latest["snapshot"]["cohort_members_configured"]
    if latest_members < min_members:
        return {
            **base,
            "decision": "HOLD",
            "generated_at": now.isoformat(),
            "reasons": ["stage_not_sufficiently_enrolled"],
            "summary": {
                "configured_members": latest_members,
                "required_members": min_members,
                "healthy_windows": 0,
            },
        }

    relevant = [
        item
        for item in post
        if item["snapshot"]["cohort_members_configured"] >= min_members
    ]
    times = [parse_time(item["snapshot"]["generated_at"]) for item in relevant]
    gaps = [
        (times[index] - times[index - 1]).total_seconds() / 60
        for index in range(1, len(times))
    ]
    observation_minutes = max(
        0, (times[-1] - times[0]).total_seconds() / 60
    )
    summary = {
        "configured_members": latest_members,
        "required_members": min_members,
        "healthy_windows": len(relevant),
        "observation_minutes": round(observation_minutes, 2),
        "max_gap_minutes": round(max(gaps, default=0), 2),
        "task_samples": sample_sum(relevant, "tasks"),
        "provider_samples": sample_sum(relevant, "provider"),
        "agent_samples": sample_sum(relevant, "agents"),
        "research_samples": sample_sum(relevant, "research"),
        "action_samples": sample_sum(relevant, "actions"),
    }
    reasons = []
    if summary["healthy_windows"] < plan["min_healthy_windows"]:
        reasons.append("insufficient_healthy_windows")
    if summary["observation_minutes"] < plan["min_observation_minutes"]:
        reasons.append("insufficient_observation_time")
    if summary["max_gap_minutes"] > plan["max_gap_minutes"]:
        reasons.append("monitoring_gap")
    for plan_key, summary_key in (
        ("min_task_samples", "task_samples"),
        ("min_provider_samples", "provider_samples"),
        ("min_agent_samples", "agent_samples"),
        ("min_research_samples", "research_samples"),
        ("min_action_samples", "action_samples"),
    ):
        if summary[summary_key] < plan[plan_key]:
            reasons.append("insufficient_" + summary_key)

    return {
        **base,
        "decision": (
            "ELIGIBLE_FOR_REQUALIFICATION" if not reasons else "HOLD"
        ),
        "generated_at": now.isoformat(),
        "reasons": reasons,
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate sustained health after a verified dynamic Coworker cohort expansion."
    )
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--scale-activation", type=Path, required=True)
    parser.add_argument("--release-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        plan = load_plan(args.plan)
        activation = load_activation(args.scale_activation, plan["release_id"])
        epoch = activation_epoch(
            args.scale_activation,
            args.release_ledger,
            activation=activation,
        )
        result = evaluate_observation(
            load_history(args.history_dir),
            activation,
            plan,
            epoch_start=epoch,
        )
    except (PostScaleObservationError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from None

    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if result["decision"] == "STOP_ROLLOUT":
        raise SystemExit("Post-scale observation says STOP_ROLLOUT.")
    if result["decision"] != "ELIGIBLE_FOR_REQUALIFICATION":
        raise SystemExit("Post-scale observation is HOLD.")


if __name__ == "__main__":
    main()
