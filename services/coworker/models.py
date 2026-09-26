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
    agent_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    agent_step_id: Mapped[str | None] = mapped_column(String(36), index=True)
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


class ProviderDailyUsage(Base):
    __tablename__ = "cw_provider_daily_usage"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    allocated_tokens: Mapped[int] = mapped_column(BigInteger, default=0)


class ProviderLease(Base):
    __tablename__ = "cw_provider_leases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lease_key: Mapped[str] = mapped_column(String(160), unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    reserved_tokens: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
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
    provider: Mapped[str] = mapped_column(String(20), default="google")
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


class ActionRecipient(Base):
    __tablename__ = "cw_action_recipients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_key: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(254))
    email_key: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("owner_id", "name_key", name="uq_cw_action_recipients_owner_name"),
        UniqueConstraint("owner_id", "email_key", name="uq_cw_action_recipients_owner_email"),
        Index("cw_action_recipients_owner_name", "owner_id", "name_key"),
    )


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
    agent_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    agent_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key"),
        Index("cw_actions_owner_created", "owner_id", "created_at"),
        Index("cw_actions_dispatch", "state", "delivered", "lease_until"),
    )


class ExecutionGrant(Base):
    __tablename__ = "cw_execution_grants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("cw_external_actions.id"), index=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("cw_connections.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20))
    capability: Mapped[str] = mapped_column(String(20))
    action_kind: Mapped[str] = mapped_column(String(30))
    action_version: Mapped[str] = mapped_column(String(20))
    audience: Mapped[str] = mapped_column(String(80))
    required_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    destinations_sha256: Mapped[str] = mapped_column(String(64))
    preview_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "action_id", "purpose", "preview_hash",
            name="uq_cw_execution_grants_action_purpose_preview",
        ),
        Index("cw_execution_grants_owner_state", "owner_id", "state"),
        Index("cw_execution_grants_action_created", "action_id", "created_at"),
        Index("cw_execution_grants_connection_state", "connection_id", "state"),
    )


class ConnectorReadGrant(Base):
    __tablename__ = "cw_connector_read_grants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("cw_connections.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(20))
    capability: Mapped[str] = mapped_column(String(30))
    operation: Mapped[str] = mapped_column(String(60))
    contract_version: Mapped[str] = mapped_column(String(20))
    audience: Mapped[str] = mapped_column(String(80))
    required_scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    purpose: Mapped[str] = mapped_column(String(40), default="agent_context")
    destination: Mapped[str] = mapped_column(String(60), default="planner_context")
    state: Mapped[str] = mapped_column(String(20), default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "idempotency_key",
            name="uq_cw_connector_read_grants_owner_idempotency",
        ),
        Index("cw_connector_read_grants_owner_state", "owner_id", "state"),
        Index("cw_connector_read_grants_connection_state", "connection_id", "state"),
    )


class ConnectorCursor(Base):
    __tablename__ = "cw_connector_cursors"
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("cw_connector_read_grants.id"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    connection_id: Mapped[str] = mapped_column(ForeignKey("cw_connections.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    capability: Mapped[str] = mapped_column(String(30))
    cursor: Mapped[str | None] = mapped_column(Text)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(20), default="active")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("cw_connector_cursors_owner_updated", "owner_id", "updated_at"),
        Index("cw_connector_cursors_connection", "connection_id"),
    )


class ConnectorSubscription(Base):
    __tablename__ = "cw_connector_subscriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("cw_connector_read_grants.id"), index=True
    )
    connection_id: Mapped[str] = mapped_column(ForeignKey("cw_connections.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    capability: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(30))
    generation: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    provider_subscription_id: Mapped[str | None] = mapped_column(String(512))
    provider_resource_id: Mapped[str | None] = mapped_column(String(512))
    token_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    renew_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(60))
    last_event_sequence: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "grant_id", "generation",
            name="uq_cw_connector_subscriptions_grant_generation",
        ),
        Index("cw_connector_subscriptions_owner_state", "owner_id", "state"),
        Index("cw_connector_subscriptions_grant_state", "grant_id", "state"),
        Index("cw_connector_subscriptions_due", "state", "renew_after"),
        Index(
            "cw_connector_subscriptions_provider_id",
            "provider", "provider_subscription_id",
        ),
    )


class ConnectorEvent(Base):
    __tablename__ = "cw_connector_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("cw_connector_read_grants.id"), index=True
    )
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("cw_connector_subscriptions.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(20))
    capability: Mapped[str] = mapped_column(String(30))
    provider_event_id: Mapped[str] = mapped_column(String(256))
    provider_sequence: Mapped[str | None] = mapped_column(String(64))
    provider_cursor_hint: Mapped[str | None] = mapped_column(String(1024))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claim_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(60))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "provider_event_id",
            name="uq_cw_connector_events_subscription_event",
        ),
        Index("cw_connector_events_owner_state", "owner_id", "state"),
        Index("cw_connector_events_grant_state", "grant_id", "state"),
        Index("cw_connector_events_available", "state", "available_at"),
    )


class ConnectorSnapshot(Base):
    __tablename__ = "cw_connector_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    grant_id: Mapped[str] = mapped_column(
        ForeignKey("cw_connector_read_grants.id"), index=True
    )
    connection_id: Mapped[str] = mapped_column(ForeignKey("cw_connections.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    capability: Mapped[str] = mapped_column(String(30))
    provider_resource_id: Mapped[str] = mapped_column(String(512))
    provider_version: Mapped[str] = mapped_column(String(128))
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="active")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "grant_id", "provider_resource_id",
            name="uq_cw_connector_snapshots_grant_resource",
        ),
        Index("cw_connector_snapshots_owner_updated", "owner_id", "updated_at"),
        Index("cw_connector_snapshots_grant_state", "grant_id", "state"),
    )


class ActionProposal(Base):
    __tablename__ = "cw_action_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(String(300))
    proposal_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="suggested")
    promotion_connection_id: Mapped[str | None] = mapped_column(ForeignKey("cw_connections.id"))
    promoted_action_id: Mapped[str | None] = mapped_column(ForeignKey("cw_external_actions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("cw_action_proposals_run_created", "agent_run_id", "created_at"),
        Index("cw_action_proposals_owner_state", "owner_id", "state"),
    )


class MemoryFact(Base):
    __tablename__ = "cw_memory_facts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"), index=True)
    namespace: Mapped[str] = mapped_column(String(60))
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(35), default="auto")
    provenance_type: Mapped[str] = mapped_column(String(30), default="user")
    provenance_ref: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("owner_id", "workspace_id", "namespace", "key"),
        Index("cw_memory_owner_updated", "owner_id", "updated_at"),
        Index("cw_memory_workspace_namespace", "workspace_id", "namespace"),
    )


class MemoryProposal(Base):
    __tablename__ = "cw_memory_proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), index=True)
    namespace: Mapped[str] = mapped_column(String(60))
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(35), default="auto")
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default="proposed")
    accepted_fact_id: Mapped[str | None] = mapped_column(ForeignKey("cw_memory_facts.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("cw_memory_proposals_owner_state", "owner_id", "state"),
        Index("cw_memory_proposals_run_created", "run_id", "created_at"),
    )


class PersonalGoal(Base):
    __tablename__ = "cw_personal_goals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    objective: Mapped[str] = mapped_column(Text)
    success_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    constraints: Mapped[list[str]] = mapped_column(JSON, default=list)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(30), default="active")
    milestones: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    authorized_resources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_personal_goals_owner_idempotency"),
        Index("cw_personal_goals_owner_created", "owner_id", "created_at"),
        Index("cw_personal_goals_workspace_state", "workspace_id", "state"),
    )


class PersonalGoalRevision(Base):
    __tablename__ = "cw_personal_goal_revisions"
    goal_id: Mapped[str] = mapped_column(ForeignKey("cw_personal_goals.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("cw_personal_goal_revisions_owner_goal", "owner_id", "goal_id"),
    )


class Automation(Base):
    __tablename__ = "cw_automations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"), index=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("cw_personal_goals.id"), index=True)
    goal_revision: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(30), default="active")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    schedule: Mapped[dict[str, Any]] = mapped_column(JSON)
    output_language: Mapped[str] = mapped_column(String(35), default="en")
    overlap_policy: Mapped[str] = mapped_column(String(30), default="skip")
    catchup_window_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    quiet_hours: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schedule_applied_revision: Mapped[int | None] = mapped_column(Integer)
    schedule_applied_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_automations_owner_idempotency"),
        Index("cw_automations_owner_created", "owner_id", "created_at"),
        Index("cw_automations_workspace_state", "workspace_id", "state"),
    )


class AutomationRevision(Base):
    __tablename__ = "cw_automation_revisions"
    automation_id: Mapped[str] = mapped_column(ForeignKey("cw_automations.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("cw_automation_revisions_owner_automation", "owner_id", "automation_id"),)


class AutomationScheduleOutbox(Base):
    __tablename__ = "cw_automation_schedule_outbox"
    automation_id: Mapped[str] = mapped_column(ForeignKey("cw_automations.id"), primary_key=True)
    desired_revision: Mapped[int] = mapped_column(Integer)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class AutomationOccurrence(Base):
    __tablename__ = "cw_automation_occurrences"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    automation_id: Mapped[str] = mapped_column(ForeignKey("cw_automations.id"), index=True)
    automation_revision: Mapped[int] = mapped_column(Integer)
    occurrence_key: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("cw_agent_runs.id"), index=True)
    state: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("automation_id", "occurrence_key", name="uq_cw_automation_occurrence_key"),
        Index("cw_automation_occurrences_owner_due", "owner_id", "due_at"),
    )


class Notification(Base):
    __tablename__ = "cw_notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"))
    automation_id: Mapped[str | None] = mapped_column(ForeignKey("cw_automations.id"), index=True)
    occurrence_id: Mapped[str | None] = mapped_column(ForeignKey("cw_automation_occurrences.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(30), default="pending")
    visible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("cw_notifications_owner_state_visible", "owner_id", "state", "visible_at"),)


class NotificationOutbox(Base):
    __tablename__ = "cw_notification_outbox"
    notification_id: Mapped[str] = mapped_column(ForeignKey("cw_notifications.id"), primary_key=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class BrowserSession(Base):
    __tablename__ = "cw_browser_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(30))
    start_url: Mapped[str] = mapped_column(Text)
    start_origin: Mapped[str] = mapped_column(String(512))
    allowed_origins: Mapped[list[str]] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default="prepared")
    takeover_required: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    worker_session_ref: Mapped[str | None] = mapped_column(String(128))
    last_url: Mapped[str | None] = mapped_column(Text)
    last_title: Mapped[str | None] = mapped_column(String(300))
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_cw_browser_sessions_owner_idempotency"),
        Index("cw_browser_sessions_owner_created", "owner_id", "created_at"),
        Index("cw_browser_sessions_state_expiry", "state", "expires_at"),
    )


class BrowserCommand(Base):
    __tablename__ = "cw_browser_commands"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("cw_browser_sessions.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    target_url: Mapped[str | None] = mapped_column(Text)
    target_origin: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(30), default="prepared")
    error_code: Mapped[str | None] = mapped_column(String(60))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_cw_browser_commands_session_sequence"),
        Index("cw_browser_commands_owner_session", "owner_id", "session_id"),
        Index("cw_browser_commands_state_lease", "state", "lease_until"),
    )


class AgentRun(Base):
    __tablename__ = "cw_agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cw_workspaces.id"))
    goal_id: Mapped[str | None] = mapped_column(String(36), index=True)
    goal_revision: Mapped[int | None] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    goal: Mapped[str] = mapped_column(Text)
    output_language: Mapped[str] = mapped_column(String(35))
    input_versions: Mapped[list[str]] = mapped_column(JSON, default=list)
    action_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    memory_namespaces: Mapped[list[str]] = mapped_column(JSON, default=list)
    connector_read_grant_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    phase: Mapped[str] = mapped_column(String(30), default="planning")
    message: Mapped[str] = mapped_column(String(300), default="Queued for planning.")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60))
    planner_calls: Mapped[int] = mapped_column(Integer, default=0)
    planner_tokens: Mapped[int] = mapped_column(Integer, default=0)
    planner_mode: Mapped[str] = mapped_column(String(30), default="deterministic")
    runtime_version: Mapped[int] = mapped_column(Integer, default=0, index=True)
    planner_actual_tokens: Mapped[int] = mapped_column(Integer, default=0)
    planner_cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key"),
        Index("cw_agent_runs_owner_created", "owner_id", "created_at"),
        Index("cw_agent_runs_state_deadline", "state", "deadline_at"),
    )


class AgentDecision(Base):
    __tablename__ = "cw_agent_decisions"
    run_id: Mapped[str] = mapped_column(ForeignKey("cw_agent_runs.id"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("cw_accounts.id"), index=True)
    planner_call: Mapped[int] = mapped_column(Integer)
    decision_type: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(120))
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    tool_schema_sha256: Mapped[str] = mapped_column(String(64))
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_microusd: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("run_id", "planner_call", name="uq_cw_agent_decisions_planner_call"),
        Index("cw_agent_decisions_owner_run", "owner_id", "run_id"),
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
    depends_on_ordinals: Mapped[list[int]] = mapped_column(JSON, default=list)
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
