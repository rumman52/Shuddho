"""Read-only, aggregate dispatch and worker measurements from durable ledgers."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select

from services.coworker.models import AgentOutbox, AgentRun, Outbox, Task, WorkerClaim, WorkerInstance
from services.coworker.reviewed_skill_registry import WORKER_ACTIVE_STATES, WORKER_HEARTBEAT_TTL_SECONDS


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _dispatch_summary(db, resource, outbox_id, claim_type, *, owners, task_queue, cutoff, now):
    # Outbox membership distinguishes independently admitted work from inline
    # child work. Keep unclaimed admissions in the denominator, and use only
    # the earliest durable claim on the configured queue, not every retry.
    statement = (
        select(resource.created_at, func.min(WorkerClaim.claimed_at))
        .select_from(resource)
        .join(outbox_id.class_, outbox_id == resource.id)
        .outerjoin(WorkerClaim, and_(
            WorkerClaim.resource_id == resource.id,
            WorkerClaim.claim_type == claim_type,
            WorkerClaim.task_queue == task_queue,
        ))
        .where(resource.owner_id.in_(owners), resource.created_at >= cutoff, resource.created_at <= now)
        .group_by(resource.id, resource.created_at)
    )
    admissions = unobserved = invalid_clock = 0
    delays = []
    for created, first_claim in db.execute(statement):
        admissions += 1
        if first_claim is None:
            unobserved += 1
            continue
        start, end = _utc(created), _utc(first_claim)
        if not start <= end <= now:
            invalid_clock += 1
            continue
        delays.append((end - start) // timedelta(milliseconds=1))
    delays.sort()

    def nearest_rank(quantile):
        return delays[math.ceil(len(delays) * quantile) - 1] if delays else None

    return {
        "admissions": admissions,
        "samples": len(delays),
        "unobserved": unobserved,
        "invalid_clock": invalid_clock,
        "p50_ms": nearest_rank(0.50),
        "p95_ms": nearest_rank(0.95),
    }


def _worker_summary(db, *, task_queue, now):
    statement = select(WorkerInstance.state, WorkerInstance.started_at, WorkerInstance.heartbeat_at).where(
        WorkerInstance.task_queue == task_queue,
        WorkerInstance.state.in_(WORKER_ACTIVE_STATES),
    )
    active = fresh_running = stale = invalid_clock = starting = draining = 0
    oldest = None
    ttl = timedelta(seconds=WORKER_HEARTBEAT_TTL_SECONDS)
    for state, started, heartbeat in db.execute(statement):
        active += 1
        starting += state == "starting"
        draining += state == "draining"
        heartbeat = _utc(heartbeat)
        if not _utc(started) <= heartbeat <= now:
            invalid_clock += 1
            continue
        age = now - heartbeat
        oldest = age if oldest is None else max(oldest, age)
        if age > ttl:
            stale += 1
        elif state == "running":
            fresh_running += 1
    return {
        "active_rows": active,
        "fresh_running": fresh_running,
        "stale": stale,
        "invalid_clock": invalid_clock,
        "starting": starting,
        "draining": draining,
        "oldest_valid_heartbeat_age_seconds": oldest // timedelta(seconds=1) if oldest is not None else None,
    }


def collect_dispatch_observability(db, *, owners, task_queue: str, cutoff: datetime, now: datetime) -> dict:
    """Measure dispatch admission-to-claim lag, not Temporal execution latency.

    Dispatch results are cohort scoped; heartbeat inventory is queue wide.
    Only aggregate numbers leave this read-only collector. A fresh heartbeat
    is not proof of successful Temporal polling or release qualification.
    """
    now, cutoff = _utc(now), _utc(cutoff)
    if cutoff > now:
        raise ValueError("Dispatch observation cutoff cannot be after observation time.")
    scope = dict(owners=owners, task_queue=task_queue, cutoff=cutoff, now=now)
    return {
        "dispatch": {
            "tasks": _dispatch_summary(db, Task, Outbox.task_id, "task_dispatch", **scope),
            "agents": _dispatch_summary(db, AgentRun, AgentOutbox.run_id, "agent_dispatch", **scope),
        },
        "workers": _worker_summary(db, task_queue=task_queue, now=now),
    }
