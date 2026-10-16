"""CW-10 inert-envelope tests. None of these authorize or run generated code."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone, tzinfo
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from services.coworker.code_proposal_schemas import (
    CodeComputeLimits,
    CodeInputVersion,
    CodeProposalEnvelope,
    verify_reviewed_code_identity,
    canonicalize_transport_code_proposal,
)
from services.coworker.errors import CoworkerError


def setup_envelope():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    owner, run_id = "owned-account", uuid4()
    source = "print('hello')\n"
    ref = CodeInputVersion(
        owner_id=owner, document_id=uuid4(), version_id=uuid4(),
        source_sha256="a" * 64,
    )
    limits = CodeComputeLimits(
        cpu_seconds=5, wall_seconds=15, memory_mb=128, disk_mb=32, stdout_bytes=1024,
    )
    envelope = CodeProposalEnvelope(
        owner_id=owner, run_id=run_id, source=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        input_versions=(ref,), limits=limits,
        egress_profile="none", destinations=(),
        created_at=now, expires_at=now + timedelta(minutes=10),
    )
    return envelope, now


def verified(envelope, now, **changes):
    value = {
        "reviewed_sha256": envelope.review_sha256(),
        "owner_id": envelope.owner_id,
        "run_id": envelope.run_id,
        "input_versions": envelope.input_versions,
        "maximum_limits": CodeComputeLimits(
            cpu_seconds=10, wall_seconds=30, memory_mb=256,
            disk_mb=64, stdout_bytes=4096,
        ),
        "now": now,
    }
    value.update(changes)
    return verify_reviewed_code_identity(envelope, value.pop("reviewed_sha256"), **value)


def test_exact_immutable_review_envelope_can_be_verified_without_running_code():
    envelope, now = setup_envelope()
    assert len(envelope.review_sha256()) == 64
    assert verified(envelope, now) is None
    with pytest.raises(ValidationError):
        envelope.source = "print('changed')"
    assert envelope.destinations == ()
    assert envelope.egress_profile == "none"


@pytest.mark.parametrize("field,replacement", [
    ("source", "print('changed')\n"),
    ("limits", CodeComputeLimits(
        cpu_seconds=6, wall_seconds=15, memory_mb=128, disk_mb=32, stdout_bytes=1024,
    )),
    ("expires_at", datetime(2026, 10, 14, 12, 11, tzinfo=timezone.utc)),
])
def test_any_changed_reviewed_envelope_invalidates_original_digest(field, replacement):
    envelope, now = setup_envelope()
    original = envelope.review_sha256()
    updates = {field: replacement}
    if field == "source":
        updates["source_sha256"] = hashlib.sha256(replacement.encode()).hexdigest()
    modified = envelope.model_copy(update=updates)
    with pytest.raises(CoworkerError, match="changed"):
        verified(modified, now, reviewed_sha256=original)


def test_cross_owner_run_and_revoked_exact_input_versions_fail_closed():
    envelope, now = setup_envelope()
    with pytest.raises(CoworkerError, match="owned"):
        verified(envelope, now, owner_id="another-owner")
    with pytest.raises(CoworkerError, match="owned"):
        verified(envelope, now, run_id=uuid4())
    with pytest.raises(CoworkerError, match="no longer"):
        verified(envelope, now, input_versions=())


def test_expiry_and_limit_reductions_invalidate_previously_reviewed_compute():
    envelope, now = setup_envelope()
    with pytest.raises(CoworkerError, match="no longer"):
        verified(envelope, envelope.expires_at)
    with pytest.raises(CoworkerError, match="exceeds"):
        verified(envelope, now, maximum_limits=CodeComputeLimits(
            cpu_seconds=4, wall_seconds=30, memory_mb=256, disk_mb=64,
            stdout_bytes=4096,
        ))



def test_future_created_at_cannot_extend_proposal_validity_window():
    envelope, now = setup_envelope()
    future = envelope.model_copy(update={
        "created_at": now + timedelta(days=365),
        "expires_at": now + timedelta(days=365, minutes=10),
    })
    with pytest.raises(CoworkerError, match="before creation"):
        verified(future, now, reviewed_sha256=future.review_sha256())




def test_dst_fall_back_cannot_extend_proposal_expiry_beyond_utc_limit():
    envelope, _ = setup_envelope()
    zone = ZoneInfo("America/New_York")
    # At the 2026 fall-back, 01:45 EDT -> 02:00 EST is 75 elapsed
    # minutes, although wall-time subtraction returns only 15.
    created = datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0)
    expires = datetime(2026, 11, 1, 2, 0, tzinfo=zone)
    assert (expires.astimezone(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() == 4500
    with pytest.raises(ValidationError, match="bounded in UTC"):
        CodeProposalEnvelope.model_validate({
            **envelope.model_dump(mode="python"),
            "created_at": created, "expires_at": expires,
        })



def test_invalid_sources_cross_owner_inputs_and_network_destinations_rejected():
    envelope, _ = setup_envelope()
    with pytest.raises(ValidationError):
        CodeProposalEnvelope.model_validate({
            **envelope.model_dump(mode="python"), "source_sha256": "b" * 64,
        })
    with pytest.raises(ValidationError):
        CodeProposalEnvelope.model_validate({
            **envelope.model_dump(mode="python"), "destinations": ("https://example.com",),
        })
    with pytest.raises(ValidationError):
        CodeProposalEnvelope.model_validate({
            **envelope.model_dump(mode="python"), "egress_profile": "internet",
        })
    with pytest.raises(ValidationError):
        CodeProposalEnvelope.model_validate({
            **envelope.model_dump(mode="python"),
            "input_versions": ({**envelope.input_versions[0].model_dump(), "owner_id": "foreign"},),
        })
    with pytest.raises(ValidationError):
        CodeProposalEnvelope.model_validate({
            **envelope.model_dump(mode="python"), "expires_at": envelope.created_at,
        })


@pytest.mark.parametrize("invalid_change", [
    {"egress_profile": "internet"},
    {"destinations": ("https://example.com/",)},
    {"destinations": []},
    "limits_mapping_same_values",
    "inputs_mapping_same_values",
    {"source_sha256": "b" * 64},
    {"expires_at": "2026-10-14T12:10:00Z"},
    {"schema_version": True},
    {"limits": CodeComputeLimits(
        cpu_seconds=5, wall_seconds=15, memory_mb=128,
        disk_mb=32, stdout_bytes=1024,
    ).model_copy(update={"cpu_seconds": 5.0})},
    {"limits": CodeComputeLimits(
        cpu_seconds=5, wall_seconds=15, memory_mb=128,
        disk_mb=32, stdout_bytes=1024,
    ).model_copy(update={"cpu_seconds": 120})},
    {"expires_at": datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc)},
])
def test_model_copy_bypass_cannot_persuade_review_identity(invalid_change):
    """Even a matching digest of an invalid copied object is never approval."""
    original, now = setup_envelope()
    if invalid_change == "limits_mapping_same_values":
        invalid_change = {"limits": original.limits.model_dump(mode="python")}
    elif invalid_change == "inputs_mapping_same_values":
        invalid_change = {
            "input_versions": (
                original.input_versions[0].model_dump(mode="python"),
            )
        }
    forged = original.model_copy(update=invalid_change)
    # Pydantic intentionally skips validation for model_copy(update=...).
    # The attacker supplies a self-consistent digest of the forged instance.
    with pytest.raises(CoworkerError) as denied:
        verified(forged, now, reviewed_sha256=forged.review_sha256())
    assert denied.value.code == "code_proposal_invalid"


@pytest.mark.parametrize("field", ["approved", "network_grant", "model_dump"])
def test_copied_envelope_undeclared_state_fails_even_with_matching_digest(field):
    original, now = setup_envelope()
    # Pydantic silently ignores unknown copied fields when serializing, so
    # the forged review hash can equal the original despite the extra state.
    value = (lambda **kw: original.model_dump(**kw)) if field == "model_dump" else True
    copied = original.model_copy(update={field: value})
    with pytest.raises(CoworkerError) as denied:
        verified(copied, now, reviewed_sha256=original.review_sha256())
    assert denied.value.code == "code_proposal_invalid"


@pytest.mark.parametrize("field", ["limits", "input_versions"])
def test_nested_copied_models_with_extra_state_are_not_immutable(field):
    original, now = setup_envelope()
    if field == "limits":
        replaced = original.limits.model_copy(update={"grant": "unreviewed"})
        copied = original.model_copy(update={"limits": replaced})
    else:
        replaced = original.input_versions[0].model_copy(update={"grant": "unreviewed"})
        copied = original.model_copy(update={"input_versions": (replaced,)})
    with pytest.raises(CoworkerError) as denied:
        verified(copied, now, reviewed_sha256=copied.review_sha256())
    assert denied.value.code == "code_proposal_invalid"


def test_envelope_subclass_is_not_a_reviewed_base_envelope():
    original, now = setup_envelope()

    class UntrustedSubclass(CodeProposalEnvelope):
        def model_dump(self, *args, **kwargs):
            # Overridden serializers cannot establish the original object's
            # claimed identity, even if they return benign-looking content.
            return original.model_dump(*args, **kwargs)

    subclass = UntrustedSubclass.model_validate(original.model_dump(mode="python"))
    with pytest.raises(CoworkerError) as denied:
        verified(subclass, now, reviewed_sha256=original.review_sha256())
    assert denied.value.code == "code_proposal_invalid"


class MisleadingDatetime(datetime):
    """Represents a late expiry but can claim a shorter one when normalized."""

    def astimezone(self, tz=None):
        # This is not valid evidence of the underlying actual instant.
        return super().astimezone(tz) - timedelta(hours=3)


class UntrustedUUID(UUID):
    """The verifier must accept only the ordinary, non-overridden identity type."""


@pytest.mark.parametrize("field", ["created_at", "expires_at", "run_id"])
def test_review_rejects_copied_datetime_and_run_uuid_subclasses_before_hashing(field):
    envelope, now = setup_envelope()
    if field == "run_id":
        changed = UntrustedUUID(hex=envelope.run_id.hex)
    else:
        original = getattr(envelope, field)
        # Expiry appears ten minutes out when astimezone() lies, while
        # its underlying clock stores an additional three hours.
        disguised = original + timedelta(hours=3)
        changed = MisleadingDatetime(
            disguised.year, disguised.month, disguised.day, disguised.hour,
            disguised.minute, disguised.second, disguised.microsecond,
            tzinfo=disguised.tzinfo,
        )
    suspect = envelope.model_copy(update={field: changed})
    assert type(getattr(suspect, field)) is type(changed)
    with pytest.raises(CoworkerError) as error:
        # A copied model can serialize plausibly; it is never a grant.
        verified(suspect, now, reviewed_sha256=suspect.review_sha256())
    assert error.value.code == "code_proposal_invalid"


@pytest.mark.parametrize("field", ["document_id", "version_id"])
def test_review_rejects_subclassed_input_uuids_with_unchanged_document_identity(field):
    envelope, now = setup_envelope()
    original = envelope.input_versions[0]
    altered = original.model_copy(update={
        field: UntrustedUUID(hex=getattr(original, field).hex),
    })
    suspect = envelope.model_copy(update={"input_versions": (altered,)})
    with pytest.raises(CoworkerError) as error:
        verified(suspect, now, reviewed_sha256=suspect.review_sha256())
    assert error.value.code == "code_proposal_invalid"


def test_normal_datetime_and_uuids_remain_reviewable():
    envelope, now = setup_envelope()
    assert type(envelope.created_at) is datetime
    assert type(envelope.expires_at) is datetime
    assert type(envelope.run_id) is UUID
    assert all(type(item.document_id) is UUID and type(item.version_id) is UUID
               for item in envelope.input_versions)
    assert verified(envelope, now) is None


class AdversarialTimezone(tzinfo):
    def utcoffset(self, _datetime):
        return -timedelta(hours=3)

    def dst(self, _datetime):
        return timedelta(0)

    def tzname(self, _datetime):
        return "untrusted-offset"


class AdversarialInt(int):
    def __eq__(self, _other):
        return True


def test_self_hashed_proposal_with_custom_tzinfo_cannot_redefine_expiry_window():
    envelope, now = setup_envelope()
    # A legitimate timezone is handled by ZoneInfo, not arbitrary tzinfo
    # implementations whose utcoffset() can vary between hash and claim.
    suspect = envelope.model_copy(update={
        "created_at": envelope.created_at.replace(tzinfo=AdversarialTimezone()),
        "expires_at": envelope.expires_at.replace(tzinfo=AdversarialTimezone()),
    })
    assert type(suspect.created_at) is datetime
    assert type(suspect.expires_at) is datetime
    with pytest.raises(CoworkerError) as error:
        verified(suspect, now + timedelta(hours=3),
                 reviewed_sha256=suspect.review_sha256())
    assert error.value.code == "code_proposal_invalid"


@pytest.mark.parametrize("which", ["now_subclass", "now_custom_timezone"])
def test_review_clock_must_not_use_overridden_time_operations(which):
    envelope, now = setup_envelope()
    if which == "now_subclass":
        time = MisleadingDatetime(
            now.year, now.month, now.day, now.hour, now.minute,
            tzinfo=now.tzinfo,
        )
    else:
        time = now.replace(tzinfo=AdversarialTimezone())
    with pytest.raises(CoworkerError) as error:
        verified(envelope, time)
    assert error.value.code == "code_review_time_invalid"


@pytest.mark.parametrize("field", ["run_id", "document_id", "version_id"])
def test_review_rejects_uuid_with_subclassed_integer_payload_and_matching_digest(field):
    envelope, now = setup_envelope()
    if field == "run_id":
        # Different underlying run id; hostile integer claims to equal every
        # other run identity. The outer class is *exactly* UUID.
        disguised = UUID(int=uuid4().int)
        # UUID.__init__ counts None parameters using equality; create a
        # normal UUID before injecting the adversarial integer subclass.
        object.__setattr__(disguised, "int", AdversarialInt(uuid4().int))
        assert type(disguised) is UUID
        assert type(disguised.int) is AdversarialInt
        suspect = envelope.model_copy(update={"run_id": disguised})
    else:
        first = envelope.input_versions[0]
        disguised = UUID(int=uuid4().int)
        # UUID.__init__ counts None parameters using equality; create a
        # normal UUID before injecting the adversarial integer subclass.
        object.__setattr__(disguised, "int", AdversarialInt(uuid4().int))
        assert type(disguised) is UUID
        assert type(disguised.int) is AdversarialInt
        modified = first.model_copy(update={field: disguised})
        suspect = envelope.model_copy(update={"input_versions": (modified,)})
    with pytest.raises(CoworkerError) as error:
        verified(suspect, now, reviewed_sha256=suspect.review_sha256())
    assert error.value.code == "code_proposal_invalid"

def test_api_json_datetime_roundtrip_is_canonical_without_changing_review_hash():
    from pydantic_core import TzInfo

    envelope, now = setup_envelope()
    parsed = CodeProposalEnvelope.model_validate(envelope.model_dump(mode="json"))
    assert type(parsed.created_at.tzinfo) is TzInfo
    assert type(parsed.expires_at.tzinfo) is TzInfo

    normalized = canonicalize_transport_code_proposal(parsed)
    assert type(normalized.created_at.tzinfo) is timezone
    assert type(normalized.expires_at.tzinfo) is timezone
    assert normalized.review_sha256() == envelope.review_sha256()
    assert verified(normalized, now) is None


def test_transport_normalization_does_not_launder_forged_envelope_fields():
    envelope, now = setup_envelope()
    parsed = CodeProposalEnvelope.model_validate(envelope.model_dump(mode="json"))
    forged = parsed.model_copy(update={"unreviewed_approval": True})
    normalized = canonicalize_transport_code_proposal(forged)
    with pytest.raises(CoworkerError) as denied:
        verified(normalized, now, reviewed_sha256=envelope.review_sha256())
    assert denied.value.code == "code_proposal_invalid"



@pytest.mark.parametrize("source, valid", [
    ("print('safe inert draft')\n", True),
    ("print('unterminated'\n", False),
    ("print(1)\x00", False),
    ("x = 1\n" * 2000, False),
])
def test_deepseek_model_code_draft_rejects_malformed_bounded_source(source, valid):
    import asyncio
    import json
    import httpx
    from services.coworker.agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
    from services.coworker.config import Settings

    seen = []
    def provider(request):
        data = json.loads(request.content)
        seen.append(data)
        return httpx.Response(200, json={
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": json.dumps({"source": source})},
            }],
            "usage": {"total_tokens": 35},
        })
    planner = DeepSeekAgentPlanner(
        Settings(database_url="sqlite+pysqlite:///:memory:",
                 auth_issuer="https://identity.example.test/auth/v1",
                 deepseek_api_key="synthetic-unit-test-key"),
        transport=httpx.MockTransport(provider),
    )
    if valid:
        produced, tokens = asyncio.run(planner.propose_code("Write an inert greeting."))
        assert produced == source
        assert tokens == 35
    else:
        with pytest.raises(PlannerFailure) as exc:
            asyncio.run(planner.propose_code("Write a greeting."))
        assert exc.value.code == "invalid_code_proposal"
    assert len(seen) == 1
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert seen[0]["messages"][0]["role"] == "system"
    assert all("tool_calls" not in message for message in seen[0]["messages"])
