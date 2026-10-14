"""CW-10 immutable *inert* code-proposal envelope, not an execution grant.

No method here creates a sandbox session, records an approval, or authorizes
generated code to run. Exact reviewed identity must later be persisted and
revalidated by the existing sandbox worker at claim before CW-10 activation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import CoworkerError


class ImmutableReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=False)


class CodeInputVersion(ImmutableReviewModel):
    owner_id: str = Field(min_length=1, max_length=128)
    document_id: UUID
    version_id: UUID
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CodeComputeLimits(ImmutableReviewModel):
    cpu_seconds: int = Field(ge=1, le=120)
    wall_seconds: int = Field(ge=1, le=120)
    memory_mb: int = Field(ge=64, le=1024)
    disk_mb: int = Field(ge=16, le=512)
    stdout_bytes: int = Field(ge=1, le=65536)

    @model_validator(mode="after")
    def check_cpu_bound(self):
        if self.cpu_seconds > self.wall_seconds:
            raise ValueError("CPU seconds cannot exceed wall seconds")
        return self


class CodeProposalEnvelope(ImmutableReviewModel):
    schema_version: Literal[1] = 1
    owner_id: str = Field(min_length=1, max_length=128)
    run_id: UUID
    source: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_versions: tuple[CodeInputVersion, ...] = Field(default=(), max_length=12)
    limits: CodeComputeLimits
    egress_profile: Literal["none"] = "none"
    destinations: tuple[()] = ()
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def check_exact_identity(self):
        if (
            len(self.source.encode("utf-8")) > 20000
            or hashlib.sha256(self.source.encode("utf-8")).hexdigest() != self.source_sha256
        ):
            raise ValueError("Exact code source bytes/digest are invalid")
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Proposal timestamps must be timezone-aware")
        # Same-zone subtraction can use wall time across DST. Check elapsed
        # instants in UTC to prevent extending the approved lifetime.
        created_utc = self.created_at.astimezone(timezone.utc)
        expires_utc = self.expires_at.astimezone(timezone.utc)
        if expires_utc <= created_utc or (expires_utc - created_utc).total_seconds() > 1800:
            raise ValueError("Proposal timestamps must be increasing and bounded in UTC")
        ids = [str(x.version_id) for x in self.input_versions]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate input document versions are forbidden")
        if any(x.owner_id != self.owner_id for x in self.input_versions):
            raise ValueError("Inputs must be owned by the exact proposal owner")
        return self

    def review_sha256(self) -> str:
        # Hash everything an operator inspects, including all compute/egress
        # limits and expiry. Model proposals never grant execution authority.
        return hashlib.sha256(json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()


def verify_reviewed_code_identity(
    proposal: CodeProposalEnvelope,
    reviewed_sha256: str,
    *,
    owner_id: str,
    run_id: UUID,
    input_versions: tuple[CodeInputVersion, ...],
    maximum_limits: CodeComputeLimits,
    now: datetime,
) -> None:
    """Fail closed on any changed proposal, revoked source, budget or expiry.

    This is an immutable-envelope verifier, NOT sandbox execution approval.
    A future worker claim must also verify a persisted exact human review and
    server-owned run, source, inputs, permission and release identity.
    """
    # Frozen Pydantic models are not necessarily valid: model_copy(update=...)
    # deliberately bypasses field and model validators, including the egress
    # and source-hash restrictions. Reconstruct from primitives at this
    # authority boundary; never trust an in-memory type alone.
    try:
        if not isinstance(proposal, CodeProposalEnvelope):
            raise ValueError("Unexpected proposal type")
        # Python bool compares equal to 1; it is not a schema version.
        if type(proposal.schema_version) is not int:
            raise ValueError("Proposal schema_version must be an integer")
        proposal = CodeProposalEnvelope.model_validate(
            proposal.model_dump(mode="python"), strict=True,
        )
    except Exception:
        raise CoworkerError(
            "code_proposal_invalid",
            "The reviewed code proposal does not satisfy its immutable schema.",
            409,
        ) from None
    if now.tzinfo is None:
        raise CoworkerError("code_review_time_invalid", "Review time must include a timezone.", 409)
    if now.astimezone(timezone.utc) < proposal.created_at.astimezone(timezone.utc):
        raise CoworkerError("code_proposal_not_yet_valid", "Code proposals cannot be reviewed before creation.", 409)
    if now.astimezone(timezone.utc) >= proposal.expires_at.astimezone(timezone.utc):
        raise CoworkerError("code_proposal_expired", "The code proposal is no longer valid.", 409)
    if proposal.owner_id != owner_id or proposal.run_id != run_id:
        raise CoworkerError("code_proposal_owner_mismatch", "The reviewed code is not owned by this run.", 403)
    if (
        len(reviewed_sha256) != 64
        or not hmac.compare_digest(reviewed_sha256, proposal.review_sha256())
    ):
        raise CoworkerError("code_proposal_changed", "Code or its reviewed envelope has changed.", 409)
    if proposal.input_versions != input_versions:
        raise CoworkerError("code_input_revoked", "The reviewed input versions are no longer authorized.", 409)
    expected = proposal.limits
    if (
        expected.cpu_seconds > maximum_limits.cpu_seconds
        or expected.wall_seconds > maximum_limits.wall_seconds
        or expected.memory_mb > maximum_limits.memory_mb
        or expected.disk_mb > maximum_limits.disk_mb
        or expected.stdout_bytes > maximum_limits.stdout_bytes
    ):
        raise CoworkerError("code_resource_limit", "The reviewed code exceeds the sandbox policy.", 409)
