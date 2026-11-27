from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _exact_true(value: object) -> object:
    if value is not True:
        raise ValueError("Isolation evidence must be the boolean true")
    return value


VerifiedTrue = Annotated[Literal[True], BeforeValidator(_exact_true)]


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
    # Legacy workers omit this and remain Python-only by default.
    supported_kinds: list[Literal["python", "repository_test"]] = Field(
        default_factory=lambda: ["python"], min_length=1, max_length=2,
    )


class SandboxWorkerArtifact(SandboxModel):
    kind: Literal["interactive_html"]
    body_b64: str = Field(min_length=4, max_length=90000, pattern=r"^[A-Za-z0-9+/]+={0,2}$")
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(ge=1, le=65536, strict=True)


class SandboxWorkerCompletion(SandboxWorkerIdentity):
    policy_version: Literal["sandbox-control-v1"]
    executor_contract: Literal["bwrap-python311-v1", "bwrap-python311-node22-v1"]
    exit_code: int = Field(ge=-255, le=255, strict=True)
    stdout: str = Field(max_length=65536)
    stderr: str = Field(max_length=65536)
    elapsed_ms: int = Field(ge=0, le=120000, strict=True)
    sandbox_destroyed: VerifiedTrue
    network_isolated: VerifiedTrue
    filesystem_isolated: VerifiedTrue
    environment_sanitized: VerifiedTrue
    artifact: SandboxWorkerArtifact | None = None


class SandboxWorkerFailure(SandboxWorkerIdentity):
    error_code: Literal[
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
    ]
    sandbox_destroyed: VerifiedTrue
