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
CONNECTOR_READ_AUDIENCE = "shuddho.connector.reads.v1"


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
        required_scopes=("https://www.googleapis.com/auth/gmail.send",),
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
        required_scopes=("https://www.googleapis.com/auth/calendar.events.owned",),
        action_kinds=frozenset({
            "calendar_create",
            "calendar_create_with_reminder",
        }),
    ),
    ("google", "drive"): ConnectorCapabilitySpec(
        provider="google",
        capability="drive",
        version="1",
        required_scopes=("https://www.googleapis.com/auth/drive.file",),
        action_kinds=frozenset({"document_share"}),
    ),
    ("microsoft", "email"): ConnectorCapabilitySpec(
        provider="microsoft",
        capability="email",
        version="1",
        required_scopes=("Mail.Send",),
        action_kinds=frozenset({
            "email_send",
            "email_send_with_attachments",
        }),
    ),
    ("microsoft", "calendar"): ConnectorCapabilitySpec(
        provider="microsoft",
        capability="calendar",
        version="1",
        required_scopes=("Calendars.ReadWrite",),
        action_kinds=frozenset({
            "calendar_create",
            "calendar_create_with_reminder",
        }),
    ),
    ("linkedin", "social"): ConnectorCapabilitySpec(
        provider="linkedin",
        capability="social",
        version="1",
        required_scopes=("w_member_social",),
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


@dataclass(frozen=True)
class ConnectorReadSpec:
    provider: str
    capability: str
    operation: str
    version: str
    required_scopes: tuple[str, ...]
    audience: str = CONNECTOR_READ_AUDIENCE
    ownership_resolver: str = "connection.owner_id"
    approval_class: str = "explicit_oauth_consent"
    destination_policy: str = "agent_context_only"
    timeout_seconds: int = 20
    retry_policy: str = "bounded_idempotent_read"
    reconciliation_policy: str = "cursor_reconciliation"
    receipt_policy: str = "cursor_and_snapshot_hash"
    egress_policy: str = "fixed_provider_endpoints"
    max_items_per_sync: int = 50

    def public(self) -> dict:
        return {
            "provider": self.provider,
            "capability": self.capability,
            "operation": self.operation,
            "version": self.version,
            "required_scopes": list(self.required_scopes),
            "audience": self.audience,
            "ownership_resolver": self.ownership_resolver,
            "approval_class": self.approval_class,
            "destination_policy": self.destination_policy,
            "timeout_seconds": self.timeout_seconds,
            "retry_policy": self.retry_policy,
            "reconciliation_policy": self.reconciliation_policy,
            "receipt_policy": self.receipt_policy,
            "egress_policy": self.egress_policy,
            "max_items_per_sync": self.max_items_per_sync,
        }


CONNECTOR_READ_CAPABILITIES = {
    ("google", "email_read"): ConnectorReadSpec(
        provider="google",
        capability="email_read",
        operation="gmail.metadata.sync",
        version="1",
        required_scopes=("https://www.googleapis.com/auth/gmail.readonly",),
        max_items_per_sync=30,
    ),
    ("google", "calendar_read"): ConnectorReadSpec(
        provider="google",
        capability="calendar_read",
        operation="calendar.events.sync",
        version="1",
        required_scopes=("https://www.googleapis.com/auth/calendar.readonly",),
        max_items_per_sync=50,
    ),
    ("microsoft", "email_read"): ConnectorReadSpec(
        provider="microsoft",
        capability="email_read",
        operation="graph.mail.inbox.delta",
        version="1",
        required_scopes=("Mail.ReadBasic",),
        max_items_per_sync=30,
    ),
    ("microsoft", "calendar_read"): ConnectorReadSpec(
        provider="microsoft",
        capability="calendar_read",
        operation="graph.calendar_view.delta",
        version="1",
        required_scopes=("Calendars.Read",),
        max_items_per_sync=50,
    ),
}


def connector_read_capability(provider: str, capability: str) -> ConnectorReadSpec:
    spec = CONNECTOR_READ_CAPABILITIES.get((provider, capability))
    if spec is None:
        raise CoworkerError(
            "connector_read_unregistered",
            "This connected read capability is not registered.",
            409,
        )
    return spec


def registered_connector_read_capabilities() -> list[dict]:
    return [
        CONNECTOR_READ_CAPABILITIES[key].public()
        for key in sorted(CONNECTOR_READ_CAPABILITIES)
    ]
