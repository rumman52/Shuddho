from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import select

from test_coworker import account, signed_client
from services.coworker.config import Settings
from services.coworker.errors import CoworkerError
from services.coworker.github_app import GitHubAppService, safe_repository_path
from services.coworker.models import (
    GitHubConnectAttempt,
    GitHubInstallation,
    GitHubRepositoryBinding,
    utcnow,
)
from services.coworker.project_schemas import ProjectCreate


def _enabled(container, transport=None):
    settings = replace(
        container.settings,
        projects_enabled=True,
        conversations_enabled=True,
        fly_github_enabled=True,
        github_app_id="12345",
        github_app_slug="rukh-ai",
        github_app_client_id="Iv1.test-client",
        github_app_client_secret="test-client-secret",
        github_app_redirect_uri="https://rukhai.example/fly",
        connector_encryption_key=base64.urlsafe_b64encode(b"c" * 32).decode("ascii"),
        github_timeout_seconds=5,
        github_max_file_bytes=262144,
        github_max_tree_files=500,
    )
    settings.validate()
    container.settings = settings
    container.repository.settings = settings
    container.projects.settings = settings
    container.conversations.settings = settings
    container.github.settings = settings
    container.github.transport = transport
    return settings


def _project(container, owner):
    value, created = container.projects.create(
        owner,
        ProjectCreate(name="Repository project", description="Fly GitHub connection test"),
        "github-project-key",
    )
    assert created
    return value


def _transport(*, accessible_installation=True):
    source = b"print('repository context')\n"
    repo = {
        "id": 777,
        "full_name": "acme/demo",
        "default_branch": "main",
        "private": True,
        "permissions": {"pull": True, "push": False, "admin": False},
    }

    def handler(request: httpx.Request):
        path = request.url.path
        if request.url.host == "github.com" and path == "/login/oauth/access_token":
            from urllib.parse import parse_qs
            form = parse_qs(request.content.decode("utf-8"))
            if form.get("grant_type") == ["refresh_token"]:
                return httpx.Response(200, json={
                    "access_token": "rotated-user-token",
                    "refresh_token": "rotated-refresh-token",
                    "expires_in": 28800,
                    "refresh_token_expires_in": 15897600,
                    "token_type": "bearer",
                })
            return httpx.Response(200, json={
                "access_token": "short-lived-user-token",
                "refresh_token": "short-lived-refresh-token",
                "expires_in": 28800,
                "refresh_token_expires_in": 15897600,
                "token_type": "bearer",
            })
        if request.url.host == "api.github.com":
            if path == "/user":
                return httpx.Response(200, json={"id": 9001, "login": "rukh-user"})
            if path == "/user/installations":
                items = [{
                    "id": 321,
                    "app_id": 12345,
                    "account": {"id": 55, "login": "acme", "type": "Organization"},
                    "permissions": {"metadata": "read", "contents": "read"},
                    "suspended_at": None,
                }] if accessible_installation else []
                return httpx.Response(200, json={"total_count": len(items), "installations": items})
            if path == "/user/installations/321/repositories":
                return httpx.Response(200, json={"total_count": 1, "repositories": [repo]})
            if path == "/repos/acme/demo/git/ref/heads/main":
                return httpx.Response(200, json={"object": {"sha": "a" * 40}})
            if path == "/repos/acme/demo/git/commits/" + ("a" * 40):
                return httpx.Response(200, json={"tree": {"sha": "b" * 40}})
            if path == "/repos/acme/demo/git/trees/" + ("b" * 40):
                return httpx.Response(200, json={"truncated": False, "tree": [
                    {"path": "src/app.py", "type": "blob", "size": 25, "sha": "c" * 40},
                    {"path": "README.md", "type": "blob", "size": 40, "sha": "d" * 40},
                    {"path": ".env", "type": "blob", "size": 20, "sha": "e" * 40},
                    {"path": "secrets/token.py", "type": "blob", "size": 20, "sha": "f" * 40},
                    {"path": "node_modules/pkg/index.js", "type": "blob", "size": 20, "sha": "1" * 40},
                    {"path": "assets/logo.png", "type": "blob", "size": 100, "sha": "2" * 40},
                ]})
            if path == "/repos/acme/demo/contents/src/app.py":
                return httpx.Response(200, json={
                    "type": "file",
                    "encoding": "base64",
                    "size": len(source),
                    "sha": "c" * 40,
                    "content": base64.b64encode(source).decode("ascii")[:12] + "\n" + base64.b64encode(source).decode("ascii")[12:],
                })
        return httpx.Response(404, json={"message": "not found"})

    return httpx.MockTransport(handler)


def _connect(container, owner):
    service = container.github
    project = _project(container, owner)
    started = service.start_connection(owner, project["id"])
    query = parse_qs(urlparse(started["authorization_url"]).query)
    oauth_state = query["state"][0]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"] == ["offline_access"]
    assert len(query["code_challenge"][0]) == 43
    finished = service.finish_oauth(owner, oauth_state, "single-use-code")
    assert "access_token" not in finished and "refresh_token" not in finished
    return project, finished


def test_github_connection_is_disabled_by_default(container):
    owner = account(container)
    with pytest.raises(CoworkerError) as error:
        container.github.start_connection(owner, "00000000-0000-0000-0000-000000000000")
    assert error.value.code == "github_repository_unavailable"


def test_github_app_oauth_pkce_install_verification_and_repository_browsing(container):
    _enabled(container, _transport())
    owner = account(container)
    project, finished = _connect(container, owner)
    assert finished["github_login"] == "rukh-user"
    assert finished["install_url"].startswith("https://github.com/apps/rukh-ai/installations/new?")
    assert finished["state"]

    connected = container.github.complete_install(owner, finished["state"], 321)
    installation = connected["installation"]
    assert installation["account_login"] == "acme"
    assert [item["full_name"] for item in connected["repositories"]] == ["acme/demo"]

    binding = container.github.bind_repository(
        owner, project["id"], installation["id"], 777, project["revision"],
    )
    assert binding["full_name"] == "acme/demo"
    assert binding["can_read_contents"] is True
    assert binding["can_write_contents"] is False

    tree = container.github.repository_tree(owner, project["id"])
    assert tree["commit_sha"] == "a" * 40
    assert {item["path"] for item in tree["files"]} == {"src/app.py", "README.md"}
    file = container.github.read_repository_file(owner, project["id"], "src/app.py", "a" * 40)
    assert file["repository"] == "acme/demo"
    assert file["commit_sha"] == "a" * 40
    assert file["blob_sha"] == "c" * 40
    assert file["content"] == "print('repository context')\n"
    assert file["sha256"] == hashlib.sha256(file["content"].encode()).hexdigest()
    with pytest.raises(CoworkerError) as stale:
        container.github.read_repository_file(owner, project["id"], "src/app.py", "b" * 40)
    assert stale.value.code == "github_repository_changed"

    assert container.github.get_repository(owner, project["id"])["repository"]["id"] == binding["id"]
    container.github.disconnect_repository(owner, project["id"])
    assert container.github.get_repository(owner, project["id"])["repository"] is None


def test_github_installation_id_is_verified_against_the_oauth_user(container):
    _enabled(container, _transport(accessible_installation=False))
    owner = account(container)
    project, finished = _connect(container, owner)
    with pytest.raises(CoworkerError) as error:
        container.github.complete_install(owner, finished["state"], 321)
    assert error.value.code == "github_install_not_owned"
    with container.repository.sessions() as db:
        attempt = db.scalar(select(GitHubConnectAttempt).where(
            GitHubConnectAttempt.owner_id == owner,
            GitHubConnectAttempt.project_id == project["id"],
        ))
        assert attempt.stage == "awaiting_install"
        assert attempt.user_access_token_ciphertext


def test_github_oauth_state_is_owner_scoped_single_use_and_expiring(container):
    _enabled(container, _transport())
    owner = account(container)
    other = account(container, "bob")
    project = _project(container, owner)
    started = container.github.start_connection(owner, project["id"])
    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    with pytest.raises(CoworkerError) as error:
        container.github.finish_oauth(other, state, "code")
    assert error.value.code == "github_oauth_expired"
    finished = container.github.finish_oauth(owner, state, "code")
    with pytest.raises(CoworkerError) as replay:
        container.github.finish_oauth(owner, state, "code")
    assert replay.value.code == "github_oauth_expired"
    with container.repository.sessions.begin() as db:
        attempt = db.scalar(select(GitHubConnectAttempt).where(GitHubConnectAttempt.owner_id == owner))
        attempt.expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(CoworkerError) as expired:
        container.github.complete_install(owner, finished["state"], 321)
    assert expired.value.code == "github_install_expired"


def test_github_repository_bindings_are_owner_and_project_scoped(container):
    _enabled(container, _transport())
    owner = account(container)
    other = account(container, "bob")
    project, finished = _connect(container, owner)
    connected = container.github.complete_install(owner, finished["state"], 321)
    with pytest.raises(CoworkerError) as error:
        container.github.bind_repository(other, project["id"], connected["installation"]["id"], 777, project["revision"])
    assert error.value.status_code == 404
    with pytest.raises(CoworkerError) as foreign:
        container.github.get_repository(other, project["id"])
    assert foreign.value.status_code == 404


def test_github_user_access_token_refreshes_and_rotates_encrypted_refresh_token(container):
    _enabled(container, _transport())
    owner = account(container)
    project, finished = _connect(container, owner)
    connected = container.github.complete_install(owner, finished["state"], 321)
    installation_id = connected["installation"]["id"]
    with container.repository.sessions.begin() as db:
        row = db.scalar(select(GitHubInstallation).where(
            GitHubInstallation.owner_id == owner,
            GitHubInstallation.id == installation_id,
        ))
        row.access_token_expires_at = utcnow() - timedelta(seconds=1)
    result = container.github.list_repositories(owner, installation_id)
    assert result["repositories"][0]["full_name"] == "acme/demo"
    with container.repository.sessions() as db:
        row = db.scalar(select(GitHubInstallation).where(
            GitHubInstallation.owner_id == owner,
            GitHubInstallation.id == installation_id,
        ))
        bundle = container.github._vault().open(
            row.user_token_bundle_ciphertext,
            owner + ":github-installation:" + installation_id,
        )
        assert bundle["access_token"] == "rotated-user-token"
        assert bundle["refresh_token"] == "rotated-refresh-token"
        expiry = row.access_token_expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=utcnow().tzinfo)
        assert expiry > utcnow()


def test_disconnect_github_installation_revokes_tokens_and_all_project_bindings(container):
    _enabled(container, _transport())
    owner = account(container)
    project, finished = _connect(container, owner)
    connected = container.github.complete_install(owner, finished["state"], 321)
    installation_id = connected["installation"]["id"]
    container.github.bind_repository(owner, project["id"], installation_id, 777, project["revision"])
    container.github.disconnect_installation(owner, installation_id)
    assert container.github.get_repository(owner, project["id"])["repository"] is None
    with container.repository.sessions() as db:
        row = db.scalar(select(GitHubInstallation).where(
            GitHubInstallation.owner_id == owner,
            GitHubInstallation.id == installation_id,
        ))
        binding = db.scalar(select(GitHubRepositoryBinding).where(
            GitHubRepositoryBinding.owner_id == owner,
            GitHubRepositoryBinding.project_id == project["id"],
        ))
        assert row.active is False
        assert row.user_token_bundle_ciphertext == ""
        assert binding.active is False


def test_github_paths_reject_traversal_and_credential_files():
    for value in ("../app.py", "src/../app.py", "/etc/passwd", r"src\..\app.py", ".env", "config/.env.production", "certs/private.pem"):
        with pytest.raises(CoworkerError):
            safe_repository_path(value)
    assert safe_repository_path("src/main.py") == "src/main.py"
    assert safe_repository_path("docs/README.md") == "docs/README.md"
    assert safe_repository_path("Dockerfile") == "Dockerfile"
    assert safe_repository_path(".github/workflows/ci.yml") == ".github/workflows/ci.yml"


def test_github_repository_credentials_and_bindings_are_erased_with_account(container):
    _enabled(container, _transport())
    owner = account(container)
    project, finished = _connect(container, owner)
    connected = container.github.complete_install(owner, finished["state"], 321)
    container.github.bind_repository(owner, project["id"], connected["installation"]["id"], 777, project["revision"])
    container.retention.erase_account(owner)
    with container.repository.sessions() as db:
        assert db.scalar(select(GitHubConnectAttempt).where(GitHubConnectAttempt.owner_id == owner)) is None
        assert db.scalar(select(GitHubInstallation).where(GitHubInstallation.owner_id == owner)) is None
        assert db.scalar(select(GitHubRepositoryBinding).where(GitHubRepositoryBinding.owner_id == owner)) is None


def test_github_status_and_start_routes_require_auth_and_return_no_store(container, signed_client):
    client, headers = signed_client
    assert client.get("/api/v1/github/status").status_code == 401
    assert client.get("/api/v1/github/status", headers=headers()).json() == {"enabled": False}

    _enabled(container)
    owner = account(container)
    project = _project(container, owner)
    status = client.get("/api/v1/github/status", headers=headers())
    assert status.json() == {"enabled": True}
    response = client.post(
        f"/api/v1/projects/{project['id']}/github/connect/start",
        headers=headers(),
    )
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["authorization_url"].startswith("https://github.com/login/oauth/authorize?")
