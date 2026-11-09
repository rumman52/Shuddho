from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


class FlyWorkspaceFileOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str = Field(min_length=3, max_length=255)
    branch: str = Field(min_length=1, max_length=255)
    commit_sha: str = Field(pattern=_SHA1.pattern)
    blob_sha: str = Field(pattern=_SHA1.pattern)
    source_sha256: str = Field(pattern=_SHA256.pattern)


class FlyWorkspaceFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=512)
    document_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    sha256: str = Field(pattern=_SHA256.pattern)
    byte_size: int = Field(ge=0, le=262144)
    origin: FlyWorkspaceFileOrigin | None = None


class FlyWorkspaceSync(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    repository: str = Field(pattern=_REPOSITORY.pattern, max_length=255)
    branch: str = Field(min_length=1, max_length=255)
    commit_sha: str = Field(pattern=_SHA1.pattern)
    files: list[FlyWorkspaceFileInput] = Field(max_length=12)

    @model_validator(mode="after")
    def unique_paths(self):
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Fly workspace paths must be unique")
        for item in self.files:
            if item.origin and (
                item.origin.repository != self.repository
                or item.origin.branch != self.branch
                or item.origin.commit_sha != self.commit_sha
            ):
                raise ValueError("GitHub file provenance must match the workspace repository revision")
        return self


class FlyPatchChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=512)
    operation: Literal["create", "update", "delete"]
    content: str | None = Field(default=None, max_length=262144)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def content_matches_operation(self):
        if self.operation == "delete" and self.content is not None:
            raise ValueError("Delete changes must not include replacement content")
        if self.operation in {"create", "update"} and self.content is None:
            raise ValueError("Create and update changes require complete file content")
        return self


class FlyPatchModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=500)
    changes: list[FlyPatchChange] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_change_paths(self):
        paths = [item.path for item in self.changes]
        if len(paths) != len(set(paths)):
            raise ValueError("A patch may change each path only once")
        return self


class FlyPatchGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    instruction: str = Field(min_length=5, max_length=12000)


class FlyPatchReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_sha256: str = Field(pattern=_SHA256.pattern)
    decision: Literal["approve", "reject"]


class FlyRepositoryTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    patch_proposal_id: str | None = Field(default=None, max_length=36)



class FlyPatchApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_sha256: str = Field(pattern=_SHA256.pattern)
