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
from zoneinfo import ZoneInfo
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import TzInfo

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



def canonicalize_transport_code_proposal(proposal: CodeProposalEnvelope) -> CodeProposalEnvelope:
    """Normalize only Pydantic's JSON-parser timezone, never arbitrary tzinfo.

    Pydantic emits `TzInfo` from JSON datetime strings, whereas the existing
    immutable review validator deliberately accepts only stdlib timezone and
    ZoneInfo. Preserve the original field set and all nested objects so
    `verify_reviewed_code_identity` still detects forged model_copy() state.
    """
    if type(proposal) is not CodeProposalEnvelope:
        return proposal
    updates = {}
    for field in ("created_at", "expires_at"):
        value = getattr(proposal, field)
        if type(value) is datetime and type(value.tzinfo) is TzInfo:
            # This exact type comes from Pydantic's bounded JSON datetime
            # parser. datetime.fromisoformat supplies a stdlib fixed-offset
            # timezone without changing the reviewed UTC instant.
            updates[field] = datetime.fromisoformat(value.isoformat())
    return proposal.model_copy(update=updates) if updates else proposal


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
        # A copied or subclassed Pydantic model can contain unreviewed state:
        # model_copy(update=...) writes unknown keys to __dict__, while
        # model_dump() silently omits them for extra="forbid" models. Require
        # exact runtime classes and exactly the declared instance fields
        # before invoking any overridable serialization or hash method.
        if type(proposal) is not CodeProposalEnvelope:
            raise ValueError("Unexpected proposal type")
        def only_declared_fields(value, expected_type):
            fields = set(expected_type.model_fields)
            return (
                type(value) is expected_type
                and set(value.__dict__) == fields
                and value.__pydantic_fields_set__ <= fields
                and not value.__pydantic_extra__
                and not value.__pydantic_private__
            )
        if not only_declared_fields(proposal, CodeProposalEnvelope):
            raise ValueError("Unexpected proposal fields")
        # Strict Pydantic reconstruction preserves datetime/UUID subclasses.
        # An adversarial datetime may override astimezone() to disguise its
        # expiry, while a UUID subclass may override string/hex identity.
        # Inspect the *original* values before invoking their methods.
        def canonical_datetime(value):
            # The exact datetime class may still hold an arbitrary tzinfo
            # capable of lying in utcoffset()/astimezone()/isoformat().
            # Accept only immutable stdlib timezone or canonical tzdata zones.
            return (
                type(value) is datetime
                and type(value.tzinfo) in {timezone, ZoneInfo}
            )

        def canonical_uuid(value):
            # CPython's UUID(int=...) can retain a subclassed integer whose
            # __eq__/hash/format implementation misrepresents its identity.
            return (
                type(value) is UUID
                and type(value.int) is int
                and 0 <= value.int < (1 << 128)
            )

        if (
            not canonical_datetime(proposal.created_at)
            or not canonical_datetime(proposal.expires_at)
            or not canonical_uuid(proposal.run_id)
        ):
            raise ValueError("Proposal contains non-canonical timestamp or run identity")
        if any(
            not canonical_uuid(item.document_id)
            or not canonical_uuid(item.version_id)
            for item in proposal.input_versions
        ):
            raise ValueError("Proposal contains non-canonical input identity")
        # Python bool compares equal to 1; it is not a schema version.
        if type(proposal.schema_version) is not int:
            raise ValueError("Proposal schema_version must be an integer")
        # A strict round trip is not enough to prove the *original* copy is
        # immutable: Pydantic accepts nested mappings as construction inputs.
        # Future callers must never inherit mutable limits/input refs after
        # this verifier returns.
        if (
            not only_declared_fields(proposal.limits, CodeComputeLimits)
            or type(proposal.input_versions) is not tuple
            or any(not only_declared_fields(item, CodeInputVersion) for item in proposal.input_versions)
            or type(proposal.destinations) is not tuple
        ):
            raise ValueError("Proposal contains mutable nested fields")
        proposal = CodeProposalEnvelope.model_validate(
            proposal.model_dump(mode="python"), strict=True,
        )
    except Exception:
        raise CoworkerError(
            "code_proposal_invalid",
            "The reviewed code proposal does not satisfy its immutable schema.",
            409,
        ) from None
    if type(now) is not datetime or type(now.tzinfo) not in {timezone, ZoneInfo}:
        raise CoworkerError(
            "code_review_time_invalid",
            "Review time must use a canonical timezone-aware datetime.",
            409,
        )
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


class CodeProposalRevocation(ImmutableReviewModel):
    """Explicit owner decision to revoke one exact proposal identity.

    No acceptance/approval or worker execution authority is expressible.
    """
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


