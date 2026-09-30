from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from .errors import CoworkerError
from .models import Account, DailyUsage, utcnow
from .provider_capacity import acquire_provider_lease, settle_provider_lease
from .repository import not_found
from .suggestion_relevance_model import SuggestionRelevanceModel
from .suggestion_repository import SuggestionRepository


class SuggestionRelevanceService:
    """Explicit, budgeted PA-10 ranking over already-authorized inert suggestions."""

    def __init__(self, repository: SuggestionRepository, model: SuggestionRelevanceModel):
        self.repo = repository
        self.model = model
        self.settings = repository.settings
        self.sessions = repository.sessions

    def _reservation(self) -> int:
        calls = max(1, self.settings.max_agent_planner_calls)
        return max(
            1,
            min(
                2000,
                self.settings.agent_planner_token_budget // calls,
                self.settings.agent_planner_token_budget,
            ),
        )

    def _reserve(self, owner: str, resource_id: str, tokens: int) -> str:
        with self.sessions.begin() as db:
            if db.scalar(
                select(Account.id).where(Account.id == owner).with_for_update()
            ) is None:
                raise not_found()
            day = utcnow().date().isoformat()
            daily = db.get(DailyUsage, (owner, day))
            if daily is None:
                daily = DailyUsage(
                    owner_id=owner,
                    day=day,
                    allocated_tokens=0,
                    task_count=0,
                )
                db.add(daily)
            if daily.allocated_tokens + tokens > self.settings.daily_token_budget:
                raise CoworkerError(
                    "daily_limit",
                    "Your daily coworker model budget has been reached.",
                    429,
                )
            acquire_provider_lease(
                db,
                self.settings,
                owner_id=owner,
                kind="planner",
                resource_id=resource_id,
                sequence=1,
                reserved_tokens=tokens,
            )
            daily.allocated_tokens += tokens
            return day

    def _settle(
        self,
        owner: str,
        resource_id: str,
        day: str,
        reserved_tokens: int,
        actual_tokens: int | None,
    ) -> None:
        with self.sessions.begin() as db:
            settle_provider_lease(
                db,
                kind="planner",
                resource_id=resource_id,
                sequence=1,
                actual_tokens=actual_tokens,
            )
            if actual_tokens is None:
                return
            daily = db.get(DailyUsage, (owner, day))
            if daily is not None:
                daily.allocated_tokens += max(0, actual_tokens) - reserved_tokens

    async def rank(self, owner: str) -> dict:
        context = self.repo.relevance_context(owner)
        suggestions = context["suggestions"]
        if len(suggestions) <= 1:
            return {
                "available": True,
                "enabled": True,
                "mode": "deterministic",
                "model": None,
                "prompt_sha256": None,
                "latency_ms": 0,
                "suggestions": suggestions,
            }

        resource_id = str(uuid4())
        reserved_tokens = self._reservation()
        day = self._reserve(owner, resource_id, reserved_tokens)
        actual_tokens = None
        try:
            ranking, actual_tokens, evidence = await self.model.rank(
                context["model_candidates"]
            )
            expected = [item["id"] for item in suggestions]
            if len(ranking.ranked_ids) != len(expected) or set(ranking.ranked_ids) != set(expected):
                raise CoworkerError(
                    "invalid_suggestion_relevance",
                    "Suggestion ranking changed the bounded candidate set. The deterministic order is still available.",
                    502,
                )
            by_id = {item["id"]: item for item in suggestions}
            return {
                "available": True,
                "enabled": True,
                "mode": "model",
                "model": evidence["model"],
                "prompt_sha256": evidence["prompt_sha256"],
                "latency_ms": evidence["latency_ms"],
                "suggestions": [by_id[item_id] for item_id in ranking.ranked_ids],
            }
        finally:
            self._settle(
                owner,
                resource_id,
                day,
                reserved_tokens,
                actual_tokens,
            )
