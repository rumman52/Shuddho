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

from sqlalchemy import func, select

from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.errors import CoworkerError
from services.coworker.models import ReviewedSkillPublication, ReviewedSkillRegistryEvent, Step, Task
from services.coworker.repository import Repository, TERMINAL
from services.coworker.reviewed_skill_registry import (
    REVIEWED_RESEARCH_SKILL,
    REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
)
from services.coworker.task_workflow_versions import PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect read-only CW-11 staging qualification evidence.")
    parser.add_argument("--expected-publication-version", required=True)
    parser.add_argument("--old-source-revision", required=True)
    parser.add_argument("--output", default="cw11-staging-evidence.json")
    args = parser.parse_args()

    settings = Settings.from_env()
    if settings.environment != "staging":
        raise SystemExit("CW-11 evidence is staging-only.")
    if not settings.source_revision:
        raise SystemExit("A deployment-attested candidate source revision is required.")

    repository = Repository(session_factory(settings.database_url), settings)
    try:
        selected = repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL)
        if selected is None:
            raise CoworkerError(
                "staging_evidence_selection_missing",
                "No reviewed publication is explicitly selected.",
                409,
            )
        if selected["publication_version"] != args.expected_publication_version:
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
        active = [row for row in inventory if row["state"] in {"starting", "running", "draining"}]
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
            if row["source_revision"] == args.old_source_revision
        ]
        old_blockers = [
            row for row in old_rows
            if row["state"] not in {"drained"}
        ]
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
        if old_rows and old_blockers:
            raise CoworkerError(
                "staging_evidence_old_worker",
                "A legacy worker row is not explicitly drained.",
                409,
            )

        with repository.sessions() as db:
            legacy_reviewed = db.scalar(
                select(func.count())
                .select_from(Task)
                .join(Step, (Step.task_id == Task.id) & (Step.phase == "reviewed_skill_identity"))
                .where(
                    Task.workflow_version == PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION,
                    Task.state.not_in(TERMINAL),
                )
            )
            control_events = db.scalars(
                select(ReviewedSkillRegistryEvent)
                .order_by(ReviewedSkillRegistryEvent.created_at.asc())
            ).all()
            publications = db.scalars(
                select(ReviewedSkillPublication)
                .where(ReviewedSkillPublication.skill_name == REVIEWED_RESEARCH_SKILL)
                .order_by(ReviewedSkillPublication.published_at.asc())
            ).all()

        if legacy_reviewed:
            raise CoworkerError(
                "staging_evidence_legacy_tasks",
                "Active pre-fence reviewed tasks remain; drain/migration is incomplete.",
                409,
            )

        evidence = {
            "schema_version": 1,
            "qualified_at": datetime.now(timezone.utc).isoformat(),
            "environment": settings.environment,
            "task_queue": settings.task_queue,
            "candidate_source_revision": settings.source_revision,
            "expected_publication_version": args.expected_publication_version,
            "selected_publication": selected,
            "workers": inventory,
            "legacy_active_reviewed_tasks": int(legacy_reviewed),
            "old_source_revision": args.old_source_revision,
            "old_worker_rows_observed": len(old_rows),
            "control_events": [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "actor_reference": row.actor_reference,
                    "reason": row.reason,
                    "publication_id": row.publication_id,
                    "metadata": dict(row.metadata or {}),
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
                "selected_publication_is_published": selected["state"] == "selected",
                "candidate_revision_matches_selection": True,
                "fresh_compatible_worker_present": True,
                "no_active_incompatible_workers": True,
                "no_active_pre_fence_reviewed_tasks": True,
            },
            "verified": True,
        }
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
