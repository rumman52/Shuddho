"""Typed owner-authenticated GitHub repository connection requests."""
from pydantic import BaseModel, ConfigDict, Field


class GitHubRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GitHubOAuthFinish(GitHubRequest):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=32, max_length=256)


class GitHubInstallComplete(GitHubRequest):
    installation_id: int = Field(gt=0)
    state: str = Field(min_length=32, max_length=256)


class GitHubRepositoryBind(GitHubRequest):
    installation_record_id: str = Field(min_length=36, max_length=36)
    repository_id: int = Field(gt=0)
    expected_revision: int = Field(ge=1)
