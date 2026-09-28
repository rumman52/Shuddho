from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from datetime import timedelta
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func, or_, select

from .errors import CoworkerError
from .interactive_artifacts import (
    create_preview_token,
    validate_static_preview_html,
    verify_preview_token,
)
from .models import Account, Artifact, AuditEvent, SandboxExecution, SandboxSession, Workspace, utcnow
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
    """Durable PA-08 control plane for separately isolated execution.

    The API process never executes generated code. Source remains untrusted and
    may be leased only to the separately authenticated sandbox worker. Results
    are accepted only with the exact isolation contract and are still marked
    untrusted for downstream consumers.
    """

    def __init__(self, sessions, settings, storage):
        self.sessions = sessions
        self.settings = settings
        self.storage = storage

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
                "output_bytes": self.settings.sandbox_max_output_bytes,
            },
            "artifacts": {
                "interactive_html": {
                    "path": "/tmp/shuddho-preview.html",
                    "content_type": "text/html; charset=utf-8",
                    "max_bytes": self.settings.sandbox_artifact_max_bytes,
                },
            },
            "executor": {
                "contract": "bwrap-python311-v1",
                "network_namespace": "private_empty",
                "filesystem": "minimal_readonly_runtime",
                "environment": "cleared",
                "packages": "stdlib_only",
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
                SandboxExecution.state.in_(("prepared", "running")),
            ).with_for_update()).all():
                if execution.state == "running":
                    row.cleanup_state = "required"
                execution.state = "failed"
                execution.error_code = "session_expired"
                execution.request_spec = {"source_scrubbed": True}
                execution.finished_at = now
                execution.lease_until = None
                execution.claimed_by = None
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
                "executor_attached": state == "running",
                "code_executed": row.cleanup_state == "verified_destroyed",
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
            "attempts": int(row.attempts or 0),
            "result": dict(row.result or {}),
            "created_at": iso(row.created_at),
            "started_at": iso(row.started_at) if row.started_at else None,
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

    def claim_executions(self, worker_id: str, limit: int = 1) -> list[dict]:
        self._require_enabled()
        if not worker_id or len(worker_id) > 64:
            raise CoworkerError("sandbox_worker_invalid", "The sandbox worker identity is invalid.", 403)
        now = utcnow()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db)
            exhausted = db.scalars(
                select(SandboxExecution)
                .join(SandboxSession, SandboxSession.id == SandboxExecution.session_id)
                .where(
                    SandboxExecution.state == "running",
                    SandboxExecution.lease_until.is_not(None),
                    SandboxExecution.lease_until < now,
                    SandboxExecution.attempts >= self.settings.sandbox_execution_max_attempts,
                    SandboxSession.state.not_in(tuple(TERMINAL_SANDBOX_STATES)),
                )
                .with_for_update(skip_locked=True)
            ).all()
            for execution in exhausted:
                session = db.get(SandboxSession, execution.session_id)
                execution.state = "failed"
                execution.error_code = "sandbox_worker_lost"
                execution.request_spec = {"source_scrubbed": True}
                execution.finished_at = now
                execution.lease_until = None
                execution.claimed_by = None
                if session is not None:
                    session.state = "failed"
                    session.cleanup_state = "required"
                    session.updated_at = now
                    db.add(AuditEvent(
                        id=str(uuid4()),
                        owner_id=execution.owner_id,
                        resource_id=session.id,
                        action="sandbox_execution.worker_lost",
                    ))
            rows = db.scalars(
                select(SandboxExecution)
                .join(SandboxSession, SandboxSession.id == SandboxExecution.session_id)
                .where(
                    SandboxSession.cancel_requested.is_(False),
                    SandboxSession.expires_at > now,
                    SandboxSession.state.not_in(tuple(TERMINAL_SANDBOX_STATES)),
                    SandboxExecution.attempts < self.settings.sandbox_execution_max_attempts,
                    SandboxExecution.state.in_(("prepared", "running")),
                    or_(SandboxExecution.lease_until.is_(None), SandboxExecution.lease_until < now),
                )
                .order_by(SandboxExecution.created_at)
                .limit(max(1, min(limit, 10)))
                .with_for_update(skip_locked=True)
            ).all()
            claimed: list[dict] = []
            for execution in rows:
                session = db.get(SandboxSession, execution.session_id)
                if session is None:
                    continue
                if execution.state == "running" and execution.lease_until and aware(execution.lease_until) < now:
                    db.add(AuditEvent(
                        id=str(uuid4()),
                        owner_id=execution.owner_id,
                        resource_id=session.id,
                        action="sandbox_execution.lease_recovered",
                    ))
                execution.state = "running"
                execution.attempts = int(execution.attempts or 0) + 1
                execution.claimed_by = worker_id
                execution.lease_until = now + timedelta(seconds=self.settings.sandbox_worker_lease_seconds)
                execution.started_at = execution.started_at or now
                session.state = "running"
                session.cleanup_state = "pending"
                session.updated_at = now
                source = (execution.request_spec or {}).get("source")
                if not isinstance(source, str):
                    execution.state = "failed"
                    execution.error_code = "sandbox_source_missing"
                    execution.finished_at = now
                    execution.lease_until = None
                    execution.claimed_by = None
                    session.state = "prepared"
                    session.cleanup_state = "not_required"
                    session.updated_at = now
                    continue
                claimed.append({
                    "id": execution.id,
                    "sequence": execution.sequence,
                    "runtime": session.runtime,
                    "purpose": session.purpose,
                    "source": source,
                    "source_sha256": execution.source_sha256,
                    "source_bytes": execution.source_bytes,
                    "attempt": execution.attempts,
                    "expires_at": iso(session.expires_at),
                    "policy": dict(session.execution_policy or {}),
                })
            return claimed

    def worker_control(self, worker_id: str, execution_id: str) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            execution = db.scalar(select(SandboxExecution).where(
                SandboxExecution.id == execution_id,
            ).with_for_update())
            if execution is None:
                raise not_found()
            session = db.scalar(select(SandboxSession).where(
                SandboxSession.id == execution.session_id,
                SandboxSession.owner_id == execution.owner_id,
            ).with_for_update())
            if session is None:
                raise not_found()
            if session.cancel_requested or session.state == "cancelled":
                if execution.state in {"prepared", "running"}:
                    execution.state = "cancelled"
                    execution.error_code = "session_cancelled"
                    execution.request_spec = {"source_scrubbed": True}
                    execution.finished_at = now
                    execution.lease_until = None
                    execution.claimed_by = None
                session.cleanup_state = "required"
                return {"action": "stop", "reason": "session_cancelled"}
            if aware(session.expires_at) <= now:
                session.state = "expired"
                session.cancel_requested = True
                session.cleanup_state = "required"
                session.updated_at = now
                if execution.state in {"prepared", "running"}:
                    execution.state = "failed"
                    execution.error_code = "session_expired"
                    execution.request_spec = {"source_scrubbed": True}
                    execution.finished_at = now
                    execution.lease_until = None
                    execution.claimed_by = None
                return {"action": "stop", "reason": "session_expired"}
            if (
                execution.state != "running"
                or execution.claimed_by != worker_id
                or execution.lease_until is None
                or aware(execution.lease_until) <= now
            ):
                raise CoworkerError(
                    "sandbox_worker_claim_invalid",
                    "This sandbox execution is not actively owned by this worker.",
                    409,
                )
            execution.lease_until = now + timedelta(seconds=self.settings.sandbox_worker_lease_seconds)
            session.updated_at = now
            return {"action": "continue", "lease_until": iso(execution.lease_until)}

    def _validated_artifact(self, session: SandboxSession, observation: dict, exit_code: int):
        artifact = observation.get("artifact")
        if exit_code != 0:
            if artifact is not None:
                raise CoworkerError(
                    "sandbox_artifact_invalid",
                    "Failed sandbox executions cannot publish artifacts.",
                    409,
                )
            return None
        if session.purpose != "interactive_artifact":
            if artifact is not None:
                raise CoworkerError(
                    "sandbox_artifact_invalid",
                    "This sandbox purpose cannot publish an interactive artifact.",
                    409,
                )
            return None
        if not isinstance(artifact, dict) or artifact.get("kind") != "interactive_html":
            raise CoworkerError(
                "sandbox_artifact_missing",
                "Interactive sandbox execution did not produce its required preview artifact.",
                409,
            )
        body_b64 = artifact.get("body_b64")
        declared_sha = artifact.get("sha256")
        declared_bytes = artifact.get("byte_size")
        if (
            not isinstance(body_b64, str)
            or not isinstance(declared_sha, str)
            or not isinstance(declared_bytes, int)
            or isinstance(declared_bytes, bool)
        ):
            raise CoworkerError("sandbox_artifact_invalid", "Interactive artifact metadata is invalid.", 409)
        try:
            body = base64.b64decode(body_b64, validate=True)
        except (binascii.Error, ValueError):
            raise CoworkerError("sandbox_artifact_invalid", "Interactive artifact encoding is invalid.", 409) from None
        if (
            len(body) != declared_bytes
            or len(body) > self.settings.sandbox_artifact_max_bytes
            or hashlib.sha256(body).hexdigest() != declared_sha
        ):
            raise CoworkerError(
                "sandbox_artifact_integrity_failed",
                "Interactive artifact bytes did not match their verified manifest.",
                409,
            )
        validate_static_preview_html(body, self.settings.sandbox_artifact_max_bytes)
        return body, declared_sha

    def complete_execution(self, worker_id: str, execution_id: str, observation: dict) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            execution = db.scalar(select(SandboxExecution).where(
                SandboxExecution.id == execution_id,
            ).with_for_update())
            if execution is None:
                raise not_found()
            session = db.scalar(select(SandboxSession).where(
                SandboxSession.id == execution.session_id,
                SandboxSession.owner_id == execution.owner_id,
            ).with_for_update())
            if session is None:
                raise not_found()
            if (
                execution.state != "running"
                or execution.claimed_by != worker_id
                or execution.lease_until is None
                or aware(execution.lease_until) <= now
            ):
                raise CoworkerError(
                    "sandbox_worker_claim_invalid",
                    "This sandbox execution is not actively owned by this worker.",
                    409,
                )
            if session.cancel_requested or session.state == "cancelled" or aware(session.expires_at) <= now:
                execution.state = "cancelled" if session.cancel_requested or session.state == "cancelled" else "failed"
                execution.error_code = "session_cancelled" if execution.state == "cancelled" else "session_expired"
                execution.request_spec = {"source_scrubbed": True}
                execution.finished_at = now
                execution.lease_until = None
                execution.claimed_by = None
                session.cleanup_state = "required"
                if aware(session.expires_at) <= now:
                    session.state = "expired"
                    session.cancel_requested = True
                session.updated_at = now
                raise CoworkerError(
                    "sandbox_session_closed",
                    "The sandbox session closed before this result could be accepted.",
                    409,
                )
            if (
                observation.get("policy_version") != SANDBOX_POLICY_VERSION
                or observation.get("executor_contract") != "bwrap-python311-v1"
                or observation.get("sandbox_destroyed") is not True
                or observation.get("network_isolated") is not True
                or observation.get("filesystem_isolated") is not True
                or observation.get("environment_sanitized") is not True
            ):
                raise CoworkerError(
                    "sandbox_isolation_evidence_invalid",
                    "Sandbox completion did not prove the required isolation contract.",
                    409,
                )
            stdout = observation.get("stdout")
            stderr = observation.get("stderr")
            if not isinstance(stdout, str) or not isinstance(stderr, str):
                raise CoworkerError("sandbox_result_invalid", "Sandbox output is invalid.", 409)
            if (
                len(stdout.encode("utf-8")) > self.settings.sandbox_max_output_bytes
                or len(stderr.encode("utf-8")) > self.settings.sandbox_max_output_bytes
            ):
                raise CoworkerError("sandbox_output_limit", "Sandbox output exceeded the configured byte limit.", 409)
            exit_code = observation.get("exit_code")
            elapsed_ms = observation.get("elapsed_ms")
            if (
                not isinstance(exit_code, int)
                or not -255 <= exit_code <= 255
                or not isinstance(elapsed_ms, int)
                or not 0 <= elapsed_ms <= self.settings.sandbox_wall_seconds * 1000
            ):
                raise CoworkerError("sandbox_result_invalid", "Sandbox result metadata is invalid.", 409)
            validated_artifact = self._validated_artifact(session, observation, exit_code)
            artifact_manifest = None
            if validated_artifact is not None:
                artifact_body, artifact_sha = validated_artifact
                account = db.scalar(select(Account).where(
                    Account.id == execution.owner_id,
                ).with_for_update())
                if account is None:
                    raise not_found()
                if account.storage_bytes + len(artifact_body) > self.settings.max_account_bytes:
                    raise CoworkerError(
                        "storage_limit",
                        "Your workspace has reached its file storage limit.",
                        429,
                    )
                artifact_id = str(uuid5(
                    NAMESPACE_URL,
                    "shuddho:sandbox-artifact:" + execution.id + ":" + artifact_sha,
                ))
                filename = "interactive-preview.html"
                object_key = (
                    f"{execution.owner_id}/outputs/sandbox/"
                    f"{execution.id}/{artifact_sha}.html"
                )
                expires_at = now + timedelta(seconds=self.settings.sandbox_artifact_ttl_seconds)
                try:
                    self.storage.put(
                        object_key,
                        artifact_body,
                        "text/html; charset=utf-8",
                    )
                except Exception:
                    raise CoworkerError(
                        "sandbox_artifact_storage",
                        "The interactive artifact could not be stored privately.",
                        503,
                    ) from None
                db.add(Artifact(
                    id=artifact_id,
                    task_id=None,
                    sandbox_execution_id=execution.id,
                    owner_id=execution.owner_id,
                    artifact_class="sandbox_interactive",
                    filename=filename,
                    content_type="text/html; charset=utf-8",
                    object_key=object_key,
                    sha256=artifact_sha,
                    byte_size=len(artifact_body),
                    created_at=now,
                    expires_at=expires_at,
                ))
                account.storage_bytes += len(artifact_body)
                artifact_manifest = {
                    "id": artifact_id,
                    "filename": filename,
                    "content_type": "text/html; charset=utf-8",
                    "byte_size": len(artifact_body),
                    "sha256": artifact_sha,
                    "artifact_class": "sandbox_interactive",
                    "preview_available": True,
                    "expires_at": iso(expires_at),
                }

            execution.result = {
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
                "elapsed_ms": elapsed_ms,
                "policy_version": SANDBOX_POLICY_VERSION,
                "executor_contract": "bwrap-python311-v1",
                "sandbox_destroyed": True,
                "network_isolated": True,
                "filesystem_isolated": True,
                "environment_sanitized": True,
                "output_trust": "untrusted",
                "artifact": artifact_manifest,
            }
            execution.state = "succeeded" if exit_code == 0 else "failed"
            execution.error_code = None if exit_code == 0 else "sandbox_nonzero_exit"
            execution.request_spec = {"source_scrubbed": True}
            execution.finished_at = now
            execution.lease_until = None
            execution.claimed_by = None
            session.state = "prepared"
            session.cleanup_state = "verified_destroyed"
            session.updated_at = now
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=execution.owner_id,
                resource_id=session.id,
                action="sandbox_execution.completed" if exit_code == 0 else "sandbox_execution.failed",
            ))
            return self._execution_dto(execution)

    def fail_execution(self, worker_id: str, execution_id: str, error_code: str, sandbox_destroyed: bool) -> dict:
        self._require_enabled()
        now = utcnow()
        allowed = {
            "sandbox_timeout",
            "sandbox_output_limit",
            "sandbox_resource_limit",
            "sandbox_runner_unavailable",
            "sandbox_policy_invalid",
            "sandbox_source_integrity_failed",
            "sandbox_execution_failed",
            "sandbox_artifact_missing",
            "sandbox_artifact_invalid",
            "sandbox_artifact_unsafe",
            "sandbox_artifact_limit",
            "sandbox_artifact_encoding",
            "sandbox_artifact_integrity_failed",
            "worker_interrupted",
        }
        if error_code not in allowed or sandbox_destroyed is not True:
            raise CoworkerError("sandbox_failure_invalid", "Sandbox failure evidence is invalid.", 409)
        with self.sessions.begin() as db:
            execution = db.scalar(select(SandboxExecution).where(
                SandboxExecution.id == execution_id,
            ).with_for_update())
            if execution is None:
                raise not_found()
            session = db.scalar(select(SandboxSession).where(
                SandboxSession.id == execution.session_id,
                SandboxSession.owner_id == execution.owner_id,
            ).with_for_update())
            if session is None:
                raise not_found()
            if (
                execution.state != "running"
                or execution.claimed_by != worker_id
                or execution.lease_until is None
                or aware(execution.lease_until) <= now
            ):
                raise CoworkerError(
                    "sandbox_worker_claim_invalid",
                    "This sandbox execution is not actively owned by this worker.",
                    409,
                )
            execution.state = "failed"
            execution.error_code = error_code
            execution.request_spec = {"source_scrubbed": True}
            execution.finished_at = now
            execution.lease_until = None
            execution.claimed_by = None
            execution.result = {
                "executor_contract": "bwrap-python311-v1",
                "sandbox_destroyed": True,
                "output_trust": "untrusted",
            }
            session.state = "prepared"
            session.cleanup_state = "verified_destroyed"
            session.updated_at = now
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=execution.owner_id,
                resource_id=session.id,
                action="sandbox_execution.failed",
            ))
            return self._execution_dto(execution)

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

    def get_execution(self, owner: str, execution_id: str) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            self._expire_stale_sessions(db, owner)
            row = db.scalar(select(SandboxExecution).where(
                SandboxExecution.id == execution_id,
                SandboxExecution.owner_id == owner,
            ))
            if row is None:
                raise not_found()
            session = db.scalar(select(SandboxSession.id).where(
                SandboxSession.id == row.session_id,
                SandboxSession.owner_id == owner,
            ))
            if session is None:
                raise not_found()
            return self._execution_dto(row)

    def preview_url(self, owner: str, artifact_id: str) -> dict:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            artifact = db.scalar(select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.owner_id == owner,
                Artifact.artifact_class == "sandbox_interactive",
                Artifact.sandbox_execution_id.is_not(None),
            ))
            if artifact is None:
                raise not_found()
            if artifact.expires_at is None or aware(artifact.expires_at) <= now:
                raise CoworkerError(
                    "sandbox_artifact_expired",
                    "This interactive artifact expired.",
                    410,
                )
            remaining = max(1, int((aware(artifact.expires_at) - now).total_seconds()))
            ttl = min(self.settings.sandbox_preview_url_ttl_seconds, remaining)
            expires_epoch = int(time.time()) + ttl
            token = create_preview_token(
                self.settings.sandbox_preview_secret,
                artifact.id,
                artifact.sha256,
                expires_epoch,
            )
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=artifact.id,
                action="sandbox_artifact.preview_link_created",
            ))
            return {
                "artifact_id": artifact.id,
                "url": (
                    self.settings.sandbox_preview_origin
                    + f"/sandbox-preview/{artifact.id}?token={quote(token, safe='')}"
                ),
                "expires_at": expires_epoch,
                "sandbox": {
                    "scripts": False,
                    "network": False,
                    "forms": False,
                    "privileged_api_bridge": False,
                    "workspace_credentials": False,
                },
            }

    def preview_content(self, artifact_id: str, token: str) -> bytes:
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            artifact = db.scalar(select(Artifact).where(
                Artifact.id == artifact_id,
                Artifact.artifact_class == "sandbox_interactive",
                Artifact.sandbox_execution_id.is_not(None),
            ))
            if artifact is None:
                raise not_found()
            if artifact.expires_at is None or aware(artifact.expires_at) <= now:
                raise CoworkerError(
                    "sandbox_artifact_expired",
                    "This interactive artifact expired.",
                    410,
                )
            verify_preview_token(
                self.settings.sandbox_preview_secret,
                artifact.id,
                artifact.sha256,
                token,
                max_future_seconds=self.settings.sandbox_preview_url_ttl_seconds,
            )
            body = self.storage.get(
                artifact.object_key,
                min(artifact.byte_size, self.settings.sandbox_artifact_max_bytes),
            )
            if (
                len(body) != artifact.byte_size
                or hashlib.sha256(body).hexdigest() != artifact.sha256
            ):
                raise CoworkerError(
                    "sandbox_artifact_integrity_failed",
                    "This interactive artifact could not be verified.",
                    503,
                )
            validate_static_preview_html(body, self.settings.sandbox_artifact_max_bytes)
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=artifact.owner_id,
                resource_id=artifact.id,
                action="sandbox_artifact.previewed",
            ))
            return body

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
                    SandboxExecution.state.in_(("prepared", "running")),
                ).with_for_update()).all():
                    if execution.state == "running":
                        row.cleanup_state = "required"
                    execution.state = "cancelled"
                    execution.error_code = "session_cancelled"
                    execution.request_spec = {"source_scrubbed": True}
                    execution.finished_at = now
                    execution.lease_until = None
                    execution.claimed_by = None
                db.add(AuditEvent(
                    id=str(uuid4()),
                    owner_id=owner,
                    resource_id=row.id,
                    action="sandbox_session.cancelled",
                ))
            return self._session_dto(row)
