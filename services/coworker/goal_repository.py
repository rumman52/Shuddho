from __future__ import annotations

import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select

from .config import Settings
from .errors import CoworkerError
from .goal_schemas import GoalCreate, GoalPatch
from .models import Account, AgentRun, AuditEvent, PersonalGoal, PersonalGoalRevision, Workspace, utcnow
from .repository import iso, not_found


class GoalRepository:
    """Owner-scoped persistent goals with immutable revision snapshots."""

    def __init__(self, sessions, settings: Settings):
        self.sessions = sessions
        self.settings = settings

    def _require_enabled(self) -> None:
        if not self.settings.personal_goals_enabled:
            raise CoworkerError("personal_goals_unavailable", "Persistent goals are not enabled in this workspace yet.", 409)

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    @staticmethod
    def _workspace(db, owner: str) -> str:
        value = db.scalar(select(Workspace.id).where(Workspace.owner_id == owner))
        if value is None:
            raise not_found()
        return value

    @staticmethod
    def _goal(db, owner: str, goal_id: str, *, lock: bool = False) -> PersonalGoal:
        query = select(PersonalGoal).where(PersonalGoal.id == goal_id, PersonalGoal.owner_id == owner)
        if lock:
            query = query.with_for_update()
        value = db.scalar(query)
        if value is None:
            raise not_found()
        return value

    @staticmethod
    def _snapshot(row: PersonalGoal) -> dict:
        return {
            "objective": row.objective,
            "success_criteria": list(row.success_criteria),
            "constraints": list(row.constraints),
            "deadline_at": iso(row.deadline_at) if row.deadline_at else None,
            "timezone": row.timezone,
            "state": row.state,
            "milestones": list(row.milestones),
            "budget": dict(row.budget),
            "authorized_resources": list(row.authorized_resources),
            "next_review_at": iso(row.next_review_at) if row.next_review_at else None,
        }

    def _record_revision(self, db, row: PersonalGoal) -> None:
        db.add(PersonalGoalRevision(goal_id=row.id, revision=row.revision, owner_id=row.owner_id, snapshot=self._snapshot(row)))

    def _dto(self, db, row: PersonalGoal) -> dict:
        runs = db.scalars(select(AgentRun).where(
            AgentRun.owner_id == row.owner_id, AgentRun.goal_id == row.id,
        ).order_by(AgentRun.created_at.desc()).limit(30)).all()
        return {
            "id": row.id,
            "objective": row.objective,
            "success_criteria": list(row.success_criteria),
            "constraints": list(row.constraints),
            "deadline_at": iso(row.deadline_at) if row.deadline_at else None,
            "timezone": row.timezone,
            "revision": row.revision,
            "state": row.state,
            "milestones": list(row.milestones),
            "budget": dict(row.budget),
            "authorized_resources": list(row.authorized_resources),
            "next_review_at": iso(row.next_review_at) if row.next_review_at else None,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
            "run_links": [{"run_id": run.id, "goal_revision": run.goal_revision, "state": run.state, "created_at": iso(run.created_at)} for run in runs],
        }

    def create(self, owner: str, request: GoalCreate, idempotency_key: str) -> tuple[dict, bool]:
        self._require_enabled()
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as db:
            if db.scalar(select(Account.id).where(Account.id == owner).with_for_update()) is None:
                raise not_found()
            previous = db.scalar(select(PersonalGoal).where(PersonalGoal.owner_id == owner, PersonalGoal.idempotency_key == idempotency_key))
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError("idempotency_conflict", "This request key belongs to a different persistent goal.", 409)
                return self._dto(db, previous), False
            count = db.scalar(select(func.count()).select_from(PersonalGoal).where(PersonalGoal.owner_id == owner))
            if count >= self.settings.max_personal_goals:
                raise CoworkerError("goal_limit", "This workspace reached its persistent goal limit.", 429)
            now = utcnow()
            row = PersonalGoal(
                id=str(uuid4()), owner_id=owner, workspace_id=self._workspace(db, owner),
                idempotency_key=idempotency_key, fingerprint=fingerprint, objective=request.objective,
                success_criteria=list(request.success_criteria), constraints=list(request.constraints),
                deadline_at=request.deadline_at, timezone=request.timezone, revision=1, state=request.state,
                milestones=[item.model_dump(mode="json") for item in request.milestones],
                budget=request.budget.model_dump(mode="json"),
                authorized_resources=[item.model_dump(mode="json") for item in request.authorized_resources],
                next_review_at=request.next_review_at, created_at=now, updated_at=now,
            )
            db.add(row); db.flush()
            self._record_revision(db, row)
            self._audit(db, owner, row.id, "personal_goal_created")
            return self._dto(db, row), True

    def list(self, owner: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            rows = db.scalars(select(PersonalGoal).where(PersonalGoal.owner_id == owner).order_by(PersonalGoal.updated_at.desc()).limit(self.settings.max_personal_goals)).all()
            return [self._dto(db, row) for row in rows]

    def get(self, owner: str, goal_id: str) -> dict:
        self._require_enabled()
        with self.sessions() as db:
            return self._dto(db, self._goal(db, owner, goal_id))

    def revisions(self, owner: str, goal_id: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            self._goal(db, owner, goal_id)
            rows = db.scalars(select(PersonalGoalRevision).where(PersonalGoalRevision.goal_id == goal_id, PersonalGoalRevision.owner_id == owner).order_by(PersonalGoalRevision.revision)).all()
            return [{"revision": row.revision, "snapshot": row.snapshot, "created_at": iso(row.created_at)} for row in rows]

    @staticmethod
    def _check_revision(row: PersonalGoal, expected_revision: int) -> None:
        if row.revision != expected_revision:
            raise CoworkerError("goal_revision_conflict", "This goal changed. Review the latest revision before editing it.", 409)

    def update(self, owner: str, goal_id: str, request: GoalPatch) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = self._goal(db, owner, goal_id, lock=True)
            self._check_revision(row, request.expected_revision)
            if row.state in {"cancelled", "archived"}:
                raise CoworkerError("goal_not_editable", "Cancelled or archived goals cannot be edited.", 409)
            fields = request.model_fields_set - {"expected_revision"}
            for field in {"objective", "success_criteria", "constraints", "deadline_at", "timezone", "next_review_at"} & fields:
                setattr(row, field, getattr(request, field))
            if "milestones" in fields:
                row.milestones = [item.model_dump(mode="json") for item in (request.milestones or [])]
            if "budget" in fields:
                row.budget = request.budget.model_dump(mode="json") if request.budget else {}
            if "authorized_resources" in fields:
                row.authorized_resources = [item.model_dump(mode="json") for item in (request.authorized_resources or [])]
            row.revision += 1; row.updated_at = utcnow()
            self._record_revision(db, row)
            self._audit(db, owner, row.id, "personal_goal_updated")
            return self._dto(db, row)

    def _transition(self, owner: str, goal_id: str, expected_revision: int, target: str, allowed: set[str]) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = self._goal(db, owner, goal_id, lock=True)
            self._check_revision(row, expected_revision)
            if row.state not in allowed:
                raise CoworkerError("invalid_goal_transition", f"Goal state {row.state!r} cannot transition to {target!r}.", 409)
            row.state = target; row.revision += 1; row.updated_at = utcnow()
            self._record_revision(db, row)
            self._audit(db, owner, row.id, f"personal_goal_{target}")
            return self._dto(db, row)

    def pause(self, owner: str, goal_id: str, expected_revision: int) -> dict:
        return self._transition(owner, goal_id, expected_revision, "paused", {"active", "blocked"})

    def resume(self, owner: str, goal_id: str, expected_revision: int) -> dict:
        return self._transition(owner, goal_id, expected_revision, "active", {"draft", "paused"})

    def cancel(self, owner: str, goal_id: str, expected_revision: int) -> dict:
        return self._transition(owner, goal_id, expected_revision, "cancelled", {"draft", "active", "paused", "blocked"})
