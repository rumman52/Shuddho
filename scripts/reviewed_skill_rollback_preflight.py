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

from sqlalchemy import and_, case, func, select

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
    # One SQL statement observes one consistent database statement snapshot,
    # unlike four independent SELECTs under PostgreSQL READ COMMITTED.
    live = Task.state.not_in(TERMINAL)
    has_review = Step.task_id.is_not(None)
    new_version = Task.workflow_version == REVIEWED_RESEARCH_WORKFLOW_VERSION
    legacy = Task.workflow_version == LEGACY_RESEARCH_WORKFLOW_VERSION
    with sessions() as db:
        values = db.execute(
            select(
                func.sum(case((and_(live, has_review, ~new_version), 1), else_=0)),
                func.sum(case((and_(live, new_version, ~has_review), 1), else_=0)),
                func.sum(case((and_(live, new_version, has_review), 1), else_=0)),
                func.sum(case((and_(~live, legacy, has_review), 1), else_=0)),
                func.sum(case((
                    and_(live, legacy, ~has_review, Task.agent_run_id.is_not(None)),
                    1,
                ), else_=0)),
            ).select_from(Task).outerjoin(Step, pinned)
        ).one()
    unfenced, without_identity, pinned_fenced, historical_terminal, legacy_agent_missing = (
        int(value or 0) for value in values
    )
    blockers = []
    if unfenced:
        blockers.append("active_reviewed_tasks_without_worker_version_fence")
    if without_identity:
        blockers.append("active_fenced_tasks_missing_review_identity")
    if legacy_agent_missing:
        # A missing reviewed Step cannot prove that old Agent-owned research
        # was unreviewed: the old-worker path remains ambiguous and unsafe.
        blockers.append("active_legacy_agent_research_without_review_identity")
    return {
        "decision": "BLOCKED_TASK_LEDGER" if blockers else "TASK_LEDGER_CHECK_ONLY",
        "active_unfenced_reviewed_tasks": unfenced,
        "active_fenced_tasks_missing_review_identity": without_identity,
        "active_fenced_reviewed_tasks": pinned_fenced,
        "active_legacy_agent_research_without_review_identity": legacy_agent_missing,
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
