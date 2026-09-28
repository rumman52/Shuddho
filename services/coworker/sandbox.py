from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from .errors import CoworkerError
from .models import Account, AuditEvent, SandboxExecution, SandboxSession, Workspace, utcnow
from .repository import aware, iso, not_found
from .sandbox_schemas import SandboxExecutionCreate, SandboxSessionCreate


TERMINAL_SANDBOX_STATES = {"cancelled", "completed", "expired", "failed"}
ACTIVE_SANDBOX_STATES = {"prepared", "queued", "running"}
SANDBOX_POLICY_VERSION = "sandbox-control-v1"


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class SandboxRepository:
    """Durable PA-08 control plane.

    This slice intentionally does not execute code in the API process. Source is
    persisted as untrusted input for a future separately isolated executor and
    is never returned through user-facing DTOs.
    """

    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings

    def _require_enabled(self) -> None:
        if not self.settings.code_execution_enabled:
            raise CoworkerError(
                "sandbox_disabled",
                "Sandboxed computation is not enabled in this deployment.",
                503,
            )

    def _policy(self) -> dict:
        return {
            "version": SANDBOX_POLICY_VERSION,
            "network": "none",
            "dependencies": [],
            "mounts": [],
            "host_filesystem": False,
            "docker_socket": False,
            "production_secrets": False,
            "connector_credentials": False,
            "privileged_api_bridge": False,
            "resource_limits": {
                "wall_seconds": self.settings.sandbox_wall_seconds,
                "cpu_seconds": self.settings.sandbox_cpu_seconds,
                "memory_mb": self.settings.sandbox_memory_mb,
                "disk_mb": self.settings.sandbox_disk_mb,
            },
        }

    def _expire_stale_sessions(self, db, owner: str | None = None) -> None:
        now = utcnow()
        query = select(SandboxSession).where(
            SandboxSession.state.not_in(tuple(TERMINAL_SANDBOX_STATES)),
            SandboxSession.expires_at <= now,
        )
        if owner is not None:
            query = query.where(SandboxSession.owner_id == owner)
        rows = db.scalars(query.with_for_update()).all()
        for row in rows:
            row.state = "expired"
            row.cancel_requested = True
            row.cleanup_state = "not_required"
            row.updated_at = now
            for execution in db.scalars(select(SandboxExecution).where(
                SandboxExecution.session_id == row.id,
                SandboxExecution.state == "prepared",
            ).with_for_update()).all():
                execution.state = "failed"
                execution.error_code = "session_expired"
                execution.request_spec = {"source_scrubbed": True}
                execution.finished_at = now
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=row.owner_id,
                resource_id=row.id,
                action="sandbox_session.expired",
            ))

    def _session_dto(self, row: SandboxSession) -> dict:
        state = row.state
        if state not in TERMINAL_SANDBOX_STATES and aware(row.expires_at) <= utcnow():
            state = "expired"
        return {
            "id": row.id,
            "purpose": row.purpose,
            "runtime": row.runtime,
            "state": state,
            "cancel_requested": row.cancel_requested,
            "cleanup_state": row.cleanup_state,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
            "expires_at": iso(row.expires_at),
            "policy": dict(row.execution_policy or {}),
            "execution": {
                "executor_attached": False,
                "code_executed": False,
                "planner_tool_registered": False,
                "source_trust": "untrusted",
            },
        }

    @staticmethod
    def _execution_dto(row: SandboxExecution) -> dict:
        return {
            "id": row.id,
            "sequence": row.sequence,
            "kind": row.kind,
            "source_sha256": row.source_sha256,
            "source_bytes": row.source_bytes,
            "state": row.state,
            "error_code": row.error_code,
            "created_at": iso(row.created_at),
            "finished_at": iso(row.finished_at) if row.finished_at else None,
        }

    def create(self, owner: str, request: SandboxSessionCreate, idempotency_key: str) -> tuple[dict, bool]:
        self._require_enabled()
        fingerprint = _digest({"purpose": request.purpose, "runtime": request.runtime})
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            account = db.get(Account, owner)
            workspace_id = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
            if account is None or workspace_id is None:
                raise not_found()
            previous = db.scalar(select(SandboxSession).where(
                SandboxSession.owner_id == owner,
                SandboxSession.idempotency_key == idempotency_key,
            ))
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different sandbox session.",
                        409,
                    )
                return self._session_dto(previous), False
            active = db.scalar(select(func.count()).select_from(SandboxSession).where(
                SandboxSession.owner_id == owner,
                SandboxSession.state.in_(tuple(ACTIVE_SANDBOX_STATES)),
                SandboxSession.expires_at > utcnow(),
            )) or 0
            if active >= self.settings.max_active_sandbox_sessions:
                raise CoworkerError(
                    "sandbox_session_limit",
                    "Close an active sandbox session before starting another.",
                    429,
                )
            now = utcnow()
            row = SandboxSession(
                id=str(uuid4()),
                owner_id=owner,
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                purpose=request.purpose,
                runtime=request.runtime,
                state="prepared",
                execution_policy=self._policy(),
                cancel_requested=False,
                cleanup_state="pending",
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(seconds=self.settings.sandbox_session_ttl_seconds),
            )
            db.add(row)
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=row.id,
                action="sandbox_session.prepared",
            ))
            db.flush()
            return self._session_dto(row), True

    def list(self, owner: str) -> list[dict]:
        self._require_enabled()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            rows = db.scalars(select(SandboxSession).where(
                SandboxSession.owner_id == owner,
            ).order_by(SandboxSession.created_at.desc()).limit(50)).all()
            return [self._session_dto(row) for row in rows]

    def get(self, owner: str, session_id: str) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            row = db.scalar(select(SandboxSession).where(
                SandboxSession.id == session_id,
                SandboxSession.owner_id == owner,
            ))
            if row is None:
                raise not_found()
            return self._session_dto(row)

    def prepare_execution(self, owner: str, session_id: str, request: SandboxExecutionCreate) -> dict:
        self._require_enabled()
        encoded = request.source.encode("utf-8")
        if len(encoded) > self.settings.sandbox_max_source_bytes:
            raise CoworkerError(
                "sandbox_source_too_large",
                "Sandbox source exceeded the configured byte limit.",
                413,
            )
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            session = db.scalar(select(SandboxSession).where(
                SandboxSession.id == session_id,
                SandboxSession.owner_id == owner,
            ).with_for_update())
            if session is None:
                raise not_found()
            if aware(session.expires_at) <= utcnow():
                raise CoworkerError("sandbox_session_expired", "This sandbox session expired.", 410)
            if session.state in TERMINAL_SANDBOX_STATES or session.cancel_requested:
                raise CoworkerError("sandbox_session_closed", "This sandbox session is no longer active.", 409)
            count = db.scalar(select(func.count()).select_from(SandboxExecution).where(
                SandboxExecution.session_id == session_id,
            )) or 0
            if count >= self.settings.sandbox_max_executions_per_session:
                raise CoworkerError(
                    "sandbox_execution_limit",
                    "This sandbox session reached its execution-request limit.",
                    429,
                )
            sequence = (db.scalar(select(func.max(SandboxExecution.sequence)).where(
                SandboxExecution.session_id == session_id,
            )) or 0) + 1
            row = SandboxExecution(
                id=str(uuid4()),
                session_id=session_id,
                owner_id=owner,
                sequence=sequence,
                kind="python",
                source_sha256=hashlib.sha256(encoded).hexdigest(),
                source_bytes=len(encoded),
                request_spec={
                    "source": request.source,
                    "source_trust": "untrusted",
                    "policy_version": SANDBOX_POLICY_VERSION,
                },
                state="prepared",
            )
            db.add(row)
            session.updated_at = utcnow()
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=session.id,
                action="sandbox_execution.prepared",
            ))
            db.flush()
            return self._execution_dto(row) | {
                "policy": dict(session.execution_policy or {}),
                "executor_attached": False,
                "code_executed": False,
            }

    def list_executions(self, owner: str, session_id: str) -> list[dict]:
        self._require_enabled()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            exists = db.scalar(select(SandboxSession.id).where(
                SandboxSession.id == session_id,
                SandboxSession.owner_id == owner,
            ))
            if exists is None:
                raise not_found()
            rows = db.scalars(select(SandboxExecution).where(
                SandboxExecution.session_id == session_id,
                SandboxExecution.owner_id == owner,
            ).order_by(SandboxExecution.sequence.desc()).limit(50)).all()
            return [self._execution_dto(row) for row in rows]

    def cancel(self, owner: str, session_id: str) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = db.scalar(select(SandboxSession).where(
                SandboxSession.id == session_id,
                SandboxSession.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state not in TERMINAL_SANDBOX_STATES:
                now = utcnow()
                row.state = "cancelled"
                row.cancel_requested = True
                row.cleanup_state = "not_required"
                row.updated_at = now
                for execution in db.scalars(select(SandboxExecution).where(
                    SandboxExecution.session_id == row.id,
                    SandboxExecution.state == "prepared",
                ).with_for_update()).all():
                    execution.state = "cancelled"
                    execution.request_spec = {"source_scrubbed": True}
                    execution.finished_at = now
                db.add(AuditEvent(
                    id=str(uuid4()),
                    owner_id=owner,
                    resource_id=row.id,
                    action="sandbox_session.cancelled",
                ))
            return self._session_dto(row)
