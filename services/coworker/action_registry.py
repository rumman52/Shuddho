"""Connector-neutral consequential-action policy contracts.

Every external mutation must be registered here before it can be prepared,
approved, executed, or exposed to the Agent Runtime.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Literal

from .errors import CoworkerError


ReconcileMode = Literal["none", "provider_receipt"]


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    version: str
    capability: str
    providers: frozenset[str]
    approval_ttl_seconds: int
    execution_ttl_seconds: int
    reconcile_mode: ReconcileMode
    destination_fields: tuple[str, ...]
    requires_future_start: bool = False
    attachments_allowed: bool = False
    calendar: str | None = None
    guest_notifications: str | None = None
    reminders: str = "none"
    owned_artifact_required: bool = False
    document_access: str | None = None
    notification_policy: str | None = None

    def public(self) -> dict:
        return {
            "kind": self.kind,
            "version": self.version,
            "capability": self.capability,
            "providers": sorted(self.providers),
            "approval_ttl_seconds": self.approval_ttl_seconds,
            "execution_ttl_seconds": self.execution_ttl_seconds,
            "reconcile_mode": self.reconcile_mode,
            "attachments_allowed": self.attachments_allowed,
        }

    @property
    def reconcile_supported(self) -> bool:
        return self.reconcile_mode == "provider_receipt"

    def policy_manifest(self) -> dict:
        # Preserve the existing preview shape for existing actions. New policy
        # fields are emitted only for the action kind that owns them so old
        # immutable previews remain verifiable.
        result = {
            "execution": "immediately_after_approval",
            "attachments": [] if not self.attachments_allowed else None,
            "calendar": self.calendar,
            "guest_notifications": self.guest_notifications,
            "reminders": self.reminders,
        }
        if self.owned_artifact_required:
            result["document_sharing"] = {
                "source": "owned_shuddho_artifact",
                "access": self.document_access,
                "notifications": self.notification_policy,
            }
        return result


ACTION_SPECS = {
    "email_send": ActionSpec(
        kind="email_send",
        version="1",
        capability="email",
        providers=frozenset({"google", "microsoft"}),
        approval_ttl_seconds=15 * 60,
        execution_ttl_seconds=5 * 60,
        reconcile_mode="none",
        destination_fields=("to", "cc", "bcc"),
    ),
    "email_send_with_attachments": ActionSpec(
        kind="email_send_with_attachments",
        version="1",
        capability="email",
        providers=frozenset({"google", "microsoft"}),
        approval_ttl_seconds=15 * 60,
        execution_ttl_seconds=5 * 60,
        reconcile_mode="none",
        destination_fields=("to", "cc", "bcc"),
        attachments_allowed=True,
    ),
    "calendar_create": ActionSpec(
        kind="calendar_create",
        version="1",
        capability="calendar",
        providers=frozenset({"google", "microsoft"}),
        approval_ttl_seconds=15 * 60,
        execution_ttl_seconds=5 * 60,
        reconcile_mode="provider_receipt",
        destination_fields=("attendees",),
        requires_future_start=True,
        calendar="primary",
        guest_notifications="all",
    ),
    "calendar_create_with_reminder": ActionSpec(
        kind="calendar_create_with_reminder",
        version="1",
        capability="calendar",
        providers=frozenset({"google", "microsoft"}),
        approval_ttl_seconds=15 * 60,
        execution_ttl_seconds=5 * 60,
        reconcile_mode="provider_receipt",
        destination_fields=("attendees",),
        requires_future_start=True,
        calendar="primary",
        guest_notifications="all",
        reminders="single_explicit",
    ),
    "document_share": ActionSpec(
        kind="document_share",
        version="1",
        capability="drive",
        providers=frozenset({"google"}),
        approval_ttl_seconds=15 * 60,
        execution_ttl_seconds=5 * 60,
        reconcile_mode="provider_receipt",
        destination_fields=("recipients",),
        owned_artifact_required=True,
        document_access="reader",
        notification_policy="recipient",
    ),
}


def stable_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def action_spec(kind: str, provider: str | None = None) -> ActionSpec:
    spec = ACTION_SPECS.get(kind)
    if spec is None:
        raise CoworkerError(
            "action_not_registered",
            "This external action is not registered.",
            409,
        )
    if provider is not None and provider not in spec.providers:
        raise CoworkerError(
            "connection_removed",
            "The connected service cannot perform this action.",
            409,
        )
    return spec


def destinations(spec: ActionSpec, payload: dict) -> dict:
    result = {}
    for field in spec.destination_fields:
        value = payload.get(field, [])
        if not isinstance(value, list):
            raise CoworkerError(
                "approval_changed",
                "The action destination policy could not be verified.",
                409,
            )
        result[field] = list(value)
    if spec.calendar is not None:
        result["calendar"] = spec.calendar
    return result



def attachment_manifest(preview: dict, spec: ActionSpec) -> list[dict]:
    value = preview.get("attachments", [])
    if not spec.attachments_allowed:
        if value != []:
            raise CoworkerError(
                "approval_changed",
                "This action does not allow attachments.",
                409,
            )
        return []
    if not isinstance(value, list) or not 1 <= len(value) <= 3:
        raise CoworkerError(
            "approval_changed",
            "The approved attachment list could not be verified.",
            409,
        )
    result = []
    required = {"id", "filename", "content_type", "byte_size", "sha256"}
    for item in value:
        if not isinstance(item, dict) or set(item) != required:
            raise CoworkerError(
                "approval_changed",
                "The approved attachment metadata could not be verified.",
                409,
            )
        if (
            not isinstance(item["id"], str)
            or not isinstance(item["filename"], str)
            or not isinstance(item["content_type"], str)
            or not isinstance(item["byte_size"], int)
            or isinstance(item["byte_size"], bool)
            or item["byte_size"] < 1
            or not isinstance(item["sha256"], str)
            or len(item["sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in item["sha256"])
        ):
            raise CoworkerError(
                "approval_changed",
                "The approved attachment metadata is invalid.",
                409,
            )
        result.append(dict(item))
    return result


def shared_artifact_manifest(preview: dict, spec: ActionSpec) -> dict | None:
    value = preview.get("shared_artifact")
    if not spec.owned_artifact_required:
        if value is not None:
            raise CoworkerError(
                "approval_changed",
                "This action does not allow a shared document.",
                409,
            )
        return None
    required = {"id", "filename", "content_type", "byte_size", "sha256"}
    if not isinstance(value, dict) or set(value) != required:
        raise CoworkerError(
            "approval_changed",
            "The approved shared-document metadata could not be verified.",
            409,
        )
    if (
        not isinstance(value["id"], str)
        or not isinstance(value["filename"], str)
        or not isinstance(value["content_type"], str)
        or not isinstance(value["byte_size"], int)
        or isinstance(value["byte_size"], bool)
        or value["byte_size"] < 1
        or not isinstance(value["sha256"], str)
        or len(value["sha256"]) != 64
        or any(char not in "0123456789abcdef" for char in value["sha256"])
    ):
        raise CoworkerError(
            "approval_changed",
            "The approved shared-document metadata is invalid.",
            409,
        )
    return dict(value)


def build_approval_scope(preview: dict) -> dict:
    payload = preview.get("payload")
    if not isinstance(payload, dict):
        raise CoworkerError(
            "approval_changed",
            "The action payload could not be verified.",
            409,
        )
    kind = payload.get("kind")
    provider = preview.get("provider")
    if not isinstance(kind, str) or not isinstance(provider, str):
        raise CoworkerError(
            "approval_changed",
            "The action authorization scope could not be verified.",
            409,
        )
    spec = action_spec(kind, provider)
    attachments = attachment_manifest(preview, spec)
    shared_artifact = shared_artifact_manifest(preview, spec)
    result = {
        "contract": "shuddho.consequential-action",
        "contract_version": 3 if spec.owned_artifact_required else 2 if spec.attachments_allowed else 1,
        "action_kind": spec.kind,
        "action_version": spec.version,
        "provider": provider,
        "capability": spec.capability,
        "connection_id": preview.get("connection_id"),
        "account": preview.get("account"),
        "subject_id": preview.get("subject_id"),
        "payload_sha256": stable_digest(payload),
        "destinations": destinations(spec, payload),
        "policy": {
            "execution": preview.get("execution"),
            "attachments": (
                "owned_artifacts" if spec.attachments_allowed else "none"
            ),
            "calendar": preview.get("calendar"),
            "guest_notifications": preview.get("guest_notifications"),
            "reminders": preview.get("reminders"),
            "reconcile_mode": spec.reconcile_mode,
            **({
                "document_sharing": preview.get("document_sharing"),
            } if spec.owned_artifact_required else {}),
        },
        "expires_at": preview.get("expires_at"),
    }
    if spec.attachments_allowed:
        result["attachments"] = attachments
        result["attachments_sha256"] = stable_digest(attachments)
    if spec.owned_artifact_required:
        result["shared_artifact"] = shared_artifact
        result["shared_artifact_sha256"] = stable_digest(shared_artifact)
    return result


def validate_approval_scope(preview: dict) -> ActionSpec:
    scope = preview.get("approval_scope")
    if not isinstance(scope, dict):
        # Backward compatibility only for previews persisted before this
        # contract existed. Their immutable preview_hash still binds all v1
        # fields. New v2+ previews must always carry approval_scope.
        if preview.get("version") == 1:
            payload = preview.get("payload")
            provider = preview.get("provider")
            if not isinstance(payload, dict) or not isinstance(provider, str):
                raise CoworkerError(
                    "approval_changed",
                    "The legacy action approval could not be verified.",
                    409,
                )
            spec = action_spec(str(payload.get("kind", "")), provider)
            manifest = spec.policy_manifest()
            for key, expected in manifest.items():
                if preview.get(key) != expected:
                    raise CoworkerError(
                        "approval_changed",
                        "The legacy action policy changed.",
                        409,
                    )
            return spec
        raise CoworkerError(
            "approval_changed",
            "The action approval scope is missing.",
            409,
        )
    expected = build_approval_scope(preview)
    if not hmac.compare_digest(stable_digest(scope), stable_digest(expected)):
        raise CoworkerError(
            "approval_changed",
            "The action approval scope changed. Review it again before approving.",
            409,
        )
    return action_spec(expected["action_kind"], expected["provider"])


def registered_actions() -> list[dict]:
    return [ACTION_SPECS[name].public() for name in sorted(ACTION_SPECS)]
