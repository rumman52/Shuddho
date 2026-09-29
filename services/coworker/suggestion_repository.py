from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from sqlalchemy import select

from .errors import CoworkerError
from .models import (
    Account,
    AgentRun,
    AuditEvent,
    Automation,
    Document,
    DocumentVersion,
    MemoryFact,
    Notification,
    PersonalGoal,
    utcnow,
)
from .repository import aware, iso, not_found
from .suggestion_schemas import PersonalSuggestionPreferences


class SuggestionRepository:
    """Deterministic, owner-scoped PA-10 preview and bounded in-app delivery."""

    PREFERENCES_KEY = "personal_suggestions"
    SOURCE_KIND = "personal_suggestion"
    MAX_DISMISSED_IDS = 100
    MAX_SUGGESTIONS = 5
    ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
    DELIVERY_QUIET_HOURS = {"start": "22:00", "end": "07:00"}
    DELIVERY_TTL = timedelta(days=7)
    CONTEXT_DELIVERY_TTL = timedelta(days=14)

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
            return {"enabled": False, "delivery_enabled": False, "dismissed_ids": []}
        raw = value.get(cls.PREFERENCES_KEY)
        if not isinstance(raw, dict):
            return {"enabled": False, "delivery_enabled": False, "dismissed_ids": []}
        dismissed = raw.get("dismissed_ids")
        if not isinstance(dismissed, list):
            dismissed = []
        safe_ids: list[str] = []
        for item in dismissed:
            if isinstance(item, str) and cls.ID_PATTERN.fullmatch(item) and item not in safe_ids:
                safe_ids.append(item)
            if len(safe_ids) >= cls.MAX_DISMISSED_IDS:
                break
        enabled = raw.get("enabled") is True
        return {
            "enabled": enabled,
            "delivery_enabled": enabled and raw.get("delivery_enabled") is True,
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

    def preferences(self, owner: str) -> dict:
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            value = self._normalized_preferences(account.preferences)
            available = self.settings.personal_goals_enabled
            delivery_available = self._delivery_available()
            return {
                "available": available,
                "enabled": value["enabled"] if available else False,
                "delivery_available": delivery_available,
                "delivery_enabled": value["delivery_enabled"] if delivery_available else False,
                "dismissed_count": len(value["dismissed_ids"]),
            }

    def save_preferences(self, owner: str, request: PersonalSuggestionPreferences) -> dict:
        self._require_available()
        if request.delivery_enabled and not self.settings.automations_enabled:
            raise CoworkerError(
                "personal_suggestion_delivery_unavailable",
                "In-app suggestion delivery requires the existing Notifications inbox.",
                409,
            )
        with self.sessions.begin() as db:
            account = db.scalar(select(Account).where(Account.id == owner).with_for_update())
            if account is None:
                raise not_found()
            current = dict(account.preferences or {})
            previous = self._normalized_preferences(current)
            current[self.PREFERENCES_KEY] = {
                "enabled": request.enabled,
                "delivery_enabled": request.delivery_enabled,
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
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            prefs = self._normalized_preferences(account.preferences)
            allowed = (
                self._delivery_available() and prefs["enabled"] and prefs["delivery_enabled"]
                and self.notifications.in_app_enabled(account.preferences)
            )
            if allowed:
                plans = self._delivery_plans(db, owner, set(prefs["dismissed_ids"]))
        self.notifications.reconcile_sources(owner, self.SOURCE_KIND, plans)

    def notification_source_allowed(self, db, notification: Notification, account: Account) -> bool:
        source_id = notification.source_id
        if source_id is None or not self.ID_PATTERN.fullmatch(source_id) or not self._delivery_available():
            return False
        prefs = self._normalized_preferences(account.preferences)
        if not prefs["enabled"] or not prefs["delivery_enabled"] or source_id in set(prefs["dismissed_ids"]):
            return False
        return source_id in {item["id"] for item in self._candidates(db, notification.owner_id)}

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
                    "enabled": prefs["enabled"], "delivery_enabled": prefs["delivery_enabled"],
                    "dismissed_ids": [suggestion_id, *prefs["dismissed_ids"]][:self.MAX_DISMISSED_IDS],
                }
                account.preferences = current
                self._audit(db, owner, suggestion_id, "personal_suggestion_dismissed")
        self.reconcile_delivery(owner)
        return {"id": suggestion_id, "state": "dismissed"}
