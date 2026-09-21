from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "cw_accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(128))
    storage_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("issuer", "subject"),)


class Workspace(Base):
    __tablename__ = "cw_workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), unique=True)
    name: Mapped[str] = mapped_column(String(100), default="My workspace")


class Document(Base):
    __tablename__ = "cw_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"))
    filename: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class DocumentVersion(Base):
    __tablename__ = "cw_document_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("cw_documents.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(10))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(512))
    state: Mapped[str] = mapped_column(String(30), default="awaiting_upload")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("document_id", "version"),)


class Task(Base):
    __tablename__ = "cw_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    workflow_version: Mapped[str] = mapped_column(String(40), default="report_email_v1")
    instruction: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text)
    output_language: Mapped[str] = mapped_column(String(35))
    input_versions: Mapped[list[str]] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    phase: Mapped[str] = mapped_column(String(30), default="queued")
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(String(300), default="Queued for your coworker.")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key"),
        Index("cw_tasks_owner_created", "owner_id", "created_at"),
        Index("cw_tasks_state_deadline", "state", "deadline_at"),
    )


class Step(Base):
    __tablename__ = "cw_steps"
    task_id: Mapped[str] = mapped_column(ForeignKey("cw_tasks.id"), primary_key=True)
    phase: Mapped[str] = mapped_column(String(30), primary_key=True)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    __tablename__ = "cw_outbox"
    task_id: Mapped[str] = mapped_column(ForeignKey("cw_tasks.id"), primary_key=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class TaskEvent(Base):
    __tablename__ = "cw_task_events"
    task_id: Mapped[str] = mapped_column(ForeignKey("cw_tasks.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(30))
    phase: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artifact(Base):
    __tablename__ = "cw_artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("cw_tasks.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    filename: Mapped[str] = mapped_column(String(160))
    content_type: Mapped[str] = mapped_column(String(100))
    object_key: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("task_id", "filename"),)


class DailyUsage(Base):
    __tablename__ = "cw_daily_usage"
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), primary_key=True)
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    allocated_tokens: Mapped[int] = mapped_column(Integer, default=0)
    task_count: Mapped[int] = mapped_column(Integer, default=0)


class ModelAttempt(Base):
    __tablename__ = "cw_model_attempts"
    task_id: Mapped[str] = mapped_column(ForeignKey("cw_tasks.id"), primary_key=True)
    attempt: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"))
    day: Mapped[str] = mapped_column(String(10))
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    charged_tokens: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30), default="reserved")
    model: Mapped[str] = mapped_column(String(120))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "cw_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    resource_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OAuthAttempt(Base):
    __tablename__ = "cw_oauth_attempts"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    capability: Mapped[str] = mapped_column(String(20))
    verifier_ciphertext: Mapped[str] = mapped_column(Text)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Connection(Base):
    __tablename__ = "cw_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="google")
    capability: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(254))
    scopes: Mapped[list[str]] = mapped_column(JSON)
    token_ciphertext: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExternalAction(Base):
    __tablename__ = "cw_external_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"))
    connection_id: Mapped[str] = mapped_column(ForeignKey("cw_connections.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(30))
    preview: Mapped[dict[str, Any]] = mapped_column(JSON)
    preview_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="awaiting_approval")
    receipt: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key"),
        Index("cw_actions_owner_created", "owner_id", "created_at"),
        Index("cw_actions_dispatch", "state", "delivered", "lease_until"),
    )


class AgentRun(Base):
    __tablename__ = "cw_agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    goal: Mapped[str] = mapped_column(Text)
    output_language: Mapped[str] = mapped_column(String(35))
    input_versions: Mapped[list[str]] = mapped_column(JSON, default=list)
    action_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    phase: Mapped[str] = mapped_column(String(30), default="planning")
    message: Mapped[str] = mapped_column(String(300), default="Queued for planning.")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key"),
        Index("cw_agent_runs_owner_created", "owner_id", "created_at"),
        Index("cw_agent_runs_state_deadline", "state", "deadline_at"),
    )


class AgentOutbox(Base):
    __tablename__ = "cw_agent_outbox"
    run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), primary_key=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class AgentStep(Base):
    __tablename__ = "cw_agent_steps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(30), default="planned")
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("run_id", "ordinal"),)


class AgentEvent(Base):
    __tablename__ = "cw_agent_events"
    run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    state: Mapped[str] = mapped_column(String(30))
    phase: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ToolInvocation(Base):
    __tablename__ = "cw_tool_invocations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), index=True)
    step_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_steps.id"), unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    tool_version: Mapped[str] = mapped_column(String(20))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(30), default="prepared")
    consequential: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolReceipt(Base):
    __tablename__ = "cw_tool_receipts"
    invocation_id: Mapped[str] = mapped_column(ForeignKey("cw_tool_invocations.id"), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
