from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from .config import Settings
from .errors import CoworkerError
from .github_app import safe_repository_path
from .models import (
    Document,
    DocumentVersion,
    FlyWorkspaceManifest,
    GitHubRepositoryBinding,
    Project,
    ProjectResource,
    Workspace,
)
from .time import aware, utcnow


_EXCLUDED_PARTS = {
    ".git", "node_modules", ".next", ".nuxt", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".turbo", ".cache", "dist", "build", "coverage", "target",
}
_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")
_SECRET_NAMES = {"id_rsa", "id_ed25519", "credentials.json", "secrets.json"}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def validate_fly_path(value: str) -> str:
    try:
        path = safe_repository_path(value)
    except CoworkerError:
        raise
    except Exception as error:
        raise CoworkerError("fly_workspace_path_invalid", "The workspace path is not safe.", 422) from error
    parts = path.split("/")
    lowered = [part.casefold() for part in parts]
    filename = lowered[-1]
    if any(part in _EXCLUDED_PARTS for part in lowered):
        raise CoworkerError(
            "fly_workspace_path_excluded",
            "Dependency, build and cache directories cannot be added to the Fly workspace.",
            422,
        )
    if filename in _SECRET_NAMES or filename.endswith(_SECRET_SUFFIXES):
        raise CoworkerError(
            "fly_workspace_secret_path",
            "Credential and private-key files cannot be added to the Fly workspace.",
            422,
        )
    if "\x00" in path or "\\" in path:
        raise CoworkerError("fly_workspace_path_invalid", "The workspace path is not safe.", 422)
    return path


class FlyWorkspaceService:
    """Project-scoped logical manifest over existing private DocumentVersion objects."""

    def __init__(self, sessions, settings: Settings, storage, github):
        self.sessions = sessions
        self.settings = settings
        self.storage = storage
        self.github = github

    def _project(self, db, owner: str, project_id: str, *, lock: bool = False) -> Project:
        query = select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner,
            Project.deleted.is_(False),
        )
        if lock:
            query = query.with_for_update()
        project = db.scalar(query)
        if project is None:
            raise CoworkerError("project_not_found", "The Fly project was not found.", 404)
        return project

    def _binding(self, db, owner: str, project_id: str, *, lock: bool = False) -> GitHubRepositoryBinding:
        query = select(GitHubRepositoryBinding).where(
            GitHubRepositoryBinding.owner_id == owner,
            GitHubRepositoryBinding.project_id == project_id,
            GitHubRepositoryBinding.active.is_(True),
        )
        if lock:
            query = query.with_for_update()
        binding = db.scalar(query)
        if binding is None:
            raise CoworkerError("fly_repository_not_connected", "Connect a GitHub repository before using Fly coding.", 409)
        return binding

    def _version_record(self, db, owner: str, project_id: str, item):
        document = db.scalar(select(Document).where(
            Document.id == item.document_id,
            Document.owner_id == owner,
            Document.deleted.is_(False),
        ))
        if document is None:
            raise CoworkerError("fly_workspace_source_missing", "A saved workspace file is no longer available.", 409)
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == owner))
        if workspace is None or document.workspace_id != workspace.id:
            raise CoworkerError("fly_workspace_source_owner_mismatch", "A workspace file does not belong to this owner.", 403)
        version = db.scalar(select(DocumentVersion).where(
            DocumentVersion.id == item.version_id,
            DocumentVersion.document_id == document.id,
            DocumentVersion.owner_id == owner,
        ))
        if version is None or version.state != "uploaded":
            raise CoworkerError("fly_workspace_source_missing", "A saved workspace file version is unavailable.", 409)
        if aware(version.expires_at) <= utcnow():
            raise CoworkerError("fly_workspace_source_expired", "A saved workspace file has expired. Save it again before coding.", 409)
        if version.sha256 != item.sha256 or version.byte_size != item.byte_size:
            raise CoworkerError("fly_workspace_source_changed", "A saved workspace file no longer matches its recorded digest.", 409)
        linked = db.scalar(select(ProjectResource).where(
            ProjectResource.project_id == project_id,
            ProjectResource.owner_id == owner,
            ProjectResource.resource_type == "document",
            ProjectResource.resource_id == document.id,
        ))
        if linked is None:
            raise CoworkerError("fly_workspace_source_not_linked", "Every Fly workspace file must be linked to this project.", 403)
        return document, version

    def read_version(
        self,
        owner: str,
        document_id: str,
        version_id: str,
        *,
        expected_sha256: str | None = None,
        max_bytes: int | None = None,
    ) -> bytes:
        with self.sessions() as db:
            row = db.execute(
                select(DocumentVersion, Document).join(
                    Document, Document.id == DocumentVersion.document_id
                ).where(
                    DocumentVersion.id == version_id,
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.owner_id == owner,
                    Document.owner_id == owner,
                    Document.deleted.is_(False),
                    DocumentVersion.state == "uploaded",
                )
            ).first()
            if row is None:
                raise CoworkerError("fly_workspace_source_missing", "A saved workspace file version is unavailable.", 409)
            version, document = row
            if aware(version.expires_at) <= utcnow():
                raise CoworkerError("fly_workspace_source_expired", "A saved workspace file has expired.", 409)
            if expected_sha256 and version.sha256 != expected_sha256:
                raise CoworkerError("fly_workspace_source_changed", "A saved workspace file digest has changed.", 409)
            object_key, digest, size = version.object_key, version.sha256, version.byte_size
        limit = max_bytes or self.settings.fly_max_workspace_file_bytes
        data = self.storage.get(object_key, max_bytes=limit)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise CoworkerError("fly_workspace_object_integrity_failed", "A saved workspace file failed its integrity check.", 409)
        return data

    def get(self, owner: str, project_id: str) -> dict[str, Any]:
        with self.sessions() as db:
            self._project(db, owner, project_id)
            manifest = db.scalar(select(FlyWorkspaceManifest).where(
                FlyWorkspaceManifest.owner_id == owner,
                FlyWorkspaceManifest.project_id == project_id,
            ))
            if manifest is None:
                return {
                    "project_id": project_id,
                    "revision": 0,
                    "sha256": "",
                    "repository": "",
                    "branch": "",
                    "commit_sha": "",
                    "files": [],
                }
            snapshot = {
                "project_id": project_id,
                "revision": manifest.revision,
                "sha256": manifest.sha256,
                "repository": manifest.repository,
                "branch": manifest.branch,
                "commit_sha": manifest.commit_sha,
                "files": list(manifest.files or []),
            }
        files = []
        total = 0
        for item in snapshot["files"]:
            path = validate_fly_path(item["path"])
            content_bytes = self.read_version(
                owner,
                item["document_id"],
                item["version_id"],
                expected_sha256=item["sha256"],
                max_bytes=self.settings.fly_max_workspace_file_bytes,
            )
            total += len(content_bytes)
            if total > self.settings.fly_max_workspace_bytes:
                raise CoworkerError("fly_workspace_too_large", "The saved Fly workspace exceeds its size limit.", 413)
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError as error:
                raise CoworkerError("fly_workspace_binary_file", "Fly coding currently accepts UTF-8 text files only.", 422) from error
            if "\x00" in content:
                raise CoworkerError("fly_workspace_binary_file", "Fly coding currently accepts UTF-8 text files only.", 422)
            files.append({
                **item,
                "path": path,
                "content": content,
            })
        return {**snapshot, "files": files}

    def sync(self, owner: str, project_id: str, request) -> dict[str, Any]:
        if not self.settings.fly_code_generation_enabled:
            raise CoworkerError("fly_code_generation_disabled", "Fly repository coding is not enabled for this environment.", 503)
        from .fly_code_schemas import FlyWorkspaceSync

        payload = request if isinstance(request, FlyWorkspaceSync) else FlyWorkspaceSync.model_validate(request)
        if len(payload.files) > self.settings.fly_max_workspace_files:
            raise CoworkerError("fly_workspace_file_limit", "The Fly workspace contains too many files.", 413)

        validated = []
        total = 0
        with self.sessions() as db:
            self._project(db, owner, project_id)
            binding = self._binding(db, owner, project_id)
            if payload.repository != binding.full_name or payload.branch != binding.default_branch:
                raise CoworkerError("fly_workspace_repository_mismatch", "The workspace must match the connected repository and its default branch.", 409)
            if db.scalar(select(Workspace.id).where(Workspace.owner_id == owner)) is None:
                raise CoworkerError("workspace_not_found", "The owner workspace was not found.", 404)
            for item in payload.files:
                path = validate_fly_path(item.path)
                document, version = self._version_record(db, owner, project_id, item)
                total += version.byte_size
                if version.byte_size > self.settings.fly_max_workspace_file_bytes:
                    raise CoworkerError("fly_workspace_file_too_large", f"{path} exceeds the per-file workspace limit.", 413)
                if total > self.settings.fly_max_workspace_bytes:
                    raise CoworkerError("fly_workspace_too_large", "The Fly workspace exceeds its total size limit.", 413)
                validated.append({
                    "path": path,
                    "document_id": document.id,
                    "version_id": version.id,
                    "sha256": version.sha256,
                    "byte_size": version.byte_size,
                    "origin": item.origin.model_dump(mode="json") if item.origin else None,
                    "object_key": version.object_key,
                    "expires_at": version.expires_at,
                })

        # Verify bytes and original GitHub provenance outside the DB transaction.
        for item in validated:
            data = self.storage.get(item["object_key"], max_bytes=self.settings.fly_max_workspace_file_bytes)
            if len(data) != item["byte_size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise CoworkerError("fly_workspace_object_integrity_failed", f"{item['path']} failed its saved-file integrity check.", 409)
            try:
                decoded = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise CoworkerError("fly_workspace_binary_file", f"{item['path']} is not UTF-8 text.", 422) from error
            if "\x00" in decoded:
                raise CoworkerError("fly_workspace_binary_file", f"{item['path']} is not UTF-8 text.", 422)
            origin = item["origin"]
            if origin:
                remote = self.github.read_repository_file(owner, project_id, item["path"], payload.commit_sha)
                if (
                    remote.get("repository") != payload.repository
                    or remote.get("branch") != payload.branch
                    or remote.get("commit_sha") != payload.commit_sha
                    or remote.get("blob_sha") != origin["blob_sha"]
                    or remote.get("sha256") != origin["source_sha256"]
                ):
                    raise CoworkerError("fly_workspace_source_provenance_mismatch", f"GitHub provenance for {item['path']} could not be verified.", 409)
            item.pop("object_key", None)
            item.pop("expires_at", None)

        files = sorted(validated, key=lambda item: item["path"])
        manifest_sha = canonical_sha256({
            "repository": payload.repository,
            "branch": payload.branch,
            "commit_sha": payload.commit_sha,
            "files": files,
        })
        now = utcnow()
        retain_until = now + timedelta(seconds=self.settings.fly_workspace_file_ttl_seconds)
        with self.sessions() as db, db.begin():
            self._project(db, owner, project_id, lock=True)
            self._binding(db, owner, project_id, lock=True)
            manifest = db.scalar(select(FlyWorkspaceManifest).where(
                FlyWorkspaceManifest.owner_id == owner,
                FlyWorkspaceManifest.project_id == project_id,
            ).with_for_update())
            current_revision = manifest.revision if manifest else 0
            if current_revision != payload.expected_revision:
                raise CoworkerError("fly_workspace_revision_conflict", "The Fly workspace changed. Reload it before syncing.", 409)
            for item in payload.files:
                version = db.scalar(select(DocumentVersion).where(
                    DocumentVersion.id == item.version_id,
                    DocumentVersion.document_id == item.document_id,
                    DocumentVersion.owner_id == owner,
                ).with_for_update())
                if version is None or version.state != "uploaded" or aware(version.expires_at) <= now:
                    raise CoworkerError("fly_workspace_source_changed", "A saved workspace version changed during sync.", 409)
                version.expires_at = max(aware(version.expires_at), retain_until)
            if manifest and manifest.sha256 == manifest_sha:
                return self._manifest_summary(manifest)
            if manifest is None:
                manifest = FlyWorkspaceManifest(
                    id=str(uuid4()),
                    owner_id=owner,
                    project_id=project_id,
                    revision=1,
                    repository=payload.repository,
                    branch=payload.branch,
                    commit_sha=payload.commit_sha,
                    files=files,
                    sha256=manifest_sha,
                    created_at=now,
                    updated_at=now,
                )
                db.add(manifest)
            else:
                manifest.revision += 1
                manifest.repository = payload.repository
                manifest.branch = payload.branch
                manifest.commit_sha = payload.commit_sha
                manifest.files = files
                manifest.sha256 = manifest_sha
                manifest.updated_at = now
            db.flush()
            return self._manifest_summary(manifest)

    @staticmethod
    def _manifest_summary(manifest: FlyWorkspaceManifest) -> dict[str, Any]:
        return {
            "project_id": manifest.project_id,
            "revision": manifest.revision,
            "sha256": manifest.sha256,
            "repository": manifest.repository,
            "branch": manifest.branch,
            "commit_sha": manifest.commit_sha,
            "files": [
                {
                    "path": item["path"],
                    "sha256": item["sha256"],
                    "byte_size": item["byte_size"],
                    "origin": item.get("origin"),
                }
                for item in (manifest.files or [])
            ],
        }
