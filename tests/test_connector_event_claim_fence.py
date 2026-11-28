from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from test_coworker import account, container
from test_connector_reads import (
    AllowPush, _one_gmail_event, connect_read, create_grant, enable_reads,
)
from services.coworker.models import ConnectorEvent, utcnow


def _reclaim(container, event):
    with container.repository.sessions.begin() as db:
        row = db.get(ConnectorEvent, event["id"])
        row.claim_until = utcnow() - timedelta(seconds=1)
    claimed = container.connector_reads.repo.claim_events()
    assert len(claimed) == 1
    assert claimed[0]["id"] == event["id"]
    assert claimed[0]["attempts"] == event["attempts"] + 1
    return claimed[0]


@pytest.mark.parametrize("boundary", ["sync_success", "sync_error", "consumer_success", "consumer_error"])
def test_reclaimed_event_attempt_cannot_mutate_new_claim(container, monkeypatch, boundary):
    enable_reads(container)
    service = container.connector_reads
    service.push_verifier = AllowPush()
    owner = account(container)
    grant = create_grant(container, owner, connect_read(container, owner))
    asyncio.run(service.subscribe(owner, grant["id"]))
    first = _one_gmail_event(container, "event-claim-fence")
    admitted = []

    async def sync(*args, **kwargs):
        if boundary.startswith("sync"):
            _reclaim(container, first)
            if boundary == "sync_error":
                raise RuntimeError("synthetic stale worker failure")
        return {"snapshot_ids": []}

    def consume(event):
        admitted.append(event["attempts"])
        if boundary.startswith("consumer"):
            _reclaim(container, first)
            if boundary == "consumer_error":
                raise RuntimeError("synthetic stale consumer failure")

    monkeypatch.setattr(service, "sync", sync)
    service.set_automation_consumer(consume)
    service.set_event_consumer(None)
    asyncio.run(service.process_event(first))

    with container.repository.sessions() as db:
        row = db.get(ConnectorEvent, first["id"])
        assert row.state == "processing"
        assert row.attempts == 2
        assert row.claim_until is not None
        assert row.processed_at is None
        assert row.last_error_code is None
    assert admitted == ([1] if boundary.startswith("consumer") else [])
