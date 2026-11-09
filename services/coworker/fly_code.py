from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select

from .agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
from .config import Settings
from .errors import CoworkerError
from .fly_code_schemas import FlyPatchGenerateRequest, FlyPatchModelOutput, FlyPatchReviewRequest
from .fly_workspace import canonical_json, canonical_sha256, validate_fly_path
from .models import (
    Account,
    AuditEvent,
    Document,
    DocumentVersion,
    FlyPatchProposal,
    FlyPatchReview,
    FlyWorkspaceManifest,
    Project,
    ProjectResource,
    Workspace,
)
from .provider_capacity import acquire_provider_lease, settle_provider_lease
from .time import aware, utcnow


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FlyCodeService:
    """Human-gated repository patch generation, review and application."""

    def __init__(self, sessions, settings: Settings, storage, workspace, sandbox=None, planner=None):
        self.sessions = sessions
        self.settings = settings
        self.storage = storage
        self.workspace = workspace
        self.sandbox = sandbox
        self.planner = planner or DeepSeekAgentPlanner(settings)

    def _require_generation(self) -> None:
        if not self.settings.fly_code_generation_enabled:
            raise CoworkerError("fly_code_generation_disabled", "Fly repository code generation is not enabled.", 503)

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

    def _manifest(self, db, owner: str, project_id: str, *, lock: bool = False) -> FlyWorkspaceManifest:
        query = select(FlyWorkspaceManifest).where(
            FlyWorkspaceManifest.owner_id == owner,
            FlyWorkspaceManifest.project_id == project_id,
        )
        if lock:
            query = query.with_for_update()
        manifest = db.scalar(query)
        if manifest is None:
            raise CoworkerError("fly_workspace_empty", "Save repository files to the Fly workspace before generating code.", 409)
        return manifest

    def _proposal(self, db, owner: str, project_id: str, proposal_id: str, *, lock: bool = False) -> FlyPatchProposal:
        query = select(FlyPatchProposal).where(
            FlyPatchProposal.id == proposal_id,
            FlyPatchProposal.owner_id == owner,
            FlyPatchProposal.project_id == project_id,
        )
        if lock:
            query = query.with_for_update()
        proposal = db.scalar(query)
        if proposal is None:
            raise CoworkerError("fly_patch_not_found", "The Fly patch proposal was not found.", 404)
        return proposal

    @staticmethod
    def _review_digest(proposal_id: str, owner: str, project_id: str, base_revision: int,
                       base_manifest_sha256: str, base_commit_sha: str, patch_sha256: str) -> str:
        return canonical_sha256({
            "schema_version": 1,
            "proposal_id": proposal_id,
            "owner_id": owner,
            "project_id": project_id,
            "base_revision": base_revision,
            "base_manifest_sha256": base_manifest_sha256,
            "base_commit_sha": base_commit_sha,
            "patch_sha256": patch_sha256,
        })

    def _make_snapshot(
        self,
        proposal_id: str,
        instruction: str,
        workspace: dict,
        output: FlyPatchModelOutput,
    ) -> tuple[dict, list[dict]]:
        current = {item["path"]: item for item in workspace["files"]}
        seen: set[str] = set()
        changes: list[dict] = []
        summaries: list[dict] = []
        total_after_bytes = 0
        for change in output.changes:
            path = validate_fly_path(change.path)
            if path in seen:
                raise CoworkerError("fly_patch_duplicate_path", "A patch cannot change the same path more than once.", 422)
            seen.add(path)
            before = current.get(path)
            if change.operation == "create" and before is not None:
                raise CoworkerError("fly_patch_create_exists", f"{path} already exists in the Fly workspace.", 422)
            if change.operation in {"update", "delete"} and before is None:
                raise CoworkerError("fly_patch_source_missing", f"{path} is not present in the Fly workspace.", 422)
            before_meta = None
            if before is not None:
                before_meta = {
                    "document_id": before["document_id"],
                    "version_id": before["version_id"],
                    "sha256": before["sha256"],
                    "byte_size": before["byte_size"],
                    "origin": before.get("origin"),
                }
            after_content = change.content
            after_sha256 = None
            after_bytes = 0
            if change.operation in {"create", "update"}:
                encoded = (after_content or "").encode("utf-8")
                if not encoded or len(encoded) > self.settings.fly_max_workspace_file_bytes or b"\x00" in encoded:
                    raise CoworkerError("fly_patch_file_limit", f"{path} has empty, binary or oversized replacement content.", 413)
                if before is not None and before["content"] == after_content:
                    raise CoworkerError("fly_patch_noop", f"{path} contains no effective change.", 422)
                after_sha256 = hashlib.sha256(encoded).hexdigest()
                after_bytes = len(encoded)
                total_after_bytes += after_bytes
            changes.append({
                "path": path,
                "operation": change.operation,
                "rationale": change.rationale,
                "before": before_meta,
                "after_content": after_content,
                "after_sha256": after_sha256,
                "after_byte_size": after_bytes,
            })
            summaries.append({
                "path": path,
                "operation": change.operation,
                "rationale": change.rationale,
                "before_sha256": before_meta["sha256"] if before_meta else None,
                "after_sha256": after_sha256,
                "after_byte_size": after_bytes,
            })
        if len(changes) > self.settings.fly_max_patch_files or total_after_bytes > self.settings.fly_max_patch_bytes:
            raise CoworkerError("fly_patch_size_limit", "The generated multi-file patch exceeds its configured limits.", 413)
        snapshot = {
            "schema_version": 1,
            "proposal_id": proposal_id,
            "instruction": instruction,
            "summary": output.summary,
            "base": {
                "revision": workspace["revision"],
                "manifest_sha256": workspace["sha256"],
                "commit_sha": workspace["commit_sha"],
            },
            "changes": changes,
        }
        return snapshot, summaries

    async def generate(self, owner: str, project_id: str, request, idempotency_key: str) -> dict:
        self._require_generation()
        payload = request if isinstance(request, FlyPatchGenerateRequest) else FlyPatchGenerateRequest.model_validate(request)
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
            raise CoworkerError("idempotency_key_invalid", "Provide a valid Fly proposal idempotency key.", 422)
        return await self._generate(owner, project_id, payload, idempotency_key)

    async def _generate(
        self,
        owner: str,
        project_id: str,
        payload: FlyPatchGenerateRequest,
        idempotency_key: str,
        *,
        repair_context: dict | None = None,
        repair_of_execution_id: str | None = None,
        repair_root_proposal_id: str | None = None,
        repair_attempt: int = 0,
    ) -> dict:
        workspace = self.workspace.get(owner, project_id)
        if workspace["revision"] != payload.expected_revision or not workspace["sha256"]:
            raise CoworkerError("fly_workspace_revision_conflict", "The Fly workspace changed. Reload it before generating a patch.", 409)
        if not workspace["files"]:
            raise CoworkerError("fly_workspace_empty", "Import and save at least one file before generating a patch.", 409)
        files = [{"path": item["path"], "content": item["content"]} for item in workspace["files"]]
        context_bytes = len(payload.instruction.encode("utf-8")) + sum(
            len(item["path"].encode("utf-8")) + len(item["content"].encode("utf-8"))
            for item in files
        )
        if context_bytes > self.settings.fly_max_model_context_bytes:
            raise CoworkerError("fly_model_context_limit", "The selected Fly files exceed the model context limit. Reduce the workspace selection and retry.", 413)
        fingerprint = canonical_sha256({
            "instruction": payload.instruction,
            "revision": workspace["revision"],
            "manifest_sha256": workspace["sha256"],
            "repair_context_sha256": canonical_sha256(repair_context) if repair_context else "",
        })
        now = utcnow()
        proposal_id = str(uuid4())
        reserve = self.settings.fly_model_reservation_tokens
        existing_id = None
        with self.sessions() as db, db.begin():
            self._project(db, owner, project_id, lock=True)
            manifest = self._manifest(db, owner, project_id, lock=True)
            if manifest.revision != payload.expected_revision or manifest.sha256 != workspace["sha256"]:
                raise CoworkerError("fly_workspace_revision_conflict", "The Fly workspace changed during proposal preparation.", 409)
            existing = db.scalar(select(FlyPatchProposal).where(
                FlyPatchProposal.owner_id == owner,
                FlyPatchProposal.project_id == project_id,
                FlyPatchProposal.idempotency_key == idempotency_key,
            ).with_for_update())
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise CoworkerError("idempotency_conflict", "This Fly proposal key was already used for different input.", 409)
                if existing.state in {"unreviewed", "applied"}:
                    existing_id = existing.id
                else:
                    raise CoworkerError("fly_proposal_replay", "This Fly proposal key already has a terminal or in-progress result. Use a new key to retry.", 409)
            else:
                proposal = FlyPatchProposal(
                    id=proposal_id,
                    owner_id=owner,
                    project_id=project_id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                    base_revision=workspace["revision"],
                    base_manifest_sha256=workspace["sha256"],
                    base_commit_sha=workspace["commit_sha"],
                    instruction=payload.instruction,
                    state="generating",
                    repair_of_execution_id=repair_of_execution_id,
                    repair_root_proposal_id=repair_root_proposal_id or proposal_id,
                    repair_attempt=repair_attempt,
                    reserved_tokens=reserve,
                    created_at=now,
                    expires_at=now + timedelta(seconds=self.settings.fly_proposal_ttl_seconds),
                )
                db.add(proposal)
                db.flush()
                acquire_provider_lease(
                    db,
                    self.settings,
                    owner_id=owner,
                    kind="fly_patch",
                    resource_id=proposal_id,
                    sequence=1,
                    reserved_tokens=reserve,
                )
        if existing_id:
            return self.get_proposal(owner, project_id, existing_id)

        usage_tokens = None
        object_key = ""
        stored = False
        ready = False
        try:
            output, usage_tokens = await self.planner.propose_repository_patch(
                payload.instruction,
                files,
                repair_context=repair_context,
            )
            snapshot, summaries = self._make_snapshot(proposal_id, payload.instruction, workspace, output)
            patch_bytes = canonical_json(snapshot)
            if len(patch_bytes) > self.settings.fly_max_patch_bytes:
                raise CoworkerError("fly_patch_size_limit", "The generated patch exceeds the configured storage limit.", 413)
            patch_sha256 = hashlib.sha256(patch_bytes).hexdigest()
            review_sha256 = self._review_digest(
                proposal_id, owner, project_id, workspace["revision"],
                workspace["sha256"], workspace["commit_sha"], patch_sha256,
            )
            object_key = f"{owner}/fly-patches/{proposal_id}/{patch_sha256}.json"
            self.storage.put(object_key, patch_bytes, "application/json")
            stored = True
            with self.sessions() as db, db.begin():
                proposal = self._proposal(db, owner, project_id, proposal_id, lock=True)
                manifest = self._manifest(db, owner, project_id, lock=True)
                if (
                    proposal.state != "generating"
                    or manifest.revision != proposal.base_revision
                    or manifest.sha256 != proposal.base_manifest_sha256
                    or aware(proposal.expires_at) <= utcnow()
                ):
                    raise CoworkerError("fly_workspace_revision_conflict", "The Fly workspace changed while the model was generating the patch.", 409)
                proposal.summary = output.summary
                proposal.file_summaries = summaries
                proposal.patch_object_key = object_key
                proposal.patch_sha256 = patch_sha256
                proposal.patch_bytes = len(patch_bytes)
                proposal.review_sha256 = review_sha256
                proposal.state = "unreviewed"
            ready = True
        except BaseException:
            if stored and object_key and not ready:
                try:
                    self.storage.delete(object_key)
                except Exception:
                    pass
            with self.sessions() as db, db.begin():
                proposal = db.scalar(select(FlyPatchProposal).where(
                    FlyPatchProposal.id == proposal_id,
                    FlyPatchProposal.owner_id == owner,
                    FlyPatchProposal.project_id == project_id,
                ).with_for_update())
                if proposal is not None and proposal.state == "generating":
                    proposal.state = "failed"
                    proposal.patch_object_key = ""
            raise
        finally:
            with self.sessions() as db, db.begin():
                settle_provider_lease(
                    db,
                    kind="fly_patch",
                    resource_id=proposal_id,
                    sequence=1,
                    actual_tokens=usage_tokens,
                )
        return self.get_proposal(owner, project_id, proposal_id)

    def _expire_due(self, owner: str, project_id: str) -> None:
        now = utcnow()
        object_keys: list[str] = []
        with self.sessions() as db, db.begin():
            rows = db.scalars(select(FlyPatchProposal).where(
                FlyPatchProposal.owner_id == owner,
                FlyPatchProposal.project_id == project_id,
                FlyPatchProposal.expires_at <= now,
                FlyPatchProposal.patch_object_key != "",
            ).with_for_update()).all()
            for row in rows:
                if row.state in {"generating", "unreviewed"}:
                    row.state = "expired"
                object_keys.append(row.patch_object_key)
                row.patch_object_key = ""
        for key in object_keys:
            try:
                self.storage.delete(key)
            except Exception:
                # The orphan sweeper will remove unreferenced private objects.
                pass

    def list_proposals(self, owner: str, project_id: str) -> list[dict]:
        self._expire_due(owner, project_id)
        with self.sessions() as db:
            self._project(db, owner, project_id)
            rows = db.scalars(select(FlyPatchProposal).where(
                FlyPatchProposal.owner_id == owner,
                FlyPatchProposal.project_id == project_id,
            ).order_by(FlyPatchProposal.created_at.desc()).limit(20)).all()
            reviews = {
                item.proposal_id: item
                for item in db.scalars(select(FlyPatchReview).where(
                    FlyPatchReview.owner_id == owner,
                    FlyPatchReview.project_id == project_id,
                )).all()
            }
            return [self._summary(row, reviews.get(row.id)) for row in rows]

    @staticmethod
    def _summary(proposal: FlyPatchProposal, review: FlyPatchReview | None = None) -> dict:
        return {
            "id": proposal.id,
            "state": proposal.state,
            "summary": proposal.summary,
            "base_revision": proposal.base_revision,
            "base_manifest_sha256": proposal.base_manifest_sha256,
            "review_sha256": proposal.review_sha256,
            "file_summaries": list(proposal.file_summaries or []),
            "repair_of_execution_id": proposal.repair_of_execution_id,
            "repair_attempt": proposal.repair_attempt,
            "review": {
                "decision": review.decision,
                "review_sha256": review.review_sha256,
                "expires_at": review.expires_at.isoformat(),
                "revoked_at": review.revoked_at.isoformat() if review.revoked_at else None,
            } if review else None,
            "created_at": proposal.created_at.isoformat(),
            "expires_at": proposal.expires_at.isoformat(),
            "applied_revision": proposal.applied_revision,
        }

    def _load_patch(self, proposal: FlyPatchProposal) -> dict:
        if not proposal.patch_object_key:
            raise CoworkerError("fly_patch_payload_expired", "The exact patch payload is no longer available.", 410)
        raw = self.storage.get(
            proposal.patch_object_key,
            max_bytes=self.settings.fly_max_patch_bytes + 8192,
        )
        if len(raw) != proposal.patch_bytes or hashlib.sha256(raw).hexdigest() != proposal.patch_sha256:
            raise CoworkerError("fly_patch_integrity_failed", "The stored Fly patch failed its integrity check.", 409)
        try:
            snapshot = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CoworkerError("fly_patch_integrity_failed", "The stored Fly patch is not valid UTF-8 JSON.", 409) from error
        expected_review = self._review_digest(
            proposal.id, proposal.owner_id, proposal.project_id, proposal.base_revision,
            proposal.base_manifest_sha256, proposal.base_commit_sha, proposal.patch_sha256,
        )
        if (
            snapshot.get("proposal_id") != proposal.id
            or snapshot.get("base", {}).get("revision") != proposal.base_revision
            or snapshot.get("base", {}).get("manifest_sha256") != proposal.base_manifest_sha256
            or expected_review != proposal.review_sha256
        ):
            raise CoworkerError("fly_patch_integrity_failed", "The Fly patch no longer matches its approved review digest.", 409)
        return snapshot

    def get_proposal(self, owner: str, project_id: str, proposal_id: str) -> dict:
        self._expire_due(owner, project_id)
        with self.sessions() as db:
            self._project(db, owner, project_id)
            proposal = self._proposal(db, owner, project_id, proposal_id)
            review = db.get(FlyPatchReview, proposal_id)
            summary = self._summary(proposal, review)
            snapshot = self._load_patch(proposal) if proposal.patch_object_key else None
        if snapshot is None:
            return summary | {"changes": []}
        changes = []
        for item in snapshot["changes"]:
            before = item.get("before")
            before_text = ""
            if before:
                before_bytes = self.workspace.read_version(
                    owner,
                    before["document_id"],
                    before["version_id"],
                    expected_sha256=before["sha256"],
                    max_bytes=self.settings.fly_max_workspace_file_bytes,
                )
                before_text = before_bytes.decode("utf-8")
            after_text = item.get("after_content") or ""
            diff = "".join(difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile=f"a/{item['path']}" if before else "/dev/null",
                tofile=f"b/{item['path']}" if item["operation"] != "delete" else "/dev/null",
                n=3,
            ))
            changes.append({
                "path": item["path"],
                "operation": item["operation"],
                "rationale": item["rationale"],
                "before_sha256": before["sha256"] if before else None,
                "after_sha256": item.get("after_sha256"),
                "diff": diff,
            })
        return summary | {"changes": changes}

    def review(self, owner: str, project_id: str, proposal_id: str, request) -> dict:
        payload = request if isinstance(request, FlyPatchReviewRequest) else FlyPatchReviewRequest.model_validate(request)
        object_to_delete = ""
        now = utcnow()
        with self.sessions() as db, db.begin():
            self._project(db, owner, project_id, lock=True)
            manifest = self._manifest(db, owner, project_id, lock=True)
            proposal = self._proposal(db, owner, project_id, proposal_id, lock=True)
            if proposal.state != "unreviewed" or aware(proposal.expires_at) <= now:
                raise CoworkerError("fly_patch_not_reviewable", "This Fly patch is no longer available for review.", 409)
            if manifest.revision != proposal.base_revision or manifest.sha256 != proposal.base_manifest_sha256:
                raise CoworkerError("fly_workspace_revision_conflict", "The workspace changed after this patch was generated. Generate a fresh patch.", 409)
            if payload.review_sha256 != proposal.review_sha256:
                raise CoworkerError("fly_review_digest_mismatch", "The reviewed digest does not match the exact patch.", 409)
            review = db.get(FlyPatchReview, proposal_id)
            if review is not None and aware(review.expires_at) > now:
                if review.decision == payload.decision and review.review_sha256 == payload.review_sha256 and review.revoked_at is None:
                    return self._summary(proposal, review)
                raise CoworkerError("fly_review_already_recorded", "A different review decision is already recorded for this patch.", 409)
            expires_at = min(aware(proposal.expires_at), now + timedelta(seconds=self.settings.fly_review_ttl_seconds))
            if review is None:
                review = FlyPatchReview(
                    proposal_id=proposal_id,
                    owner_id=owner,
                    project_id=project_id,
                    review_sha256=payload.review_sha256,
                    decision=payload.decision,
                    decided_at=now,
                    expires_at=expires_at,
                    revoked_at=None,
                )
                db.add(review)
            else:
                review.review_sha256 = payload.review_sha256
                review.decision = payload.decision
                review.decided_at = now
                review.expires_at = expires_at
                review.revoked_at = None
            if payload.decision == "reject":
                proposal.state = "rejected"
                object_to_delete = proposal.patch_object_key
                proposal.patch_object_key = ""
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=proposal_id,
                action="fly_patch_approved" if payload.decision == "approve" else "fly_patch_rejected",
            ))
            result = self._summary(proposal, review)
        if object_to_delete:
            try:
                self.storage.delete(object_to_delete)
            except Exception:
                pass
        return result

    def apply(self, owner: str, project_id: str, proposal_id: str, review_sha256: str) -> dict:
        if not isinstance(review_sha256, str) or not _SHA256.fullmatch(review_sha256):
            raise CoworkerError("fly_review_digest_invalid", "The exact review digest is required to apply this patch.", 422)
        preflight_applied = False
        with self.sessions() as db:
            self._project(db, owner, project_id)
            proposal = self._proposal(db, owner, project_id, proposal_id)
            if proposal.state == "applied":
                preflight_applied = True
            review = db.get(FlyPatchReview, proposal_id) if not preflight_applied else None
            if not preflight_applied:
                if review is None or review.decision != "approve" or review.revoked_at is not None:
                    raise CoworkerError("fly_patch_approval_required", "Approve the exact diff before applying it.", 403)
                if review.review_sha256 != review_sha256 or proposal.review_sha256 != review_sha256:
                    raise CoworkerError("fly_review_digest_mismatch", "The approval does not match this exact patch.", 409)
                if aware(review.expires_at) <= utcnow() or aware(proposal.expires_at) <= utcnow():
                    raise CoworkerError("fly_patch_approval_expired", "The patch approval expired. Review the exact diff again.", 409)
                snapshot = self._load_patch(proposal)
            else:
                snapshot = None

        if preflight_applied:
            return self.workspace.get(owner, project_id)

        planned_objects: list[dict] = []
        uploaded_keys: list[str] = []
        already_applied = False
        applied = False
        try:
            for item in snapshot["changes"]:
                if item["operation"] == "delete":
                    continue
                content = item["after_content"]
                data = content.encode("utf-8")
                digest = hashlib.sha256(data).hexdigest()
                if (
                    len(data) > self.settings.fly_max_workspace_file_bytes
                    or len(data) != item.get("after_byte_size")
                    or digest != item.get("after_sha256")
                    or b"\x00" in data
                ):
                    raise CoworkerError("fly_patch_integrity_failed", f"{item['path']} no longer matches its generated after-digest.", 409)
                version_id = str(uuid4())
                object_key = f"{owner}/inputs/{version_id}/{digest}"
                self.storage.put(object_key, data, "text/plain; charset=utf-8")
                uploaded_keys.append(object_key)
                planned_objects.append({
                    "path": item["path"],
                    "operation": item["operation"],
                    "document_id": item["before"]["document_id"] if item.get("before") else str(uuid4()),
                    "version_id": version_id,
                    "object_key": object_key,
                    "sha256": digest,
                    "byte_size": len(data),
                    "kind": PurePosixPath(item["path"]).suffix.lstrip(".").lower()[:10] or "txt",
                    "filename": self._document_filename(proposal_id, item["path"]),
                    "origin": item["before"].get("origin") if item.get("before") else None,
                })

            now = utcnow()
            retain_until = now + timedelta(seconds=self.settings.fly_workspace_file_ttl_seconds)
            with self.sessions() as db, db.begin():
                account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
                if account is None:
                    raise CoworkerError("account_not_found", "The owner account was not found.", 404)
                project = self._project(db, owner, project_id, lock=True)
                manifest = self._manifest(db, owner, project_id, lock=True)
                proposal = self._proposal(db, owner, project_id, proposal_id, lock=True)
                review = db.get(FlyPatchReview, proposal_id)
                if proposal.state == "applied":
                    already_applied = True
                else:
                    if proposal.state != "unreviewed" or aware(proposal.expires_at) <= now:
                        raise CoworkerError("fly_patch_not_applicable", "This Fly patch is no longer applicable.", 409)
                    if (
                        review is None or review.decision != "approve" or review.revoked_at is not None
                        or review.review_sha256 != review_sha256 or aware(review.expires_at) <= now
                    ):
                        raise CoworkerError("fly_patch_approval_required", "A current approval for the exact diff is required.", 403)
                    if manifest.revision != proposal.base_revision or manifest.sha256 != proposal.base_manifest_sha256:
                        raise CoworkerError("fly_workspace_revision_conflict", "The workspace changed after review. Generate a fresh patch.", 409)
                    current = {item["path"]: item for item in (manifest.files or [])}
                    planned_by_path = {item["path"]: item for item in planned_objects}
                    updated_files = dict(current)
                    total_new_bytes = sum(item["byte_size"] for item in planned_objects)
                    if account.storage_bytes + total_new_bytes > self.settings.max_account_bytes:
                        raise CoworkerError("storage_limit", "Applying this patch would exceed the workspace storage limit.", 429)
                    new_document_count = sum(1 for item in planned_objects if item["operation"] == "create")
                    document_count = int(db.scalar(select(func.count()).select_from(Document).where(
                        Document.owner_id == owner,
                        Document.deleted.is_(False),
                    )) or 0)
                    if document_count + new_document_count > 100:
                        raise CoworkerError("document_limit", "Applying this patch would exceed the workspace file limit.", 429)
                    resource_count = int(db.scalar(select(func.count()).select_from(ProjectResource).where(
                        ProjectResource.project_id == project_id,
                        ProjectResource.owner_id == owner,
                    )) or 0)
                    if resource_count + new_document_count > 1000:
                        raise CoworkerError("project_resource_limit", "Applying this patch would exceed the project resource limit.", 429)

                    for change in snapshot["changes"]:
                        path = change["path"]
                        before = change.get("before")
                        current_item = current.get(path)
                        if change["operation"] == "create":
                            if current_item is not None:
                                raise CoworkerError("fly_workspace_revision_conflict", f"{path} already exists.", 409)
                        else:
                            if (
                                current_item is None
                                or before is None
                                or current_item["document_id"] != before["document_id"]
                                or current_item["version_id"] != before["version_id"]
                                or current_item["sha256"] != before["sha256"]
                            ):
                                raise CoworkerError("fly_workspace_source_changed", f"{path} changed after the patch was generated.", 409)
                        if change["operation"] == "delete":
                            updated_files.pop(path, None)
                            remaining_doc_refs = any(
                                value["document_id"] == current_item["document_id"]
                                for value in updated_files.values()
                            )
                            if not remaining_doc_refs:
                                link = db.scalar(select(ProjectResource).where(
                                    ProjectResource.project_id == project_id,
                                    ProjectResource.owner_id == owner,
                                    ProjectResource.resource_type == "document",
                                    ProjectResource.resource_id == current_item["document_id"],
                                ))
                                if link is not None:
                                    db.delete(link)
                            continue

                        plan = planned_by_path[path]
                        if change["operation"] == "create":
                            workspace = db.scalar(select(Workspace).where(Workspace.owner_id == owner))
                            if workspace is None:
                                raise CoworkerError("workspace_not_found", "The owner workspace was not found.", 404)
                            document = Document(
                                id=plan["document_id"],
                                owner_id=owner,
                                workspace_id=workspace.id,
                                filename=plan["filename"],
                            )
                            db.add(document)
                            db.flush()
                            db.add(ProjectResource(
                                project_id=project_id,
                                owner_id=owner,
                                resource_type="document",
                                resource_id=document.id,
                            ))
                            version_number = 1
                        else:
                            document = db.scalar(select(Document).where(
                                Document.id == plan["document_id"],
                                Document.owner_id == owner,
                                Document.deleted.is_(False),
                            ).with_for_update())
                            if document is None:
                                raise CoworkerError("fly_workspace_source_missing", "A source document disappeared during patch application.", 409)
                            latest_version = int(db.scalar(select(func.max(DocumentVersion.version)).where(
                                DocumentVersion.document_id == document.id,
                                DocumentVersion.owner_id == owner,
                            )) or 0)
                            version_number = latest_version + 1
                        db.add(DocumentVersion(
                            id=plan["version_id"],
                            document_id=plan["document_id"],
                            owner_id=owner,
                            version=version_number,
                            kind=plan["kind"],
                            byte_size=plan["byte_size"],
                            sha256=plan["sha256"],
                            object_key=plan["object_key"],
                            state="uploaded",
                            expires_at=retain_until,
                        ))
                        updated_files[path] = {
                            "path": path,
                            "document_id": plan["document_id"],
                            "version_id": plan["version_id"],
                            "sha256": plan["sha256"],
                            "byte_size": plan["byte_size"],
                            "origin": plan["origin"],
                        }

                    manifest.files = sorted(updated_files.values(), key=lambda value: value["path"])
                    manifest.revision += 1
                    manifest.sha256 = canonical_sha256({
                        "repository": manifest.repository,
                        "branch": manifest.branch,
                        "commit_sha": manifest.commit_sha,
                        "files": manifest.files,
                    })
                    manifest.updated_at = now
                    project.revision += 1
                    project.updated_at = now
                    account.storage_bytes += total_new_bytes
                    proposal.state = "applied"
                    proposal.applied_revision = manifest.revision
                    proposal.applied_manifest_sha256 = manifest.sha256
                    proposal.applied_at = now
                    db.add(AuditEvent(
                        id=str(uuid4()),
                        owner_id=owner,
                        resource_id=proposal_id,
                        action="fly_patch_applied",
                    ))
                    db.flush()
                    applied = True
        except BaseException:
            for key in uploaded_keys:
                try:
                    self.storage.delete(key)
                except Exception:
                    pass
            raise

        if already_applied or not applied:
            for key in uploaded_keys:
                try:
                    self.storage.delete(key)
                except Exception:
                    pass
        return self.workspace.get(owner, project_id)

    @staticmethod
    def _document_filename(proposal_id: str, path: str) -> str:
        basename = PurePosixPath(path).name
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._-") or "source.txt"
        return f"fly-{proposal_id[:8]}-{safe}"[:160]
