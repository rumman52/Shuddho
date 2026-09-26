"""Code-owned connector capability contracts.

These contracts are security metadata, not model/tool descriptions. They define
which provider capability may service a registered action, the exact delegated
scopes required, the internal credential audience, and the egress/approval
class enforced by the trusted connector boundary.
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import CoworkerError

CONNECTOR_ACTION_AUDIENCE = "shuddho.connector.actions.v1"


@dataclass(frozen=True)
class ConnectorCapabilitySpec:
    provider: str
    capability: str
    version: str
    required_scopes: tuple[str, ...]
    action_kinds: frozenset[str]
    audience: str = CONNECTOR_ACTION_AUDIENCE
    ownership_resolver: str = "connection.owner_id"
    approval_class: str = "exact_preview"
    destination_policy: str = "approval_scope"
    timeout_seconds: int = 20
    retry_policy: str = "no_blind_mutation_retry"
    reconciliation_policy: str = "registered_action_contract"
    receipt_policy: str = "registered_action_receipt"
    egress_policy: str = "fixed_provider_endpoints"

    def public(self) -> dict:
        return {
            "provider": self.provider,
            "capability": self.capability,
            "version": self.version,
            "required_scopes": list(self.required_scopes),
            "action_kinds": sorted(self.action_kinds),
            "audience": self.audience,
            "ownership_resolver": self.ownership_resolver,
            "approval_class": self.approval_class,
            "destination_policy": self.destination_policy,
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy,
            "reconciliation_policy": self.reconciliation_policy,
            "receipt_policy": self.receipt_policy,
            "egress_policy": self.egress_policy,
        }


CONNECTOR_CAPABILITIES = {
    ("google", "email"): ConnectorCapabilitySpec(
        provider="google",
        capability="email",
        version="1",
        required_scopes=(
            "openid",
            "email",
            "https://www.googleapis.com/auth/gmail.send",
        ),
        action_kinds=frozenset({
            "email_send",
            "email_send_with_attachments",
            "email_thread_reply",
        }),
    ),
    ("google", "calendar"): ConnectorCapabilitySpec(
        provider="google",
        capability="calendar",
        version="1",
        required_scopes=(
            "openid",
            "email",
            "https://www.googleapis.com/auth/calendar.events.owned",
        ),
        action_kinds=frozenset({
            "calendar_create",
            "calendar_create_with_reminder",
        }),
    ),
    ("google", "drive"): ConnectorCapabilitySpec(
        provider="google",
        capability="drive",
        version="1",
        required_scopes=(
            "openid",
            "email",
            "https://www.googleapis.com/auth/drive.file",
        ),
        action_kinds=frozenset({"document_share"}),
    ),
    ("microsoft", "email"): ConnectorCapabilitySpec(
        provider="microsoft",
        capability="email",
        version="1",
        required_scopes=("User.Read", "Mail.Send"),
        action_kinds=frozenset({
            "email_send",
            "email_send_with_attachments",
        }),
    ),
    ("microsoft", "calendar"): ConnectorCapabilitySpec(
        provider="microsoft",
        capability="calendar",
        version="1",
        required_scopes=("User.Read", "Calendars.ReadWrite"),
        action_kinds=frozenset({
            "calendar_create",
            "calendar_create_with_reminder",
        }),
    ),
    ("linkedin", "social"): ConnectorCapabilitySpec(
        provider="linkedin",
        capability="social",
        version="1",
        required_scopes=("r_liteprofile", "w_member_social"),
        action_kinds=frozenset({"social_publish_linkedin"}),
    ),
}


def connector_capability(
    provider: str,
    capability: str,
    *,
    action_kind: str | None = None,
) -> ConnectorCapabilitySpec:
    spec = CONNECTOR_CAPABILITIES.get((provider, capability))
    if spec is None:
        raise CoworkerError(
            "connector_capability_unregistered",
            "This connector capability is not registered.",
            409,
        )
    if action_kind is not None and action_kind not in spec.action_kinds:
        raise CoworkerError(
            "connector_operation_unregistered",
            "This connector operation is not registered for that capability.",
            409,
        )
    return spec


def registered_connector_capabilities() -> list[dict]:
    return [
        CONNECTOR_CAPABILITIES[key].public()
        for key in sorted(CONNECTOR_CAPABILITIES)
    ]
