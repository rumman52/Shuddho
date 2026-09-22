from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.models import AgentRun, AgentStep, Artifact, Task
from services.coworker.workflow import AgentWorkflowV2

REQUIRED_FLAGS = (
    "agent_runtime_enabled",
    "agent_dependency_graph_enabled",
    "agent_parallel_execution_enabled",
    "research_services_enabled",
    "work_services_enabled",
)


class RecoveryFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def parse_utc(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RecoveryFailure("Restart time must be an ISO-8601 timestamp with a timezone.") from None
    if result.tzinfo is None:
        raise RecoveryFailure("Restart time must include a timezone.")
    return result.astimezone(timezone.utc)


def require_exercise_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_RECOVERY_EXERCISE", "").lower() != "true":
        raise RecoveryFailure("Set SHUDDHO_STAGING_ALLOW_RECOVERY_EXERCISE=true only in the controlled staging environment.")


def require_runtime(settings: Settings) -> None:
    missing = [name for name in REQUIRED_FLAGS if not getattr(settings, name)]
    if missing:
        raise RecoveryFailure("Required staging runtime flags are disabled: " + ", ".join(missing))
    if settings.max_agent_parallel_steps < 2:
        raise RecoveryFailure("SHUDDHO_AGENT_MAX_PARALLEL_STEPS must be at least 2 for the recovery exercise.")


def staging_owner() -> str:
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    try:
        response = httpx.get(
            base_url + "/api/v1/me",
            headers={"Authorization": "Bearer " + token},
            timeout=20,
            follow_redirects=False,
        )
    except httpx.HTTPError as error:
        raise RecoveryFailure(f"Staging /me request failed: {type(error).__name__}") from None
    if response.status_code != 200:
        raise RecoveryFailure(f"Staging /me returned HTTP {response.status_code}.")
    try:
        value = response.json()
    except ValueError:
        raise RecoveryFailure("Staging /me did not return JSON.") from None
    owner = value.get("account_id") if isinstance(value, dict) else None
    if not isinstance(owner, str) or not owner:
        raise RecoveryFailure("Staging /me did not return an account id.")
    return owner


def synthetic_plan() -> list[AgentPlanStep]:
    return [
        AgentPlanStep(tool="research.search", arguments={
            "instruction": "Research the official Python language website for a synthetic staging reliability check.",
            "notes": "", "document_ids": [], "output_language": "en",
            "query": "Python official language website", "time_range": "any",
        }),
        AgentPlanStep(tool="research.search", arguments={
            "instruction": "Research the official Temporal documentation for a synthetic staging reliability check.",
            "notes": "", "document_ids": [], "output_language": "en",
            "query": "Temporal official documentation workflows", "time_range": "any",
        }),
        AgentPlanStep(tool="document.create", arguments={
            "instruction": "Create a short synthetic staging reliability summary from the completed workflow context.",
            "notes": "Synthetic staging probe only. No customer data.",
            "document_ids": [], "output_language": "en",
        }),
    ]


async def temporal_client(settings: Settings) -> Client:
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        api_key=settings.temporal_api_key or None,
        tls=settings.temporal_tls,
    )


async def prepare(settings: Settings, state_path: Path) -> dict:
    require_exercise_guard()
    require_runtime(settings)
    owner = staging_owner()
    container = Container.create(settings)
    key = "staging-temporal-recovery-" + uuid.uuid4().hex
    try:
        run, _created = container.agent.create(
            owner,
            AgentRunCreate(
                goal="Run a synthetic two-branch research fan-out and document fan-in recovery exercise.",
                output_language="en",
            ),
            key,
        )
        saved = container.agent.save_plan(owner, run["id"], synthetic_plan())
        dependencies = [step["depends_on"] for step in saved["steps"]]
        if dependencies != [[], [], [1, 2]]:
            raise RecoveryFailure(f"Unexpected persisted dependency graph: {dependencies!r}")
        client = await temporal_client(settings)
        workflow_id = "shuddho-agent-" + run["id"]
        try:
            await client.start_workflow(
                AgentWorkflowV2.run,
                {"run_id": run["id"], "max_parallel_steps": settings.max_agent_parallel_steps},
                id=workflow_id,
                task_queue=settings.task_queue,
                execution_timeout=timedelta(seconds=settings.agent_run_timeout_seconds),
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        except WorkflowAlreadyStartedError:
            pass
        container.agent.delivered(run["id"])
        state = {
            "run_id": run["id"],
            "workflow_id": workflow_id,
            "owner_id": owner,
            "created_at": run["created_at"],
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return state
    finally:
        container.repository.sessions.kw["bind"].dispose()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def validate_persisted_recovery(
    run: AgentRun,
    steps: list[AgentStep],
    tasks: list[Task],
    restart_at: datetime,
) -> dict:
    if run.state != "completed":
        raise RecoveryFailure(f"Agent recovery run ended in state {run.state!r}, not completed.")
    ordered = sorted(steps, key=lambda item: item.ordinal)
    if [item.ordinal for item in ordered] != [1, 2, 3]:
        raise RecoveryFailure("Recovery run did not persist exactly three agent steps.")
    if [list(item.depends_on_ordinals or []) for item in ordered] != [[], [], [1, 2]]:
        raise RecoveryFailure("Persisted fan-out/fan-in dependencies changed during recovery.")
    if any(item.state != "completed" for item in ordered):
        raise RecoveryFailure("One or more persisted agent steps did not complete.")
    if any(item.started_at is None or item.finished_at is None for item in ordered):
        raise RecoveryFailure("Agent step timing evidence is incomplete.")
    if _utc(ordered[2].started_at) < max(_utc(ordered[0].finished_at), _utc(ordered[1].finished_at)):
        raise RecoveryFailure("Fan-in step started before both dependencies completed.")

    if len(tasks) != 3:
        raise RecoveryFailure(f"Expected exactly three child tasks for the run; found {len(tasks)}.")
    step_ids = {item.id for item in ordered}
    task_step_ids = [item.agent_step_id for item in tasks]
    if len(set(task_step_ids)) != 3 or set(task_step_ids) != step_ids:
        raise RecoveryFailure("Child task linkage is duplicated or does not match the three agent steps.")
    expected_keys = {f"agent:{run.id}:{ordinal}" for ordinal in (1, 2, 3)}
    if {item.idempotency_key for item in tasks} != expected_keys:
        raise RecoveryFailure("Child task idempotency keys do not match the server-owned run/ordinal contract.")

    start = _utc(run.created_at) - timedelta(seconds=30)
    finish = _utc(run.updated_at) + timedelta(seconds=30)
    if not start <= restart_at <= finish:
        raise RecoveryFailure("Recorded worker restart did not occur during the recovery run window.")
    return {
        "fan_in_started_at": _utc(ordered[2].started_at).isoformat(),
        "branch_finished_at": [_utc(ordered[0].finished_at).isoformat(), _utc(ordered[1].finished_at).isoformat()],
        "child_tasks": len(tasks),
    }


async def verify(
    settings: Settings,
    state_path: Path,
    restart_at: datetime,
    restart_reference: str,
    evidence_path: Path,
    base_evidence: Path | None,
) -> dict:
    require_exercise_guard()
    require_runtime(settings)
    if not restart_reference.strip():
        raise RecoveryFailure("A non-empty worker restart evidence reference is required.")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise RecoveryFailure("Recovery state file must be a JSON object.")
    run_id = str(state.get("run_id") or "")
    owner = str(state.get("owner_id") or "")
    workflow_id = str(state.get("workflow_id") or "")
    if not run_id or not owner or workflow_id != "shuddho-agent-" + run_id:
        raise RecoveryFailure("Recovery state file is incomplete or inconsistent.")

    container = Container.create(settings)
    try:
        with container.repository.sessions() as db:
            run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_id == owner))
            if run is None:
                raise RecoveryFailure("Recovery agent run was not found in staging.")
            steps = list(db.scalars(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.owner_id == owner,
            )).all())
            tasks = list(db.scalars(select(Task).where(
                Task.agent_run_id == run_id, Task.owner_id == owner,
            )).all())
            artifact_count = len(list(db.scalars(select(Artifact.id).where(
                Artifact.task_id.in_([task.id for task in tasks]),
                Artifact.owner_id == owner,
            )).all())) if tasks else 0
            facts = validate_persisted_recovery(run, steps, tasks, restart_at)

        client = await temporal_client(settings)
        description = await client.get_workflow_handle(workflow_id).describe()
        status_name = str(getattr(description.status, "name", description.status)).lower()
        if "completed" not in status_name:
            raise RecoveryFailure(f"Temporal workflow is not completed: {status_name}")

        base = {}
        if base_evidence:
            value = json.loads(base_evidence.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise RecoveryFailure("Base staging evidence must be a JSON object.")
            base.update(value)
        concise_ref = restart_reference.strip()[:240]
        base.update({
            "temporal": passed(
                f"AgentWorkflow v2 completed across controlled worker restart; restart_ref={concise_ref}; workflow={workflow_id}"
            ),
            "parallel_restart": passed(
                f"post-restart run completed with exactly {facts['child_tasks']} server-idempotent child tasks and {artifact_count} persisted artifacts; restart_ref={concise_ref}"
            ),
            "fan_in": passed(
                "persisted step 3 depended on [1,2] and started only after both branch steps finished"
            ),
        })
        evidence_path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        return {"checks": {"temporal": "passed", "parallel_restart": "passed", "fan_in": "passed"}}
    finally:
        container.repository.sessions.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled Temporal/AgentWorkflow v2 staging recovery validation.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--restart-at", required=True, help="ISO-8601 timestamp from the staging worker restart/deployment event.")
    verify_parser.add_argument("--restart-reference", required=True, help="Deployment event, pod UID transition, or platform run reference.")
    verify_parser.add_argument("--base-evidence", type=Path)
    verify_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "prepare":
            result = asyncio.run(prepare(settings, args.state))
            print(json.dumps({
                "status": "prepared",
                "run_id": result["run_id"],
                "workflow_id": result["workflow_id"],
                "next": "Restart/replace the staging Coworker worker while this run is active, then run verify with the platform restart timestamp and reference.",
            }, indent=2))
        else:
            result = asyncio.run(verify(
                settings,
                args.state,
                parse_utc(args.restart_at),
                args.restart_reference,
                args.output,
                args.base_evidence,
            ))
            print(json.dumps({"written": str(args.output), **result}, indent=2))
    except (RecoveryFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
