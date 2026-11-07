"""Projects organize existing records; they never grant execution or file access."""
from dataclasses import replace
from uuid import uuid4
import pytest
from test_coworker import account, container, signed_client
from services.coworker.errors import CoworkerError
from services.coworker.project_schemas import ProjectCreate, ProjectEdit, ProjectLink
from services.coworker.conversation_schemas import ConversationCreate


def enabled(container):
    settings = replace(container.settings, projects_enabled=True, conversations_enabled=True)
    container.settings = settings
    container.projects.settings = settings
    container.conversations.settings = settings
    return container.projects


def test_projects_default_off(container):
    with pytest.raises(CoworkerError) as error:
        container.projects.list(account(container))
    assert error.value.code == "projects_unavailable"


def test_project_replay_revision_and_owner_isolation(container):
    repo = enabled(container)
    owner, other = account(container), account(container, "bob")
    payload = ProjectCreate(name="বাংলা প্রকল্প", description="Research")
    project, created = repo.create(owner, payload, "project-key")
    assert created
    assert repo.list(owner)[0]["conversation_count"] == 0
    assert repo.create(owner, payload, "project-key") == (project, False)
    with pytest.raises(CoworkerError): repo.create(owner, ProjectCreate(name="Changed"), "project-key")
    assert repo.list(other) == []
    with pytest.raises(CoworkerError) as error: repo.get(other, project["id"])
    assert error.value.status_code == 404
    renamed = repo.edit(owner, project["id"], ProjectEdit(name="Updated", description="", expected_revision=1))
    assert renamed["revision"] == 2
    with pytest.raises(CoworkerError) as error: repo.edit(owner, project["id"], ProjectEdit(name="Stale", expected_revision=1))
    assert error.value.status_code == 409


def test_project_links_are_owned_and_deletion_preserves_chats(container):
    repo = enabled(container)
    owner, other = account(container), account(container, "bob")
    project, _ = repo.create(owner, ProjectCreate(name="Project"), "project-key")
    chat, _ = container.conversations.create(owner, ConversationCreate(title="Chat"), "chat-key")
    foreign, _ = container.conversations.create(other, ConversationCreate(title="Foreign"), "chat-key")
    with pytest.raises(CoworkerError): repo.link(owner, project["id"], ProjectLink(resource_type="conversation", resource_id=foreign["id"], expected_revision=1))
    assert repo.get(owner, project["id"])["revision"] == 1
    linked = repo.link(owner, project["id"], ProjectLink(resource_type="conversation", resource_id=chat["id"], expected_revision=1))
    assert linked["resources"][0]["title"] == "Chat"
    assert repo.list(owner)[0]["conversation_count"] == 1
    assert repo.link(owner, project["id"], ProjectLink(resource_type="conversation", resource_id=chat["id"], expected_revision=1))["revision"] == 2
    repo.delete(owner, project["id"], 2)
    assert container.conversations.get(owner, chat["id"])["title"] == "Chat"
    with pytest.raises(CoworkerError): repo.get(owner, project["id"])


def test_deleted_and_foreign_files_are_not_exposed_by_project_links(container):
    repo = enabled(container)
    owner = account(container)
    project, _ = repo.create(owner, ProjectCreate(name="Project"), "project-key")
    with pytest.raises(CoworkerError): repo.link(owner, project["id"], ProjectLink(resource_type="document", resource_id=uuid4(), expected_revision=1))
    chat, _ = container.conversations.create(owner, ConversationCreate(title="Chat"), "chat-key")
    repo.link(owner, project["id"], ProjectLink(resource_type="conversation", resource_id=chat["id"], expected_revision=1))
    container.conversations.delete(owner, chat["id"])
    assert repo.get(owner, project["id"])["resources"] == []
    assert repo.list(owner)[0]["conversation_count"] == 0
    assert container.retention.erase_account(owner)["database_erased"]


def test_project_routes_require_auth_and_enforce_ownership(container, signed_client):
    enabled(container)
    client, headers = signed_client
    assert client.get("/api/v1/projects").status_code == 401
    result = client.post("/api/v1/projects", json={"name":"Project"}, headers={**headers(), "Idempotency-Key":"project-key"})
    assert result.status_code == 201
    project_id = result.json()["id"]
    assert client.get(f"/api/v1/projects/{project_id}", headers=headers("bob")).status_code == 404
    listed = client.get("/api/v1/projects", headers=headers()).json()["items"][0]
    assert listed["id"] == project_id
    assert listed["conversation_count"] == 0
    assert client.get("/api/v1/runtime-manifest", headers=headers()).json()["capabilities"]["projects"] is True


def test_additive_project_migration_preserves_existing_conversation(tmp_path):
    from alembic import command
    from services.coworker.migrate import migration_config, upgrade
    from services.coworker.config import Settings
    from services.coworker.container import Container
    from services.coworker.models import Account, Project
    from sqlalchemy import select
    url = f"sqlite:///{tmp_path / 'upgrade.sqlite3'}"
    command.upgrade(migration_config(url), "0063")
    settings = Settings(database_url=url, auth_issuer="https://identity.example.test/auth/v1", environment="development", storage_backend="local", local_storage_path=tmp_path / "objects", conversations_enabled=True, projects_enabled=True)
    current = Container.create(settings)
    try:
        owner = account(current)
        chat, _ = current.conversations.create(owner, ConversationCreate(title="Existing Bangla বাংলা"), "existing-chat")
        upgrade(url)
        assert current.conversations.get(owner, chat["id"])["title"] == "Existing Bangla বাংলা"
        project, _ = current.projects.create(owner, ProjectCreate(name="After migration"), "new-project")
        assert current.projects.get(owner, project["id"])["name"] == "After migration"
        assert current.retention.erase_account(owner)["database_erased"]
        with current.repository.sessions() as db:
            assert db.get(Account, owner) is None
            assert db.scalar(select(Project)) is None
    finally:
        current.repository.sessions.kw["bind"].dispose()
