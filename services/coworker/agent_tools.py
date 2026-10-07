"""Server-owned tool contracts for the bounded Agent Runtime foundation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Type

from pydantic import BaseModel, ConfigDict, Field

from .action_registry import action_spec
from .agent_schemas import (
    ApprovedActionToolInput,
    ResearchToolInput,
    SandboxPythonToolInput,
    TaskToolInput,
)
from .config import Settings
from .errors import CoworkerError


ToolKind = Literal["task", "approved_action", "sandbox"]
ReadWriteClass = Literal["read", "write", "read_write", "compute"]
RiskClass = Literal["low", "medium", "high", "critical"]
ApprovalRequirement = Literal["none", "explicit_user_approval"]
RetryMode = Literal["none", "bounded"]
IdempotencyMode = Literal[
    "server_idempotency_key",
    "provider_idempotency_key",
    "reconcile_only",
]


class ToolExecutionOutput(BaseModel):
    """Canonical runtime observation shape for every core Agent tool."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "completed",
        "needs_input",
        "executing",
        "awaiting_approval",
        "provider_confirmed",
    ]
    resource_type: str | None = Field(default=None, max_length=40)
    resource_id: str | None = Field(default=None, max_length=128)
    summary: dict = Field(default_factory=dict)


@dataclass(frozen=True)
class RetryPolicy:
    mode: RetryMode = "none"
    max_attempts: int = 1
    initial_backoff_seconds: float = 0.0
    retryable_errors: tuple[str, ...] = ()

    def public(self) -> dict:
        return {
            "mode": self.mode,
            "max_attempts": self.max_attempts,
            "initial_backoff_seconds": self.initial_backoff_seconds,
            "retryable_errors": list(self.retryable_errors),
        }


@dataclass(frozen=True)
class IdempotencyPolicy:
    mode: IdempotencyMode
    key_scope: str
    outcome_unknown_policy: str

    def public(self) -> dict:
        return {
            "mode": self.mode,
            "key_scope": self.key_scope,
            "outcome_unknown_policy": self.outcome_unknown_policy,
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    kind: ToolKind
    input_model: Type[BaseModel]
    capability: str
    permissions: tuple[str, ...]
    read_write_classification: ReadWriteClass
    risk_class: RiskClass
    retry_policy: RetryPolicy
    idempotency_policy: IdempotencyPolicy
    approval_requirement: ApprovalRequirement
    output_model: Type[BaseModel] = ToolExecutionOutput
    skill_id: str | None = None
    consequential: bool = False
    timeout_seconds: int = 180
    max_result_bytes: int = 65536
    circuit_breaker_failures: int = 3
    circuit_breaker_cooldown_seconds: int = 30

    def __post_init__(self):
        if self.timeout_seconds < 1 or self.timeout_seconds > 600:
            raise ValueError("Tool timeout must be between 1 and 600 seconds")
        if self.max_result_bytes < 1024 or self.max_result_bytes > 1_048_576:
            raise ValueError("Tool result limit must be between 1 KiB and 1 MiB")
        if self.retry_policy.max_attempts < 1 or self.retry_policy.max_attempts > 3:
            raise ValueError("Tool retry attempts must be bounded between 1 and 3")
        if self.consequential and self.retry_policy.max_attempts != 1:
            raise ValueError("Consequential tools cannot receive blind execution retries")
        if self.approval_requirement == "explicit_user_approval" and not self.consequential:
            raise ValueError("Explicit approval tools must be consequential")
        if self.kind == "approved_action":
            expected_kind = {
                "email.send": "email_send",
                "calendar.create": "calendar_create",
            }.get(self.name)
            if expected_kind is None:
                raise ValueError("Approved Agent tool must map to a registered action kind")
            registered = action_spec(expected_kind)
            if registered.capability != self.capability:
                raise ValueError("Agent tool capability does not match the action registry")
            if not self.consequential or self.approval_requirement != "explicit_user_approval":
                raise ValueError("Registered consequential Agent tools require explicit approval")
            if self.idempotency_policy.mode not in {
                "provider_idempotency_key",
                "reconcile_only",
            }:
                raise ValueError("Approved actions require provider idempotency or reconcile-only policy")

    @property
    def approval_required(self) -> bool:
        return self.approval_requirement == "explicit_user_approval"

    def public(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "capability": self.capability,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "permissions": list(self.permissions),
            "read_write_classification": self.read_write_classification,
            "risk_class": self.risk_class,
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy.public(),
            "idempotency_policy": self.idempotency_policy.public(),
            "approval_requirement": self.approval_requirement,
            "consequential": self.consequential,
            "approval_required": self.approval_required,
            "max_result_bytes": self.max_result_bytes,
            "circuit_breaker": {
                "failure_threshold": self.circuit_breaker_failures,
                "cooldown_seconds": self.circuit_breaker_cooldown_seconds,
            },
        }

    def enabled(self, settings: Settings) -> bool:
        if self.name == "sandbox.execute_python":
            return (
                settings.code_execution_enabled
                and settings.agent_sandbox_tool_enabled
                and settings.agent_runtime_v3_enabled
                and settings.intelligent_planner_enabled
            )
        if self.name == "research.search":
            return settings.research_services_enabled
        if self.name in {"presentation.create", "spreadsheet.create"}:
            return settings.artifact_services_enabled
        if self.kind == "approved_action":
            return settings.actions_enabled
        return settings.work_services_enabled or self.skill_id == "report_email"

    def validate(self, arguments: dict):
        try:
            return self.input_model.model_validate(arguments)
        except Exception as error:
            raise CoworkerError(
                "invalid_tool_input",
                "The Agent tool input does not match its registered schema.",
                422,
            ) from error

    def validate_output(self, value: dict):
        try:
            return self.output_model.model_validate(value)
        except Exception as error:
            raise CoworkerError(
                "provider_unavailable",
                "The tool returned a malformed response.",
                502,
            ) from error


BOUNDED_READ_RETRY = RetryPolicy(
    mode="bounded",
    max_attempts=2,
    initial_backoff_seconds=0.25,
    retryable_errors=("provider_unavailable", "provider_rate_limited", "tool_timeout"),
)
DURABLE_TASK_RETRY = RetryPolicy(
    mode="bounded",
    max_attempts=2,
    initial_backoff_seconds=0.25,
    retryable_errors=("provider_unavailable", "provider_rate_limited", "tool_timeout"),
)
NO_RETRY = RetryPolicy()
SERVER_TASK_IDEMPOTENCY = IdempotencyPolicy(
    mode="server_idempotency_key",
    key_scope="agent_run_step",
    outcome_unknown_policy="resume_durable_resource",
)
SANDBOX_IDEMPOTENCY = IdempotencyPolicy(
    mode="server_idempotency_key",
    key_scope="agent_run_step",
    outcome_unknown_policy="inspect_existing_execution_before_new_execution",
)
ACTION_IDEMPOTENCY = IdempotencyPolicy(
    mode="reconcile_only",
    key_scope="approved_external_action",
    outcome_unknown_policy="reconcile_or_manual_verify_never_blind_retry",
)


def _task(
    name: str,
    skill_id: str,
    *,
    timeout_seconds: int = 180,
    capability: str | None = None,
    read_write_classification: ReadWriteClass = "write",
    risk_class: RiskClass = "medium",
    permissions: tuple[str, ...] = ("workspace:write", "owned_documents:read"),
    input_model: Type[BaseModel] = TaskToolInput,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        version="1",
        kind="task",
        input_model=input_model,
        skill_id=skill_id,
        capability=capability or skill_id,
        permissions=permissions,
        read_write_classification=read_write_classification,
        risk_class=risk_class,
        retry_policy=BOUNDED_READ_RETRY if read_write_classification == "read" else DURABLE_TASK_RETRY,
        idempotency_policy=SERVER_TASK_IDEMPOTENCY,
        approval_requirement="none",
        timeout_seconds=timeout_seconds,
    )


TOOLS = {
    spec.name: spec
    for spec in (
        _task("report.create", "report_email", capability="report"),
        _task("document.create", "document"),
        _task("career.create", "career"),
        _task("social.draft", "social"),
        _task("daily_plan.create", "daily_plan"),
        _task("personal_plan.create", "personal_plan"),
        _task("email.draft", "email"),
        _task("meeting.prepare", "meeting"),
        _task("presentation.create", "presentation", timeout_seconds=240),
        _task("spreadsheet.create", "spreadsheet", timeout_seconds=240),
        _task(
            "research.search",
            "research",
            timeout_seconds=240,
            input_model=ResearchToolInput,
            capability="public_research",
            read_write_classification="read",
            permissions=("public_web:read", "workspace:write"),
            risk_class="medium",
        ),
        ToolSpec(
            "sandbox.execute_python",
            "1",
            "sandbox",
            SandboxPythonToolInput,
            capability="isolated_python",
            permissions=("sandbox:execute",),
            read_write_classification="compute",
            risk_class="high",
            retry_policy=NO_RETRY,
            idempotency_policy=SANDBOX_IDEMPOTENCY,
            approval_requirement="none",
            timeout_seconds=120,
            max_result_bytes=32768,
        ),
        ToolSpec(
            "email.send",
            "1",
            "approved_action",
            ApprovedActionToolInput,
            capability="email",
            permissions=("connected_email:write",),
            read_write_classification="write",
            risk_class="high",
            retry_policy=NO_RETRY,
            idempotency_policy=ACTION_IDEMPOTENCY,
            approval_requirement="explicit_user_approval",
            consequential=True,
            timeout_seconds=120,
            max_result_bytes=16384,
        ),
        ToolSpec(
            "calendar.create",
            "1",
            "approved_action",
            ApprovedActionToolInput,
            capability="calendar",
            permissions=("connected_calendar:write",),
            read_write_classification="write",
            risk_class="high",
            retry_policy=NO_RETRY,
            idempotency_policy=ACTION_IDEMPOTENCY,
            approval_requirement="explicit_user_approval",
            consequential=True,
            timeout_seconds=120,
            max_result_bytes=16384,
        ),
    )
}


def tool(name: str) -> ToolSpec:
    value = TOOLS.get(name)
    if value is None:
        raise CoworkerError(
            "tool_not_supported",
            "This Agent tool is not registered.",
            409,
        )
    return value


def available_tools(settings: Settings) -> list[dict]:
    return [spec.public() for spec in TOOLS.values() if spec.enabled(settings)]
