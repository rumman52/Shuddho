from __future__ import annotations

import hashlib

from sqlalchemy import select

from .action_repository import ActionRepository
from .action_schemas import ActionPrepare
from .errors import CoworkerError
from .models import Account, DailyUsage, utcnow
from .negotiation_model import NegotiationProposalModel
from .negotiation_repository import NegotiationRepository
from .negotiation_schemas import (
    NegotiationProposalRequest,
    NegotiationProposalReview,
)
from .provider_capacity import acquire_provider_lease, settle_provider_lease
from .repository import not_found


class NegotiationProposalService:
    """Coordinates bounded model drafting with durable inert proposal storage."""

    def __init__(
        self,
        repository: NegotiationRepository,
        model: NegotiationProposalModel,
        actions: ActionRepository,
    ):
        self.repo = repository
        self.model = model
        self.actions = actions
        self.settings = repository.settings
        self.sessions = repository.sessions

    def _resource_id(self, owner: str, case_id: str, idempotency_key: str) -> str:
        return hashlib.sha256(
            f"{owner}:{case_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()[:36]

    def _reservation(self) -> int:
        calls = max(1, self.settings.max_agent_planner_calls)
        return max(
            1,
            min(
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

    async def generate(
        self,
        owner: str,
        case_id: str,
        request: NegotiationProposalRequest,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        if not self.settings.intelligent_planner_enabled:
            raise CoworkerError(
                "negotiation_proposals_disabled",
                "Model-assisted negotiation proposals are not enabled in this deployment.",
                503,
            )
        context, previous = self.repo.proposal_context(
            owner,
            case_id,
            request,
            idempotency_key,
        )
        if previous is not None:
            return previous, False

        resource_id = self._resource_id(owner, case_id, idempotency_key)
        reserved_tokens = self._reservation()
        day = self._reserve(owner, resource_id, reserved_tokens)
        actual_tokens = None
        try:
            draft, actual_tokens, evidence = await self.model.propose(context, request)
            return self.repo.save_proposal(
                owner,
                case_id,
                request,
                idempotency_key,
                context,
                draft,
                model=evidence["model"],
                prompt_sha256=evidence["prompt_sha256"],
            )
        finally:
            self._settle(
                owner,
                resource_id,
                day,
                reserved_tokens,
                actual_tokens,
            )

    def dismiss(
        self,
        owner: str,
        case_id: str,
        proposal_id: str,
        review: NegotiationProposalReview,
    ) -> dict:
        return self.repo.dismiss_proposal(
            owner,
            case_id,
            proposal_id,
            review,
        )

    def promote(
        self,
        owner: str,
        case_id: str,
        proposal_id: str,
        review: NegotiationProposalReview,
    ) -> dict:
        if not self.settings.agent_action_proposals_enabled:
            raise CoworkerError(
                "negotiation_proposal_promotion_disabled",
                "Negotiation proposal promotion is disabled in this deployment.",
                503,
            )
        reservation = self.repo.reserve_proposal_promotion(
            owner,
            case_id,
            proposal_id,
            review,
        )
        existing_action_id = reservation.get("existing_action_id")
        if existing_action_id:
            return self.actions.get(owner, existing_action_id)
        try:
            request = ActionPrepare.model_validate({
                "connection_id": reservation["connection_id"],
                "payload": reservation["payload"],
            })
            action = self.actions.prepare(
                owner,
                request,
                "negotiation-proposal:" + proposal_id,
                source_binding=reservation["source_binding"],
            )
        except Exception:
            self.repo.release_proposal_promotion(owner, case_id, proposal_id)
            raise
        try:
            self.repo.finalize_proposal_promotion(
                owner,
                case_id,
                proposal_id,
                review.proposal_hash,
                action["id"],
                reservation["source_binding"],
            )
        except Exception:
            try:
                self.actions.cancel(owner, action["id"])
            finally:
                self.repo.release_proposal_promotion(owner, case_id, proposal_id)
            raise
        return action
