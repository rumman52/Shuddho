"""CW-11 trusted reviewed-skill publication registry.

The registry is a persisted server-owned record of reviewed skill publications.
It is intentionally separate from model planning and from the controlled release
ledger: the ledger proves release evidence; this registry is the runtime
selection boundary. Publication/selection mutations are operator-only and are
never exposed as model or end-user tool authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .errors import CoworkerError
from .skill_manifests import (
    CoworkerSkillManifest,
    SkillResourceLimits,
    pilot_skill_manifest,
    validate_manifest,
)

REVIEWED_RESEARCH_SKILL = "research"
REVIEWED_RESEARCH_PUBLICATION_VERSION = "research_reviewed_v1"
REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION = "work_research_reviewed_v2"
REVIEWED_RESEARCH_TOOL = "research.search"

PUBLICATION_STATES = frozenset({"published", "rolled_back", "revoked"})
SELECTION_STATE = "selected"
WORKER_ACTIVE_STATES = frozenset({"starting", "running", "draining"})
WORKER_TERMINAL_STATES = frozenset({"drained", "lost"})
WORKER_HEARTBEAT_TTL_SECONDS = 15


@dataclass(frozen=True)
class ReviewedSkillBinding:
    publication_id: str
    skill_name: str
    publication_version: str
    task_workflow_version: str
    review_sha256: str
    publication_sha256: str
    source_revision: str


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _source_revision(value: str) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[0-9a-f]{40}", value) is None
    ):
        raise CoworkerError(
            "skill_publication_untrusted",
            "A reviewed skill publication requires an exact 40-character lowercase source revision.",
            409,
        )
    return value


def _manifest_snapshot(manifest: CoworkerSkillManifest) -> dict[str, Any]:
    return asdict(manifest)


def manifest_from_snapshot(value: object) -> CoworkerSkillManifest:
    if type(value) is not dict:
        raise CoworkerError(
            "skill_publication_untrusted",
            "The persisted reviewed skill manifest is invalid.",
            409,
        )
    try:
        limits = value["resource_limits"]
        manifest = CoworkerSkillManifest(
            name=value["name"],
            version=value["version"],
            instruction_sha256=value["instruction_sha256"],
            input_schema_sha256=value["input_schema_sha256"],
            output_schema_sha256=value["output_schema_sha256"],
            tool_contract_sha256=value["tool_contract_sha256"],
            tool_names=tuple(value["tool_names"]),
            resource_limits=SkillResourceLimits(
                max_tool_calls=limits["max_tool_calls"],
                max_wall_seconds=limits["max_wall_seconds"],
                max_output_bytes=limits["max_output_bytes"],
            ),
            rollback_version=value["rollback_version"],
        )
    except (KeyError, TypeError, ValueError):
        raise CoworkerError(
            "skill_publication_untrusted",
            "The persisted reviewed skill manifest is invalid.",
            409,
        ) from None
    return manifest


def publication_payload(
    *,
    skill_name: str,
    publication_version: str,
    task_workflow_version: str,
    source_revision: str,
    manifest: CoworkerSkillManifest,
    rollback_target_version: str | None,
) -> dict[str, Any]:
    return {
        "skill_name": skill_name,
        "publication_version": publication_version,
        "task_workflow_version": task_workflow_version,
        "source_revision": source_revision,
        "manifest": _manifest_snapshot(manifest),
        "rollback_target_version": rollback_target_version,
    }


def publication_sha256(
    *,
    skill_name: str,
    publication_version: str,
    task_workflow_version: str,
    source_revision: str,
    manifest: CoworkerSkillManifest,
    rollback_target_version: str | None,
) -> str:
    return _digest(
        publication_payload(
            skill_name=skill_name,
            publication_version=publication_version,
            task_workflow_version=task_workflow_version,
            source_revision=source_revision,
            manifest=manifest,
            rollback_target_version=rollback_target_version,
        )
    )


def build_reviewed_publication(
    *,
    skill_name: str,
    publication_version: str,
    task_workflow_version: str,
    source_revision: str,
    rollback_target_version: str | None = None,
) -> dict[str, Any]:
    source_revision = _source_revision(source_revision)
    if type(publication_version) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", publication_version) is None:
        raise CoworkerError("skill_publication_untrusted", "The publication version is invalid.", 409)
    if skill_name != REVIEWED_RESEARCH_SKILL:
        raise CoworkerError("skill_publication_untrusted", "Only the reviewed research skill is supported.", 409)
    if task_workflow_version != REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION:
        raise CoworkerError(
            "skill_publication_untrusted",
            "The reviewed research publication requires a registry-bound supported workflow version.",
            409,
        )
    if rollback_target_version is not None and (
        type(rollback_target_version) is not str
        or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", rollback_target_version) is None
        or rollback_target_version == publication_version
    ):
        raise CoworkerError("skill_publication_untrusted", "Rollback target must be another publication version.", 409)
    manifest = pilot_skill_manifest()
    validate_manifest(manifest, frozenset({REVIEWED_RESEARCH_TOOL}))
    if manifest.name != REVIEWED_RESEARCH_SKILL:
        raise CoworkerError("skill_publication_untrusted", "The reviewed pilot skill identity changed.", 409)
    payload = publication_payload(
        skill_name=skill_name,
        publication_version=publication_version,
        task_workflow_version=task_workflow_version,
        source_revision=source_revision,
        manifest=manifest,
        rollback_target_version=rollback_target_version,
    )
    return {
        **payload,
        "manifest_version": manifest.version,
        "review_sha256": manifest.review_sha256(),
        "publication_sha256": publication_sha256(
            skill_name=skill_name,
            publication_version=publication_version,
            task_workflow_version=task_workflow_version,
            source_revision=source_revision,
            manifest=manifest,
            rollback_target_version=rollback_target_version,
        ),
        "tool_names": list(manifest.tool_names),
        "resource_limits": asdict(manifest.resource_limits),
    }


def build_pilot_publication(
    *,
    source_revision: str,
    publication_version: str = REVIEWED_RESEARCH_PUBLICATION_VERSION,
    task_workflow_version: str = REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
    rollback_target_version: str | None = None,
) -> dict[str, Any]:
    return build_reviewed_publication(
        skill_name=REVIEWED_RESEARCH_SKILL,
        publication_version=publication_version,
        task_workflow_version=task_workflow_version,
        source_revision=source_revision,
        rollback_target_version=rollback_target_version,
    )


def _publication_values(row: Any) -> tuple[CoworkerSkillManifest, str]:
    manifest = manifest_from_snapshot(row.manifest)
    source_revision = _source_revision(row.source_revision)
    expected = publication_sha256(
        skill_name=row.skill_name,
        publication_version=row.publication_version,
        task_workflow_version=row.task_workflow_version,
        source_revision=source_revision,
        manifest=manifest,
        rollback_target_version=row.rollback_target_version,
    )
    if row.publication_sha256 != expected:
        raise CoworkerError(
            "skill_publication_untrusted",
            "The persisted reviewed skill publication hash does not match its immutable fields.",
            409,
        )
    if row.review_sha256 != manifest.review_sha256():
        raise CoworkerError(
            "skill_publication_untrusted",
            "The persisted reviewed skill review hash does not match its manifest.",
            409,
        )
    if row.state not in PUBLICATION_STATES:
        raise CoworkerError(
            "skill_publication_untrusted",
            "The reviewed skill publication has an unsupported lifecycle state.",
            409,
        )
    return manifest, source_revision


def binding_from_row(row: Any) -> ReviewedSkillBinding:
    _publication_values(row)
    return ReviewedSkillBinding(
        publication_id=row.id,
        skill_name=row.skill_name,
        publication_version=row.publication_version,
        task_workflow_version=row.task_workflow_version,
        review_sha256=row.review_sha256,
        publication_sha256=row.publication_sha256,
        source_revision=row.source_revision,
    )


def require_selected_pilot(row: Any, *, worker_source_revision: str | None) -> ReviewedSkillBinding:
    if row is None:
        raise CoworkerError(
            "skill_publication_unavailable",
            "The reviewed research skill has no explicitly selected publication.",
            409,
        )
    manifest, source_revision = _publication_values(row)
    validate_manifest(manifest, frozenset({REVIEWED_RESEARCH_TOOL}))
    if (
        row.skill_name != REVIEWED_RESEARCH_SKILL
        or row.task_workflow_version != REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION
        or row.state != "published"
        or list(row.tool_names or ()) != [REVIEWED_RESEARCH_TOOL]
        or row.manifest_version != manifest.version
    ):
        raise CoworkerError(
            "skill_publication_unavailable",
            "The selected reviewed research publication is not a supported compatible version.",
            409,
        )
    if worker_source_revision != source_revision:
        raise CoworkerError(
            "skill_worker_revision_mismatch",
            "The worker source revision does not match the reviewed skill publication.",
            409,
        )
    return ReviewedSkillBinding(
        publication_id=row.id,
        skill_name=row.skill_name,
        publication_version=row.publication_version,
        task_workflow_version=row.task_workflow_version,
        review_sha256=row.review_sha256,
        publication_sha256=row.publication_sha256,
        source_revision=source_revision,
    )


def require_pinned_publication(
    row: Any,
    pinned: object,
    *,
    worker_source_revision: str | None,
) -> ReviewedSkillBinding:
    if row is None or type(pinned) is not dict:
        raise CoworkerError(
            "skill_manifest_unreviewed",
            "The Task has no matching persisted reviewed skill publication.",
            409,
        )
    expected_keys = {
        "publication_id",
        "publication_version",
        "publication_sha256",
        "review_sha256",
        "source_revision",
        "task_workflow_version",
    }
    if set(pinned) != expected_keys:
        raise CoworkerError(
            "skill_manifest_unreviewed",
            "The Task reviewed skill identity is incomplete.",
            409,
        )
    _publication_values(row)
    binding = binding_from_row(row)
    if (
        row.state != "published"
        or pinned["publication_id"] != binding.publication_id
        or pinned["publication_version"] != binding.publication_version
        or pinned["publication_sha256"] != binding.publication_sha256
        or pinned["review_sha256"] != binding.review_sha256
        or pinned["source_revision"] != binding.source_revision
        or pinned["task_workflow_version"] != binding.task_workflow_version
        or worker_source_revision != binding.source_revision
    ):
        raise CoworkerError(
            "skill_manifest_unreviewed",
            "The Task reviewed skill publication is revoked, changed, or incompatible with this worker.",
            409,
        )
    return binding
