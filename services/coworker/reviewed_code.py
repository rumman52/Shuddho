"""CW-10: explicit owner review and atomic sandbox admission for exact code.

This is a constrained, separately gated review endpoint, not a model tool.
Only source-less input versions (no document grants) and networkless stdlib
code_task sandbox are supported. More capabilities require separate approval.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from .code_proposal_schemas import CodeComputeLimits, CodeProposalEnvelope, verify_reviewed_code_identity
from .errors import CoworkerError
from .models import AgentRun, AuditEvent, ReviewedCodeProposal, SandboxExecution, SandboxSession, utcnow
from .repository import aware, not_found
from .sandbox import SANDBOX_POLICY_VERSION, _digest

TERMINAL_RUNS = {"completed", "failed", "cancelled", "expired"}


class ReviewedCodeRepository:
    def __init__(self, sessions, settings, sandbox):
        self.sessions = sessions
        self.settings = settings
        self.sandbox = sandbox

    def _require_enabled(self):
        if not (self.settings.reviewed_code_execution_enabled and self.settings.code_execution_enabled):
            raise CoworkerError("reviewed_code_disabled", "Reviewed code is not enabled.", 503)

    def _maximum_limits(self):
        return CodeComputeLimits(
            cpu_seconds=self.settings.sandbox_cpu_seconds,
            wall_seconds=self.settings.sandbox_wall_seconds,
            memory_mb=self.settings.sandbox_memory_mb,
            disk_mb=self.settings.sandbox_disk_mb,
            stdout_bytes=self.settings.sandbox_max_output_bytes,
        )

    def _validate(self, envelope, owner: str, run_id: str, review_hash: str, now):
        try:
            proposal = CodeProposalEnvelope.model_validate(envelope)
        except Exception:
            raise CoworkerError("code_proposal_invalid", "The code proposal schema is invalid.", 409) from None
        verify_reviewed_code_identity(
            proposal, review_hash, owner_id=owner, run_id=UUID(run_id),
            input_versions=(), maximum_limits=self._maximum_limits(), now=now,
        )
        # Until document purpose-grants are implemented, even an otherwise
        # well-formed pinned input must not become an implicit sandbox mount.
        if proposal.input_versions or proposal.destinations or proposal.egress_profile != "none":
            raise CoworkerError("code_inputs_not_authorized", "Reviewed code cannot access document inputs or destinations.", 409)
        if len(proposal.source.encode("utf-8")) > self.settings.sandbox_max_source_bytes:
            raise CoworkerError("sandbox_source_too_large", "Reviewed code exceeds sandbox source budget.", 413)
        if proposal.expires_at.astimezone(timezone.utc) > now + timedelta(
            seconds=self.settings.sandbox_session_ttl_seconds
        ):
            raise CoworkerError("code_review_expiry_too_long", "The proposal outlives the sandbox session limit.", 409)
        return proposal

    def _run(self, db, owner, run_id, now, lock=False):
        query = select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_id == owner)
        if lock:
            query = query.with_for_update()
        run = db.scalar(query)
        if run is None:
            raise not_found()
        if run.cancel_requested or run.state in TERMINAL_RUNS or aware(run.deadline_at) <= now:
            raise CoworkerError("code_run_closed", "The owning Agent run is no longer eligible.", 409)
        return run

    @staticmethod
    def _dto(row):
        return {
            "id": row.id, "run_id": row.agent_run_id,
            "review_sha256": row.review_sha256, "state": row.state,
            "envelope": dict(row.envelope or {}),
            "session_id": row.session_id, "execution_id": row.execution_id,
            "expires_at": aware(row.expires_at).isoformat(),
            "decided_at": aware(row.decided_at).isoformat() if row.decided_at else None,
        }

    def propose(self, owner: str, run_id: str, envelope: CodeProposalEnvelope, key: str):
        self._require_enabled()
        now = utcnow()
        sha = envelope.review_sha256()
        self._validate(envelope.model_dump(mode="python"), owner, run_id, sha, now)
        with self.sessions.begin() as db:
            self._run(db, owner, run_id, now, lock=True)
            prev = db.scalar(select(ReviewedCodeProposal).where(
                ReviewedCodeProposal.owner_id == owner, ReviewedCodeProposal.idempotency_key == key,
            ))
            if prev:
                if prev.review_sha256 != sha or prev.agent_run_id != run_id:
                    raise CoworkerError("idempotency_conflict", "The request key belongs to another code review.", 409)
                return self._dto(prev), False
            row = ReviewedCodeProposal(
                id=str(uuid4()), owner_id=owner, agent_run_id=run_id,
                idempotency_key=key, review_sha256=sha,
                envelope=envelope.model_dump(mode="json"), state="pending",
                created_at=now, expires_at=envelope.expires_at,
            )
            db.add(row)
            db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=row.id,
                              action="reviewed_code.proposed"))
            db.flush()
            return self._dto(row), True

    def get(self, owner: str, review_id: str):
        self._require_enabled()
        with self.sessions() as db:
            row = db.scalar(select(ReviewedCodeProposal).where(
                ReviewedCodeProposal.owner_id == owner, ReviewedCodeProposal.id == review_id,
            ))
            if row is None:
                raise not_found()
            return self._dto(row)

    def decide(self, owner: str, review_id: str, review_sha256: str, decision: str):
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            row = db.scalar(select(ReviewedCodeProposal).where(
                ReviewedCodeProposal.owner_id == owner, ReviewedCodeProposal.id == review_id,
            ).with_for_update())
            if row is None:
                raise not_found()
            if not hmac.compare_digest(row.review_sha256, review_sha256):
                raise CoworkerError("code_review_hash_mismatch", "The reviewed code has changed.", 409)
            if row.state == "approved" and decision == "approve":
                return self._dto(row)
            if row.state != "pending" or aware(row.expires_at) <= now:
                raise CoworkerError("code_review_closed", "This code review is no longer eligible.", 409)
            run = self._run(db, owner, row.agent_run_id, now, lock=True)
            envelope = self._validate(row.envelope, owner, row.agent_run_id, row.review_sha256, now)
            if decision == "reject":
                row.state = "rejected"
                row.envelope = {"source_scrubbed": True}
            elif decision == "approve":
                # Approval, owned sandbox session and exact execution become
                # visible together in ONE DB transaction; no pre-approval job.
                policy = self.sandbox._policy()
                session = SandboxSession(
                    id=str(uuid4()), owner_id=owner, workspace_id=run.workspace_id,
                    idempotency_key=f"review:{review_id}",
                    fingerprint=_digest({"purpose": "code_task", "runtime": "python311"}),
                    purpose="code_task", runtime="python311", state="prepared",
                    execution_policy=policy, cancel_requested=False,
                    cleanup_state="pending", created_at=now, updated_at=now,
                    expires_at=min(aware(row.expires_at), now + timedelta(
                        seconds=self.settings.sandbox_session_ttl_seconds
                    )),
                )
                db.add(session)
                db.flush()
                encoded = envelope.source.encode("utf-8")
                execution = SandboxExecution(
                    id=str(uuid4()), owner_id=owner, session_id=session.id,
                    sequence=1, kind="python", source_sha256=hashlib.sha256(encoded).hexdigest(),
                    source_bytes=len(encoded),
                    request_spec={
                        "source": envelope.source, "source_trust": "untrusted",
                        "policy_version": SANDBOX_POLICY_VERSION,
                        "review_id": review_id, "review_sha256": row.review_sha256,
                    }, state="prepared",
                )
                db.add(execution)
                db.flush()
                row.session_id, row.execution_id = session.id, execution.id
                row.state = "approved"
            else:
                raise CoworkerError("code_review_decision_invalid", "Invalid code review decision.", 422)
            row.decided_at = now
            db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=row.id,
                              action="reviewed_code." + row.state))
            return self._dto(row)

    def revoke(self, owner: str, review_id: str):
        self._require_enabled()
        now = utcnow()
        with self.sessions.begin() as db:
            pending = db.scalar(select(ReviewedCodeProposal).where(
                ReviewedCodeProposal.owner_id == owner, ReviewedCodeProposal.id == review_id,
            ))
            if pending is None:
                raise not_found()
            if pending.state == "revoked":
                return self._dto(pending)
            if pending.state not in {"pending", "approved"}:
                raise CoworkerError("code_review_closed", "The code review is already closed.", 409)
            # Match worker claim lock order: execution, session, review.
            execution = db.scalar(select(SandboxExecution).where(
                SandboxExecution.id == pending.execution_id,
                SandboxExecution.owner_id == owner,
            ).with_for_update()) if pending.execution_id else None
            session = db.scalar(select(SandboxSession).where(
                SandboxSession.id == pending.session_id, SandboxSession.owner_id == owner,
            ).with_for_update()) if pending.session_id else None
            row = db.scalar(select(ReviewedCodeProposal).where(
                ReviewedCodeProposal.id == review_id, ReviewedCodeProposal.owner_id == owner,
            ).with_for_update())
            if row is None or row.state not in {"pending", "approved"}:
                raise CoworkerError("code_review_closed", "The code review changed before revocation.", 409)
            row.state = "revoked"
            row.envelope = {"source_scrubbed": True}
            row.decided_at = now
            if session:
                session.state = "cancelled"
                session.cancel_requested = True
                session.updated_at = now
                session.cleanup_state = "required" if execution and execution.state == "running" else "not_required"
            if execution and execution.state in {"prepared", "running"}:
                execution.state = "cancelled"
                execution.error_code = "code_review_revoked"
                execution.request_spec = {"source_scrubbed": True}
                execution.finished_at = now
                execution.lease_until = None
                execution.claimed_by = None
            db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=review_id,
                              action="reviewed_code.revoked"))
            return self._dto(row)
