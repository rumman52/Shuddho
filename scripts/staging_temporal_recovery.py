from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from scripts.staging_api_exercise import ExerciseFailure, env_secret, verified_staging_owner
from scripts.staging_release_evidence import (
    StagingReleaseEvidenceError,
    passed,
    prepared_release_context,
    validate_prepared_release_context,
    write_private_json,
)
from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.models import AgentOutbox, AgentRun, AgentStep, Artifact, Outbox, Task
from services.coworker.reviewed_skill_registry import WORKER_HEARTBEAT_TTL_SECONDS
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


def parse_utc(value: str) -> datetime:
    try:
        if not isinstance(value, str):
            raise ValueError("missing timestamp")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RecoveryFailure("Restart time must be an ISO-8601 timestamp with a timezone.") from None
    if result.tzinfo is None:
        raise RecoveryFailure("Restart time must include a timezone.")
    return result.astimezone(timezone.utc)


def _preflight_private_state(path: Path) -> None:
    """Fail before staging mutations if private evidence cannot be published safely."""
    if path.exists() or path.is_symlink():
        raise StagingReleaseEvidenceError("Refusing to overwrite existing private evidence file.")
    if not path.parent.is_dir():
        raise StagingReleaseEvidenceError("Private evidence directory does not exist.")
    probe = path.parent / f".{path.name}.{uuid.uuid4().hex}.preflight"
    try:
        write_private_json(probe, {"preflight": True})
    finally:
        probe.unlink(missing_ok=True)



def read_private_recovery_receipt(path: Path) -> dict:
    """Read only a protected, regular, single-owner receipt, without following symlinks.

    Operator evidence may contain resource identities. Do not silently read
    a public, replaced, malformed or duplicate-key checkpoint file.
    """
    def unique_fields(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecoveryFailure("Protected recovery receipt contains duplicate JSON fields.")
            result[key] = value
        return result

    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_size > 1024 * 1024
                or (os.name == "posix" and (
                    stat.S_IMODE(info.st_mode) & 0o077
                    or info.st_uid != os.getuid()
                ))):
            raise RecoveryFailure("Protected recovery receipt must be an owned private regular file.")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = None
            receipt = json.load(
                handle, object_pairs_hook=unique_fields,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    RecoveryFailure("Protected recovery receipt has non-finite JSON values.")
                ),
            )
        if not isinstance(receipt, dict):
            raise RecoveryFailure("Protected recovery receipt must contain a JSON object.")
        return receipt
    except (OSError, UnicodeError, ValueError):
        raise RecoveryFailure("Protected recovery receipt cannot be safely opened or decoded.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


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
    """Authenticate the reviewed managed owner before starting an AgentRun."""
    try:
        return verified_staging_owner(
            env_secret("SHUDDHO_STAGING_TOKEN_A"),
            origin=env_secret("SHUDDHO_STAGING_API_BASE_URL"),
        )
    except ExerciseFailure:
        raise RecoveryFailure(
            "Managed staging owner cannot be verified for Temporal recovery."
        ) from None


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


async def prepare(settings: Settings, state_path: Path, rollout_path: Path) -> dict:
    require_exercise_guard()
    require_runtime(settings)
    context = prepared_release_context(settings, rollout_path)
    _preflight_private_state(state_path)
    owner = staging_owner()
    container = Container.create(settings)
    key = "staging-temporal-recovery-" + uuid.uuid4().hex
    try:
        worker_before = require_active_worker(
            container.repository.worker_inventory(task_queue=settings.task_queue),
            revision=settings.source_revision, task_queue=settings.task_queue,
        )
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
            "release_context": context,
            "run_id": run["id"],
            "workflow_id": workflow_id,
            "owner_id": owner,
            "created_at": run["created_at"],
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "worker_before": {
                key: worker_before[key]
                for key in ("id", "task_queue", "source_revision", "started_at", "heartbeat_at")
            },
        }
        write_private_json(state_path, state)
        return state
    finally:
        container.repository.sessions.kw["bind"].dispose()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)




def require_active_worker(workers: list[dict], *, revision: str, task_queue: str) -> dict:
    """Require one fresh real poller, not an orphan or another SHA on the queue."""
    live = [
        row for row in workers
        if row.get("task_queue") == task_queue
        and row.get("state") == "running"
        and row.get("heartbeat_fresh") is True
    ]
    if len(live) != 1 or live[0].get("source_revision") != revision:
        raise RecoveryFailure("Expected exactly one fresh running worker on the reviewed SHA and queue.")
    row = live[0]
    if not isinstance(row.get("id"), str) or not row["id"]:
        raise RecoveryFailure("Live worker registration has no identity.")
    parse_utc(row.get("started_at", ""))
    parse_utc(row.get("heartbeat_at", ""))
    return row


def validate_worker_replacement(
    before: dict,
    current: list[dict],
    *,
    revision: str,
    task_queue: str,
    restart_at: datetime,
    active_start: datetime,
    active_finish: datetime,
) -> dict:
    """Corroborate the platform event with a *new* registered worker during work."""
    if not isinstance(before, dict) or before.get("source_revision") != revision or before.get("task_queue") != task_queue:
        raise RecoveryFailure("Pre-restart worker identity is missing or belongs to a different release.")
    previous_id = before.get("id")
    if not isinstance(previous_id, str) or not previous_id:
        raise RecoveryFailure("Pre-restart worker ID is missing.")
    before_started = parse_utc(before.get("started_at", ""))
    before_heartbeat = parse_utc(before.get("heartbeat_at", ""))
    if before_heartbeat < before_started or before_started >= restart_at:
        raise RecoveryFailure("Pre-restart worker was not registered before the restart event.")
    # The prepare receipt snapshots the OLD worker. A later platform event
    # cannot treat that snapshot as proof of an active poller when its last
    # heartbeat is older than the SAME registry TTL used for live-worker
    # inventory. A future-dated heartbeat also cannot prove interruption.
    if (before_started > active_start
            or before_heartbeat > restart_at
            or (restart_at - before_heartbeat).total_seconds() > WORKER_HEARTBEAT_TTL_SECONDS):
        raise RecoveryFailure(
            "Pre-restart worker heartbeat was stale, future-dated or registered after active work began."
        )

    after = require_active_worker(current, revision=revision, task_queue=task_queue)
    if after["id"] == previous_id:
        raise RecoveryFailure("No distinct worker registration appeared after the restart.")
    started_at = parse_utc(after["started_at"])
    heartbeat = parse_utc(after["heartbeat_at"])
    if not active_start <= started_at <= active_finish:
        raise RecoveryFailure("Replacement worker did not register while the Agent run was active.")
    if not 0 <= (started_at - restart_at).total_seconds() <= 300:
        raise RecoveryFailure("Replacement worker registration must follow the platform restart event within five minutes.")
    if heartbeat <= started_at:
        raise RecoveryFailure("Replacement worker did not advance its heartbeat after registration.")
    return {
        "worker_before_id": previous_id,
        "worker_after_id": after["id"],
        "worker_after_started_at": started_at.isoformat(),
        "worker_before_heartbeat_at": before_heartbeat.isoformat(),
        "worker_after_heartbeat_at": heartbeat.isoformat(),
    }



def attest_active_worker_checkpoint(
    state: dict,
    run: AgentRun,
    steps: list[AgentStep],
    tasks: list[Task],
    current: list[dict],
    *,
    revision: str,
    task_queue: str,
    captured_at: datetime,
) -> dict:
    """Read-only proof of a live child and the ORIGINAL worker just before restart.

    The initial prepare snapshot may have aged beyond the 15-second registry
    TTL while a legitimate research child executes. A new private checkpoint
    must be captured during the active child; no timestamp is backdated.
    """
    original = state.get("worker_before")
    if not isinstance(original, dict) or not isinstance(original.get("id"), str):
        raise RecoveryFailure("Initial worker identity is missing from the protected prepare state.")
    if run.id != state.get("run_id") or run.owner_id != state.get("owner_id") or run.state != "running":
        raise RecoveryFailure("Pre-restart checkpoint requires the original actively running AgentRun.")
    worker = require_active_worker(current, revision=revision, task_queue=task_queue)
    if worker["id"] != original["id"]:
        raise RecoveryFailure("Original staging worker has already been replaced; checkpoint cannot be backfilled.")
    if worker["task_queue"] != original.get("task_queue") or worker["source_revision"] != original.get("source_revision"):
        raise RecoveryFailure("Checkpoint worker differs from the reviewed original queue or SHA.")
    registered, heartbeat = parse_utc(worker["started_at"]), parse_utc(worker["heartbeat_at"])
    old_registered = parse_utc(original.get("started_at", ""))
    if registered != old_registered or not registered <= heartbeat <= captured_at:
        raise RecoveryFailure("Checkpoint worker registration or heartbeat chronology is invalid.")
    if (captured_at - heartbeat).total_seconds() > WORKER_HEARTBEAT_TTL_SECONDS:
        raise RecoveryFailure("Original worker heartbeat was already stale when checkpointed.")

    running = [
        (step, task)
        for step in steps
        for task in tasks
        if step.ordinal in (1, 2, 3)
        and step.run_id == run.id and step.owner_id == run.owner_id
        and step.state == "running" and step.started_at is not None
        and step.finished_at is None and _utc(step.started_at) <= captured_at
        and task.agent_run_id == run.id and task.owner_id == run.owner_id
        and task.agent_step_id == step.id and task.state == "running"
    ]
    if not running:
        raise RecoveryFailure(
            "Pre-restart checkpoint requires an actively executing, persisted Agent child task."
        )
    step, child = sorted(running, key=lambda pair: pair[0].ordinal)[0]
    return {
        "status": "active_child_observed",
        "release_context": state["release_context"],
        "run_id": run.id,
        "owner_id": run.owner_id,
        "workflow_id": state["workflow_id"],
        "captured_at": captured_at.isoformat(),
        "active_ordinal": step.ordinal,
        "active_child_task_id": child.id,
        "worker_before": {
            key: worker[key]
            for key in ("id", "task_queue", "source_revision", "started_at", "heartbeat_at")
        },
    }


def worker_from_active_checkpoint(
    state: dict,
    checkpoint: object,
    facts: dict,
    *,
    restart_at: datetime,
    revision: str,
    task_queue: str,
) -> dict:
    """Bind a private pre-restart observation to the same child and event."""
    if not isinstance(checkpoint, dict) or checkpoint.get("status") != "active_child_observed":
        raise RecoveryFailure("A valid private active-child checkpoint receipt is required.")
    if any(checkpoint.get(key) != state.get(key) for key in (
        "release_context", "run_id", "owner_id", "workflow_id",
    )):
        raise RecoveryFailure("Active-worker checkpoint belongs to a different prepared run or release.")
    original = state.get("worker_before")
    before = checkpoint.get("worker_before")
    if not isinstance(original, dict) or not isinstance(before, dict):
        raise RecoveryFailure("Checkpoint has no corroborated original worker identity.")
    if (before.get("id") != original.get("id")
            or before.get("task_queue") != task_queue
            or before.get("source_revision") != revision
            or before.get("started_at") != original.get("started_at")):
        raise RecoveryFailure("Checkpoint worker is not the initial reviewed worker.")
    captured = parse_utc(checkpoint.get("captured_at", ""))
    heartbeat = parse_utc(before.get("heartbeat_at", ""))
    if not heartbeat <= captured <= restart_at:
        raise RecoveryFailure("Checkpoint was not captured before restart with a real prior heartbeat.")
    if ((restart_at - captured).total_seconds() > WORKER_HEARTBEAT_TTL_SECONDS
            or (restart_at - heartbeat).total_seconds() > WORKER_HEARTBEAT_TTL_SECONDS):
        raise RecoveryFailure("Checkpoint or original-worker heartbeat is stale at the platform restart.")
    ordinal, child_id = checkpoint.get("active_ordinal"), checkpoint.get("active_child_task_id")
    if type(ordinal) is not int or ordinal not in (1, 2, 3) or not isinstance(child_id, str):
        raise RecoveryFailure("Checkpoint active-child identity is invalid.")
    matching_children = [
        child for child in facts.get("completed_children", [])
        if child.get("ordinal") == ordinal and child.get("task_id") == child_id
    ]
    if len(matching_children) != 1:
        raise RecoveryFailure("Checkpoint child does not match the persisted recovered child tasks.")
    child = matching_children[0]
    if not parse_utc(child["started_at"]) <= captured <= restart_at <= parse_utc(child["finished_at"]):
        raise RecoveryFailure("Checkpoint and platform restart did not interrupt the same active child.")
    return before


def capture_active_checkpoint(
    settings: Settings, state_path: Path, rollout_path: Path, checkpoint_path: Path,
) -> dict:
    """Observe only: DB active child and old worker heartbeat, then private 0600 receipt."""
    require_exercise_guard()
    require_runtime(settings)
    _preflight_private_state(checkpoint_path)
    state = read_private_recovery_receipt(state_path)
    validate_prepared_release_context(state.get("release_context"), settings, rollout_path)
    run_id, owner = state.get("run_id"), state.get("owner_id")
    if (not isinstance(run_id, str) or not isinstance(owner, str)
            or state.get("workflow_id") != "shuddho-agent-" + run_id):
        raise RecoveryFailure("Pre-restart checkpoint state has an invalid AgentRun identity.")
    container = Container.create(settings)
    try:
        with container.repository.sessions() as db:
            run = db.scalar(select(AgentRun).where(
                AgentRun.id == run_id, AgentRun.owner_id == owner,
            ))
            if run is None:
                raise RecoveryFailure("Prepared recovery AgentRun was not found.")
            steps = list(db.scalars(select(AgentStep).where(
                AgentStep.run_id == run_id, AgentStep.owner_id == owner,
            )).all())
            tasks = list(db.scalars(select(Task).where(
                Task.agent_run_id == run_id, Task.owner_id == owner,
            )).all())
            receipt = attest_active_worker_checkpoint(
                state, run, steps, tasks,
                container.repository.worker_inventory(task_queue=settings.task_queue),
                revision=settings.source_revision, task_queue=settings.task_queue,
                captured_at=datetime.now(timezone.utc),
            )
        write_private_json(checkpoint_path, receipt)
        return receipt
    finally:
        container.repository.sessions.kw["bind"].dispose()


def validate_outbox_effects(
    run: AgentRun,
    tasks: list[Task],
    agent_outbox: list[AgentOutbox],
    task_outbox: list[Outbox],
) -> dict:
    """Verify a single parent dispatch effect and no duplicate child outbox writes.

    The Agent runtime creates child tasks with enqueue=False because Temporal
    executes their activities directly. A cw_outbox row for any child is an
    unexpected second dispatch path, not proof of correct recovery. The parent
    cw_agent_outbox is the only logical dispatch effect for this AgentRun.
    """
    if len(agent_outbox) != 1 or agent_outbox[0].run_id != run.id or agent_outbox[0].delivered is not True:
        raise RecoveryFailure("Recovery AgentRun does not have exactly one delivered outbox effect.")
    if len({task.id for task in tasks}) != 3:
        raise RecoveryFailure("Recovered child task identities are not distinct.")
    if task_outbox:
        raise RecoveryFailure("Direct Agent child tasks unexpectedly generated task outbox effects.")
    return {"agent_outbox_effect_count": 1, "agent_outbox_delivered": True,
            "child_task_outbox_count": 0, "child_task_outbox_expected_absent": True}


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
    if any(item.state != "completed" for item in tasks):
        raise RecoveryFailure("Recovered child tasks did not all complete.")
    step_ids = {item.id for item in ordered}
    task_step_ids = [item.agent_step_id for item in tasks]
    if len(set(task_step_ids)) != 3 or set(task_step_ids) != step_ids:
        raise RecoveryFailure("Child task linkage is duplicated or does not match the three agent steps.")
    expected_keys = {f"agent:{run.id}:{ordinal}" for ordinal in (1, 2, 3)}
    if {item.idempotency_key for item in tasks} != expected_keys:
        raise RecoveryFailure("Child task idempotency keys do not match the server-owned run/ordinal contract.")

    active_start = min(_utc(item.started_at) for item in ordered)
    # A restart after the final persisted step finished cannot prove recovery
    # of active work, even if the AgentRun row was updated seconds later.
    finish = _utc(ordered[2].finished_at)
    if not active_start <= restart_at <= finish:
        raise RecoveryFailure("Recorded worker restart did not occur after agent execution started and before the recovery run finished.")
    if not any(_utc(item.started_at) <= restart_at <= _utc(item.finished_at) for item in ordered):
        raise RecoveryFailure("Recorded worker restart did not interrupt an actively executing child task.")
    # Carry database-verified child identities and active step windows into
    # the private receipt; a prose fan-in assertion is not independently
    # checkable by the subsequent Day 2 release reconciler.
    by_step = {item.agent_step_id: item for item in tasks}
    completed_children = [
        {
            "ordinal": item.ordinal,
            "task_id": by_step[item.id].id,
            "state": by_step[item.id].state,
            "idempotency_key": by_step[item.id].idempotency_key,
            "started_at": _utc(item.started_at).isoformat(),
            "finished_at": _utc(item.finished_at).isoformat(),
        }
        for item in ordered
    ]
    return {
        "completed_children": completed_children,
        "fan_in_started_at": _utc(ordered[2].started_at).isoformat(),
        "branch_finished_at": [_utc(ordered[0].finished_at).isoformat(), _utc(ordered[1].finished_at).isoformat()],
        "child_tasks": len(tasks),
        "active_start": active_start.isoformat(),
        "active_finish": finish.isoformat(),
    }


async def verify(
    settings: Settings,
    state_path: Path,
    restart_at: datetime,
    restart_reference: str,
    rollout_path: Path,
    evidence_path: Path,
    base_evidence: Path | None,
    checkpoint_path: Path | None = None,
) -> dict:
    require_exercise_guard()
    require_runtime(settings)
    if not restart_reference.strip():
        raise RecoveryFailure("A non-empty worker restart evidence reference is required.")
    state = read_private_recovery_receipt(state_path)
    context = validate_prepared_release_context(
        state.get("release_context"),
        settings,
        rollout_path,
    )
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
            agent_outbox = list(db.scalars(select(AgentOutbox).where(AgentOutbox.run_id == run_id)).all())
            task_outbox = list(db.scalars(select(Outbox).where(
                Outbox.task_id.in_([task.id for task in tasks]),
            )).all())
            outbox = validate_outbox_effects(run, tasks, agent_outbox, task_outbox)

        before = state.get("worker_before")
        if checkpoint_path is not None:
            # Refreshing a stale prepare snapshot is allowed ONLY via a
            # separate read-only observation made during a live child task.
            checkpoint = read_private_recovery_receipt(checkpoint_path)
            before = worker_from_active_checkpoint(
                state, checkpoint, facts,
                restart_at=restart_at, revision=settings.source_revision,
                task_queue=settings.task_queue,
            )
        worker = validate_worker_replacement(
            before,
            container.repository.worker_inventory(task_queue=settings.task_queue),
            revision=settings.source_revision, task_queue=settings.task_queue,
            restart_at=restart_at, active_start=parse_utc(facts["active_start"]),
            active_finish=parse_utc(facts["active_finish"]),
        )

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
        verified_at = datetime.now(timezone.utc)
        base.update({
            "recovery_outbox": {
                "agent_run_id": run_id, "workflow_id": workflow_id,
                "source_revision": settings.source_revision,
                "run_started_at": facts["active_start"],
                "run_finished_at": facts["active_finish"],
                "restart_at": restart_at.isoformat(),
                "restart_reference": concise_ref,
                **worker, **outbox,
                "completed_children": facts["completed_children"],
            },
            "temporal": passed(
                f"AgentWorkflow v2 completed across controlled worker restart; restart_ref={concise_ref}; workflow={workflow_id}",
                context,
                now=verified_at,
            ),
            "parallel_restart": passed(
                f"post-restart run completed with exactly {facts['child_tasks']} server-idempotent child tasks, "
                f"{outbox['agent_outbox_effect_count']} AgentRun outbox effect, "
                f"{outbox['child_task_outbox_count']} child-task outbox dispatches and "
                f"{artifact_count} persisted artifacts; restart_ref={concise_ref}",
                context,
                now=verified_at,
            ),
            "fan_in": passed(
                "persisted step 3 depended on [1,2] and started only after both branch steps finished",
                context,
                now=verified_at,
            ),
        })
        write_private_json(evidence_path, base)
        return {"checks": {"temporal": "passed", "parallel_restart": "passed",
                            "fan_in": "passed", "outbox_once": "passed", "worker_replaced": "passed"}}
    finally:
        container.repository.sessions.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled Temporal/AgentWorkflow v2 staging recovery validation.")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--state", type=Path, required=True)
    prepare_parser.add_argument("--rollout", type=Path, required=True)

    checkpoint_parser = sub.add_parser(
        "checkpoint", help="Capture a read-only active-child/old-worker heartbeat before the real restart.",
    )
    checkpoint_parser.add_argument("--state", type=Path, required=True)
    checkpoint_parser.add_argument("--rollout", type=Path, required=True)
    checkpoint_parser.add_argument("--output", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--restart-at", required=True, help="ISO-8601 timestamp from the staging worker restart/deployment event.")
    verify_parser.add_argument("--restart-reference", required=True, help="Deployment event, pod UID transition, or platform run reference.")
    verify_parser.add_argument("--rollout", type=Path, required=True)
    verify_parser.add_argument("--base-evidence", type=Path)
    verify_parser.add_argument(
        "--checkpoint", type=Path,
        help="Separate protected active-child heartbeat checkpoint, captured just before the real platform restart.",
    )
    verify_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "prepare":
            result = asyncio.run(prepare(settings, args.state, args.rollout))
            print(json.dumps({
                "status": "prepared",
                "run_id": result["run_id"],
                "workflow_id": result["workflow_id"],
                "next": "Capture a just-in-time active-child worker checkpoint, immediately restart the real staging worker, then verify with the checkpoint and platform event.",
            }, indent=2))
        elif args.command == "checkpoint":
            result = capture_active_checkpoint(
                settings, args.state, args.rollout, args.output,
            )
            print(json.dumps({
                "status": result["status"],
                "run_id": result["run_id"],
                "captured_at": result["captured_at"],
                "written": str(args.output),
                "next": "Immediately restart the actual staging worker while this child task is active, then verify with the platform event.",
            }, indent=2))
        else:
            result = asyncio.run(verify(
                settings,
                args.state,
                parse_utc(args.restart_at),
                args.restart_reference,
                args.rollout,
                args.output,
                args.base_evidence,
                args.checkpoint,
            ))
            print(json.dumps({"written": str(args.output), **result}, indent=2))
    except (
        RecoveryFailure,
        StagingReleaseEvidenceError,
        httpx.HTTPError,
        OSError,
        ValueError,
    ) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
