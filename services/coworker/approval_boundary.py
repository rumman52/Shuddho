"""Core Agent approval-boundary invariants.

The model may plan/read/draft/prepare, but it never receives direct provider
mutation authority. Consequential work may appear to the model only as an
opaque reference to an already prepared ExternalAction that remains subject to
immutable preview approval and the execution gateway.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from .agent_tools import tool
from .errors import CoworkerError


INERT_AGENT_PROPOSAL_KINDS = frozenset({"email_send", "calendar_create"})
OPTIONAL_AGENT_PROPOSAL_KINDS = frozenset({"social_publish_linkedin"})
_OPAQUE_ACTION_HANDLE = re.compile(r"^attached\.(email|calendar)\.[1-3]$")


def _violation(message: str) -> CoworkerError:
    return CoworkerError("approval_boundary", message, 409)


def assert_model_tool_surface(tool_names: Iterable[str]) -> None:
    """Reject any direct consequential tool exposed to a planning model."""
    for name in tool_names:
        if _OPAQUE_ACTION_HANDLE.fullmatch(name):
            # Opaque handles reference an already prepared action. The model
            # cannot edit its payload, choose its provider, approve it, or
            # execute it directly.
            continue
        try:
            spec = tool(name)
        except CoworkerError as error:
            raise _violation("The planner tool surface contains an unregistered capability.") from error
        if spec.consequential or spec.approval_required or spec.kind == "approved_action":
            raise _violation(
                "Consequential tools cannot be exposed directly to the planning model."
            )


def assert_model_action_proposals(
    proposals,
    *,
    allow_action_proposals: bool,
    allow_linkedin_action_proposals: bool,
) -> None:
    """Require every model-created action to remain an inert proposal only."""
    proposals = list(proposals or [])
    if proposals and not allow_action_proposals:
        raise _violation("The model is not authorized to create action proposals.")

    allowed = set(INERT_AGENT_PROPOSAL_KINDS)
    if allow_linkedin_action_proposals:
        allowed.update(OPTIONAL_AGENT_PROPOSAL_KINDS)

    for proposal in proposals:
        payload = proposal.payload.model_dump(mode="json")
        kind = payload.get("kind")
        if kind not in allowed:
            raise _violation(
                "The model proposed a consequential action outside the inert proposal boundary."
            )


def assert_inert_proposal_payload(
    payload: dict,
    *,
    allow_linkedin_action_proposals: bool,
) -> None:
    """Defense-in-depth check at the persistence boundary."""
    kind = payload.get("kind") if isinstance(payload, dict) else None
    allowed = set(INERT_AGENT_PROPOSAL_KINDS)
    if allow_linkedin_action_proposals:
        allowed.update(OPTIONAL_AGENT_PROPOSAL_KINDS)
    if kind not in allowed:
        raise _violation(
            "Only server-approved inert action proposal kinds may be persisted."
        )
