"""Reviewed Agent admission: editing a proposed objective cannot reuse stale approval.

The browser fixture already exercises three admitted, independently steerable runs.
This focused regression keeps the digest transition explicit without model calls.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("temporalio")

from sqlalchemy import func, select
from test_conversation_reviewed_briefs import append, brief, setup
from services.coworker.errors import CoworkerError
from services.coworker.models import AgentRun, AgentOutbox


def test_edited_objective_requires_fresh_preview_before_single_admission(container):
    owner, conversation, messages, service, dispatch = setup(container, "objective-review")
    item = append(messages, owner, conversation, "Prepare a quarterly sales report.", "one")
    original = brief()
    old_preview = service.validate(
        owner, conversation["id"], item["id"], expected_sequence=1, brief=original)
    edited = original.model_copy(update={"objective": "Prepare a revised quarterly sales report"})
    new_preview = service.validate(
        owner, conversation["id"], item["id"], expected_sequence=1, brief=edited)
    assert new_preview["canonical_digest"] != old_preview["canonical_digest"]

    # A stale digest cannot authorize execution, regardless of the objective.
    with pytest.raises(CoworkerError):
        dispatch.dispatch(
            owner, conversation["id"], item["id"], expected_sequence=1,
            output_language="en-GB", reviewed_brief=edited,
            expected_digest=old_preview["canonical_digest"])
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 0
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 0

    # Re-preview plus explicit confirmation admits one run and one outbox row.
    result, created = dispatch.dispatch(
        owner, conversation["id"], item["id"], expected_sequence=1,
        output_language="en-GB", reviewed_brief=edited,
        expected_digest=new_preview["canonical_digest"])
    assert created and result["run_id"]
    replay, created = dispatch.dispatch(
        owner, conversation["id"], item["id"], expected_sequence=1,
        output_language="en-GB", reviewed_brief=edited,
        expected_digest=new_preview["canonical_digest"])
    assert not created and replay["run_id"] == result["run_id"]
    with dispatch.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AgentRun)) == 1
        assert db.scalar(select(func.count()).select_from(AgentOutbox)) == 1
