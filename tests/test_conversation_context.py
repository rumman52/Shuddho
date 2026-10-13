"""CW-08 context-selection regression tests: synthetic DB, no provider side effects."""
from datetime import timedelta
from uuid import uuid4

import pytest

# Lightweight CI does not install coworker extras; mandatory coworker CI does.
pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from services.coworker.conversation_context import revalidate_selected_sources, require_current_selected_sources
from services.coworker.errors import CoworkerError
from services.coworker.models import Account, Artifact, Base, Document, DocumentVersion, Workspace, utcnow


def new_id():
    return str(uuid4())


@pytest.fixture
def records():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        alice, bob, workspace, doc_id, version_id, artifact_id = [new_id() for _ in range(6)]
        for owner in (alice, bob):
            db.add(Account(id=owner, issuer="https://issuer.example", subject=owner))
        db.flush()
        db.add(Workspace(id=workspace, owner_id=alice, name="Workspace"))
        db.add(Document(id=doc_id, owner_id=alice, workspace_id=workspace, filename="document.txt", deleted=False))
        db.add(DocumentVersion(
            id=version_id, document_id=doc_id, owner_id=alice, version=1,
            kind="txt", byte_size=10, sha256="a" * 64, object_key="private/object",
            state="uploaded", expires_at=utcnow() + timedelta(days=1),
        ))
        db.add(Artifact(
            id=artifact_id, owner_id=alice, filename="output.txt", content_type="text/plain",
            object_key="private/output", sha256="b" * 64, byte_size=10,
            expires_at=utcnow() + timedelta(days=1),
        ))
        db.commit()
        yield db, alice, bob, doc_id, version_id, artifact_id
    engine.dispose()


def doc_pin(doc_id, version_id):
    return {
        "resource_type": "document_version", "resource_id": version_id,
        "document_id": doc_id, "version": 1,
        "sha256": "a" * 64, "trust": "untrusted_source",
    }


def artifact_pin(artifact_id):
    return {"resource_type": "artifact", "resource_id": artifact_id, "sha256": "b" * 64}


def test_owned_exact_references_are_resolved_without_private_content(records):
    db, owner, _, doc_id, version_id, artifact_id = records
    result = require_current_selected_sources(db, owner, [doc_pin(doc_id, version_id), artifact_pin(artifact_id)])
    assert len(result) == 2
    assert all(item["trust"] == "untrusted_source" for item in result)
    assert all("object_key" not in item and "text" not in item for item in result)


def test_cross_owner_selection_not_usable(records):
    db, _, other, doc_id, version_id, artifact_id = records
    result = revalidate_selected_sources(db, other, [doc_pin(doc_id, version_id), artifact_pin(artifact_id)])
    assert result["active"] == []
    assert len(result["invalidated"]) == 2
    with pytest.raises(CoworkerError) as failure:
        require_current_selected_sources(db, other, [doc_pin(doc_id, version_id)])
    assert failure.value.code == "context_sources_changed"


def test_changed_hash_or_version_is_invalidated(records):
    db, owner, _, doc_id, version_id, _ = records
    result = revalidate_selected_sources(db, owner, [
        doc_pin(doc_id, version_id) | {"sha256": "c" * 64},
        doc_pin(doc_id, version_id) | {"version": 2},
    ])
    assert result["active"] == []
    assert len(result["invalidated"]) == 2


def test_deleted_or_nonuploaded_document_is_invalidated(records):
    db, owner, _, doc_id, version_id, _ = records
    document = db.get(Document, doc_id)
    document.deleted = True
    db.flush()
    assert revalidate_selected_sources(db, owner, [doc_pin(doc_id, version_id)])["invalidated"]
    document.deleted = False
    db.get(DocumentVersion, version_id).state = "awaiting_upload"
    db.flush()
    assert revalidate_selected_sources(db, owner, [doc_pin(doc_id, version_id)])["invalidated"]


def test_expired_artifact_and_document_version_rejected(records):
    db, owner, _, doc_id, version_id, artifact_id = records
    db.get(Artifact, artifact_id).expires_at = utcnow() - timedelta(seconds=1)
    db.get(DocumentVersion, version_id).expires_at = utcnow() - timedelta(seconds=1)
    db.flush()
    assert not revalidate_selected_sources(db, owner, [
        doc_pin(doc_id, version_id), artifact_pin(artifact_id),
    ])["active"]


def test_malformed_duplicate_and_oversized_selections_fail_closed(records):
    db, owner, _, doc_id, version_id, _ = records
    duplicate = [doc_pin(doc_id, version_id)] * 2
    result = revalidate_selected_sources(db, owner, duplicate)
    assert len(result["active"]) == 1
    assert len(result["invalidated"]) == 1
    for invalid in (["raw"], [None], [
        {"resource_type": "document_version", "resource_id": version_id, "sha256": "a" * 64},
    ], [{"resource_type": "artifact", "resource_id": "x", "sha256": "NOT_SHA"}]):
        assert revalidate_selected_sources(db, owner, invalid)["invalidated"]
    with pytest.raises(CoworkerError):
        revalidate_selected_sources(db, owner, duplicate * 6)


def test_empty_selection_safe_but_creates_no_authority(records):
    db, owner, *_ = records
    assert require_current_selected_sources(db, owner, []) == []


def test_workspace_manifest_tracks_source_changes_without_exposing_object_keys(records):
    """Revision digest follows authoritative records; it grants no file read."""
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    from services.coworker.workspace_manifest import WorkspaceManifestService

    db, owner, other, doc_id, version_id, artifact_id = records
    sessions = sessionmaker(bind=db.bind)
    service = WorkspaceManifestService(sessions, SimpleNamespace(
        conversations_enabled=True, agent_memory_enabled=False,
    ))
    first = service.get(owner)
    assert first["schema_version"] == 1
    assert len(first["revision_sha256"]) == 64
    assert first["documents"][0]["version_id"] == version_id
    assert first["artifacts"][0]["artifact_id"] == artifact_id
    assert first["memory"] == []
    assert first["truncated"] == {"documents": False, "artifacts": False, "memory": False}
    assert service.get(owner) == first
    assert "private/object" not in str(first) and "private/output" not in str(first)

    db.get(DocumentVersion, version_id).expires_at = utcnow() - timedelta(seconds=5)
    db.commit()
    changed = service.get(owner)
    assert changed["revision_sha256"] != first["revision_sha256"]
    assert changed["documents"][0]["available"] is False

    db.get(Document, doc_id).deleted = True
    db.commit()
    removed = service.get(owner)
    assert removed["documents"] == []
    assert removed["revision_sha256"] != changed["revision_sha256"]
    with pytest.raises(CoworkerError):
        service.get(other)


def test_runtime_context_invalidates_expired_document_after_admission(records):
    """CW-08 expiry must be enforced at worker-time read, not just task admission."""
    from types import SimpleNamespace
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from services.coworker.context import ContextService
    from services.coworker.models import AgentRun

    db, owner, _, doc_id, version_id, _ = records
    workspace_id = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
    run_id = new_id()
    db.add(AgentRun(
        id=run_id, owner_id=owner, workspace_id=workspace_id,
        idempotency_key="ctx-expiry-case", fingerprint="c" * 64,
        goal="Create a report about the selected document",
        output_language="en", input_versions=[version_id],
        action_ids=[], memory_namespaces=[], connector_read_grant_ids=[],
        connector_snapshot_ids=[], tool_allowlist=[],
        deadline_at=utcnow() + timedelta(minutes=20),
    ))
    db.commit()
    service = ContextService(sessionmaker(bind=db.bind), SimpleNamespace(), None, None)
    _, sources = service._run_and_sources(owner, run_id)
    assert len(sources) == 1 and sources[0]["state"] == "active"
    assert service._source_current(owner, sources[0])

    db.get(DocumentVersion, version_id).expires_at = utcnow() - timedelta(seconds=5)
    db.commit()
    _, expired = service._run_and_sources(owner, run_id)
    assert expired[0]["state"] == "invalidated"
    assert expired[0]["reason"] == "expired"
    assert not service._source_current(owner, sources[0])

    db.get(DocumentVersion, version_id).expires_at = utcnow() + timedelta(days=1)
    db.get(DocumentVersion, version_id).sha256 = "d" * 64
    db.commit()
    assert not service._source_current(owner, sources[0])


def _conversation_context_run(records, *, selected=True):
    """A real owner-scoped conversation message bound to its persisted run identity."""
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from types import SimpleNamespace

    from services.coworker.context import ContextService
    from services.coworker.models import AgentRun, Conversation, ConversationMessage

    db, owner, _, doc_id, version_id, _ = records
    workspace_id = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
    conversation_id, message_id, run_id = new_id(), new_id(), new_id()
    db.add(Conversation(
        id=conversation_id, owner_id=owner, idempotency_key="cw08-conv-" + conversation_id,
        fingerprint="a" * 64, title="Pinned document", message_sequence=1,
    ))
    db.add(AgentRun(
        id=run_id, owner_id=owner, workspace_id=workspace_id,
        idempotency_key="conversation:" + message_id, fingerprint="c" * 64,
        goal="Create a report about the selected document",
        output_language="en", input_versions=[version_id] if selected else [],
        action_ids=[], memory_namespaces=[], connector_read_grant_ids=[],
        connector_snapshot_ids=[], tool_allowlist=[],
        deadline_at=utcnow() + timedelta(minutes=20),
    ))
    db.add(ConversationMessage(
        id=message_id, conversation_id=conversation_id, owner_id=owner,
        client_request_key="cw08-message-key", fingerprint="b" * 64,
        sequence=1, text="Create a report about the selected document",
        selected_sources=[doc_pin(doc_id, version_id)] if selected else [],
        resource_links=[{"resource_type": "agent_run", "resource_id": run_id}],
    ))
    db.commit()
    service = ContextService(sessionmaker(bind=db.bind), SimpleNamespace(), None, None)
    return service, owner, run_id, message_id, version_id, doc_id


@pytest.mark.parametrize("changed_field", ["sha256", "version", "deleted", "expired"])
def test_worker_context_rechecks_exact_admitted_conversation_pin(records, changed_field):
    """All Agent runtime versions must reject substituted conversation source bytes."""
    from types import SimpleNamespace
    from services.coworker.agent_repository import AgentRepository

    service, owner, run_id, _, version_id, doc_id = _conversation_context_run(records)
    db = records[0]
    repository = AgentRepository(service.sessions, SimpleNamespace())
    _, sources = service._run_and_sources(owner, run_id)
    assert len(sources) == 1 and sources[0]["state"] == "active"
    assert repository.worker_run(run_id)["document_ids"] == [doc_id]

    version = db.get(DocumentVersion, version_id)
    if changed_field == "sha256":
        version.sha256 = "f" * 64
    elif changed_field == "version":
        version.version = 2
    elif changed_field == "deleted":
        db.get(Document, doc_id).deleted = True
    else:
        version.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    with pytest.raises(CoworkerError) as failure:
        service._run_and_sources(owner, run_id)
    assert failure.value.code == "context_sources_changed"
    # Runtime v1/v2 may bypass planner context; their worker entry must deny too.
    with pytest.raises(CoworkerError) as worker_failure:
        repository.worker_run(run_id)
    assert worker_failure.value.code == "context_sources_changed"


def test_worker_context_requires_original_owned_message_and_exact_run_link(records):
    from services.coworker.models import AgentRun, Conversation, ConversationMessage

    service, owner, run_id, message_id, version_id, _ = _conversation_context_run(records)
    db = records[0]
    message = db.get(ConversationMessage, message_id)
    message.resource_links = []
    db.commit()
    with pytest.raises(CoworkerError) as unlinked:
        service._run_and_sources(owner, run_id)
    assert unlinked.value.code == "context_sources_changed"

    message.resource_links = [{"resource_type": "agent_run", "resource_id": run_id}]
    db.get(AgentRun, run_id).input_versions = []
    db.commit()
    with pytest.raises(CoworkerError) as changed:
        service._run_and_sources(owner, run_id)
    assert changed.value.code == "context_sources_changed"

    db.get(AgentRun, run_id).input_versions = [version_id]
    db.get(Conversation, message.conversation_id).deleted = True
    db.commit()
    with pytest.raises(CoworkerError) as deleted:
        service._run_and_sources(owner, run_id)
    assert deleted.value.code == "context_sources_changed"


def test_worker_context_accepts_conversation_without_attached_sources(records):
    service, owner, run_id, _, _, _ = _conversation_context_run(records, selected=False)
    run, sources = service._run_and_sources(owner, run_id)
    assert run.id == run_id and sources == []


def test_manifest_stays_disabled_without_conversations(records):
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    from services.coworker.workspace_manifest import WorkspaceManifestService
    db, owner, *_ = records
    service = WorkspaceManifestService(sessionmaker(bind=db.bind), SimpleNamespace(
        conversations_enabled=False, agent_memory_enabled=False,
    ))
    with pytest.raises(CoworkerError) as failure:
        service.get(owner)
    assert failure.value.code == "conversations_unavailable"


def test_memory_review_edit_rejects_stale_version_and_can_delete(records):
    from types import SimpleNamespace
    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker
    from services.coworker.memory_repository import MemoryRepository
    from services.coworker.memory_schemas import MemoryFactUpdate
    from services.coworker.models import MemoryFact

    db, owner, *_ = records
    workspace_id = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
    fact_id = new_id()
    db.add(MemoryFact(
        id=fact_id, owner_id=owner, workspace_id=workspace_id,
        namespace="project", key="review-key", value="Old scoped fact",
        language="en", provenance_type="user", version=1,
    ))
    db.commit()
    repository = MemoryRepository(sessionmaker(bind=db.bind), SimpleNamespace(agent_memory_enabled=True))
    updated = repository.update(owner, fact_id, MemoryFactUpdate(
        value="Reviewed new fact", language="en", expected_version=1,
    ))
    assert updated["version"] == 2 and updated["value"] == "Reviewed new fact"
    with pytest.raises(CoworkerError) as stale:
        repository.update(owner, fact_id, MemoryFactUpdate(
            value="Lost competing edit", language="en", expected_version=1,
        ))
    assert stale.value.code == "memory_revision_conflict"
    with repository.sessions() as session:
        assert session.get(MemoryFact, fact_id).value == "Reviewed new fact"
    assert repository.delete(owner, fact_id)["deleted"] is True
