from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SandboxModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SandboxSessionCreate(SandboxModel):
    purpose: Literal["data_analysis", "code_task", "interactive_artifact"]
    runtime: Literal["python311"] = "python311"


class SandboxExecutionCreate(SandboxModel):
    # Code is an exact input artifact: do not trim leading/trailing whitespace,
    # because doing so changes program bytes and can change semantics.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    source: str = Field(min_length=1, max_length=20000)


class SandboxWorkerIdentity(SandboxModel):
    worker_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")


class SandboxWorkerClaim(SandboxWorkerIdentity):
    limit: int = Field(default=1, ge=1, le=10)


class SandboxWorkerCompletion(SandboxWorkerIdentity):
    policy_version: Literal["sandbox-control-v1"]
    executor_contract: Literal["bwrap-python311-v1"]
    exit_code: int = Field(ge=-255, le=255)
    stdout: str = Field(max_length=262144)
    stderr: str = Field(max_length=262144)
    elapsed_ms: int = Field(ge=0, le=120000)
    sandbox_destroyed: Literal[True]
    network_isolated: Literal[True]
    filesystem_isolated: Literal[True]
    environment_sanitized: Literal[True]


class SandboxWorkerFailure(SandboxWorkerIdentity):
    error_code: Literal[
        "sandbox_timeout",
        "sandbox_output_limit",
        "sandbox_resource_limit",
        "sandbox_runner_unavailable",
        "sandbox_policy_invalid",
        "sandbox_source_integrity_failed",
        "sandbox_execution_failed",
        "worker_interrupted",
    ]
    sandbox_destroyed: Literal[True]
