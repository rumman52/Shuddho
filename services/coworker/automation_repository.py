from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, func, or_, select

from .agent_schemas import AgentRunCreate
from .automation_schemas import AutomationCreate, AutomationPatch
from .errors import CoworkerError
from .models import (
    Account, AgentRun, AuditEvent, Automation, AutomationOccurrence, AutomationRevision,
    AutomationScheduleOutbox, ConnectorEvent, ConnectorReadGrant, PersonalGoal, Workspace, utcnow,
)
from .repository import aware, iso, not_found


class AutomationRepository:
    """Desired automation state, schedule reconciliation and occurrence admission."""

    def __init__(self, sessions, settings, agent, notifications):
        self.sessions = sessions
        self.settings = settings
        self.agent = agent
        self.notifications = notifications

    # Compatibility forwarding for existing callers while PA-10 notification
    # ownership moves out of the automation repository.
    def notification_preferences(self, owner: str) -> dict[str, bool]:
        return self.notifications.notification_preferences(owner)

    def save_notification_preferences(self, owner: str, request) -> dict[str, bool]:
        return self.notifications.save_notification_preferences(owner, request)

    def _require_enabled(self) -> None:
        if not self.settings.automations_enabled:
            raise CoworkerError("automations_unavailable", "Automations are not enabled in this workspace yet.", 409)

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    def _validate_event_trigger(self, db, owner: str, schedule: dict) -> None:
        if schedule.get("kind") != "event":
            return
        if not self.settings.connector_reads_enabled or not self.settings.agent_runtime_v3_enabled:
            raise CoworkerError(
                "event_automation_unavailable",
                "Connected-event automations require qualified connected reads and Agent Runtime v3.",
                409,
            )
        grant_id = str(schedule.get("grant_id") or "")
        grant = db.scalar(select(ConnectorReadGrant).where(
            ConnectorReadGrant.id == grant_id,
            ConnectorReadGrant.owner_id == owner,
        ))
        if (
            grant is None
            or grant.state != "active"
            or aware(grant.expires_at) <= utcnow()
            or grant.destination != "planner_context"
            or grant.purpose != "agent_context"
        ):
            raise CoworkerError(
                "event_automation_grant_unavailable",
                "The selected connected read authorization is not active for Agent context.",
                409,
            )

    @staticmethod
    def _automation(db, owner: str, automation_id: str, *, lock: bool = False) -> Automation:
        query = select(Automation).where(Automation.id == automation_id, Automation.owner_id == owner)
        if lock:
            query = query.with_for_update()
        value = db.scalar(query)
        if value is None:
            raise not_found()
        return value

    @staticmethod
    def _snapshot(row: Automation) -> dict:
        return {
            "goal_id": row.goal_id,
            "goal_revision": row.goal_revision,
            "timezone": row.timezone,
            "schedule": dict(row.schedule),
            "output_language": row.output_language,
            "overlap_policy": row.overlap_policy,
            "catchup_window_seconds": row.catchup_window_seconds,
            "quiet_hours": dict(row.quiet_hours) if row.quiet_hours else None,
            "expires_at": iso(row.expires_at) if row.expires_at else None,
            "state": row.state,
        }

    @staticmethod
    def _dto(row: Automation) -> dict:
        return {
            "id": row.id, "goal_id": row.goal_id, "goal_revision": row.goal_revision,
            "revision": row.revision, "state": row.state, "timezone": row.timezone,
            "schedule": dict(row.schedule), "output_language": row.output_language,
            "overlap_policy": row.overlap_policy, "catchup_window_seconds": row.catchup_window_seconds,
            "quiet_hours": dict(row.quiet_hours) if row.quiet_hours else None,
            "expires_at": iso(row.expires_at) if row.expires_at else None,
            "schedule_applied_revision": row.schedule_applied_revision,
            "schedule_applied_enabled": row.schedule_applied_enabled,
            "schedule_error_code": row.schedule_error_code,
            "created_at": iso(row.created_at), "updated_at": iso(row.updated_at),
        }

    @staticmethod
    def _queue_reconcile(db, row: Automation) -> None:
        outbox = db.get(AutomationScheduleOutbox, row.id)
        if outbox is None:
            db.add(AutomationScheduleOutbox(automation_id=row.id, desired_revision=row.revision))
        else:
            outbox.desired_revision = row.revision
            outbox.delivered = False
            outbox.lease_until = None

    def create(self, owner: str, request: AutomationCreate, idempotency_key: str) -> tuple[dict, bool]:
        self._require_enabled()
        if not self.settings.personal_goals_enabled or not self.settings.agent_runtime_enabled:
            raise CoworkerError("automation_dependency", "Automations require persistent goals and Agent Runtime.", 409)
        payload = request.model_dump(mode="json")
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.sessions.begin() as db:
            if db.scalar(select(Account.id).where(Account.id == owner).with_for_update()) is None:
                raise not_found()
            previous = db.scalar(select(Automation).where(
                Automation.owner_id == owner, Automation.idempotency_key == idempotency_key,
            ))
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError("idempotency_conflict", "This request key belongs to another automation.", 409)
                return self._dto(previous), False
            active_count = db.scalar(select(func.count()).select_from(Automation).where(
                Automation.owner_id == owner, Automation.state != "cancelled",
            ))
            if active_count >= self.settings.max_automations:
                raise CoworkerError("automation_limit", "This workspace reached its automation limit.", 429)
            goal = db.scalar(select(PersonalGoal).where(
                PersonalGoal.id == str(request.goal_id), PersonalGoal.owner_id == owner,
            ).with_for_update())
            if goal is None:
                raise not_found()
            if goal.revision != request.goal_revision:
                raise CoworkerError("goal_revision_conflict", "Review the latest goal revision before scheduling it.", 409)
            if goal.state != "active":
                raise CoworkerError("goal_not_active", "Only an active goal can be automated.", 409)
            if request.expires_at is not None and aware(request.expires_at) <= utcnow():
                raise CoworkerError("automation_expired", "Automation expiry must be in the future.", 409)
            self._validate_event_trigger(db, owner, payload["schedule"])
            now = utcnow()
            row = Automation(
                id=str(uuid4()), owner_id=owner, workspace_id=goal.workspace_id,
                goal_id=goal.id, goal_revision=goal.revision, idempotency_key=idempotency_key,
                fingerprint=fingerprint, revision=1, state="active", timezone=request.timezone,
                schedule=request.schedule.model_dump(mode="json"), output_language=request.output_language,
                overlap_policy=request.overlap_policy, catchup_window_seconds=request.catchup_window_seconds,
                quiet_hours=request.quiet_hours.model_dump(mode="json") if request.quiet_hours else None,
                expires_at=request.expires_at, created_at=now, updated_at=now,
            )
            db.add(row); db.flush()
            db.add(AutomationRevision(automation_id=row.id, revision=1, owner_id=owner, snapshot=self._snapshot(row)))
            self._queue_reconcile(db, row)
            self._audit(db, owner, row.id, "automation_created")
            return self._dto(row), True

    def list(self, owner: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            rows = db.scalars(select(Automation).where(
                Automation.owner_id == owner,
            ).order_by(Automation.updated_at.desc()).limit(self.settings.max_automations)).all()
            return [self._dto(row) for row in rows]

    def get(self, owner: str, automation_id: str) -> dict:
        self._require_enabled()
        with self.sessions() as db:
            return self._dto(self._automation(db, owner, automation_id))

    def revisions(self, owner: str, automation_id: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            self._automation(db, owner, automation_id)
            rows = db.scalars(select(AutomationRevision).where(
                AutomationRevision.automation_id == automation_id, AutomationRevision.owner_id == owner,
            ).order_by(AutomationRevision.revision)).all()
            return [{"revision": row.revision, "snapshot": row.snapshot, "created_at": iso(row.created_at)} for row in rows]

    @staticmethod
    def _check_revision(row: Automation, expected: int) -> None:
        if row.revision != expected:
            raise CoworkerError("automation_revision_conflict", "This automation changed. Review the latest revision.", 409)

    def update(self, owner: str, automation_id: str, request: AutomationPatch) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = self._automation(db, owner, automation_id, lock=True)
            self._check_revision(row, request.expected_revision)
            if row.state == "cancelled":
                raise CoworkerError("automation_not_editable", "Cancelled automations cannot be edited.", 409)
            fields = request.model_fields_set - {"expected_revision"}
            for field in {"timezone", "output_language", "overlap_policy", "catchup_window_seconds", "expires_at"} & fields:
                setattr(row, field, getattr(request, field))
            if "schedule" in fields:
                row.schedule = request.schedule.model_dump(mode="json")
            if "quiet_hours" in fields:
                row.quiet_hours = request.quiet_hours.model_dump(mode="json") if request.quiet_hours else None
            self._validate_event_trigger(db, owner, dict(row.schedule))
            if row.expires_at is not None and aware(row.expires_at) <= utcnow():
                raise CoworkerError("automation_expired", "Automation expiry must be in the future.", 409)
            row.revision += 1; row.updated_at = utcnow(); row.schedule_error_code = None
            db.add(AutomationRevision(automation_id=row.id, revision=row.revision, owner_id=owner, snapshot=self._snapshot(row)))
            self._queue_reconcile(db, row)
            self._audit(db, owner, row.id, "automation_updated")
            return self._dto(row)

    def _transition(self, owner: str, automation_id: str, expected: int, target: str, allowed: set[str]) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = self._automation(db, owner, automation_id, lock=True)
            self._check_revision(row, expected)
            if row.state not in allowed:
                raise CoworkerError("invalid_automation_transition", f"Automation state {row.state!r} cannot transition to {target!r}.", 409)
            row.state = target; row.revision += 1; row.updated_at = utcnow(); row.schedule_error_code = None
            db.add(AutomationRevision(automation_id=row.id, revision=row.revision, owner_id=owner, snapshot=self._snapshot(row)))
            self._queue_reconcile(db, row)
            self._audit(db, owner, row.id, f"automation_{target}")
            return self._dto(row)

    def pause(self, owner: str, automation_id: str, expected: int) -> dict:
        return self._transition(owner, automation_id, expected, "paused", {"active"})

    def resume(self, owner: str, automation_id: str, expected: int) -> dict:
        return self._transition(owner, automation_id, expected, "active", {"paused"})

    def cancel(self, owner: str, automation_id: str, expected: int) -> dict:
        return self._transition(owner, automation_id, expected, "cancelled", {"active", "paused"})

    def claim_reconciliation(self, limit: int = 10) -> list[dict]:
        """Lease desired schedule changes, including runtime kill-switch drift."""
        with self.sessions.begin() as db:
            now = utcnow()
            if self.settings.automations_enabled:
                drift = or_(
                    AutomationScheduleOutbox.delivered.is_(False),
                    Automation.schedule_applied_revision.is_(None),
                    Automation.schedule_applied_revision != Automation.revision,
                    (Automation.state == "active") & Automation.schedule_applied_enabled.is_(False),
                    (Automation.state != "active") & Automation.schedule_applied_enabled.is_(True),
                )
            else:
                drift = or_(
                    AutomationScheduleOutbox.delivered.is_(False),
                    Automation.schedule_applied_enabled.is_(True),
                )
            rows = db.execute(select(AutomationScheduleOutbox, Automation).join(
                Automation, Automation.id == AutomationScheduleOutbox.automation_id,
            ).where(
                drift,
                or_(AutomationScheduleOutbox.lease_until.is_(None), AutomationScheduleOutbox.lease_until < now),
            ).order_by(Automation.updated_at).limit(limit).with_for_update(skip_locked=True)).all()
            result = []
            for outbox, row in rows:
                outbox.lease_until = now + timedelta(seconds=30)
                outbox.attempts += 1
                desired = self._dto(row)
                if not self.settings.automations_enabled and desired["state"] == "active":
                    desired["state"] = "paused"
                result.append(desired | {"desired_revision": outbox.desired_revision})
            return result

    def reconciliation_applied(self, automation_id: str, revision: int, enabled: bool) -> None:
        with self.sessions.begin() as db:
            row = db.get(Automation, automation_id)
            outbox = db.get(AutomationScheduleOutbox, automation_id)
            if row is None or outbox is None or outbox.desired_revision != revision:
                return
            row.schedule_applied_revision = revision; row.schedule_applied_enabled = enabled; row.schedule_error_code = None
            outbox.delivered = True; outbox.lease_until = None

    def reconciliation_failed(self, automation_id: str, revision: int, code: str) -> None:
        with self.sessions.begin() as db:
            row = db.get(Automation, automation_id)
            outbox = db.get(AutomationScheduleOutbox, automation_id)
            if row is not None and outbox is not None and outbox.desired_revision == revision:
                row.schedule_error_code = code[:80]
                delay = min(300, max(5, 2 ** min(outbox.attempts, 8)))
                outbox.lease_until = utcnow() + timedelta(seconds=delay)

    @staticmethod
    def occurrence_key(owner: str, automation_id: str, revision: int, due_at: datetime) -> str:
        canonical = aware(due_at).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        return hashlib.sha256(f"{owner}|{automation_id}|{revision}|{canonical}".encode()).hexdigest()

    @staticmethod
    def event_occurrence_key(owner: str, automation_id: str, revision: int, event_id: str) -> str:
        return hashlib.sha256(f"{owner}|{automation_id}|{revision}|event|{event_id}".encode()).hexdigest()

    def handle_connector_event(self, event: dict) -> None:
        """Wake bounded runs for explicitly configured connected-event automations.

        The connector event is already authenticated, persisted, deduplicated and
        synchronized before this callback is invoked. Provider content remains
        untrusted context; it never changes automation authority.
        """
        event_id = str(event.get("id") or "")
        owner = str(event.get("owner_id") or "")
        grant_id = str(event.get("grant_id") or "")
        if not event_id or not owner or not grant_id:
            return
        with self.sessions() as db:
            row = db.scalar(select(ConnectorEvent).where(
                ConnectorEvent.id == event_id,
                ConnectorEvent.owner_id == owner,
                ConnectorEvent.grant_id == grant_id,
            ))
            if row is None:
                return
            candidates = db.scalars(select(Automation).where(
                Automation.owner_id == owner,
                Automation.state == "active",
            ).order_by(Automation.created_at, Automation.id)).all()
            matches = [
                item for item in candidates
                if isinstance(item.schedule, dict)
                and item.schedule.get("kind") == "event"
                and str(item.schedule.get("grant_id") or "") == grant_id
            ]
        for automation in matches:
            self.accept_event_occurrence(automation.id, automation.revision, event_id)

    def accept_event_occurrence(self, automation_id: str, revision: int, event_id: str) -> dict:
        with self.sessions.begin() as db:
            automation = db.scalar(select(Automation).where(
                Automation.id == automation_id,
            ).with_for_update())
            if automation is None:
                raise CoworkerError("automation_missing", "The event automation no longer exists.", 404)
            event = db.scalar(select(ConnectorEvent).where(
                ConnectorEvent.id == event_id,
                ConnectorEvent.owner_id == automation.owner_id,
            ))
            key = self.event_occurrence_key(
                automation.owner_id, automation.id, revision, event_id
            )
            previous = db.scalar(select(AutomationOccurrence).where(
                AutomationOccurrence.automation_id == automation.id,
                AutomationOccurrence.occurrence_key == key,
            ))
            if previous is not None:
                if previous.run_id:
                    return {"occurrence_id": previous.id, "run_id": previous.run_id, "state": previous.state, "replayed": True}
                if previous.state in {"skipped", "blocked", "buffered"}:
                    return {"occurrence_id": previous.id, "run_id": None, "state": previous.state, "reason": previous.reason, "replayed": True}

            reason = None
            if not self.settings.automations_enabled:
                reason = "kill_switch"
            elif event is None or event.grant_id != str(automation.schedule.get("grant_id") or ""):
                reason = "event_source_mismatch"
            elif automation.revision != revision:
                reason = "stale_revision"
            elif automation.state != "active":
                reason = "not_active"
            elif automation.expires_at is not None and aware(automation.expires_at) <= utcnow():
                reason = "expired"

            goal = db.scalar(select(PersonalGoal).where(
                PersonalGoal.id == automation.goal_id,
                PersonalGoal.owner_id == automation.owner_id,
            ))
            grant = db.scalar(select(ConnectorReadGrant).where(
                ConnectorReadGrant.id == str(automation.schedule.get("grant_id") or ""),
                ConnectorReadGrant.owner_id == automation.owner_id,
            ))
            if goal is None or goal.state != "active" or goal.revision != automation.goal_revision:
                reason = reason or "goal_changed"
            if (
                grant is None
                or grant.state != "active"
                or aware(grant.expires_at) <= utcnow()
                or grant.destination != "planner_context"
                or grant.purpose != "agent_context"
            ):
                reason = reason or "grant_revoked"

            due_at = aware(event.received_at) if event is not None else utcnow()
            if previous is None:
                previous = AutomationOccurrence(
                    id=str(uuid4()), owner_id=automation.owner_id, automation_id=automation.id,
                    automation_revision=revision, occurrence_key=key, trigger_event_id=event_id,
                    due_at=due_at, state="accepting", created_at=utcnow(), updated_at=utcnow(),
                )
                db.add(previous); db.flush()
            if reason:
                previous.state = "skipped"; previous.reason = reason; previous.updated_at = utcnow()
                return {"occurrence_id": previous.id, "run_id": None, "state": "skipped", "reason": reason, "replayed": False}

            active_run = db.scalar(select(AgentRun.id).join(
                AutomationOccurrence, AutomationOccurrence.run_id == AgentRun.id,
            ).where(
                AutomationOccurrence.automation_id == automation.id,
                AutomationOccurrence.id != previous.id,
                AgentRun.state.not_in({"completed", "failed", "cancelled"}),
            ).limit(1))
            if active_run is not None:
                if automation.overlap_policy == "skip":
                    previous.state = "skipped"; previous.reason = "overlap"; previous.updated_at = utcnow()
                    return {"occurrence_id": previous.id, "run_id": None, "state": "skipped", "reason": "overlap", "replayed": False}
                buffered = db.scalar(select(AutomationOccurrence.id).where(
                    AutomationOccurrence.automation_id == automation.id,
                    AutomationOccurrence.state == "buffered",
                    AutomationOccurrence.id != previous.id,
                ).limit(1))
                if buffered is not None:
                    previous.state = "skipped"; previous.reason = "buffer_full"; previous.updated_at = utcnow()
                    return {"occurrence_id": previous.id, "run_id": None, "state": "skipped", "reason": "buffer_full", "replayed": False}
                previous.state = "buffered"; previous.reason = "overlap"; previous.updated_at = utcnow()
                return {"occurrence_id": previous.id, "run_id": None, "state": "buffered", "reason": "overlap", "replayed": False}

            owner = automation.owner_id
            goal_id = automation.goal_id
            goal_revision = automation.goal_revision
            output_language = automation.output_language
            objective = goal.objective
            grant_id = grant.id
            workspace_id = automation.workspace_id
            timezone_name = automation.timezone
            quiet_hours = automation.quiet_hours

        idempotency_key = f"automation-event:{automation_id}:{revision}:{event_id}"
        try:
            run, _ = self.agent.create(
                owner,
                AgentRunCreate(
                    goal=objective,
                    document_ids=[],
                    action_ids=[],
                    memory_namespaces=[],
                    connector_read_grant_ids=[grant_id],
                    output_language=output_language,
                ),
                idempotency_key,
                persistent_goal_id=goal_id,
                persistent_goal_revision=goal_revision,
            )
        except CoworkerError as error:
            with self.sessions.begin() as db:
                occurrence = db.scalar(select(AutomationOccurrence).where(
                    AutomationOccurrence.automation_id == automation_id,
                    AutomationOccurrence.occurrence_key == key,
                ).with_for_update())
                if occurrence is not None:
                    occurrence.state = "blocked"; occurrence.reason = error.code[:80]; occurrence.updated_at = utcnow()
            return {"occurrence_id": occurrence.id if occurrence else None, "run_id": None, "state": "blocked", "reason": error.code, "replayed": False}

        with self.sessions.begin() as db:
            occurrence = db.scalar(select(AutomationOccurrence).where(
                AutomationOccurrence.automation_id == automation_id,
                AutomationOccurrence.occurrence_key == key,
            ).with_for_update())
            if occurrence is None:
                raise CoworkerError("automation_occurrence_lost", "Connected-event occurrence state was unavailable.", 503)
            occurrence.run_id = run["id"]; occurrence.state = "accepted"; occurrence.reason = None; occurrence.updated_at = utcnow()
            visible_at = self.notifications.visible_at_after_quiet_hours(
                due_at, timezone_name, quiet_hours,
            )
            self.notifications.enqueue_pending(
                db,
                owner=owner,
                workspace_id=workspace_id,
                automation_id=automation_id,
                occurrence_id=occurrence.id,
                kind="automation_started",
                title="Connected update started bounded work",
                message="Your personal agent started one bounded run after an authorized connected update.",
                visible_at=visible_at,
                expires_at=visible_at + timedelta(days=30),
            )
            return {"occurrence_id": occurrence.id, "run_id": run["id"], "state": "accepted", "replayed": False}

    def accept_occurrence(self, automation_id: str, revision: int, due_at: datetime) -> dict:
        """Idempotently accept one Temporal Schedule occurrence and wake one bounded run."""
        due_at = aware(due_at).astimezone(timezone.utc)
        with self.sessions.begin() as db:
            row = db.scalar(select(Automation).where(Automation.id == automation_id).with_for_update())
            if row is None:
                raise CoworkerError("automation_missing", "The scheduled automation no longer exists.", 404)
            key = self.occurrence_key(row.owner_id, row.id, revision, due_at)
            previous = db.scalar(select(AutomationOccurrence).where(
                AutomationOccurrence.automation_id == row.id, AutomationOccurrence.occurrence_key == key,
            ))
            if previous is not None:
                if previous.run_id:
                    return {"occurrence_id": previous.id, "run_id": previous.run_id, "state": previous.state, "replayed": True}
                if previous.state in {"skipped", "blocked", "buffered"}:
                    return {
                        "occurrence_id": previous.id, "run_id": None, "state": previous.state,
                        "reason": previous.reason, "replayed": True,
                    }
            if previous is None:
                previous = AutomationOccurrence(
                    id=str(uuid4()), owner_id=row.owner_id, automation_id=row.id, automation_revision=revision,
                    occurrence_key=key, due_at=due_at, state="accepting", created_at=utcnow(), updated_at=utcnow(),
                )
                db.add(previous); db.flush()
            owner, goal_id, goal_revision, output_language = row.owner_id, row.goal_id, row.goal_revision, row.output_language
            objective = db.scalar(select(PersonalGoal.objective).where(
                PersonalGoal.id == goal_id, PersonalGoal.owner_id == owner,
            ))
            reason = None
            if not self.settings.automations_enabled:
                reason = "kill_switch"
            elif row.revision != revision:
                reason = "stale_revision"
            elif row.state != "active":
                reason = "not_active"
            elif row.expires_at is not None and aware(row.expires_at) <= due_at:
                reason = "expired"
            elif objective is None:
                reason = "goal_missing"
            elif utcnow() - due_at > timedelta(seconds=row.catchup_window_seconds):
                reason = "catchup_window"
            active_run = db.scalar(select(AgentRun.id).join(
                AutomationOccurrence, AutomationOccurrence.run_id == AgentRun.id,
            ).where(
                AutomationOccurrence.automation_id == row.id,
                AutomationOccurrence.id != previous.id,
                AgentRun.state.not_in({"completed", "failed", "cancelled"}),
            ).limit(1))
            if reason:
                previous.state = "skipped"; previous.reason = reason; previous.updated_at = utcnow()
                return {"occurrence_id": previous.id, "run_id": None, "state": "skipped", "reason": reason, "replayed": False}
            if active_run is not None:
                if row.overlap_policy == "skip":
                    previous.state = "skipped"; previous.reason = "overlap"; previous.updated_at = utcnow()
                    return {"occurrence_id": previous.id, "run_id": None, "state": "skipped", "reason": "overlap", "replayed": False}
                buffered = db.scalar(select(AutomationOccurrence.id).where(
                    AutomationOccurrence.automation_id == row.id,
                    AutomationOccurrence.state == "buffered",
                    AutomationOccurrence.id != previous.id,
                ).limit(1))
                if buffered is not None:
                    previous.state = "skipped"; previous.reason = "buffer_full"; previous.updated_at = utcnow()
                    return {"occurrence_id": previous.id, "run_id": None, "state": "skipped", "reason": "buffer_full", "replayed": False}
                previous.state = "buffered"; previous.reason = "overlap"; previous.updated_at = utcnow()
                return {"occurrence_id": previous.id, "run_id": None, "state": "buffered", "reason": "overlap", "replayed": False}

        idempotency_key = f"automation:{automation_id}:{revision}:{self.occurrence_key(owner, automation_id, revision, due_at)[:40]}"
        try:
            run, _ = self.agent.create(
                owner,
                AgentRunCreate(goal=objective, document_ids=[], action_ids=[], memory_namespaces=[], output_language=output_language),
                idempotency_key,
                persistent_goal_id=goal_id,
                persistent_goal_revision=goal_revision,
            )
        except CoworkerError as error:
            with self.sessions.begin() as db:
                occurrence = db.scalar(select(AutomationOccurrence).where(
                    AutomationOccurrence.automation_id == automation_id,
                    AutomationOccurrence.occurrence_key == self.occurrence_key(owner, automation_id, revision, due_at),
                ).with_for_update())
                if occurrence is not None:
                    occurrence.state = "blocked"; occurrence.reason = error.code[:80]; occurrence.updated_at = utcnow()
            return {"occurrence_id": occurrence.id if occurrence else None, "run_id": None, "state": "blocked", "reason": error.code, "replayed": False}

        with self.sessions.begin() as db:
            occurrence = db.scalar(select(AutomationOccurrence).where(
                AutomationOccurrence.automation_id == automation_id,
                AutomationOccurrence.occurrence_key == self.occurrence_key(owner, automation_id, revision, due_at),
            ).with_for_update())
            if occurrence is None:
                raise CoworkerError("automation_occurrence_lost", "Scheduled occurrence state was unavailable.", 503)
            occurrence.run_id = run["id"]; occurrence.state = "accepted"; occurrence.reason = None; occurrence.updated_at = utcnow()
            automation = db.get(Automation, automation_id)
            visible_at = self.notifications.visible_at_after_quiet_hours(
                due_at,
                automation.timezone,
                automation.quiet_hours,
            )
            self.notifications.enqueue_pending(
                db,
                owner=owner,
                workspace_id=automation.workspace_id,
                automation_id=automation_id,
                occurrence_id=occurrence.id,
                kind="automation_started",
                title="Scheduled work started",
                message="Your personal agent started the scheduled bounded run.",
                visible_at=visible_at,
                expires_at=visible_at + timedelta(days=30),
            )
            return {"occurrence_id": occurrence.id, "run_id": run["id"], "state": "accepted", "replayed": False}

    @staticmethod
    def _notification_visible_at(
        value: datetime,
        timezone_name: str,
        quiet: dict | None,
    ) -> datetime:
        from .notification_repository import NotificationRepository

        return NotificationRepository.visible_at_after_quiet_hours(
            value,
            timezone_name,
            quiet,
        )

    def claim_buffered_occurrences(self, limit: int = 10) -> list[dict]:
        """Release BUFFER_ONE occurrences after the previous run is terminal.

        The accepting state is a short durable lease: a process loss before admission
        is reclaimable rather than stranding the occurrence forever.
        """
        with self.sessions.begin() as db:
            now = utcnow()
            rows = db.scalars(select(AutomationOccurrence).where(
                or_(
                    AutomationOccurrence.state == "buffered",
                    and_(
                        AutomationOccurrence.state == "accepting",
                        AutomationOccurrence.updated_at < now - timedelta(seconds=30),
                    ),
                ),
            ).order_by(AutomationOccurrence.due_at).limit(limit).with_for_update(skip_locked=True)).all()
            result = []
            for occurrence in rows:
                active = db.scalar(select(AgentRun.id).join(
                    AutomationOccurrence, AutomationOccurrence.run_id == AgentRun.id,
                ).where(
                    AutomationOccurrence.automation_id == occurrence.automation_id,
                    AutomationOccurrence.id != occurrence.id,
                    AgentRun.state.not_in({"completed", "failed", "cancelled"}),
                ).limit(1))
                if active is not None:
                    continue
                occurrence.state = "accepting"; occurrence.reason = None; occurrence.updated_at = now
                result.append({
                    "automation_id": occurrence.automation_id,
                    "revision": occurrence.automation_revision,
                    "due_at": iso(occurrence.due_at),
                    "event_id": occurrence.trigger_event_id,
                })
            return result

    def claim_notifications(self, limit: int = 20) -> list[str]:
        return self.notifications.claim_notifications(limit)

    def deliver_notification(self, notification_id: str) -> None:
        self.notifications.deliver_notification(notification_id)

    def notifications(self, owner: str, after: datetime | None = None) -> list[dict]:
        return self.notifications.notifications(owner, after)

    def mark_read(self, owner: str, notification_id: str) -> dict:
        return self.notifications.mark_read(owner, notification_id)
