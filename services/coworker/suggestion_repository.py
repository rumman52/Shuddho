from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from sqlalchemy import select

from .errors import CoworkerError
from .models import (
    Account,
    AgentRun,
    AuditEvent,
    Automation,
    Document,
    MemoryFact,
    PersonalGoal,
    utcnow,
)
from .repository import aware, iso, not_found
from .suggestion_schemas import PersonalSuggestionPreferences


class SuggestionRepository:
    """Deterministic, owner-scoped, inert PA-10 suggestion surface."""

    PREFERENCES_KEY = "personal_suggestions"
    MAX_DISMISSED_IDS = 100
    MAX_SUGGESTIONS = 5
    ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")

    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        from uuid import uuid4

        db.add(
            AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=resource,
                action=action,
            )
        )

    @classmethod
    def _normalized_preferences(cls, value: dict | None) -> dict:
        if not isinstance(value, dict):
            return {"enabled": False, "dismissed_ids": []}
        raw = value.get(cls.PREFERENCES_KEY)
        if not isinstance(raw, dict):
            return {"enabled": False, "dismissed_ids": []}
        dismissed = raw.get("dismissed_ids")
        if not isinstance(dismissed, list):
            dismissed = []
        safe_ids: list[str] = []
        for item in dismissed:
            if (
                isinstance(item, str)
                and cls.ID_PATTERN.fullmatch(item)
                and item not in safe_ids
            ):
                safe_ids.append(item)
            if len(safe_ids) >= cls.MAX_DISMISSED_IDS:
                break
        return {
            "enabled": raw.get("enabled") is True,
            "dismissed_ids": safe_ids,
        }

    def _require_available(self) -> None:
        if not self.settings.personal_goals_enabled:
            raise CoworkerError(
                "personal_suggestions_unavailable",
                "Personal suggestions require persistent goals to be enabled.",
                409,
            )

    def preferences(self, owner: str) -> dict:
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            value = self._normalized_preferences(account.preferences)
            return {
                "available": self.settings.personal_goals_enabled,
                "enabled": (
                    value["enabled"]
                    if self.settings.personal_goals_enabled
                    else False
                ),
                "dismissed_count": len(value["dismissed_ids"]),
            }

    def save_preferences(
        self,
        owner: str,
        request: PersonalSuggestionPreferences,
    ) -> dict:
        self._require_available()
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
                "dismissed_ids": previous["dismissed_ids"],
            }
            account.preferences = current
            self._audit(db, owner, owner, "personal_suggestion_preferences_updated")
            return {
                "available": True,
                "enabled": request.enabled,
                "dismissed_count": len(previous["dismissed_ids"]),
            }

    @staticmethod
    def _suggestion_id(
        owner: str,
        goal: PersonalGoal,
        kind: str,
        due_at,
    ) -> str:
        due_marker = iso(aware(due_at)) if due_at is not None else ""
        raw = (
            f"{owner}|{goal.id}|{goal.revision}|{kind}|{due_marker}"
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _time_score(due_at, now, windows: tuple[tuple[timedelta, int], ...]) -> int:
        delta = aware(due_at) - now
        for window, score in windows:
            if delta <= window:
                return score
        return 0

    def _valid_resource_sets(
        self,
        db,
        owner: str,
        goals: list[PersonalGoal],
        now,
    ) -> tuple[set[str], set[str]]:
        document_ids: set[str] = set()
        namespaces: set[str] = set()
        for goal in goals:
            for resource in list(goal.authorized_resources or []):
                if not isinstance(resource, dict):
                    continue
                kind = resource.get("kind")
                reference = resource.get("reference")
                if not isinstance(reference, str) or not reference:
                    continue
                if kind == "document":
                    document_ids.add(reference)
                elif kind == "memory_namespace":
                    namespaces.add(reference)

        valid_documents: set[str] = set()
        if document_ids:
            valid_documents = set(
                db.scalars(
                    select(Document.id).where(
                        Document.owner_id == owner,
                        Document.id.in_(document_ids),
                        Document.deleted.is_(False),
                    )
                ).all()
            )

        valid_namespaces: set[str] = set()
        if namespaces and self.settings.agent_memory_enabled:
            facts = db.scalars(
                select(MemoryFact).where(
                    MemoryFact.owner_id == owner,
                    MemoryFact.namespace.in_(namespaces),
                )
            ).all()
            for fact in facts:
                if fact.expires_at is None or aware(fact.expires_at) > now:
                    valid_namespaces.add(fact.namespace)
        return valid_documents, valid_namespaces

    @staticmethod
    def _resource_count(
        goal: PersonalGoal,
        valid_documents: set[str],
        valid_namespaces: set[str],
    ) -> int:
        seen: set[tuple[str, str]] = set()
        for resource in list(goal.authorized_resources or []):
            if not isinstance(resource, dict):
                continue
            kind = resource.get("kind")
            reference = resource.get("reference")
            if not isinstance(reference, str):
                continue
            if kind == "document" and reference in valid_documents:
                seen.add((kind, reference))
            elif (
                kind == "memory_namespace"
                and reference in valid_namespaces
            ):
                seen.add((kind, reference))
        return len(seen)

    def _candidates(self, db, owner: str) -> list[dict]:
        now = utcnow()
        goals = db.scalars(
            select(PersonalGoal)
            .where(
                PersonalGoal.owner_id == owner,
                PersonalGoal.state == "active",
            )
            .order_by(PersonalGoal.updated_at.desc(), PersonalGoal.id)
        ).all()
        if not goals:
            return []

        active_automation_goal_ids: set[str] = set()
        if self.settings.automations_enabled:
            active_automation_goal_ids = set(
                db.scalars(
                    select(Automation.goal_id).where(
                        Automation.owner_id == owner,
                        Automation.state == "active",
                    )
                ).all()
            )

        run_pairs = {
            (goal_id, goal_revision)
            for goal_id, goal_revision in db.execute(
                select(AgentRun.goal_id, AgentRun.goal_revision).where(
                    AgentRun.owner_id == owner,
                    AgentRun.goal_id.is_not(None),
                )
            ).all()
        }
        valid_documents, valid_namespaces = self._valid_resource_sets(
            db,
            owner,
            goals,
            now,
        )

        candidates: list[dict] = []
        for goal in goals:
            goal_candidates: list[dict] = []

            if goal.next_review_at is not None:
                score = self._time_score(
                    goal.next_review_at,
                    now,
                    (
                        (timedelta(seconds=0), 100),
                        (timedelta(hours=24), 90),
                        (timedelta(hours=48), 80),
                    ),
                )
                if score:
                    review_at = aware(goal.next_review_at)
                    reason = (
                        "This goal's scheduled review is overdue."
                        if review_at <= now
                        else "This goal's scheduled review is due soon."
                    )
                    goal_candidates.append(
                        self._candidate(
                            owner,
                            goal,
                            "goal_review_due",
                            score,
                            reason,
                            review_at,
                            "review_goal",
                            0,
                        )
                    )

            if goal.deadline_at is not None:
                deadline = aware(goal.deadline_at)
                if deadline <= now:
                    goal_candidates.append(
                        self._candidate(
                            owner,
                            goal,
                            "goal_deadline_due",
                            95,
                            "This goal's deadline has passed. Review it before starting more work.",
                            deadline,
                            "review_goal",
                            0,
                        )
                    )
                elif deadline <= now + timedelta(days=7):
                    has_active_automation = (
                        goal.id in active_automation_goal_ids
                    )
                    if self.settings.automations_enabled and not has_active_automation:
                        score = self._time_score(
                            deadline,
                            now,
                            (
                                (timedelta(hours=24), 88),
                                (timedelta(days=3), 78),
                                (timedelta(days=7), 68),
                            ),
                        )
                        goal_candidates.append(
                            self._candidate(
                                owner,
                                goal,
                                "goal_schedule_due",
                                score,
                                "This goal has a near deadline and no active automation. Review whether a bounded schedule would help.",
                                deadline,
                                "open_automations",
                                0,
                            )
                        )
                    else:
                        score = self._time_score(
                            deadline,
                            now,
                            (
                                (timedelta(hours=24), 86),
                                (timedelta(days=3), 76),
                                (timedelta(days=7), 66),
                            ),
                        )
                        goal_candidates.append(
                            self._candidate(
                                owner,
                                goal,
                                "goal_deadline_due",
                                score,
                                "This goal's deadline is approaching. Review its current plan and progress.",
                                deadline,
                                "review_goal",
                                0,
                            )
                        )

            resource_count = self._resource_count(
                goal,
                valid_documents,
                valid_namespaces,
            )
            if (
                resource_count > 0
                and (goal.id, goal.revision) not in run_pairs
            ):
                noun = "resource" if resource_count == 1 else "resources"
                goal_candidates.append(
                    self._candidate(
                        owner,
                        goal,
                        "goal_context_ready",
                        55,
                        f"{resource_count} still-owned authorized {noun} available for this goal. Review the goal before choosing whether to start bounded work.",
                        None,
                        "review_goal",
                        resource_count,
                    )
                )

            if goal_candidates:
                goal_candidates.sort(
                    key=lambda item: (
                        -item["relevance_score"],
                        item["kind"],
                        item["id"],
                    )
                )
                candidates.append(goal_candidates[0])

        candidates.sort(
            key=lambda item: (
                -item["relevance_score"],
                item["due_at"] or "9999-12-31T23:59:59+00:00",
                item["goal_id"],
                item["id"],
            )
        )
        return candidates[: self.MAX_SUGGESTIONS]

    def _candidate(
        self,
        owner: str,
        goal: PersonalGoal,
        kind: str,
        relevance_score: int,
        reason: str,
        due_at,
        action: str,
        context_resource_count: int,
    ) -> dict:
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

    def list_response(self, owner: str) -> dict:
        if not self.settings.personal_goals_enabled:
            return {
                "available": False,
                "enabled": False,
                "suggestions": [],
            }
        with self.sessions() as db:
            account = db.scalar(select(Account).where(Account.id == owner))
            if account is None:
                raise not_found()
            preferences = self._normalized_preferences(account.preferences)
            if not preferences["enabled"]:
                return {
                    "available": True,
                    "enabled": False,
                    "suggestions": [],
                }
            dismissed = set(preferences["dismissed_ids"])
            suggestions = [
                item
                for item in self._candidates(db, owner)
                if item["id"] not in dismissed
            ]
            return {
                "available": True,
                "enabled": True,
                "suggestions": suggestions,
            }

    def dismiss(self, owner: str, suggestion_id: str) -> dict:
        self._require_available()
        if not self.ID_PATTERN.fullmatch(suggestion_id):
            raise not_found()
        with self.sessions.begin() as db:
            account = db.scalar(
                select(Account).where(Account.id == owner).with_for_update()
            )
            if account is None:
                raise not_found()
            preferences = self._normalized_preferences(account.preferences)
            if suggestion_id in preferences["dismissed_ids"]:
                return {"id": suggestion_id, "state": "dismissed"}

            candidate_ids = {
                item["id"]
                for item in self._candidates(db, owner)
            }
            if suggestion_id not in candidate_ids:
                raise not_found()

            dismissed_ids = [
                suggestion_id,
                *preferences["dismissed_ids"],
            ][: self.MAX_DISMISSED_IDS]
            current = dict(account.preferences or {})
            current[self.PREFERENCES_KEY] = {
                "enabled": preferences["enabled"],
                "dismissed_ids": dismissed_ids,
            }
            account.preferences = current
            self._audit(db, owner, suggestion_id, "personal_suggestion_dismissed")
            return {"id": suggestion_id, "state": "dismissed"}
