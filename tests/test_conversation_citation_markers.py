"""Day 3: malformed source-lookalike markers cannot piggyback on valid citations.

Synthetic owned TXT fixture only; no provider/network/AgentRun side effects.
"""
import asyncio

import pytest
from sqlalchemy import select

pytest.importorskip("temporalio")

from test_coworker import container
from test_conversation_replies import _attached_chat_source, setup
from services.coworker.conversation_grounding import check_grounded_citations
from services.coworker.conversation_replies import ConversationReplyService
from services.coworker.models import AgentRun, ConversationMessage


SOURCE_MAP = {"src-1": {"resource_type": "document_version", "resource_id": "redacted-version"}}


@pytest.mark.parametrize("unfinished", [
    "[[src_999",
    "[[src—999",
    "[[sRc:999",
    "[[ src _ 999",
])
def test_valid_citation_cannot_mask_malformed_unclosed_source_marker(unfinished):
    text = "The supported renewal is 17 March 2027. [[src-1]] " + unfinished
    with pytest.raises(ValueError, match="Malformed source citation"):
        check_grounded_citations(text, SOURCE_MAP)


def test_server_reply_allowlist_rejects_malformed_source_lookalike():
    reply = {"sources": [{"source_id": "src-1", "label": "redacted.txt", "resource_type": "document_version"}]}
    with pytest.raises(ValueError, match="Malformed source citation"):
        ConversationReplyService.validate_grounded_text(
            "Supported answer [[src-1]] but source [[src_999", reply,
        )


def test_grounded_stream_never_displays_or_stores_malformed_source_lookalike(container):
    data = setup(container, question="What is the renewal date?")
    service, _model, owner, conversation, message = data
    _attached_chat_source(container, data, b"Renewal date: 17 March 2027.")

    class ForgedStream:
        async def stream(self, _messages):
            yield "The renewal is 17 March 2027. [[src-1]]"
            yield " More proof [[src_999"

    service.model = ForgedStream()

    async def collect():
        claim, queue = await service.prepare_stream(owner, conversation["id"], message["id"], 1)
        return [event async for event in service.stream_events(claim, queue)]

    events = asyncio.run(collect())
    assert [event for event, _payload in events] == ["snapshot", "final"]
    assert events[-1][1]["state"] == "failed"
    assert events[-1][1]["text"] == ""
    stored = container.conversations.messages(owner, conversation["id"])["items"][0]["assistant_reply"]
    assert stored["state"] == "failed" and stored["text"] == ""
    with container.repository.sessions() as db:
        assert db.scalar(select(AgentRun)) is None
        assert db.get(ConversationMessage, message["id"]).assistant_reply["text"] == ""
