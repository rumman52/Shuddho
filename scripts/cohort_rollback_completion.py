from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from scripts.cohort_release_gate import load_rollout
from services.coworker.config import Settings, enabled as coworker_enabled
from services.coworker.database import session_factory
from services.coworker.models import (
    AgentOutbox,
    AgentRun,
    ExternalAction,
    Outbox,
    Task,
)

TASK_TERMINAL = {"completed", "failed", "cancelled", "needs_input"}
AGENT_TERMINAL = {"completed", "failed", "cancelled"}
ACTION_TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}
ROLLBACK_MODES = {
    "global": ("global_kill_switch", "SHUDDHO_COWORKER_ENABLED"),
    "agent": ("agent_kill_switch", "SHUDDHO_AGENT_RUNTIME_ENABLED"),
    "runtime_v3": ("runtime_v3_kill_switch", "SHUDDHO_AGENT_RUNTIME_V3_ENABLED"),
    "parallel": ("parallel_kill_switch", "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED"),
    "research": ("research_kill_switch", "SHUDDHO_RESEARCH_SERVICES_ENABLED"),
    "actions": ("actions_kill_switch", "SHUDDHO_ACTIONS_ENABLED"),
}


class RollbackCompletionError(RuntimeError):
    pass


def parse_time(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RollbackCompletionError(f"{label} must be an ISO-8601 timestamp.") from None
    if result.tzinfo is None:
        raise RollbackCompletionError(f"{label} must include a timezone.")
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
        raise RollbackCompletionError(
            f"Could not read {label}: {type(error).__name__}"
        ) from None
    if not isinstance(value, dict):
        raise RollbackCompletionError(f"{label} must contain a JSON object.")
    return value


def env_disabled(name: str) -> bool:
    return os.environ.get(name, "false").strip().lower() == "false"


def require_switch_state(mode: str, rollout: dict) -> str:
    rollback = rollout.get("rollback")
    if not isinstance(rollback, dict):
        raise RollbackCompletionError("Rollout manifest has no rollback controls.")
    key, env_name = ROLLBACK_MODES[mode]
    expected = rollback.get(key)
    if expected != f"{env_name}=false":
        raise RollbackCompletionError(
            f"Rollout manifest {key} does not match the expected {env_name}=false control."
        )
    if mode == "global":
        if coworker_enabled():
            raise RollbackCompletionError("Global Coworker kill switch is still enabled.")
    elif not env_disabled(env_name):
        raise RollbackCompletionError(f"{env_name} is still enabled.")
    return expected


def cohort_counts(settings: Settings, mode: str) -> dict:
    if not settings.cohort_enforced or not settings.cohort_account_ids:
        raise RollbackCompletionError(
            "Rollback verification requires backend cohort enforcement and configured cohort members."
        )
    owners = sorted(settings.cohort_account_ids)
    sessions = session_factory(settings.database_url)
    engine = sessions.kw["bind"]
    try:
        with sessions() as db:
            active_tasks = db.scalar(
                select(func.count()).select_from(Task).where(
                    Task.owner_id.in_(owners),
                    Task.state.not_in(TASK_TERMINAL),
                )
            ) or 0
            active_agents = db.scalar(
                select(func.count()).select_from(AgentRun).where(
                    AgentRun.owner_id.in_(owners),
                    AgentRun.state.not_in(AGENT_TERMINAL),
                )
            ) or 0
            active_actions = db.scalar(
                select(func.count()).select_from(ExternalAction).where(
                    ExternalAction.owner_id.in_(owners),
                    ExternalAction.state.not_in(ACTION_TERMINAL),
                )
            ) or 0
            unknown_actions = db.scalar(
                select(func.count()).select_from(ExternalAction).where(
                    ExternalAction.owner_id.in_(owners),
                    ExternalAction.state == "outcome_unknown",
                )
            ) or 0
            undelivered_task_outbox = db.scalar(
                select(func.count()).select_from(Outbox).join(
                    Task, Task.id == Outbox.task_id
                ).where(
                    Task.owner_id.in_(owners),
                    Outbox.delivered.is_(False),
                )
            ) or 0
            undelivered_agent_outbox = db.scalar(
                select(func.count()).select_from(AgentOutbox).join(
                    AgentRun, AgentRun.id == AgentOutbox.run_id
                ).where(
                    AgentRun.owner_id.in_(owners),
                    AgentOutbox.delivered.is_(False),
                )
            ) or 0
    finally:
        engine.dispose()

    counts = {
        "active_tasks": int(active_tasks),
        "active_agent_runs": int(active_agents),
        "active_provider_actions": int(active_actions),
        "outcome_unknown_actions": int(unknown_actions),
        "undelivered_task_outbox": int(undelivered_task_outbox),
        "undelivered_agent_outbox": int(undelivered_agent_outbox),
    }

    required_zero = {"outcome_unknown_actions"}
    if mode == "global":
        required_zero.update(counts)
    elif mode == "agent":
        required_zero.update({"active_agent_runs", "undelivered_agent_outbox"})
    elif mode == "actions":
        required_zero.update({"active_provider_actions"})
    elif mode == "research":
        # Research runs on the durable task path. Require no active task work before
        # considering the research rollback fully drained.
        required_zero.update({"active_tasks", "undelivered_task_outbox"})
    elif mode == "parallel":
        # Existing v2 runs remain supported after the flag is disabled. Completion
        # means there are no active Agent runs left that still depend on that path.
        required_zero.update({"active_agent_runs", "undelivered_agent_outbox"})

    failures = {key: counts[key] for key in sorted(required_zero) if counts[key] != 0}
    if failures:
        formatted = ", ".join(f"{key}={value}" for key, value in failures.items())
        raise RollbackCompletionError(
            "Rollback drain/reconciliation is incomplete: " + formatted
        )
    return counts


def validate_post_status(
    status: dict,
    *,
    release_id: str,
    deployed_at: datetime,
) -> dict:
    if status.get("release_id") != release_id:
        raise RollbackCompletionError("Post-rollback operator status has the wrong release_id.")
    if status.get("decision") != "CONTINUE_COHORT":
        raise RollbackCompletionError(
            "Post-rollback operator status must be CONTINUE_COHORT after drain/reconciliation."
        )
    breaches = status.get("breaches")
    if breaches != []:
        raise RollbackCompletionError("Post-rollback operator status still contains breaches.")
    generated_at = status.get("generated_at")
    if not isinstance(generated_at, str):
        raise RollbackCompletionError("Post-rollback operator status has no generated_at timestamp.")
    generated = parse_time(generated_at, "operator status generated_at")
    if generated < deployed_at:
        raise RollbackCompletionError(
            "Post-rollback operator status predates the rollback deployment."
        )
    members = status.get("cohort_members_configured")
    if not isinstance(members, int) or isinstance(members, bool) or members < 1:
        raise RollbackCompletionError(
            "Post-rollback operator status has an invalid cohort member count."
        )
    return {
        "generated_at": generated.isoformat(),
        "cohort_members_configured": members,
    }


def build_evidence(
    *,
    settings: Settings,
    rollout: dict,
    rollout_path: Path,
    post_status_path: Path,
    mode: str,
    deployment_reference: str,
    deployed_at: str,
) -> dict:
    release_id = rollout.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise RollbackCompletionError("Rollout manifest release_id is required.")
    if not deployment_reference.strip() or len(deployment_reference) > 500:
        raise RollbackCompletionError(
            "deployment_reference must be non-empty and at most 500 characters."
        )
    deployment_time = parse_time(deployed_at, "deployed_at")
    applied_switch = require_switch_state(mode, rollout)
    counts = cohort_counts(settings, mode)
    status = load_json(post_status_path, "post-rollback operator status")
    status_summary = validate_post_status(
        status,
        release_id=release_id,
        deployed_at=deployment_time,
    )
    return {
        "schema_version": 1,
        "release_id": release_id,
        "status": "rollback_completed",
        "mode": mode,
        "deployment_reference": deployment_reference,
        "deployed_at": deployment_time.isoformat(),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "applied_switch": applied_switch,
        "drain": counts,
        "post_rollback_health": status_summary,
        "artifact_sha256": {
            "rollout_manifest": sha256_file(rollout_path),
            "operator_status": sha256_file(post_status_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify that a Shuddho controlled-cohort rollback actually completed."
    )
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--post-status", type=Path, required=True)
    parser.add_argument("--mode", choices=sorted(ROLLBACK_MODES), default="global")
    parser.add_argument("--deployment-reference", required=True)
    parser.add_argument("--deployed-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        rollout = load_rollout(args.rollout)
        evidence = build_evidence(
            settings=settings,
            rollout=rollout,
            rollout_path=args.rollout,
            post_status_path=args.post_status,
            mode=args.mode,
            deployment_reference=args.deployment_reference,
            deployed_at=args.deployed_at,
        )
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "written": str(args.output),
            "status": evidence["status"],
            "mode": evidence["mode"],
            "deployment_reference": evidence["deployment_reference"],
        }, indent=2))
    except (RollbackCompletionError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
