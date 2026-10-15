"""CW-10: stored code proposals are inert, exact, idempotent, and owner-bound."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import select

from test_coworker import account, container, signed_client
from test_sandbox_control_plane import enable_sandbox
from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.code_proposal_schemas import (
    CodeComputeLimits, CodeInputVersion, CodeProposalEnvelope,
)
from services.coworker.models import AgentCodeProposal, AgentRun, utcnow


def active_agent(container):
    enable_sandbox(container)
    settings = replace(container.settings, agent_sandbox_tool_enabled=True)
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.agent.settings = settings
    container.sandbox.settings = settings
    owner = account(container)
    run, created = container.agent.create(
        owner,
        AgentRunCreate(
            goal="Analyze a local CSV with exact isolated Python.",
            document_ids=[], action_ids=[], memory_namespaces=[], output_language="en",
        ),
        "code-run-" + str(uuid4()),
    )
    assert created and run["id"]
    return owner, run["id"]


def sample_proposal(owner, run_id, *, source="print('review only')\n", input_versions=()):
    now = utcnow()
    return CodeProposalEnvelope(
        owner_id=owner,
        run_id=UUID(run_id),
        source=source,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        input_versions=input_versions,
        limits=CodeComputeLimits(
            cpu_seconds=5, wall_seconds=15, memory_mb=128,
            disk_mb=32, stdout_bytes=1024,
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def prepare(client, headers, run_id, proposal, key="code-proposal-identity"):
    return client.post(
        f"/api/v1/agent-runs/{run_id}/code-proposals",
        headers={**headers(), "Idempotency-Key": key},
        json=proposal.model_dump(mode="json"),
    )


def test_owned_proposal_persists_without_granting_approval_or_execution(container, signed_client):
    owner, run_id = active_agent(container)
    proposal = sample_proposal(owner, run_id)
    client, headers = signed_client

    response = prepare(client, headers, run_id, proposal)
    assert response.status_code == 201, response.text
    value = response.json()
    assert value["state"] == "unreviewed"
    assert value["review_sha256"] == proposal.review_sha256()
    assert value["proposal"]["source"] == proposal.source
    assert value["code_executed"] is False
    assert value["approval_granted"] is False
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Idempotent-Replayed"] == "false"
    assert response.headers["Location"].endswith(f"/code-proposals/{value['id']}")

    with container.repository.sessions() as db:
        stored = db.get(AgentCodeProposal, value["id"])
        assert stored.owner_id == owner
        assert stored.run_id == run_id
        assert stored.snapshot["source"] == proposal.source
        assert stored.state == "unreviewed"

    fetched = client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{value['id']}",
        headers=headers(),
    )
    assert fetched.status_code == 200
    assert fetched.json() == value
    assert fetched.headers["Cache-Control"] == "no-store"


def test_code_proposal_idempotency_does_not_substitute_new_source(container, signed_client):
    owner, run_id = active_agent(container)
    proposal = sample_proposal(owner, run_id)
    client, headers = signed_client
    first = prepare(client, headers, run_id, proposal)
    assert first.status_code == 201
    replay = prepare(client, headers, run_id, proposal)
    assert replay.status_code == 201
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]

    changed = sample_proposal(owner, run_id, source="print('changed')\n")
    denied = prepare(client, headers, run_id, changed)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "idempotency_conflict"
    with container.repository.sessions() as db:
        rows = db.scalars(select(AgentCodeProposal).where(
            AgentCodeProposal.run_id == run_id,
        )).all()
        assert len(rows) == 1


def test_cross_owner_and_cross_run_proposals_never_expose_source(container, signed_client):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    envelope = sample_proposal(owner, run_id)
    created = prepare(client, headers, run_id, envelope)
    assert created.status_code == 201
    proposal_id = created.json()["id"]
    account(container, "bob")
    hidden = client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}",
        headers=headers("bob"),
    )
    assert hidden.status_code == 404

    forged = sample_proposal(account(container, "bob"), run_id)
    blocked = prepare(client, headers, run_id, forged, key="foreign-code-proposal")
    assert blocked.status_code == 404
    changed_run = prepare(client, headers, str(uuid4()), envelope, key="wrong-run-identity")
    assert changed_run.status_code == 404


def test_stored_code_tampering_and_source_scope_revocation_deny_reads(container, signed_client):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    created = prepare(client, headers, run_id, proposal)
    assert created.status_code == 201
    proposal_id = created.json()["id"]

    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        run.input_versions = [str(uuid4())]
    unavailable = client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}",
        headers=headers(),
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["error"]["code"] == "code_input_revoked"

    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        run.input_versions = []
        row = db.get(AgentCodeProposal, proposal_id)
        snapshot = dict(row.snapshot)
        snapshot["source"] = "print('forged')\n"
        row.snapshot = snapshot
    altered = client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}",
        headers=headers(),
    )
    assert altered.status_code == 409
    assert altered.json()["error"]["code"] == "code_proposal_invalid"

    replay = prepare(client, headers, run_id, proposal)
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "code_proposal_invalid"


def test_expired_input_and_closed_run_rejected_without_persistence(container, signed_client):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    expired = proposal.model_copy(update={
        "created_at": utcnow() - timedelta(minutes=4),
        "expires_at": utcnow() - timedelta(minutes=1),
    })
    denied = prepare(client, headers, run_id, expired, key="expired-proposal-key")
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "code_proposal_expired"

    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        run.cancel_requested = True
        run.state = "cancelled"
    closed = prepare(client, headers, run_id, proposal, key="closed-proposal-key")
    assert closed.status_code == 409
    assert closed.json()["error"]["code"] == "code_run_closed"
    with container.repository.sessions() as db:
        assert not db.scalars(select(AgentCodeProposal).where(
            AgentCodeProposal.run_id == run_id,
        )).all()


def test_proposal_must_bind_exact_run_input_versions(container, signed_client):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    ref = CodeInputVersion(
        owner_id=owner, document_id=uuid4(), version_id=uuid4(),
        source_sha256="a" * 64,
    )
    request = sample_proposal(owner, run_id, input_versions=(ref,))
    denied = prepare(client, headers, run_id, request, key="unselected-input-code")
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "code_input_revoked"

@pytest.mark.parametrize("unbound_field", [
    "memory_namespaces", "connector_read_grant_ids",
    "connector_snapshot_ids", "action_ids",
])
def test_unbound_private_context_cannot_be_silently_reviewed_as_code(
    container, signed_client, unbound_field,
):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        setattr(run, unbound_field, ["unreviewed-private-reference"])
    response = prepare(
        client, headers, run_id, sample_proposal(owner, run_id),
        key="unbound-context-" + unbound_field,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "code_context_unbound"
    with container.repository.sessions() as db:
        assert not db.scalars(select(AgentCodeProposal).where(
            AgentCodeProposal.run_id == run_id,
        )).all()

def test_actual_document_version_binding_rejects_deleted_source_on_read(
    container, signed_client,
):
    from services.coworker.schemas import UploadRequest
    from services.coworker.models import Document

    owner, run_id = active_agent(container)
    upload = container.repository.create_upload(
        owner, UploadRequest(filename="source.txt", byte_size=5, sha256="a" * 64),
    )
    container.repository.finish_upload(owner, upload["id"])
    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        run.input_versions = [upload["version_id"]]

    ref = CodeInputVersion(
        owner_id=owner, document_id=UUID(upload["id"]),
        version_id=UUID(upload["version_id"]), source_sha256="a" * 64,
    )
    client, headers = signed_client
    prepared = prepare(
        client, headers, run_id, sample_proposal(owner, run_id, input_versions=(ref,)),
        key="bound-upload-review-key",
    )
    assert prepared.status_code == 201, prepared.text
    proposal_id = prepared.json()["id"]
    assert client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}",
        headers=headers(),
    ).status_code == 200

    with container.repository.sessions.begin() as db:
        db.get(Document, upload["id"]).deleted = True

    denied = client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}",
        headers=headers(),
    )
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "code_input_revoked"

def test_review_proposal_snapshots_are_bounded_per_run(container, signed_client):
    owner, run_id = active_agent(container)
    proposal = sample_proposal(owner, run_id)
    client, headers = signed_client
    for i in range(8):
        response = prepare(
            client, headers, run_id, proposal, key=f"bounded-proposal-{i:02d}",
        )
        assert response.status_code == 201, response.text
    exceeded = prepare(
        client, headers, run_id, proposal, key="bounded-proposal-over-limit",
    )
    assert exceeded.status_code == 429
    assert exceeded.json()["error"]["code"] == "code_proposal_limit"
    with container.repository.sessions() as db:
        assert len(db.scalars(select(AgentCodeProposal).where(
            AgentCodeProposal.run_id == run_id,
        )).all()) == 8


def conversation_proposal(container):
    """Admit a real selected-source conversation through the normal dispatcher."""
    from services.coworker.conversation_schemas import ConversationCreate, MessageCreate
    from services.coworker.schemas import UploadRequest

    owner, _ = active_agent(container)
    settings = replace(container.settings, conversations_enabled=True, work_services_enabled=True)
    container.conversations.settings = settings
    container.conversation_dispatch.settings = settings
    upload = container.repository.create_upload(
        owner, UploadRequest(filename="selected.txt", byte_size=5, sha256="a" * 64),
    )
    container.repository.finish_upload(owner, upload["id"])
    conversation, _ = container.conversations.create(
        owner, ConversationCreate(title="Reviewed analysis"), "proposal-conversation",
    )
    message, _ = container.conversations.append_message(
        owner, conversation["id"], MessageCreate(
            text="Create a detailed report about the selected document",
            client_request_key="proposal-message",
            selected_resource_ids=[UUID(upload["version_id"])],
        ),
    )
    admitted, _ = container.conversation_dispatch.dispatch(
        owner, conversation["id"], message["id"], expected_sequence=1,
    )
    ref = CodeInputVersion(
        owner_id=owner, document_id=UUID(upload["id"]),
        version_id=UUID(upload["version_id"]), source_sha256="a" * 64,
    )
    proposal = sample_proposal(owner, admitted["run_id"], input_versions=(ref,))
    return proposal, conversation["id"], message["id"], upload["version_id"]


@pytest.mark.parametrize("operation", ["create", "replay", "read"])
@pytest.mark.parametrize("change", [
    "version", "conversation_deleted", "message_unlinked", "message_owner", "message_selection",
])
def test_code_proposal_rechecks_original_conversation_scope(
    container, signed_client, operation, change,
):
    """Skipping admitted pins must never expose or retain code under stale scope."""
    from services.coworker.models import Conversation, ConversationMessage, DocumentVersion

    proposal, conversation_id, message_id, version_id = conversation_proposal(container)
    client, headers = signed_client
    run_id = str(proposal.run_id)
    first = prepare(client, headers, run_id, proposal)
    assert first.status_code == 201, first.text
    proposal_id = first.json()["id"]
    path = f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}"
    assert client.get(path, headers=headers()).status_code == 200

    if change == "message_owner":
        from services.coworker.conversation_schemas import ConversationCreate
        other = account(container, "bob")
        foreign_conversation, _ = container.conversations.create(
            other, ConversationCreate(title="Other workspace"), "foreign-proposal-conversation",
        )
    with container.repository.sessions.begin() as db:
        message = db.get(ConversationMessage, message_id)
        if change == "version":
            db.get(DocumentVersion, version_id).version += 1
        elif change == "conversation_deleted":
            db.get(Conversation, conversation_id).deleted = True
        elif change == "message_unlinked":
            message.resource_links = []
        elif change == "message_owner":
            message.owner_id = other
            message.conversation_id = foreign_conversation["id"]
        else:
            message.selected_sources = []

    if operation == "read":
        denied = client.get(path, headers=headers())
    else:
        key = "new-stale-scope-proposal" if operation == "create" else "code-proposal-identity"
        denied = prepare(client, headers, run_id, proposal, key=key)
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "context_sources_changed"
    assert proposal.source not in denied.text
    with container.repository.sessions() as db:
        rows = db.scalars(select(AgentCodeProposal).where(AgentCodeProposal.run_id == run_id)).all()
        assert len(rows) == 1
        assert rows[0].state == "unreviewed"


def test_new_proposal_cannot_adopt_substituted_conversation_source_digest(container, signed_client):
    """Current DB hashes cannot replace the document digest pinned at admission."""
    from services.coworker.models import DocumentVersion

    proposal, _, _, version_id = conversation_proposal(container)
    with container.repository.sessions.begin() as db:
        db.get(DocumentVersion, version_id).sha256 = "b" * 64
    replacement_ref = proposal.input_versions[0].model_copy(update={"source_sha256": "b" * 64})
    replacement = proposal.model_copy(update={"input_versions": (replacement_ref,)})
    client, headers = signed_client
    denied = prepare(client, headers, str(proposal.run_id), replacement)
    assert denied.status_code == 409, denied.text
    assert denied.json()["error"]["code"] == "context_sources_changed"
    with container.repository.sessions() as db:
        assert not db.scalars(select(AgentCodeProposal).where(
            AgentCodeProposal.run_id == str(proposal.run_id),
        )).all()
