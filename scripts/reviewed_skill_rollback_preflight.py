"""Read-only legacy reviewed-skill rollback inventory; never grants rollout authority.

Usage (backend environment, without credentials in CLI arguments):
  python -m scripts.reviewed_skill_rollback_preflight

Requires SHUDDHO_COWORKER_DATABASE_URL and the existing schema. An empty
legacy-task inventory is only one prerequisite: worker-fleet draining, staged
PostgreSQL/Temporal replay and provider-dispatch checks are independent.
"""
from __future__ import annotations

import json
import os

from sqlalchemy import and_, func, select

from services.coworker.database import session_factory
from services.coworker.models import Step, Task
from services.coworker.repository import TERMINAL
from services.coworker.task_workflow_versions import REVIEWED_RESEARCH_WORKFLOW_VERSION

LEGACY_RESEARCH_WORKFLOW_VERSION = "work_research_v1"
REVIEW_PHASE = "reviewed_skill_identity"


def inspect_reviewed_rollback(sessions) -> dict:
    """Return counts only. No credentials, owners, task IDs or private content."""
    pinned = and_(
        Step.task_id == Task.id, Step.phase == REVIEW_PHASE,
    )
    with sessions() as db:
        unfenced = int(db.scalar(
            select(func.count()).select_from(Task).join(Step, pinned).where(
                Task.state.not_in(TERMINAL),
                Task.workflow_version != REVIEWED_RESEARCH_WORKFLOW_VERSION,
            )
        ) or 0)
        without_identity = int(db.scalar(
            select(func.count()).select_from(Task)
            .outerjoin(Step, pinned)
            .where(
                Task.state.not_in(TERMINAL),
                Task.workflow_version == REVIEWED_RESEARCH_WORKFLOW_VERSION,
                Step.task_id.is_(None),
            )
        ) or 0)
        pinned_fenced = int(db.scalar(
            select(func.count()).select_from(Task).join(Step, pinned).where(
                Task.state.not_in(TERMINAL),
                Task.workflow_version == REVIEWED_RESEARCH_WORKFLOW_VERSION,
            )
        ) or 0)
        historical_terminal = int(db.scalar(
            select(func.count()).select_from(Task).join(Step, pinned).where(
                Task.state.in_(TERMINAL),
                Task.workflow_version == LEGACY_RESEARCH_WORKFLOW_VERSION,
            )
        ) or 0)

    blockers = []
    if unfenced:
        blockers.append("active_reviewed_tasks_without_worker_version_fence")
    if without_identity:
        blockers.append("active_fenced_tasks_missing_review_identity")
    return {
        "decision": "BLOCKED_TASK_LEDGER" if blockers else "TASK_LEDGER_CHECK_ONLY",
        "active_unfenced_reviewed_tasks": unfenced,
        "active_fenced_tasks_missing_review_identity": without_identity,
        "active_fenced_reviewed_tasks": pinned_fenced,
        "terminal_legacy_reviewed_tasks": historical_terminal,
        "blockers": blockers,
        "fleet_drained_verified": False,
        "staging_verified": False,
        "rollout_authorized": False,
        "note": (
            "Read-only task-ledger snapshot. Zero blockers cannot prove no old "
            "workers, in-flight provider requests, Temporal activities, or a "
            "race with admissions. Require operated drain, replay and release "
            "evidence before enabling or rolling back reviewed research."
        ),
    }


def main() -> None:
    database_url = os.getenv("SHUDDHO_COWORKER_DATABASE_URL", "")
    if not database_url:
        raise SystemExit("Set SHUDDHO_COWORKER_DATABASE_URL in the backend environment.")
    sessions = session_factory(database_url)
    try:
        result = inspect_reviewed_rollback(sessions)
    finally:
        sessions.kw["bind"].dispose()
    print(json.dumps(result, indent=2))
    if result["blockers"]:
        raise SystemExit("Reviewed research rollback task-ledger gate is blocked.")


if __name__ == "__main__":
    main()
