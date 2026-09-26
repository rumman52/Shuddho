from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for PA-04 tests")

from services.coworker.agent_schemas import AgentMemoryProposal, AgentRunCreate
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.errors import CoworkerError
from services.coworker.auth import Principal
from services.coworker.memory_schemas import MemoryFactCreate
from services.coworker.migrate import upgrade
from services.coworker.schemas import UploadRequest

ISSUER = "https://identity.example.test/auth/v1"


@pytest.fixture
def container(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'workspace.sqlite3'}",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
    )
    upgrade(settings.database_url)
    value = Container.create(settings)
    yield value
    value.repository.sessions.kw["bind"].dispose()


def enable_pa04(container):
    settings = replace(
        container.settings,
        agent_runtime_enabled=True,
        agent_runtime_v3_enabled=True,
        intelligent_planner_enabled=True,
        agent_memory_enabled=True,
        context_retrieval_enabled=True,
        work_services_enabled=True,
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.agent.settings = settings
    container.memory.settings = settings
    container.context.settings = settings
    return settings


def owner(container, subject="alice"):
    principal = Principal(ISSUER, subject, 4102444800)
    return container.repository.ensure_account(principal)["account_id"]


def uploaded_text(container, owner_id, name="project.txt", text="Project Alpha deadline is Friday."):
    raw = text.encode("utf-8")
    item = container.repository.create_upload(
        owner_id,
        UploadRequest(
            filename=name,
            byte_size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
    )
    stored = container.repository.get_upload(owner_id, item["id"])
    container.storage.put(stored["object_key"], raw, "text/plain")
    container.repository.finish_upload(owner_id, item["id"])
    return item


def test_context_is_owner_scoped_bounded_and_deletion_aware(container):
    enable_pa04(container)
    alice = owner(container, "alice")
    bob = owner(container, "bob")
    document = uploaded_text(container, alice)
    container.memory.create(
        alice,
        MemoryFactCreate(
            namespace="project",
            key="timezone",
            value="Use Asia/Dhaka for Project Alpha.",
            language="en",
        ),
    )
    run, _ = container.agent.create(
        alice,
        AgentRunCreate(
            goal="Prepare the Project Alpha deadline update.",
            document_ids=[document["id"]],
            memory_namespaces=["project"],
            output_language="en",
        ),
        "pa04-context-owner",
    )

    view = container.context.for_run(alice, run["id"])
    assert view["enabled"] is True
    assert len(view["items"]) == 1
    assert view["items"][0]["label"] == "project.txt"
    assert "Friday" in view["items"][0]["excerpt"]
    assert view["memory"]["facts"][0]["key"] == "timezone"
    with pytest.raises(CoworkerError) as cross_owner:
        container.context.for_run(bob, run["id"])
    assert cross_owner.value.status_code == 404

    container.repository.delete_document(alice, document["id"])
    invalidated = container.context.for_run(alice, run["id"])
    assert invalidated["items"] == []
    assert invalidated["invalidated"][0]["reason"] == "deleted"


def test_memory_proposal_requires_review_and_revalidates_sources(container):
    enable_pa04(container)
    alice = owner(container, "alice")
    bob = owner(container, "bob")
    document = uploaded_text(container, alice)
    run, _ = container.agent.create(
        alice,
        AgentRunCreate(
            goal="Remember the Project Alpha deadline.",
            document_ids=[document["id"]],
            output_language="en",
        ),
        "pa04-memory-review",
    )
    planner_context, source_map = container.context.planner_context(alice, run["id"])
    assert planner_context["memory_proposals_allowed"] is True
    source_id = planner_context["items"][0]["source_id"]

    proposal = container.memory.propose_from_agent(
        alice,
        run["id"],
        AgentMemoryProposal(
            namespace="project",
            key="alpha_deadline",
            value="Project Alpha deadline is Friday.",
            language="en",
            source_ids=[source_id],
        ),
        source_map,
    )
    assert proposal["state"] == "proposed"
    assert container.memory.list(alice) == []
    with pytest.raises(CoworkerError) as cross_owner:
        container.memory.accept_proposal(bob, proposal["id"])
    assert cross_owner.value.status_code == 404

    container.repository.delete_document(alice, document["id"])
    with pytest.raises(CoworkerError) as invalidated:
        container.memory.accept_proposal(alice, proposal["id"])
    assert invalidated.value.code == "memory_proposal_source_invalidated"
    assert container.memory.list(alice) == []


def test_goal_grounded_memory_proposal_is_inert_until_acceptance(container):
    enable_pa04(container)
    alice = owner(container)
    run, _ = container.agent.create(
        alice,
        AgentRunCreate(goal="Use concise weekly updates.", output_language="en"),
        "pa04-memory-goal",
    )
    planner_context, source_map = container.context.planner_context(alice, run["id"])
    assert "goal" in planner_context["allowed_memory_source_ids"]
    proposal = container.memory.propose_from_agent(
        alice,
        run["id"],
        AgentMemoryProposal(
            namespace="preferences",
            key="weekly_update_style",
            value="Use concise weekly updates.",
            language="en",
            source_ids=["goal"],
        ),
        source_map,
    )
    result = container.memory.accept_proposal(alice, proposal["id"])
    assert result["proposal"]["state"] == "accepted"
    assert result["fact"]["provenance"]["type"] == "proposal"
    assert result["fact"]["value"] == "Use concise weekly updates."
