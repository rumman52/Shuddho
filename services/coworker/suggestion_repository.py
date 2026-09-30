from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from .errors import CoworkerError
from .models import (
    Account,
    AgentRun,
    AuditEvent,
    Automation,
    ConnectorEvent,
    ConnectorReadGrant,
    Document,
    DocumentVersion,
    MemoryFact,
    Notification,
    PersonalGoal,
    Workspace,
    utcnow,
)
from .repository import aware, iso, not_found
from .suggestion_schemas import PersonalSuggestionPreferences


class SuggestionRepository:
    """Deterministic, owner-scoped PA-10 preview and bounded in-app delivery."""

    PREFERENCES_KEY = "personal_suggestions"
    SOURCE_KIND = "personal_suggestion"
    EVENT_SOURCE_KIND = "personal_suggestion_event"
    MAX_DISMISSED_IDS = 100
    MAX_SUGGESTIONS = 5
    ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
    DELIVERY_QUIET_HOURS = {"start": "22:00", "end": "07:00"}
    DELIVERY_TTL = timedelta(days=7)
    CONTEXT_DELIVERY_TTL = timedelta(days=14)
    EVENT_DELIVERY_TTL = timedelta(hours=24)
    EVENT_SOURCE_LOOKBACK = timedelta(hours=36)
    EVENT_DEDUPE_WINDOW = timedelta(hours=6)

    def __init__(self, sessions, settings, notifications):
        self.sessions = sessions
        self.settings = settings
        self.notifications = notifications

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        from uuid import uuid4
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    @classmethod
    def _normalized_preferences(cls, value: dict | None) -> dict:
        if not isinstance(value, dict):
            return {
                "enabled": False,
                "delivery_enabled": False,
                "event_delivery_enabled": False,
                "event_timezone": "UTC",
                "dismissed_ids": [],
            }
        raw = value.get(cls.PREFERENCES_KEY)
        if not isinstance(raw, dict):
            return {
                "enabled": False,
                "delivery_enabled": False,
                "event_delivery_enabled": False,
                "event_timezone": "UTC",
                "dismissed_ids": [],
            }
        dismissed = raw.get("dismissed_ids")
        if not isinstance(dismissed, list):
            dismissed = []
        safe_ids: list[str] = []
        for item in dismissed:
            if isinstance(item, str) and cls.ID_PATTERN.fullmatch(item) and item not in safe_ids:
                safe_ids.append(item)
            if len(safe_ids) >= cls.MAX_DISMISSED_IDS:
                break

        event_timezone = raw.get("event_timezone")
        timezone_valid = isinstance(event_timezone, str) and 0 < len(event_timezone) <= 64
        if timezone_valid:
            try:
                ZoneInfo(event_timezone)
            except ZoneInfoNotFoundError:
                timezone_valid = False
        if not timezone_valid:
            event_timezone = "UTC"

        enabled = raw.get("enabled") is True
        delivery_enabled = enabled and raw.get("delivery_enabled") is True
        event_delivery_enabled = (
            delivery_enabled
            and timezone_valid
            and raw.get("event_delivery_enabled") is True
        )
        return {
            "enabled": enabled,
            "delivery_enabled": delivery_enabled,
            "event_delivery_enabled": event_delivery_enabled,
            "event_timezone": event_timezone,
            "dismissed_ids": safe_ids,
        }

    def _require_available(self) -> None:
        if not self.settings.personal_goals_enabled:
            raise CoworkerError(
                "personal_suggestions_unavailable",
                "Personal suggestions require persistent goals to be enabled.",
                409,
            )

    def _delivery_available(self) -> bool:
        return self.settings.personal_goals_enabled and self.settings.automations_enabled

    def _event_delivery_available(self) -> bool:
        return self._delivery_available() and self.settings.connector_reads_enabled

    def preferences(self, owner: str) -> dict:
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            value = self._normalized_preferences(account.preferences)
            available = self.settings.personal_goals_enabled
            delivery_available = self._delivery_available()
            event_delivery_available = self._event_delivery_available()
            return {
                "available": available,
                "enabled": value["enabled"] if available else False,
                "delivery_available": delivery_available,
                "delivery_enabled": value["delivery_enabled"] if delivery_available else False,
                "event_delivery_available": event_delivery_available,
                "event_delivery_enabled": (
                    value["event_delivery_enabled"]
                    if event_delivery_available
                    else False
                ),
                "event_timezone": value["event_timezone"],
                "model_relevance_available": (
                    available
                    and self.settings.suggestion_model_relevance_enabled
                    and self.settings.intelligent_planner_enabled
                    and bool(self.settings.deepseek_api_key)
                ),
                "dismissed_count": len(value["dismissed_ids"]),
            }

    def save_preferences(
        self,
        owner: str,
        request: PersonalSuggestionPreferences,
    ) -> dict:
        self._require_available()
        if request.delivery_enabled and not self.settings.automations_enabled:
            raise CoworkerError(
                "personal_suggestion_delivery_unavailable",
                "In-app suggestion delivery requires the existing Notifications inbox.",
                409,
            )
        if request.event_delivery_enabled and not self.settings.connector_reads_enabled:
            raise CoworkerError(
                "personal_suggestion_event_delivery_unavailable",
                "Event-triggered suggestions require connected reads to be enabled.",
                409,
            )
        with self.sessions.begin() as db:
            account = db.scalar(
                select(Account).where(Account.id == owner).with_for_update()
            )
            if account is None:
                raise not_found()
            current = dict(account.preferences or {})
            previous = self._normalized_preferences(current)
            current[self.PREFERENCES_KEY] = {
                "enabled": request.enabled,
                "delivery_enabled": request.delivery_enabled,
                "event_delivery_enabled": request.event_delivery_enabled,
                "event_timezone": request.event_timezone,
                "dismissed_ids": previous["dismissed_ids"],
            }
            account.preferences = current
            self._audit(db, owner, owner, "personal_suggestion_preferences_updated")
        self.reconcile_delivery(owner)
        return self.preferences(owner)

    @staticmethod
    def _suggestion_id(owner: str, goal: PersonalGoal, kind: str, due_at) -> str:
        due_marker = iso(aware(due_at)) if due_at is not None else ""
        raw = f"{owner}|{goal.id}|{goal.revision}|{kind}|{due_marker}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _time_score(due_at, now, windows: tuple[tuple[timedelta, int], ...]) -> int:
        delta = aware(due_at) - now
        for window, score in windows:
            if delta <= window:
                return score
        return 0

    def _valid_resource_sets(self, db, owner: str, goals: list[PersonalGoal], now) -> tuple[set[str], set[str]]:
        document_ids: set[str] = set()
        namespaces: set[str] = set()
        for goal in goals:
            for resource in list(goal.authorized_resources or []):
                if not isinstance(resource, dict):
                    continue
                kind, reference = resource.get("kind"), resource.get("reference")
                if not isinstance(reference, str) or not reference:
                    continue
                if kind == "document":
                    document_ids.add(reference)
                elif kind == "memory_namespace":
                    namespaces.add(reference)
        valid_documents: set[str] = set()
        if document_ids:
            valid_documents = set(db.scalars(
                select(Document.id).join(DocumentVersion, DocumentVersion.document_id == Document.id).where(
                    Document.owner_id == owner,
                    Document.id.in_(document_ids),
                    Document.deleted.is_(False),
                    DocumentVersion.owner_id == owner,
                    DocumentVersion.state == "uploaded",
                ).distinct()
            ).all())
        valid_namespaces: set[str] = set()
        if namespaces and self.settings.agent_memory_enabled:
            facts = db.scalars(select(MemoryFact).where(
                MemoryFact.owner_id == owner,
                MemoryFact.namespace.in_(namespaces),
            )).all()
            for fact in facts:
                if fact.expires_at is None or aware(fact.expires_at) > now:
                    valid_namespaces.add(fact.namespace)
        return valid_documents, valid_namespaces

    @staticmethod
    def _resource_count(goal: PersonalGoal, valid_documents: set[str], valid_namespaces: set[str]) -> int:
        seen: set[tuple[str, str]] = set()
        for resource in list(goal.authorized_resources or []):
            if not isinstance(resource, dict):
                continue
            kind, reference = resource.get("kind"), resource.get("reference")
            if not isinstance(reference, str):
                continue
            if kind == "document" and reference in valid_documents:
                seen.add((kind, reference))
            elif kind == "memory_namespace" and reference in valid_namespaces:
                seen.add((kind, reference))
        return len(seen)

    def _active_automation_goal_ids(self, db, owner: str) -> set[str]:
        if not self.settings.automations_enabled:
            return set()
        return set(db.scalars(select(Automation.goal_id).where(
            Automation.owner_id == owner, Automation.state == "active"
        )).all())

    def _candidate(self, owner: str, goal: PersonalGoal, kind: str, relevance_score: int,
                   reason: str, due_at, action: str, context_resource_count: int) -> dict:
        return {
            "id": self._suggestion_id(owner, goal, kind, due_at),
            "kind": kind,
            "goal_id": goal.id,
            "goal_revision": goal.revision,
            "relevance_score": relevance_score,
            "reason": reason,
            "due_at": iso(due_at) if due_at is not None else None,
            "action": action,
            "context_resource_count": context_resource_count,
        }

    def _candidates(self, db, owner: str) -> list[dict]:
        now = utcnow()
        goals = db.scalars(select(PersonalGoal).where(
            PersonalGoal.owner_id == owner, PersonalGoal.state == "active"
        ).order_by(PersonalGoal.updated_at.desc(), PersonalGoal.id)).all()
        if not goals:
            return []
        active_automation_goal_ids = self._active_automation_goal_ids(db, owner)
        run_pairs = {(goal_id, revision) for goal_id, revision in db.execute(
            select(AgentRun.goal_id, AgentRun.goal_revision).where(
                AgentRun.owner_id == owner, AgentRun.goal_id.is_not(None)
            )
        ).all()}
        valid_documents, valid_namespaces = self._valid_resource_sets(db, owner, goals, now)
        candidates: list[dict] = []
        for goal in goals:
            items: list[dict] = []
            if goal.next_review_at is not None:
                score = self._time_score(goal.next_review_at, now, (
                    (timedelta(seconds=0), 100), (timedelta(hours=24), 90), (timedelta(hours=48), 80)
                ))
                if score:
                    review_at = aware(goal.next_review_at)
                    reason = "This goal's scheduled review is overdue." if review_at <= now else "This goal's scheduled review is due soon."
                    items.append(self._candidate(owner, goal, "goal_review_due", score, reason, review_at, "review_goal", 0))
            if goal.deadline_at is not None:
                deadline = aware(goal.deadline_at)
                if deadline <= now:
                    items.append(self._candidate(owner, goal, "goal_deadline_due", 95,
                        "This goal's deadline has passed. Review it before starting more work.",
                        deadline, "review_goal", 0))
                elif deadline <= now + timedelta(days=7):
                    no_automation = self.settings.automations_enabled and goal.id not in active_automation_goal_ids
                    windows = ((timedelta(hours=24), 88 if no_automation else 86),
                               (timedelta(days=3), 78 if no_automation else 76),
                               (timedelta(days=7), 68 if no_automation else 66))
                    score = self._time_score(deadline, now, windows)
                    if no_automation:
                        items.append(self._candidate(owner, goal, "goal_schedule_due", score,
                            "This goal has a near deadline and no active automation. Review whether a bounded schedule would help.",
                            deadline, "open_automations", 0))
                    else:
                        items.append(self._candidate(owner, goal, "goal_deadline_due", score,
                            "This goal's deadline is approaching. Review its current plan and progress.",
                            deadline, "review_goal", 0))
            count = self._resource_count(goal, valid_documents, valid_namespaces)
            if count > 0 and (goal.id, goal.revision) not in run_pairs:
                noun = "resource" if count == 1 else "resources"
                items.append(self._candidate(owner, goal, "goal_context_ready", 55,
                    f"{count} still-owned authorized {noun} available for this goal. Review the goal before choosing whether to start bounded work.",
                    None, "review_goal", count))
            if items:
                items.sort(key=lambda item: (-item["relevance_score"], item["kind"], item["id"]))
                candidates.append(items[0])
        candidates.sort(key=lambda item: (
            -item["relevance_score"], item["due_at"] or "9999-12-31T23:59:59+00:00", item["goal_id"], item["id"]
        ))
        return candidates

    @staticmethod
    def _title(kind: str) -> str:
        return {
            "goal_review_due": "Goal review due",
            "goal_deadline_due": "Goal deadline update",
            "goal_schedule_due": "Review a bounded schedule",
            "goal_context_ready": "Authorized goal context is ready",
        }[kind]

    def _future_candidate(self, owner: str, goal: PersonalGoal, now, active_automation_goal_ids: set[str]) -> tuple[datetime, dict, datetime] | None:
        future: list[tuple[datetime, dict, datetime]] = []
        if goal.next_review_at is not None:
            review_at = aware(goal.next_review_at)
            opens_at = review_at - timedelta(hours=48)
            if opens_at > now:
                future.append((opens_at, self._candidate(owner, goal, "goal_review_due", 80,
                    "This goal's scheduled review is due soon.", review_at, "review_goal", 0), review_at))
        if goal.deadline_at is not None:
            deadline = aware(goal.deadline_at)
            opens_at = deadline - timedelta(days=7)
            if opens_at > now:
                no_automation = self.settings.automations_enabled and goal.id not in active_automation_goal_ids
                if no_automation:
                    item = self._candidate(owner, goal, "goal_schedule_due", 68,
                        "This goal has a near deadline and no active automation. Review whether a bounded schedule would help.",
                        deadline, "open_automations", 0)
                else:
                    item = self._candidate(owner, goal, "goal_deadline_due", 66,
                        "This goal's deadline is approaching. Review its current plan and progress.",
                        deadline, "review_goal", 0)
                future.append((opens_at, item, deadline))
        if not future:
            return None
        future.sort(key=lambda value: (value[0], -value[1]["relevance_score"], value[1]["id"]))
        return future[0]

    def _delivery_plans(self, db, owner: str, dismissed: set[str]) -> list[dict]:
        now = utcnow()
        goals = db.scalars(select(PersonalGoal).where(
            PersonalGoal.owner_id == owner, PersonalGoal.state == "active"
        ).order_by(PersonalGoal.updated_at.desc(), PersonalGoal.id)).all()
        if not goals:
            return []
        current_by_goal = {item["goal_id"]: item for item in self._candidates(db, owner)}
        active_automation_goal_ids = self._active_automation_goal_ids(db, owner)
        plans: list[dict] = []
        for goal in goals:
            item = current_by_goal.get(goal.id)
            visible_base = now
            due_at = None
            if item is not None:
                due_at = aware(datetime.fromisoformat(item["due_at"])) if item["due_at"] else None
            else:
                future = self._future_candidate(owner, goal, now, active_automation_goal_ids)
                if future is None:
                    continue
                visible_base, item, due_at = future
            if item["id"] in dismissed:
                continue
            visible_at = self.notifications.visible_at_after_quiet_hours(
                visible_base, goal.timezone, self.DELIVERY_QUIET_HOURS
            )
            expires_at = visible_at + self.CONTEXT_DELIVERY_TTL if due_at is None else max(
                visible_at + timedelta(days=1), due_at + self.DELIVERY_TTL
            )
            plans.append({
                "source_id": item["id"], "workspace_id": goal.workspace_id,
                "kind": self.SOURCE_KIND, "title": self._title(item["kind"]),
                "message": item["reason"], "visible_at": visible_at, "expires_at": expires_at,
            })
        plans.sort(key=lambda plan: (aware(plan["visible_at"]), plan["source_id"]))
        return plans[: self.MAX_SUGGESTIONS]

    def reconcile_delivery(self, owner: str) -> None:
        plans: list[dict] = []
        suppress_event_sources = False
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            prefs = self._normalized_preferences(account.preferences)
            in_app_enabled = self.notifications.in_app_enabled(account.preferences)
            allowed = (
                self._delivery_available()
                and prefs["enabled"]
                and prefs["delivery_enabled"]
                and in_app_enabled
            )
            if allowed:
                plans = self._delivery_plans(
                    db,
                    owner,
                    set(prefs["dismissed_ids"]),
                )
            suppress_event_sources = not (
                self._event_delivery_available()
                and prefs["enabled"]
                and prefs["delivery_enabled"]
                and prefs["event_delivery_enabled"]
                and in_app_enabled
            )
        self.notifications.reconcile_sources(owner, self.SOURCE_KIND, plans)
        if suppress_event_sources:
            self.notifications.reconcile_sources(owner, self.EVENT_SOURCE_KIND, [])

    def notification_source_allowed(self, db, notification: Notification, account: Account) -> bool:
        source_id = notification.source_id
        if source_id is None or not self.ID_PATTERN.fullmatch(source_id) or not self._delivery_available():
            return False
        prefs = self._normalized_preferences(account.preferences)
        if not prefs["enabled"] or not prefs["delivery_enabled"] or source_id in set(prefs["dismissed_ids"]):
            return False
        return source_id in {item["id"] for item in self._candidates(db, notification.owner_id)}

    @classmethod
    def _event_source_id(
        cls,
        owner: str,
        grant_id: str,
        capability: str,
        received_at,
    ) -> str:
        value = aware(received_at)
        bucket_seconds = int(cls.EVENT_DEDUPE_WINDOW.total_seconds())
        bucket = int(value.timestamp()) // bucket_seconds
        raw = f"{owner}|{grant_id}|{capability}|{bucket}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _event_copy(capability: str) -> tuple[str, str]:
        if capability == "email_read":
            return (
                "Connected email context changed",
                "A subscribed connected email source reported an update. Review your connected context before deciding whether to start new work.",
            )
        if capability == "calendar_read":
            return (
                "Connected calendar context changed",
                "A subscribed connected calendar source reported an update. Review your connected context before deciding whether to start new work.",
            )
        return (
            "Connected context changed",
            "A subscribed connected source reported an update. Review it before deciding whether to start new work.",
        )

    def handle_connector_event(self, event: dict) -> None:
        """Create one inert, coalesced in-app review notice from trusted event metadata only."""
        if not self._event_delivery_available():
            return
        event_id = event.get("id")
        owner = event.get("owner_id")
        if not isinstance(event_id, str) or not isinstance(owner, str):
            return
        with self.sessions.begin() as db:
            account = db.scalar(
                select(Account).where(Account.id == owner).with_for_update()
            )
            row = db.scalar(
                select(ConnectorEvent).where(
                    ConnectorEvent.id == event_id,
                    ConnectorEvent.owner_id == owner,
                )
            )
            if account is None or row is None or row.state not in {"processing", "processed"}:
                return
            prefs = self._normalized_preferences(account.preferences)
            if not (
                prefs["enabled"]
                and prefs["delivery_enabled"]
                and prefs["event_delivery_enabled"]
                and self.notifications.in_app_enabled(account.preferences)
            ):
                return
            grant = db.scalar(
                select(ConnectorReadGrant).where(
                    ConnectorReadGrant.id == row.grant_id,
                    ConnectorReadGrant.owner_id == owner,
                    ConnectorReadGrant.state == "active",
                )
            )
            now = utcnow()
            if grant is None or aware(grant.expires_at) <= now:
                return
            workspace_id = db.scalar(
                select(Workspace.id).where(Workspace.owner_id == owner)
            )
            if workspace_id is None:
                return
            source_id = self._event_source_id(
                owner,
                row.grant_id,
                row.capability,
                row.received_at,
            )
            title, message = self._event_copy(row.capability)
            visible_at = self.notifications.visible_at_after_quiet_hours(
                row.received_at,
                prefs["event_timezone"],
                self.DELIVERY_QUIET_HOURS,
            )
            self.notifications.enqueue_pending(
                db,
                owner=owner,
                workspace_id=workspace_id,
                source_kind=self.EVENT_SOURCE_KIND,
                source_id=source_id,
                kind=self.EVENT_SOURCE_KIND,
                title=title,
                message=message,
                visible_at=visible_at,
                expires_at=visible_at + self.EVENT_DELIVERY_TTL,
            )

    def event_notification_source_allowed(
        self,
        db,
        notification: Notification,
        account: Account,
    ) -> bool:
        source_id = notification.source_id
        if (
            source_id is None
            or not self.ID_PATTERN.fullmatch(source_id)
            or not self._event_delivery_available()
        ):
            return False
        prefs = self._normalized_preferences(account.preferences)
        if not (
            prefs["enabled"]
            and prefs["delivery_enabled"]
            and prefs["event_delivery_enabled"]
        ):
            return False
        now = utcnow()
        grants = db.scalars(
            select(ConnectorReadGrant).where(
                ConnectorReadGrant.owner_id == notification.owner_id,
                ConnectorReadGrant.state == "active",
                ConnectorReadGrant.expires_at > now,
            )
        ).all()
        grant_by_id = {grant.id: grant for grant in grants}
        if not grant_by_id:
            return False
        rows = db.scalars(
            select(ConnectorEvent).where(
                ConnectorEvent.owner_id == notification.owner_id,
                ConnectorEvent.grant_id.in_(list(grant_by_id)),
                ConnectorEvent.state.in_(["processing", "processed"]),
                ConnectorEvent.received_at >= now - self.EVENT_SOURCE_LOOKBACK,
            )
        ).all()
        for row in rows:
            grant = grant_by_id.get(row.grant_id)
            if grant is None or grant.capability != row.capability:
                continue
            if self._event_source_id(
                notification.owner_id,
                row.grant_id,
                row.capability,
                row.received_at,
            ) == source_id:
                return True
        return False

    def list_response(self, owner: str) -> dict:
        if not self.settings.personal_goals_enabled:
            return {"available": False, "enabled": False, "suggestions": []}
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            prefs = self._normalized_preferences(account.preferences)
            if not prefs["enabled"]:
                return {"available": True, "enabled": False, "suggestions": []}
            dismissed = set(prefs["dismissed_ids"])
            return {"available": True, "enabled": True,
                    "suggestions": [item for item in self._candidates(db, owner) if item["id"] not in dismissed][:self.MAX_SUGGESTIONS]}

    def relevance_context(self, owner: str) -> dict:
        if not self.settings.suggestion_model_relevance_enabled:
            raise CoworkerError(
                "suggestion_model_relevance_disabled",
                "Model-assisted suggestion ranking is disabled in this deployment.",
                503,
            )
        if not self.settings.intelligent_planner_enabled:
            raise CoworkerError(
                "suggestion_model_relevance_unavailable",
                "Model-assisted suggestion ranking requires the intelligent model boundary.",
                503,
            )
        if not self.settings.deepseek_api_key:
            raise CoworkerError(
                "suggestion_relevance_not_configured",
                "Model-assisted suggestion ranking is not configured.",
                503,
            )
        response = self.list_response(owner)
        if not response["enabled"]:
            raise CoworkerError(
                "personal_suggestions_disabled",
                "Enable deterministic personal suggestions before requesting model ranking.",
                409,
            )
        suggestions = list(response["suggestions"])
        if not suggestions:
            return {"suggestions": [], "model_candidates": []}
        with self.sessions() as db:
            goal_ids = {item["goal_id"] for item in suggestions}
            rows = db.scalars(select(PersonalGoal).where(
                PersonalGoal.owner_id == owner,
                PersonalGoal.id.in_(goal_ids),
                PersonalGoal.state == "active",
            )).all()
            objective_by_id = {row.id: row.objective for row in rows}
        if set(objective_by_id) != goal_ids:
            raise CoworkerError(
                "suggestion_relevance_changed",
                "The bounded suggestion set changed. Refresh before ranking.",
                409,
            )
        return {
            "suggestions": suggestions,
            "model_candidates": [
                {**item, "goal_objective": objective_by_id[item["goal_id"]]}
                for item in suggestions
            ],
        }

    def dismiss(self, owner: str, suggestion_id: str) -> dict:
        self._require_available()
        if not self.ID_PATTERN.fullmatch(suggestion_id):
            raise not_found()
        with self.sessions.begin() as db:
            account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
            if account is None:
                raise not_found()
            prefs = self._normalized_preferences(account.preferences)
            if suggestion_id not in prefs["dismissed_ids"]:
                candidate_ids = {item["id"] for item in self._candidates(db, owner)}
                if suggestion_id not in candidate_ids:
                    raise not_found()
                current = dict(account.preferences or {})
                current[self.PREFERENCES_KEY] = {
                    "enabled": prefs["enabled"],
                    "delivery_enabled": prefs["delivery_enabled"],
                    "event_delivery_enabled": prefs["event_delivery_enabled"],
                    "event_timezone": prefs["event_timezone"],
                    "dismissed_ids": [suggestion_id, *prefs["dismissed_ids"]][:self.MAX_DISMISSED_IDS],
                }
                account.preferences = current
                self._audit(db, owner, suggestion_id, "personal_suggestion_dismissed")
        self.reconcile_delivery(owner)
        return {"id": suggestion_id, "state": "dismissed"}
