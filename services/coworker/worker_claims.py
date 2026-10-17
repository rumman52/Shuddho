"""Durable per-worker dispatch claims used to fence cooperative drains.

Lock order is always WorkerInstance -> outbox/resource row -> WorkerClaim.
A claim remains active until the dispatch attempt returns and is explicitly
completed. An abandoned claim intentionally blocks drain certification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from .errors import CoworkerError
from .models import WorkerClaim, WorkerInstance, utcnow


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def lock_running_worker(
    db,
    *,
    worker_id: str | None,
    task_queue: str,
    now: datetime,
    heartbeat_ttl_seconds: int,
) -> WorkerInstance | None:
    """Lock and refresh a worker only if it is eligible to start a new claim."""
    if not worker_id:
        return None
    worker = db.scalar(
        select(WorkerInstance)
        .where(WorkerInstance.id == worker_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        worker is None
        or worker.task_queue != task_queue
        or worker.state != "running"
        or _aware(worker.heartbeat_at) < now - timedelta(seconds=heartbeat_ttl_seconds)
    ):
        return None
    worker.heartbeat_at = now
    return worker


def add_worker_claim(
    db,
    *,
    worker: WorkerInstance,
    claim_type: str,
    resource_id: str,
    now: datetime,
) -> WorkerClaim:
    if claim_type not in {"task_dispatch", "agent_dispatch", "action_dispatch"}:
        raise CoworkerError("worker_claim_type", "The dispatch claim type is not supported.", 409)
    claim = WorkerClaim(
        id=str(uuid4()),
        worker_id=worker.id,
        task_queue=worker.task_queue,
        claim_type=claim_type,
        resource_id=resource_id,
        state="active",
        claimed_at=now,
    )
    db.add(claim)
    # Force uniqueness/FK failures inside the claim transaction, before any
    # outbox IDs are returned to the dispatcher.
    db.flush()
    return claim


def complete_worker_claim(
    sessions,
    *,
    worker_id: str,
    claim_type: str,
    resource_id: str,
) -> bool:
    """Complete one claim after its dispatch attempt has returned.

    The worker row is locked first to serialize with drain requests and drain
    certification. A duplicate completion is idempotent; an unknown claim is
    a hard error rather than silent evidence loss.
    """
    with sessions.begin() as db:
        worker = db.scalar(
            select(WorkerInstance)
            .where(WorkerInstance.id == worker_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if worker is None:
            raise CoworkerError(
                "worker_claim_owner_missing",
                "The dispatch claim owner is no longer registered.",
                409,
            )
        claim = db.scalar(
            select(WorkerClaim)
            .where(
                WorkerClaim.worker_id == worker_id,
                WorkerClaim.claim_type == claim_type,
                WorkerClaim.resource_id == resource_id,
                WorkerClaim.state == "active",
            )
            .order_by(WorkerClaim.claimed_at.desc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if claim is None:
            completed = db.scalar(
                select(WorkerClaim.id).where(
                    WorkerClaim.worker_id == worker_id,
                    WorkerClaim.claim_type == claim_type,
                    WorkerClaim.resource_id == resource_id,
                    WorkerClaim.state == "completed",
                ).limit(1)
            )
            if completed is not None:
                return False
            raise CoworkerError(
                "worker_claim_missing",
                "The dispatch claim could not be found; drain evidence cannot be trusted.",
                409,
            )
        claim.state = "completed"
        claim.completed_at = utcnow()
        return True


def require_active_worker_claim(
    sessions,
    *,
    worker_id: str | None,
    claim_type: str,
    resource_id: str,
) -> None:
    """Authorize dispatch only while the exact durable claim is still active."""
    if not worker_id:
        raise CoworkerError(
            "worker_identity_required",
            "Dispatch requires a registered worker identity and an active durable claim.",
            409,
        )
    with sessions.begin() as db:
        worker = db.scalar(
            select(WorkerInstance)
            .where(WorkerInstance.id == worker_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if worker is None or worker.state not in {"running", "draining"}:
            raise CoworkerError(
                "worker_not_dispatchable",
                "The registered worker is no longer permitted to dispatch work.",
                409,
            )
        claim = db.scalar(
            select(WorkerClaim)
            .where(
                WorkerClaim.worker_id == worker_id,
                WorkerClaim.claim_type == claim_type,
                WorkerClaim.resource_id == resource_id,
                WorkerClaim.state == "active",
            )
            .with_for_update()
        )
        if claim is None:
            raise CoworkerError(
                "worker_claim_missing",
                "Dispatch is blocked because no active claim authorizes this resource.",
                409,
            )


def require_no_active_worker_claims(db, worker_id: str) -> None:
    claims = db.scalars(
        select(WorkerClaim)
        .where(WorkerClaim.worker_id == worker_id, WorkerClaim.state == "active")
        .order_by(WorkerClaim.claimed_at, WorkerClaim.id)
        .with_for_update()
    ).all()
    if claims:
        raise CoworkerError(
            "worker_claims_active",
            "The worker cannot be marked drained while dispatch claims remain active.",
            409,
        )
