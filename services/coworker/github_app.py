"""Least-privilege GitHub App user authorization and Fly repository browsing.

GitHub user access tokens are restricted to the intersection of the App's
granted repository permissions and the user's own access. Access/refresh
tokens are encrypted at rest; installation IDs from setup callbacks are never
trusted until verified against that exact user's accessible installations.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode
from uuid import uuid4

import httpx
from sqlalchemy import select, update

from .action_security import TokenVault
from .errors import CoworkerError
from .models import (
    GitHubConnectAttempt,
    GitHubInstallation,
    GitHubRepositoryBinding,
    Project,
    utcnow,
)
from .conversation_repository import ConversationRepository
from .repository import iso, not_found


GITHUB_API = "https://api.github.com"
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API_VERSION = "2026-03-10"
SOURCE_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".json", ".md", ".markdown",
    ".txt", ".yaml", ".yml", ".toml", ".xml", ".sql", ".sh", ".bash",
    ".go", ".rs", ".java", ".kt", ".dart", ".swift", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".php", ".rb", ".vue", ".svelte",
    ".astro", ".graphql", ".gql",
}
DENIED_PARTS = {
    ".git", ".venv", "venv", "node_modules", "vendor", "dist", "build",
    ".next", "coverage", "__pycache__", ".terraform", "target", ".aws",
    ".ssh", "secrets", "credentials",
}
DENIED_NAMES = {
    ".env", ".env.local", ".env.production", ".npmrc", ".pypirc",
    "id_rsa", "id_ed25519", "credentials", "secrets",
}
DENIED_SUFFIXES = {
    ".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".der",
    ".jks", ".keystore", ".secret", ".token",
}
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def safe_repository_path(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise CoworkerError("github_path_invalid", "Choose a valid repository file path.", 422)
    if value.startswith(("/", "\\")) or "\x00" in value or "\\" in value:
        raise CoworkerError("github_path_invalid", "Repository paths must be relative POSIX paths.", 422)
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CoworkerError("github_path_invalid", "Repository paths cannot traverse directories.", 422)
    lowered = [part.lower() for part in parts]
    filename = lowered[-1]
    if any(part in DENIED_PARTS for part in lowered):
        raise CoworkerError("github_source_denied", "This repository path is excluded from source context.", 403)
    if filename in DENIED_NAMES or filename.startswith(".env.") or any(filename.endswith(ext) for ext in DENIED_SUFFIXES):
        raise CoworkerError("github_source_denied", "Credential and environment files cannot be read into Fly.", 403)
    if "." not in filename or ("." + filename.rsplit(".", 1)[-1]) not in SOURCE_EXTENSIONS:
        raise CoworkerError("github_file_type_unsupported", "This file type is not supported for repository context.", 415)
    return value


class GitHubAppService:
    def __init__(self, sessions, settings, transport=None):
        self.sessions = sessions
        self.settings = settings
        self.transport = transport

    def _enabled(self):
        if not self.settings.fly_github_enabled:
            raise CoworkerError("github_repository_unavailable", "GitHub repository access is not enabled in this deployment.", 503)
        if not all((
            self.settings.github_app_id,
            self.settings.github_app_slug,
            self.settings.github_app_client_id,
            self.settings.github_app_client_secret,
            self.settings.github_app_redirect_uri,
            self.settings.connector_encryption_key,
        )):
            raise CoworkerError("github_not_configured", "GitHub App credentials are not configured.", 503)

    def _vault(self):
        return TokenVault(self.settings.connector_encryption_key)

    def _client(self):
        return httpx.Client(
            timeout=self.settings.github_timeout_seconds,
            follow_redirects=False,
            transport=self.transport,
        )

    def _headers(self, token: str | None = None):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.settings.github_api_version or GITHUB_API_VERSION,
            "User-Agent": "Rukh-AI-Fly",
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        return headers

    @staticmethod
    def _decode_response(response, *, expected=(200,)):
        if response.status_code not in expected:
            if response.status_code in {401, 403}:
                raise CoworkerError("github_access_denied", "GitHub denied this repository operation. Check the App installation and granted permissions.", 403)
            if response.status_code == 404:
                raise CoworkerError("github_resource_unavailable", "The GitHub installation or repository is no longer available.", 404)
            if response.status_code == 409:
                raise CoworkerError("github_repository_conflict", "The repository changed while Fly was reading it. Refresh and retry.", 409)
            if response.status_code == 429 or response.status_code >= 500:
                raise CoworkerError("github_temporarily_unavailable", "GitHub is temporarily unavailable. Retry this operation shortly.", 503)
            raise CoworkerError("github_request_failed", "GitHub rejected this request. Review the App permissions and try again.", 502)
        try:
            value = response.json()
        except ValueError:
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid response.", 502) from None
        if not isinstance(value, dict):
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid response.", 502)
        return value

    def _api(self, method: str, path: str, token: str, *, params=None, body=None, expected=(200,)):
        if not path.startswith("/") or path.startswith("//"):
            raise CoworkerError("github_request_invalid", "The GitHub request path is invalid.", 500)
        try:
            with self._client() as client:
                response = client.request(
                    method,
                    GITHUB_API + path,
                    headers=self._headers(token),
                    params=params,
                    json=body,
                )
        except httpx.HTTPError:
            raise CoworkerError("github_temporarily_unavailable", "GitHub could not be reached. Retry this operation shortly.", 503) from None
        if 300 <= response.status_code < 400:
            raise CoworkerError("github_redirect_denied", "GitHub returned an unexpected redirect; the request was not followed.", 502)
        return self._decode_response(response, expected=expected)

    def _oauth_post(self, body: dict):
        try:
            with self._client() as client:
                response = client.post(
                    GITHUB_TOKEN,
                    headers={"Accept": "application/json", "User-Agent": "Rukh-AI-Fly"},
                    data=body,
                )
        except httpx.HTTPError:
            raise CoworkerError("github_temporarily_unavailable", "GitHub authorization could not be completed. Start the connection again.", 503) from None
        if 300 <= response.status_code < 400 or response.status_code != 200:
            raise CoworkerError("github_oauth_failed", "GitHub authorization failed. Start the connection again.", 502)
        try:
            data = response.json()
        except ValueError:
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid authorization response.", 502) from None
        if not isinstance(data, dict):
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid authorization response.", 502)
        if data.get("error") == "bad_refresh_token":
            raise CoworkerError("github_oauth_expired", "The GitHub refresh token expired or was revoked. Reconnect GitHub.", 409)
        if data.get("error"):
            raise CoworkerError("github_oauth_failed", "GitHub authorization failed. Reconnect GitHub.", 502)
        return data

    @staticmethod
    def _token_bundle(data: dict):
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")
        refresh_expires_in = data.get("refresh_token_expires_in")
        if (
            not isinstance(access_token, str) or not access_token or len(access_token) > 4096
            or not isinstance(refresh_token, str) or not refresh_token or len(refresh_token) > 4096
            or type(expires_in) is not int or not 60 <= expires_in <= 86400
            or type(refresh_expires_in) is not int or not 3600 <= refresh_expires_in <= 31536000
        ):
            raise CoworkerError("github_oauth_failed", "GitHub did not issue the expected expiring user and refresh tokens.", 502)
        now = utcnow()
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
            "refresh_token_expires_at": (now + timedelta(seconds=refresh_expires_in)).isoformat(),
        }

    def _oauth_exchange(self, code: str, verifier: str):
        data = self._oauth_post({
            "client_id": self.settings.github_app_client_id,
            "client_secret": self.settings.github_app_client_secret,
            "code": code,
            "redirect_uri": self.settings.github_app_redirect_uri,
            "code_verifier": verifier,
        })
        return self._token_bundle(data)

    def _oauth_refresh(self, refresh_token: str):
        data = self._oauth_post({
            "client_id": self.settings.github_app_client_id,
            "client_secret": self.settings.github_app_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        })
        return self._token_bundle(data)

    @staticmethod
    def _project(db, owner: str, project_id: str):
        row = db.scalar(select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner,
            Project.deleted.is_(False),
        ))
        if row is None:
            raise not_found()
        return row

    def start_connection(self, owner: str, project_id: str):
        self._enabled()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        attempt_id = str(uuid4())
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            self._project(db, owner, project_id)
            db.add(GitHubConnectAttempt(
                id=attempt_id,
                owner_id=owner,
                project_id=project_id,
                state_hash=_sha(state),
                stage="oauth",
                code_verifier_ciphertext=self._vault().seal(
                    {"verifier": verifier}, owner + ":github-connect:" + attempt_id,
                ),
                user_access_token_ciphertext="",
                github_user_id=None,
                github_login="",
                expires_at=utcnow() + timedelta(minutes=10),
                created_at=utcnow(),
            ))
        query = urlencode({
            "client_id": self.settings.github_app_client_id,
            "redirect_uri": self.settings.github_app_redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "allow_signup": "false",
            "scope": "offline_access",
        })
        return {"authorization_url": GITHUB_AUTHORIZE + "?" + query, "expires_in_seconds": 600}

    def finish_oauth(self, owner: str, state: str, code: str):
        self._enabled()
        if not isinstance(state, str) or not 32 <= len(state) <= 256 or not isinstance(code, str) or not 1 <= len(code) <= 512:
            raise CoworkerError("github_oauth_invalid", "The GitHub callback is incomplete. Start the connection again.", 422)
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            row = db.scalar(select(GitHubConnectAttempt).where(
                GitHubConnectAttempt.state_hash == _sha(state),
                GitHubConnectAttempt.owner_id == owner,
            ).with_for_update())
            if row is None or row.stage != "oauth" or row.expires_at <= utcnow():
                raise CoworkerError("github_oauth_expired", "This GitHub connection request expired or was already used. Start again.", 409)
            self._project(db, owner, row.project_id)
            verifier = self._vault().open(
                row.code_verifier_ciphertext,
                owner + ":github-connect:" + row.id,
            ).get("verifier")
            if not isinstance(verifier, str) or not verifier:
                raise CoworkerError("github_oauth_invalid", "The GitHub connection verifier is unavailable. Start again.", 409)
            row.stage = "oauth_processing"
            attempt_id = row.id
        # Never hold an application row lock while making provider network calls.
        token_bundle = self._oauth_exchange(code, verifier)
        access_token = token_bundle["access_token"]
        user = self._api("GET", "/user", access_token)
        user_id, login = user.get("id"), user.get("login")
        if type(user_id) is not int or user_id <= 0 or not isinstance(login, str) or not LOGIN_RE.fullmatch(login):
            raise CoworkerError("github_profile_invalid", "GitHub returned an invalid user identity.", 502)
        install_state = secrets.token_urlsafe(32)
        with self.sessions.begin() as db:
            row = db.scalar(select(GitHubConnectAttempt).where(
                GitHubConnectAttempt.id == attempt_id,
                GitHubConnectAttempt.owner_id == owner,
            ).with_for_update())
            if row is None or row.stage != "oauth_processing" or row.expires_at <= utcnow():
                raise CoworkerError("github_oauth_expired", "This GitHub connection request expired. Start again.", 409)
            row.state_hash = _sha(install_state)
            row.stage = "awaiting_install"
            row.code_verifier_ciphertext = ""
            row.user_access_token_ciphertext = self._vault().seal(
                token_bundle, owner + ":github-connect:" + row.id,
            )
            row.github_user_id = user_id
            row.github_login = login
            row.expires_at = utcnow() + timedelta(minutes=10)
        install_url = (
            f"https://github.com/apps/{quote(self.settings.github_app_slug, safe='')}/installations/new?"
            + urlencode({"state": install_state})
        )
        return {
            "github_login": login,
            "github_user_id": user_id,
            "install_url": install_url,
            "state": install_state,
            "expires_in_seconds": 600,
        }

    def _user_installations(self, access_token: str):
        values = []
        for page in range(1, 6):
            data = self._api(
                "GET", "/user/installations", access_token,
                params={"per_page": 100, "page": page},
            )
            items = data.get("installations")
            if not isinstance(items, list):
                raise CoworkerError("github_response_invalid", "GitHub returned an invalid installation list.", 502)
            values.extend(item for item in items if isinstance(item, dict))
            total = data.get("total_count", len(values))
            if type(total) is not int or total < len(values):
                raise CoworkerError("github_response_invalid", "GitHub returned an invalid installation count.", 502)
            if len(values) >= total:
                return values
        raise CoworkerError("github_installation_limit", "This GitHub account has too many App installations to verify safely.", 413)

    def _reset_install_attempt(self, owner: str, attempt_id: str):
        with self.sessions.begin() as db:
            row = db.scalar(select(GitHubConnectAttempt).where(
                GitHubConnectAttempt.id == attempt_id,
                GitHubConnectAttempt.owner_id == owner,
            ).with_for_update())
            if row is not None and row.stage == "install_processing" and row.expires_at > utcnow():
                row.stage = "awaiting_install"

    def complete_install(self, owner: str, state: str, installation_id: int):
        self._enabled()
        if not isinstance(state, str) or not 32 <= len(state) <= 256 or type(installation_id) is not int or installation_id <= 0:
            raise CoworkerError("github_install_invalid", "The GitHub installation callback is invalid.", 422)
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            row = db.scalar(select(GitHubConnectAttempt).where(
                GitHubConnectAttempt.state_hash == _sha(state),
                GitHubConnectAttempt.owner_id == owner,
            ).with_for_update())
            if row is None or row.stage != "awaiting_install" or row.expires_at <= utcnow():
                raise CoworkerError("github_install_expired", "This GitHub installation request expired or was already used. Start again.", 409)
            self._project(db, owner, row.project_id)
            token_data = self._vault().open(
                row.user_access_token_ciphertext,
                owner + ":github-connect:" + row.id,
            )
            access_token = token_data.get("access_token")
            if (
                not isinstance(access_token, str) or not access_token
                or not isinstance(token_data.get("refresh_token"), str)
                or not isinstance(token_data.get("access_token_expires_at"), str)
                or not isinstance(token_data.get("refresh_token_expires_at"), str)
            ):
                raise CoworkerError("github_oauth_expired", "The temporary GitHub authorization expired. Connect GitHub again.", 409)
            row.stage = "install_processing"
            attempt_id, project_id = row.id, row.project_id
            github_user_id, github_login = row.github_user_id, row.github_login
        try:
            # GitHub explicitly warns that installation_id on a setup URL can
            # be spoofed. Verify it against this exact user's accessible installations.
            installations = self._user_installations(access_token)
            selected = next((item for item in installations if item.get("id") == installation_id), None)
            if selected is None or selected.get("app_id") != int(self.settings.github_app_id):
                raise CoworkerError("github_install_not_owned", "This GitHub installation is not accessible to the GitHub account you just connected.", 403)
            if selected.get("suspended_at"):
                raise CoworkerError("github_install_suspended", "This GitHub App installation is suspended.", 409)
            account = selected.get("account") or {}
            account_id, account_login, account_type = account.get("id"), account.get("login"), account.get("type")
            if type(account_id) is not int or not isinstance(account_login, str) or account_type not in {"User", "Organization", "Enterprise"}:
                raise CoworkerError("github_response_invalid", "GitHub returned an invalid installation owner.", 502)
            permissions = selected.get("permissions") or {}
            if not isinstance(permissions, dict) or permissions.get("contents") not in {"read", "write"}:
                raise CoworkerError("github_contents_permission_missing", "The GitHub App installation needs repository Contents: read permission.", 403)
            # Use the user token, not an app-wide installation token, so
            # repository visibility remains bounded by the signed-in user's
            # current GitHub permissions as well as the App installation.
            repositories = self._list_repositories_for_user(access_token, installation_id)
        except Exception:
            self._reset_install_attempt(owner, attempt_id)
            raise
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            attempt = db.scalar(select(GitHubConnectAttempt).where(
                GitHubConnectAttempt.id == attempt_id,
                GitHubConnectAttempt.owner_id == owner,
            ).with_for_update())
            if attempt is None or attempt.stage != "install_processing" or attempt.expires_at <= utcnow():
                raise CoworkerError("github_install_expired", "This GitHub installation request expired. Start again.", 409)
            existing = db.scalar(select(GitHubInstallation).where(
                GitHubInstallation.owner_id == owner,
                GitHubInstallation.installation_id == installation_id,
            ).with_for_update())
            if existing is None:
                installation_record_id = str(uuid4())
                existing = GitHubInstallation(
                    id=installation_record_id,
                    owner_id=owner,
                    installation_id=installation_id,
                    github_user_id=github_user_id,
                    github_login=github_login,
                    account_id=account_id,
                    account_login=account_login,
                    account_type=account_type,
                    permissions=permissions,
                    user_token_bundle_ciphertext=self._vault().seal(
                        token_data, owner + ":github-installation:" + installation_record_id,
                    ),
                    access_token_expires_at=datetime.fromisoformat(token_data["access_token_expires_at"]),
                    refresh_token_expires_at=datetime.fromisoformat(token_data["refresh_token_expires_at"]),
                    active=True,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                db.add(existing)
            else:
                existing.github_user_id = github_user_id
                existing.github_login = github_login
                existing.account_id = account_id
                existing.account_login = account_login
                existing.account_type = account_type
                existing.permissions = permissions
                existing.user_token_bundle_ciphertext = self._vault().seal(
                    token_data, owner + ":github-installation:" + existing.id,
                )
                existing.access_token_expires_at = datetime.fromisoformat(token_data["access_token_expires_at"])
                existing.refresh_token_expires_at = datetime.fromisoformat(token_data["refresh_token_expires_at"])
                existing.active = True
                existing.updated_at = utcnow()
            attempt.stage = "consumed"
            attempt.code_verifier_ciphertext = ""
            attempt.user_access_token_ciphertext = ""
            attempt.state_hash = _sha(secrets.token_urlsafe(32))
            attempt.expires_at = utcnow()
            installation_record_id = existing.id
            installation_dto = self._installation_dto(existing)
            ConversationRepository._audit(db, owner, project_id, "github.installation_connected")
        return {
            "project_id": project_id,
            "installation": installation_dto,
            "repositories": repositories,
        }

    @staticmethod
    def _installation_dto(row):
        return {
            "id": row.id,
            "installation_id": row.installation_id,
            "github_login": row.github_login,
            "account_login": row.account_login,
            "account_type": row.account_type,
            "permissions": dict(row.permissions or {}),
            "active": bool(row.active),
        }

    def list_installations(self, owner: str):
        self._enabled()
        with self.sessions() as db:
            rows = db.scalars(select(GitHubInstallation).where(
                GitHubInstallation.owner_id == owner,
                GitHubInstallation.active.is_(True),
            ).order_by(GitHubInstallation.account_login.asc(), GitHubInstallation.created_at.asc())).all()
            return {"items": [self._installation_dto(row) for row in rows]}

    def _installation(self, db, owner: str, installation_record_id: str):
        row = db.scalar(select(GitHubInstallation).where(
            GitHubInstallation.id == installation_record_id,
            GitHubInstallation.owner_id == owner,
            GitHubInstallation.active.is_(True),
        ))
        if row is None:
            raise not_found()
        return row

    def _user_token(self, owner: str, installation_record_id: str):
        expired = False
        token = None
        try:
            with self.sessions.begin() as db:
                installation = self._installation(db, owner, installation_record_id)
                binding = owner + ":github-installation:" + installation.id
                bundle = self._vault().open(installation.user_token_bundle_ciphertext, binding)
                access_token = bundle.get("access_token")
                refresh_token = bundle.get("refresh_token")
                if not isinstance(access_token, str) or not access_token or not isinstance(refresh_token, str) or not refresh_token:
                    installation.active = False
                    installation.user_token_bundle_ciphertext = ""
                    expired = True
                else:
                    access_expiry = installation.access_token_expires_at
                    refresh_expiry = installation.refresh_token_expires_at
                    if access_expiry.tzinfo is None:
                        access_expiry = access_expiry.replace(tzinfo=utcnow().tzinfo)
                    if refresh_expiry.tzinfo is None:
                        refresh_expiry = refresh_expiry.replace(tzinfo=utcnow().tzinfo)
                    if access_expiry > utcnow() + timedelta(minutes=1):
                        token = access_token
                    elif refresh_expiry <= utcnow():
                        installation.active = False
                        installation.user_token_bundle_ciphertext = ""
                        expired = True
                    else:
                        refreshed = self._oauth_refresh(refresh_token)
                        installation.user_token_bundle_ciphertext = self._vault().seal(refreshed, binding)
                        installation.access_token_expires_at = datetime.fromisoformat(refreshed["access_token_expires_at"])
                        installation.refresh_token_expires_at = datetime.fromisoformat(refreshed["refresh_token_expires_at"])
                        installation.updated_at = utcnow()
                        token = refreshed["access_token"]
        except CoworkerError as error:
            if error.code == "github_oauth_expired":
                with self.sessions.begin() as db:
                    row = db.scalar(select(GitHubInstallation).where(
                        GitHubInstallation.id == installation_record_id,
                        GitHubInstallation.owner_id == owner,
                    ).with_for_update())
                    if row is not None:
                        row.active = False
                        row.user_token_bundle_ciphertext = ""
                        row.updated_at = utcnow()
                raise CoworkerError("github_reconnect_required", "GitHub authorization expired or was revoked. Reconnect this GitHub account in Fly.", 409) from None
            raise
        if expired:
            raise CoworkerError("github_reconnect_required", "GitHub authorization expired. Reconnect this GitHub account in Fly.", 409)
        if not token:
            raise CoworkerError("github_token_unavailable", "A usable GitHub access token is unavailable.", 503)
        return token

    def _list_repositories_for_user(self, access_token: str, installation_id: int):
        repositories = []
        for page in range(1, 6):
            data = self._api(
                "GET",
                f"/user/installations/{installation_id}/repositories",
                access_token,
                params={"per_page": 100, "page": page},
            )
            items = data.get("repositories")
            if not isinstance(items, list):
                raise CoworkerError("github_response_invalid", "GitHub returned an invalid repository list.", 502)
            repositories.extend(item for item in items if isinstance(item, dict))
            total = data.get("total_count", len(repositories))
            if type(total) is not int or total < len(repositories):
                raise CoworkerError("github_response_invalid", "GitHub returned an invalid repository count.", 502)
            if len(repositories) >= total:
                break
        else:
            raise CoworkerError("github_repository_limit", "This installation has too many repositories for the current bounded picker.", 413)
        result = []
        for item in repositories:
            repo_id, full_name, default_branch = item.get("id"), item.get("full_name"), item.get("default_branch")
            if type(repo_id) is not int or repo_id <= 0 or not isinstance(full_name, str) or not isinstance(default_branch, str):
                continue
            result.append({
                "id": repo_id,
                "full_name": full_name,
                "default_branch": default_branch,
                "private": bool(item.get("private")),
                "permissions": dict(item.get("permissions") or {}),
            })
        return result

    def list_repositories(self, owner: str, installation_record_id: str):
        self._enabled()
        with self.sessions() as db:
            installation = self._installation(db, owner, installation_record_id)
            installation_id = installation.installation_id
        token = self._user_token(owner, installation_record_id)
        return {
            "installation": installation_record_id,
            "repositories": self._list_repositories_for_user(token, installation_id),
        }

    def bind_repository(self, owner: str, project_id: str, installation_record_id: str, repository_id: int, expected_revision: int):
        self._enabled()
        if type(repository_id) is not int or repository_id <= 0 or type(expected_revision) is not int or expected_revision < 1:
            raise CoworkerError("github_repository_invalid", "Choose a valid repository and current project revision.", 422)
        with self.sessions() as db:
            project = self._project(db, owner, project_id)
            revision = project.revision
            installation = self._installation(db, owner, installation_record_id)
            installation_id = installation.installation_id
        if revision != expected_revision:
            raise CoworkerError("project_revision_conflict", "This project changed elsewhere. Refresh and review it before connecting a repository.", 409)
        access_token = self._user_token(owner, installation_record_id)
        repositories = self._list_repositories_for_user(access_token, installation_id)
        selected = next((item for item in repositories if item["id"] == repository_id), None)
        if selected is None:
            raise CoworkerError("github_repository_not_installed", "This repository is not available to the selected GitHub App installation or current GitHub user.", 403)
        repository_permissions = dict(selected.get("permissions") or {})
        app_permissions = dict(installation.permissions or {})
        if app_permissions.get("contents") not in {"read", "write"} or repository_permissions.get("pull") is not True:
            raise CoworkerError("github_contents_permission_missing", "This GitHub account and App installation do not both have repository read access.", 403)
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            project = self._project(db, owner, project_id)
            if project.revision != expected_revision:
                raise CoworkerError("project_revision_conflict", "This project changed while the repository was being connected. Refresh and retry.", 409)
            installation = self._installation(db, owner, installation_record_id)
            row = db.scalar(select(GitHubRepositoryBinding).where(
                GitHubRepositoryBinding.owner_id == owner,
                GitHubRepositoryBinding.project_id == project_id,
            ).with_for_update())
            if row is None:
                row = GitHubRepositoryBinding(
                    id=str(uuid4()),
                    owner_id=owner,
                    project_id=project_id,
                    installation_record_id=installation.id,
                    repository_id=repository_id,
                    full_name=selected["full_name"],
                    default_branch=selected["default_branch"],
                    permissions={"app": app_permissions, "repository": repository_permissions},
                    active=True,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
                db.add(row)
            else:
                row.installation_record_id = installation.id
                row.repository_id = repository_id
                row.full_name = selected["full_name"]
                row.default_branch = selected["default_branch"]
                row.permissions = {"app": app_permissions, "repository": repository_permissions}
                row.active = True
                row.updated_at = utcnow()
            ConversationRepository._audit(db, owner, project_id, "github.repository_connected")
            return self._binding_dto(row)

    @staticmethod
    def _binding_dto(row):
        permissions = dict(row.permissions or {})
        app_permissions = dict(permissions.get("app") or {})
        repository_permissions = dict(permissions.get("repository") or {})
        can_read = app_permissions.get("contents") in {"read", "write"} and repository_permissions.get("pull") is True
        can_write = app_permissions.get("contents") == "write" and repository_permissions.get("push") is True
        return {
            "id": row.id,
            "project_id": row.project_id,
            "installation_record_id": row.installation_record_id,
            "repository_id": row.repository_id,
            "full_name": row.full_name,
            "default_branch": row.default_branch,
            "permissions": permissions,
            "can_read_contents": can_read,
            "can_write_contents": can_write,
            "active": bool(row.active),
            "updated_at": iso(row.updated_at),
        }

    def get_repository(self, owner: str, project_id: str):
        self._enabled()
        with self.sessions() as db:
            self._project(db, owner, project_id)
            row = db.scalar(select(GitHubRepositoryBinding).where(
                GitHubRepositoryBinding.owner_id == owner,
                GitHubRepositoryBinding.project_id == project_id,
                GitHubRepositoryBinding.active.is_(True),
            ))
            if row is None:
                return {"repository": None}
            installation_active = db.scalar(select(GitHubInstallation.id).where(
                GitHubInstallation.id == row.installation_record_id,
                GitHubInstallation.owner_id == owner,
                GitHubInstallation.active.is_(True),
            ))
            if installation_active is None:
                return {"repository": None}
            return {"repository": self._binding_dto(row)}

    def disconnect_installation(self, owner: str, installation_record_id: str):
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            installation = db.scalar(select(GitHubInstallation).where(
                GitHubInstallation.id == installation_record_id,
                GitHubInstallation.owner_id == owner,
            ).with_for_update())
            if installation is None:
                raise not_found()
            installation.active = False
            installation.user_token_bundle_ciphertext = ""
            installation.updated_at = utcnow()
            db.execute(update(GitHubRepositoryBinding).where(
                GitHubRepositoryBinding.installation_record_id == installation_record_id,
                GitHubRepositoryBinding.owner_id == owner,
            ).values(active=False, updated_at=utcnow()))
            ConversationRepository._audit(db, owner, installation_record_id, "github.installation_disconnected")
        return {"message": "GitHub authorization and all repository bindings for this installation were disconnected."}

    def disconnect_repository(self, owner: str, project_id: str):
        with self.sessions.begin() as db:
            ConversationRepository._lock_account(db, owner)
            self._project(db, owner, project_id)
            row = db.scalar(select(GitHubRepositoryBinding).where(
                GitHubRepositoryBinding.owner_id == owner,
                GitHubRepositoryBinding.project_id == project_id,
            ).with_for_update())
            if row is not None:
                row.active = False
                row.updated_at = utcnow()
                ConversationRepository._audit(db, owner, project_id, "github.repository_disconnected")
        return {"message": "GitHub repository disconnected from this Fly project."}

    def _bound(self, owner: str, project_id: str):
        with self.sessions() as db:
            self._project(db, owner, project_id)
            row = db.scalar(select(GitHubRepositoryBinding).where(
                GitHubRepositoryBinding.owner_id == owner,
                GitHubRepositoryBinding.project_id == project_id,
                GitHubRepositoryBinding.active.is_(True),
            ))
            if row is None:
                raise not_found()
            installation = self._installation(db, owner, row.installation_record_id)
            return {
                "binding": self._binding_dto(row),
                "installation_id": installation.installation_id,
                "installation_record_id": installation.id,
            }

    def repository_tree(self, owner: str, project_id: str):
        self._enabled()
        bound = self._bound(owner, project_id)
        binding = bound["binding"]
        if not binding["can_read_contents"]:
            raise CoworkerError("github_contents_permission_missing", "The connected GitHub user and App do not have repository read access.", 403)
        token = self._user_token(owner, bound["installation_record_id"])
        full_name = binding["full_name"]
        branch = quote(binding["default_branch"], safe="")
        ref = self._api(
            "GET", f"/repos/{full_name}/git/ref/heads/{branch}", token,
        )
        commit_sha = (ref.get("object") or {}).get("sha")
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid branch revision.", 502)
        commit = self._api("GET", f"/repos/{full_name}/git/commits/{commit_sha}", token)
        tree_sha = (commit.get("tree") or {}).get("sha")
        if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid repository tree.", 502)
        tree = self._api(
            "GET", f"/repos/{full_name}/git/trees/{tree_sha}", token,
            params={"recursive": "1"},
        )
        entries = tree.get("tree")
        if not isinstance(entries, list):
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid repository tree.", 502)
        files = []
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            path = entry.get("path")
            if not isinstance(path, str):
                continue
            try:
                path = safe_repository_path(path)
            except CoworkerError:
                continue
            size = entry.get("size")
            sha = entry.get("sha")
            if type(size) is not int or size < 0 or size > self.settings.github_max_file_bytes:
                continue
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                continue
            files.append({"path": path, "sha": sha, "size": size})
            if len(files) >= self.settings.github_max_tree_files:
                break
        files.sort(key=lambda item: item["path"].casefold())
        return {
            "repository": binding["full_name"],
            "branch": binding["default_branch"],
            "commit_sha": commit_sha,
            "files": files,
            "truncated": bool(tree.get("truncated")) or len(files) >= self.settings.github_max_tree_files,
        }

    def read_repository_file(self, owner: str, project_id: str, path: str):
        self._enabled()
        path = safe_repository_path(path)
        bound = self._bound(owner, project_id)
        binding = bound["binding"]
        if not binding["can_read_contents"]:
            raise CoworkerError("github_contents_permission_missing", "The connected GitHub user and App do not have repository read access.", 403)
        token = self._user_token(owner, bound["installation_record_id"])
        full_name = binding["full_name"]
        branch = quote(binding["default_branch"], safe="")
        ref = self._api("GET", f"/repos/{full_name}/git/ref/heads/{branch}", token)
        commit_sha = (ref.get("object") or {}).get("sha")
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise CoworkerError("github_response_invalid", "GitHub returned an invalid branch revision.", 502)
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        data = self._api(
            "GET", f"/repos/{full_name}/contents/{encoded_path}", token,
            params={"ref": commit_sha},
        )
        if data.get("type") != "file" or data.get("encoding") != "base64":
            raise CoworkerError("github_file_type_unsupported", "Only regular text files can be imported into Fly.", 415)
        size = data.get("size")
        encoded = data.get("content")
        if type(size) is not int or size < 0 or size > self.settings.github_max_file_bytes or not isinstance(encoded, str):
            raise CoworkerError("github_file_too_large", "This repository file exceeds Fly's safe context limit.", 413)
        try:
            raw = base64.b64decode("".join(encoded.split()), validate=True)
            text = raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise CoworkerError("github_file_not_text", "This repository file is not valid UTF-8 text.", 415) from None
        if len(raw) != size or b"\x00" in raw:
            raise CoworkerError("github_file_not_text", "This repository file failed its content integrity check.", 415)
        digest = hashlib.sha256(raw).hexdigest()
        return {
            "repository": full_name,
            "branch": binding["default_branch"],
            "commit_sha": commit_sha,
            "path": path,
            "content": text,
            "sha256": digest,
            "byte_size": len(raw),
        }
