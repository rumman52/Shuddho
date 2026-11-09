from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from test_coworker import account, container, signed_client
from services.coworker.project_schemas import ProjectCreate


def _enable_projects(container):
    settings = replace(
        container.settings,
        projects_enabled=True,
        conversations_enabled=True,
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.projects.settings = settings
    return settings


def test_fly_code_status_reports_new_capabilities_default_off(container):
    owner = account(container)
    client = signed_client(container, owner)

    response = client.get("/api/v1/fly/code/status")

    assert response.status_code == 200
    body = response.json()
    assert body["generation_enabled"] is False
    assert body["repository_execution_enabled"] is False
    assert body["automated_repair_enabled"] is False
    assert body["github_write_enabled"] is False


def test_fly_workspace_starts_empty_and_is_project_scoped(container):
    _enable_projects(container)
    owner = account(container)
    client = signed_client(container, owner)
    project, created = container.projects.create(
        owner,
        ProjectCreate(name="Fly coding project", description="Repository coding workflow"),
        "fly-workspace-" + str(uuid4()),
    )
    assert created

    response = client.get(f"/api/v1/projects/{project['id']}/fly/workspace")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project["id"]
    assert body["revision"] == 0
    assert body["files"] == []
