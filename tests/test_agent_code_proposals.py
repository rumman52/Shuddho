"""CW-10 inert-envelope tests. None of these authorize or run generated code."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from services.coworker.code_proposal_schemas import (
    CodeComputeLimits,
    CodeInputVersion,
    CodeProposalEnvelope,
    verify_reviewed_code_identity,
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
