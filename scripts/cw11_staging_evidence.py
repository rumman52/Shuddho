"""Read-only CW-11 staging evidence collector.

The command never mutates the registry. It proves the database-side release
boundary after an operator has completed the external worker drain and then
writes a machine-readable evidence artifact.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from scripts.reviewed_skill_rollback_preflight import inspect_reviewed_rollback
from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.errors import CoworkerError
from services.coworker.models import (
    ReviewedSkillPublication,
    ReviewedSkillRegistryEvent,
)
from services.coworker.repository import Repository
from services.coworker.reviewed_skill_registry import (
    REVIEWED_RESEARCH_SKILL,
    REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect read-only CW-11 staging qualification evidence."
    )
    parser.add_argument("--expected-publication-version", required=True)
    parser.add_argument("--old-source-revision", required=True)
    parser.add_argument("--external-render-evidence", required=True)
    parser.add_argument("--output", default="cw11-staging-evidence.json")
    return parser.parse_args(argv)


def load_render_evidence(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Invalid Render staging evidence: {error}") from None
    if not isinstance(value, dict):
        raise SystemExit("Invalid Render staging evidence: expected a JSON object.")
    return value


def _is_full_git_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_render_evidence(
    value: Any,
    old_source_revision: str,
    candidate_source_revision: str,
) -> None:
    if not isinstance(value, dict):
        raise SystemExit("Invalid Render staging evidence: expected a JSON object.")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("verified") is not True
    ):
        raise SystemExit(
            "Render evidence has an unsupported schema or is not verified."
        )
    expected_fields = {
        "schema_version",
        "old_worker_service_id",
        "candidate_worker_service_id",
        "old_source_revision",
        "old_worker_live_commit",
        "old_worker_instance_count",
        "candidate_worker_instance_count",
        "candidate_live_commit",
        "verified",
    }
    if set(value) != expected_fields:
        raise SystemExit("Render evidence has missing or unexpected fields.")
    if not _is_full_git_sha(old_source_revision):
        raise SystemExit(
            "Requested old source revision must be a full lowercase Git commit SHA."
        )
    if not _is_full_git_sha(candidate_source_revision):
        raise SystemExit(
            "Candidate source revision must be a full lowercase Git commit SHA."
        )
    old_service = value.get("old_worker_service_id")
    candidate_service = value.get("candidate_worker_service_id")
    if (
        not isinstance(old_service, str)
        or not old_service.strip()
        or old_service != old_service.strip()
        or not isinstance(candidate_service, str)
        or not candidate_service.strip()
        or candidate_service != candidate_service.strip()
        or old_service == candidate_service
    ):
        raise SystemExit("Render evidence must identify two distinct worker services.")
    old_count = value.get("old_worker_instance_count")
    candidate_count = value.get("candidate_worker_instance_count")
    if type(old_count) is not int or old_count != 0:
        raise SystemExit("Render evidence does not prove the legacy worker is stopped.")
    if type(candidate_count) is not int or candidate_count < 1:
        raise SystemExit("Render evidence does not prove an active candidate worker.")
    if value.get("old_source_revision") != old_source_revision:
        raise SystemExit("Render evidence old revision does not match the requested drain.")
    if value.get("old_worker_live_commit") != old_source_revision:
        raise SystemExit("Render evidence does not bind the stopped worker to the declared revision.")
    if value.get("candidate_live_commit") != candidate_source_revision:
        raise SystemExit(
            "Render evidence candidate revision does not match this qualification revision."
        )


def collect_evidence(
    repository: Repository,
    settings: Settings,
    *,
    expected_publication_version: str,
    old_source_revision: str,
    render_evidence: dict[str, Any],
) -> dict[str, Any]:
    if settings.environment != "staging":
        raise SystemExit("CW-11 evidence is staging-only.")
    if not settings.source_revision:
        raise SystemExit("A deployment-attested candidate source revision is required.")

    # Revalidate at the collector boundary. Callers other than main() must not
    # be able to turn an untrusted JSON object into a verified artifact.
    validate_render_evidence(
        render_evidence,
        old_source_revision,
        settings.source_revision,
    )

    selected = repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL)
    if selected is None:
        raise CoworkerError(
            "staging_evidence_selection_missing",
            "No reviewed publication is explicitly selected.",
            409,
        )
    if selected["publication_version"] != expected_publication_version:
        raise CoworkerError(
            "staging_evidence_selection_mismatch",
            "The selected publication is not the expected staging candidate.",
            409,
        )
    if selected["source_revision"] != settings.source_revision:
        raise CoworkerError(
            "staging_evidence_revision_mismatch",
            "The selected publication does not match the deployed candidate revision.",
            409,
        )
    if selected["task_workflow_version"] != REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION:
        raise CoworkerError(
            "staging_evidence_workflow_mismatch",
            "The selected publication does not use the reviewed workflow version.",
            409,
        )

    inventory = repository.worker_inventory(task_queue=settings.task_queue)
    active_states = {"starting", "running", "draining"}
    known_states = active_states | {"drained", "lost"}
    uncertain_workers = [
        row for row in inventory
        if row["state"] == "lost"
        or row["state"] not in known_states
        or (
            row["state"] in active_states
            and not row["heartbeat_fresh"]
        )
    ]
    if uncertain_workers:
        raise CoworkerError(
            "staging_evidence_worker_uncertain",
            "A lost, stale or unknown worker record prevents proving a safe mixed-version drain.",
            409,
        )
    active = [
        row for row in inventory
        if row["state"] in active_states
    ]
    incompatible = [
        row for row in active
        if row["source_revision"] != settings.source_revision
    ]
    compatible_running = [
        row for row in active
        if row["source_revision"] == settings.source_revision
        and row["state"] == "running"
        and row["heartbeat_fresh"]
    ]
    old_rows = [
        row for row in inventory
        if row["source_revision"] == old_source_revision
    ]
    old_blockers = [
        row for row in old_rows
        if (
            row["state"] != "drained"
            or not row["drained_at"]
            or row.get("active_claim_count", 0) != 0
        )
    ]
    active_old_worker_claim_count = sum(
        int(row.get("active_claim_count", 0)) for row in old_rows
    )
    if not compatible_running:
        raise CoworkerError(
            "staging_evidence_worker_missing",
            "No fresh running worker matches the selected publication revision.",
            409,
        )
    if incompatible:
        raise CoworkerError(
            "staging_evidence_mixed_workers",
            "An incompatible worker remains active or draining.",
            409,
        )
    if not old_rows:
        raise CoworkerError(
            "staging_evidence_old_worker",
            "No registered worker for the legacy revision was observed; explicit drain cannot be claimed.",
            409,
        )
    if old_blockers:
        raise CoworkerError(
            "staging_evidence_old_worker",
            "A legacy worker row is not explicitly drained or still has active dispatch claims.",
            409,
        )

    # Reuse the rollback preflight's conservative classification. A clean count
    # of only legacy Tasks with an identity misses both ambiguous legacy Agent
    # work and new reviewed-version Tasks that lack their required identity.
    task_ledger = inspect_reviewed_rollback(repository.sessions)
    if task_ledger["blockers"]:
        raise CoworkerError(
            "staging_evidence_task_ledger_blocked",
            "The reviewed-skill task ledger has active blockers; staging qualification is denied.",
            409,
        )

    with repository.sessions() as db:
        control_events = db.scalars(
            select(ReviewedSkillRegistryEvent)
            .order_by(ReviewedSkillRegistryEvent.created_at.asc())
        ).all()
        publications = db.scalars(
            select(ReviewedSkillPublication)
            .where(ReviewedSkillPublication.skill_name == REVIEWED_RESEARCH_SKILL)
            .order_by(ReviewedSkillPublication.published_at.asc())
        ).all()

    selection_events = [
        row for row in control_events
        if row.event_type == "publication_selected"
        and row.publication_id == selected["publication_id"]
    ]
    if not selection_events:
        raise CoworkerError(
            "staging_evidence_selection_event_missing",
            "The selected publication has no durable operator selection event.",
            409,
        )
    return {
        "schema_version": 1,
        "qualified_at": datetime.now(timezone.utc).isoformat(),
        "environment": settings.environment,
        "task_queue": settings.task_queue,
        "candidate_source_revision": settings.source_revision,
        "expected_publication_version": expected_publication_version,
        "selected_publication": selected,
        "workers": inventory,
        "reviewed_task_ledger": task_ledger,
        # Preserve the existing summary key while sourcing it from the shared
        # classifier; the full aggregate breakdown below is authoritative.
        "legacy_active_reviewed_tasks": int(
            task_ledger["active_unfenced_reviewed_tasks"]
        ),
        "old_source_revision": old_source_revision,
        "old_worker_rows_observed": len(old_rows),
        "active_old_worker_claim_count": active_old_worker_claim_count,
        "external_render_evidence": render_evidence,
        "control_events": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "actor_reference": row.actor_reference,
                "reason": row.reason,
                "publication_id": row.publication_id,
                "metadata": dict(row.event_metadata or {}),
                "created_at": row.created_at.isoformat(),
            }
            for row in control_events
        ],
        "publications": [
            {
                "id": row.id,
                "publication_version": row.publication_version,
                "state": row.state,
                "source_revision": row.source_revision,
                "review_sha256": row.review_sha256,
                "publication_sha256": row.publication_sha256,
                "rollback_target_version": row.rollback_target_version,
            }
            for row in publications
        ],
        "assertions": {
            "explicit_selection": True,
            "selection_event_present": True,
            "selected_publication_is_published": True,
            "candidate_revision_matches_selection": True,
            "fresh_compatible_worker_present": True,
            "no_active_incompatible_workers": True,
            "no_active_old_worker_claims": active_old_worker_claim_count == 0,
            "no_active_pre_fence_reviewed_tasks": True,
            "no_reviewed_task_ledger_blockers": True,
            "legacy_worker_render_instances_zero": True,
        },
        "verified": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings.from_env()
    render_evidence = load_render_evidence(args.external_render_evidence)
    repository = Repository(session_factory(settings.database_url), settings)
    try:
        evidence = collect_evidence(
            repository,
            settings,
            expected_publication_version=args.expected_publication_version,
            old_source_revision=args.old_source_revision,
            render_evidence=render_evidence,
        )
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    finally:
        repository.sessions.kw["bind"].dispose()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CoworkerError, ValueError) as error:
        print(json.dumps({
            "verified": False,
            "code": getattr(error, "code", type(error).__name__),
            "error": str(error),
        }, indent=2), file=sys.stderr)
        raise SystemExit(2) from None
