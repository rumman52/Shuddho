"""Owner-invoked, budgeted DeepSeek draft producer for CW-10.

This service never dispatches sandbox code, approves reviews, selects tools,
mounts private inputs or writes a second source copy into a planner ledger.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from .agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
from .code_proposal_schemas import CodeComputeLimits, CodeProposalEnvelope
from .errors import CoworkerError
from .models import utcnow


class ModelCodeProposalService:
    def __init__(self, container, planner=None):
        self.container = container
        self.planner = planner or DeepSeekAgentPlanner(container.settings)

    async def generate(self, owner: str, run_id: str, request_key: str) -> tuple[dict, bool]:
        agent = self.container.agent
        settings = self.container.settings
        if not 8 <= len(request_key) <= 110:
            raise CoworkerError(
                "idempotency_key_invalid", "The code draft key must be between 8 and 110 characters.", 422,
            )
        before = await run_in_threadpool(
            agent.preflight_model_code_proposal, owner, run_id, request_key,
        )
        if before["existing"] is not None:
            return before["existing"], False

        # Reuse the existing global per-run/daily/provider-capacity ledger,
        # rather than creating a second unmetered model-call path.
        reservation = await run_in_threadpool(
            agent.reserve_planner,
            run_id,
            max(1, settings.agent_v3_planner_token_budget // settings.max_agent_v3_planner_calls),
        )
        actual_tokens = None
        try:
            source, actual_tokens = await self.planner.propose_code(before["goal"])
            now = utcnow()
            deadline = datetime.fromisoformat(before["deadline_at"])
            expires = min(now + timedelta(minutes=5), deadline)
            if expires <= now:
                raise CoworkerError(
                    "code_run_closed", "The run deadline expired before this code could be reviewed.", 409,
                )
            envelope = CodeProposalEnvelope(
                owner_id=owner,
                run_id=UUID(run_id),
                source=source,
                source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                limits=CodeComputeLimits(
                    cpu_seconds=settings.sandbox_cpu_seconds,
                    wall_seconds=settings.sandbox_wall_seconds,
                    memory_mb=settings.sandbox_memory_mb,
                    disk_mb=settings.sandbox_disk_mb,
                    stdout_bytes=settings.sandbox_max_output_bytes,
                ),
                input_versions=(),
                egress_profile="none",
                destinations=(),
                created_at=now,
                expires_at=expires,
            )
            # The repository rechecks current owner scope, cancellation,
            # source identity and the exact bound envelope *after* inference.
            return await run_in_threadpool(
                agent.prepare_code_proposal,
                owner,
                run_id,
                envelope,
                "model-v1:" + request_key,
            )
        except PlannerFailure as error:
            actual_tokens = error.total_tokens
            raise
        finally:
            await run_in_threadpool(
                agent.settle_planner_capacity,
                run_id,
                reservation["call"],
                actual_tokens,
            )
