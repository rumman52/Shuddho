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
from services.coworker.models import AgentCodeProposal, AgentCodeReview, AgentRun, SandboxExecution, utcnow


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




def test_exact_owner_revocation_erases_code_and_remains_idempotent(
    container, signed_client,
):
    """Reviewing a code hash permits revocation, not running Python."""
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    saved = prepare(client, headers, run_id, proposal, key="revocable-code-key")
    assert saved.status_code == 201, saved.text
    row_id = saved.json()["id"]
    path = f"/api/v1/agent-runs/{run_id}/code-proposals/{row_id}"
    revoke = path + "/revoke"
    payload = {"review_sha256": proposal.review_sha256()}

    mismatch = client.post(
        revoke, headers=headers(), json={"review_sha256": "b" * 64},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "code_proposal_changed"

    foreign = account(container, "bob")
    assert foreign != owner
    inaccessible = client.post(revoke, headers=headers("bob"), json=payload)
    assert inaccessible.status_code == 404
    assert client.post(
        f"/api/v1/agent-runs/{uuid4()}/code-proposals/{row_id}/revoke",
        headers=headers(), json=payload,
    ).status_code == 404

    first = client.post(revoke, headers=headers(), json=payload)
    assert first.status_code == 200, first.text
    assert first.headers["Cache-Control"] == "no-store"
    assert first.json()["state"] == "revoked"
    assert first.json()["source_erased"] is True
    assert first.json()["approval_granted"] is False
    assert first.json()["code_executed"] is False
    assert "proposal" not in first.json()
    assert proposal.source not in first.text

    again = client.post(revoke, headers=headers(), json=payload)
    assert again.status_code == 200
    assert again.json() == first.json()
    denied = client.get(path, headers=headers())
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "code_proposal_revoked"
    replay = prepare(client, headers, run_id, proposal, key="revocable-code-key")
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "code_proposal_revoked"
    with container.repository.sessions() as db:
        row = db.get(AgentCodeProposal, row_id)
        assert row.snapshot == {}
        assert row.state == "revoked"
        assert row.review_sha256 == proposal.review_sha256()


def test_revocation_also_works_after_agent_run_cancellation(
    container, signed_client,
):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    saved = prepare(client, headers, run_id, proposal)
    assert saved.status_code == 201
    row_id = saved.json()["id"]
    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        run.state = "cancelled"
        run.cancel_requested = True

    revoked = client.post(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{row_id}/revoke",
        headers=headers(), json={"review_sha256": proposal.review_sha256()},
    )
    assert revoked.status_code == 200
    with container.repository.sessions() as db:
        assert db.get(AgentCodeProposal, row_id).snapshot == {}


def test_expired_code_snapshots_are_scrubbed_by_repeatable_maintenance(
    container, signed_client,
):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    saved = prepare(client, headers, run_id, proposal)
    assert saved.status_code == 201
    row_id = saved.json()["id"]
    with container.repository.sessions.begin() as db:
        db.get(AgentCodeProposal, row_id).expires_at = utcnow() - timedelta(seconds=1)

    assert container.retention.cleanup_expired_code_proposals() == {"expired": 1}
    assert container.retention.cleanup_expired_code_proposals() == {"expired": 0}
    assert client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{row_id}",
        headers=headers(),
    ).json()["error"]["code"] == "code_proposal_expired"
    with container.repository.sessions() as db:
        row = db.get(AgentCodeProposal, row_id)
        assert row.state == "expired"
        assert row.snapshot == {}
        assert row.review_sha256 == proposal.review_sha256()


def test_account_erasure_removes_owned_code_proposal_before_parent_run(
    container, signed_client,
):
    from services.coworker.models import Account

    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    saved = prepare(client, headers, run_id, proposal)
    assert saved.status_code == 201, saved.text
    proposal_id = saved.json()["id"]
    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        run.state = "cancelled"
        run.cancel_requested = True

    result = container.retention.erase_account(owner)
    assert result["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.get(AgentCodeProposal, proposal_id) is None
        assert db.get(AgentRun, run_id) is None
        assert db.get(Account, owner) is None

def human_review(client, headers, run_id, proposal_id, digest, *,
                 decision="approve", expires_at=None):
    return client.post(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}/review",
        headers=headers(),
        json={
            "review_sha256": digest,
            "decision": decision,
            "expires_at": (expires_at or utcnow() + timedelta(seconds=90)).isoformat(),
        },
    )


def test_human_review_records_exact_owned_decision_without_worker_grant(
    container, signed_client,
):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    saved = prepare(client, headers, run_id, proposal)
    assert saved.status_code == 201, saved.text
    proposal_id = saved.json()["id"]
    expiration = utcnow() + timedelta(seconds=90)
    first = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
        expires_at=expiration,
    )
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["decision"] == "approve"
    assert result["review_sha256"] == proposal.review_sha256()
    assert result["execution_authorized"] is False
    assert result["code_executed"] is False
    assert first.headers["Cache-Control"] == "no-store"

    replay = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
        expires_at=expiration,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == result

    visible = client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}",
        headers=headers(),
    )
    assert visible.status_code == 200, visible.text
    assert visible.json()["human_review"]["decision"] == "approve"
    assert visible.json()["approval_granted"] is False
    assert visible.json()["code_executed"] is False
    with container.repository.sessions() as db:
        review = db.get(AgentCodeReview, proposal_id)
        assert review.owner_id == owner
        assert review.run_id == run_id
        assert review.decision == "approve"
        assert review.revoked_at is None
        assert db.get(AgentCodeProposal, proposal_id).state == "unreviewed"
        assert not db.scalars(select(SandboxExecution).where(
            SandboxExecution.owner_id == owner,
        )).all()


def test_human_review_rejects_cross_owner_changed_identity_and_stale_run(
    container, signed_client,
):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    created = prepare(client, headers, run_id, proposal)
    assert created.status_code == 201
    proposal_id = created.json()["id"]
    path = f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}/review"
    valid = {
        "review_sha256": proposal.review_sha256(),
        "decision": "approve",
        "expires_at": (utcnow() + timedelta(seconds=60)).isoformat(),
    }
    account(container, "bob")
    assert client.post(path, headers=headers("bob"), json=valid).status_code == 404
    assert client.post(
        f"/api/v1/agent-runs/{uuid4()}/code-proposals/{proposal_id}/review",
        headers=headers(), json=valid,
    ).status_code == 404
    wrong = client.post(
        path, headers=headers(), json={**valid, "review_sha256": "c" * 64},
    )
    assert wrong.status_code == 409
    assert wrong.json()["error"]["code"] == "code_proposal_changed"

    long_lived = client.post(
        path, headers=headers(),
        json={**valid, "expires_at": (utcnow() + timedelta(minutes=11)).isoformat()},
    )
    assert long_lived.status_code == 409
    assert long_lived.json()["error"]["code"] == "code_review_expiry"

    with container.repository.sessions.begin() as db:
        run = db.get(AgentRun, run_id)
        run.cancel_requested = True
        run.state = "cancelled"
    rejected = client.post(path, headers=headers(), json=valid)
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "code_run_closed"
    with container.repository.sessions() as db:
        assert db.get(AgentCodeReview, proposal_id) is None


def test_human_approval_is_immutable_and_revocation_clears_it(
    container, signed_client,
):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    created = prepare(client, headers, run_id, proposal)
    assert created.status_code == 201
    proposal_id = created.json()["id"]
    expiry = utcnow() + timedelta(seconds=75)
    first = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
        expires_at=expiry,
    )
    assert first.status_code == 200, first.text
    changed = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
        decision="reject", expires_at=expiry,
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "code_review_conflict"

    revoked = client.post(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}/revoke",
        headers=headers(), json={"review_sha256": proposal.review_sha256()},
    )
    assert revoked.status_code == 200, revoked.text
    after_revoke = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
        expires_at=expiry,
    )
    assert after_revoke.status_code == 409
    assert after_revoke.json()["error"]["code"] == "code_review_closed"
    with container.repository.sessions() as db:
        assert db.get(AgentCodeReview, proposal_id).revoked_at is not None
        assert db.get(AgentCodeProposal, proposal_id).snapshot == {}


def test_explicit_human_rejection_revokes_source_and_does_not_grant_execution(
    container, signed_client,
):
    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    created = prepare(client, headers, run_id, proposal)
    assert created.status_code == 201
    proposal_id = created.json()["id"]
    expiry = utcnow() + timedelta(seconds=45)
    rejected = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
        decision="reject", expires_at=expiry,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["decision"] == "reject"
    assert rejected.json()["execution_authorized"] is False
    assert "source" not in rejected.text

    repeated = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
        decision="reject", expires_at=expiry,
    )
    assert repeated.status_code == 200
    assert repeated.json() == rejected.json()
    unavailable = client.get(
        f"/api/v1/agent-runs/{run_id}/code-proposals/{proposal_id}",
        headers=headers(),
    )
    assert unavailable.status_code == 409
    with container.repository.sessions() as db:
        row = db.get(AgentCodeProposal, proposal_id)
        review = db.get(AgentCodeReview, proposal_id)
        assert row.state == "revoked" and row.snapshot == {}
        assert review.decision == "reject"
        assert review.revoked_at is not None


def test_account_erasure_removes_exact_human_review_before_parent_proposal(
    container, signed_client,
):
    from services.coworker.models import Account

    owner, run_id = active_agent(container)
    client, headers = signed_client
    proposal = sample_proposal(owner, run_id)
    created = prepare(client, headers, run_id, proposal)
    assert created.status_code == 201
    proposal_id = created.json()["id"]
    approved = human_review(
        client, headers, run_id, proposal_id, proposal.review_sha256(),
    )
    assert approved.status_code == 200, approved.text
    with container.repository.sessions.begin() as db:
        db.get(AgentRun, run_id).state = "cancelled"
    erased = container.retention.erase_account(owner)
    assert erased["database_erased"] is True
    with container.repository.sessions() as db:
        assert db.get(AgentCodeReview, proposal_id) is None
        assert db.get(AgentCodeProposal, proposal_id) is None
        assert db.get(AgentRun, run_id) is None
        assert db.get(Account, owner) is None
