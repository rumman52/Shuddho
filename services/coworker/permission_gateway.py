from __future__ import annotations

import hmac
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from .action_registry import stable_digest, validate_approval_scope
from .connector_registry import CONNECTOR_ACTION_AUDIENCE, connector_capability
from .errors import CoworkerError
from .models import Connection, ExecutionGrant, ExternalAction, utcnow
from .repository import aware, iso, not_found


class PermissionGateway:
    """Deterministic authorization boundary for connector execution.

    The gateway consumes only persisted server state. Model text, retrieved
    content, remote tool descriptions, and caller-supplied provider endpoints
    cannot create or expand authority.
    """

    def __init__(self, sessions, settings):
        self.sessions = sessions
        self.settings = settings

    @staticmethod
    def _dto(row: ExecutionGrant) -> dict:
        return {
            "id": row.id,
            "owner_id": row.owner_id,
            "action_id": row.action_id,
            "connection_id": row.connection_id,
            "purpose": row.purpose,
            "provider": row.provider,
            "capability": row.capability,
            "action_kind": row.action_kind,
            "action_version": row.action_version,
            "audience": row.audience,
            "required_scopes": list(row.required_scopes or []),
            "destinations_sha256": row.destinations_sha256,
            "preview_hash": row.preview_hash,
            "state": row.state,
            "expires_at": iso(row.expires_at),
            "created_at": iso(row.created_at),
            "revoked_at": iso(row.revoked_at) if row.revoked_at else None,
        }

    def _authorize_rows(
        self,
        action: ExternalAction,
        connection: Connection,
        *,
        purpose: str,
        audience: str,
    ) -> tuple[dict, object]:
        if audience != CONNECTOR_ACTION_AUDIENCE:
            raise CoworkerError(
                "connector_audience",
                "This connector request is not intended for the action worker.",
                403,
            )
        if purpose not in {"execute", "reconcile"}:
            raise CoworkerError(
                "connector_purpose",
                "This connector request has an unsupported purpose.",
                409,
            )
        if not connection.active or connection.owner_id != action.owner_id:
            raise CoworkerError(
                "connection_removed",
                "Reconnect your connected account.",
                409,
            )
        if action.connection_id != connection.id:
            raise CoworkerError(
                "connector_resource_scope",
                "The approved action is not bound to this connection.",
                409,
            )
        if not action.approved_at:
            raise CoworkerError(
                "approval_required",
                "This external action has not been approved.",
                409,
            )
        if purpose == "execute" and action.state not in {"queued", "executing"}:
            raise CoworkerError(
                "connector_state",
                "This action is not eligible for connector execution.",
                409,
            )
        if purpose == "reconcile" and action.state not in {"executing", "outcome_unknown"}:
            raise CoworkerError(
                "connector_state",
                "This action is not eligible for reconciliation.",
                409,
            )
        if aware(action.expires_at) <= utcnow() and action.state == "queued":
            raise CoworkerError(
                "approval_expired",
                "This approval expired before connector execution.",
                409,
            )
        if stable_digest(action.preview) != action.preview_hash:
            raise CoworkerError(
                "approval_changed",
                "The approved action changed after review.",
                409,
            )

        action_spec = validate_approval_scope(action.preview)
        if (
            connection.provider not in action_spec.providers
            or connection.capability != action_spec.capability
        ):
            raise CoworkerError(
                "connector_capability_scope",
                "The connection does not satisfy the approved action capability.",
                409,
            )
        contract = connector_capability(
            connection.provider,
            connection.capability,
            action_kind=action.kind,
        )
        granted_scopes = set(connection.scopes or [])
        missing = [scope for scope in contract.required_scopes if scope not in granted_scopes]
        if missing:
            raise CoworkerError(
                "connector_scope_missing",
                "The connected account no longer has the required permission.",
                409,
            )

        approval_scope = action.preview.get("approval_scope")
        if not isinstance(approval_scope, dict):
            raise CoworkerError(
                "approval_changed",
                "The approved connector destination scope is missing.",
                409,
            )
        destinations = approval_scope.get("destinations")
        if not isinstance(destinations, dict):
            raise CoworkerError(
                "approval_changed",
                "The approved connector destinations are invalid.",
                409,
            )
        if (
            approval_scope.get("provider") != connection.provider
            or approval_scope.get("capability") != connection.capability
            or approval_scope.get("connection_id") != connection.id
            or approval_scope.get("action_kind") != action.kind
        ):
            raise CoworkerError(
                "approval_changed",
                "The approved connector authorization no longer matches.",
                409,
            )
        return {
            "provider": connection.provider,
            "capability": connection.capability,
            "action_kind": action.kind,
            "action_version": action_spec.version,
            "required_scopes": list(contract.required_scopes),
            "destinations_sha256": stable_digest(destinations),
            "preview_hash": action.preview_hash,
            "expires_at": (
                action.expires_at
                if purpose == "execute"
                else utcnow() + timedelta(minutes=5)
            ),
        }, contract

    def authorize_action(
        self,
        owner_id: str,
        action_id: str,
        *,
        purpose: str,
        audience: str = CONNECTOR_ACTION_AUDIENCE,
    ) -> dict:
        if not self.settings.connector_trust_boundary_enabled:
            raise CoworkerError(
                "connector_trust_boundary_disabled",
                "The connector trust boundary is not enabled in this deployment.",
                503,
            )
        with self.sessions.begin() as db:
            snapshot = db.scalar(
                select(ExternalAction).where(
                    ExternalAction.id == action_id,
                    ExternalAction.owner_id == owner_id,
                )
            )
            if snapshot is None:
                raise not_found()
            # Match the existing connector lock order: connection before action.
            # This serializes disconnect/revocation against grant admission.
            connection = db.scalar(
                select(Connection)
                .where(
                    Connection.id == snapshot.connection_id,
                    Connection.owner_id == owner_id,
                )
                .with_for_update()
            )
            if connection is None:
                raise not_found()
            action = db.scalar(
                select(ExternalAction)
                .where(
                    ExternalAction.id == action_id,
                    ExternalAction.owner_id == owner_id,
                    ExternalAction.connection_id == connection.id,
                )
                .with_for_update()
            )
            if action is None:
                raise not_found()
            expected, contract = self._authorize_rows(
                action,
                connection,
                purpose=purpose,
                audience=audience,
            )
            existing = db.scalar(
                select(ExecutionGrant).where(
                    ExecutionGrant.action_id == action.id,
                    ExecutionGrant.purpose == purpose,
                    ExecutionGrant.preview_hash == action.preview_hash,
                )
            )
            if existing is not None:
                if (
                    existing.state != "active"
                    or existing.connection_id != connection.id
                    or existing.owner_id != action.owner_id
                    or existing.provider != expected["provider"]
                    or existing.capability != expected["capability"]
                    or existing.action_kind != expected["action_kind"]
                    or existing.action_version != expected["action_version"]
                    or existing.audience != contract.audience
                    or list(existing.required_scopes or []) != expected["required_scopes"]
                    or not hmac.compare_digest(
                        existing.destinations_sha256,
                        expected["destinations_sha256"],
                    )
                    or aware(existing.expires_at) <= utcnow()
                ):
                    raise CoworkerError(
                        "connector_grant_invalid",
                        "The connector execution grant is no longer valid.",
                        409,
                    )
                return self._dto(existing)

            grant = ExecutionGrant(
                id=str(uuid4()),
                owner_id=action.owner_id,
                action_id=action.id,
                connection_id=connection.id,
                purpose=purpose,
                provider=expected["provider"],
                capability=expected["capability"],
                action_kind=expected["action_kind"],
                action_version=expected["action_version"],
                audience=contract.audience,
                required_scopes=expected["required_scopes"],
                destinations_sha256=expected["destinations_sha256"],
                preview_hash=expected["preview_hash"],
                expires_at=expected["expires_at"],
            )
            db.add(grant)
            db.flush()
            return self._dto(grant)

    def validate_grant(
        self,
        grant_id: str,
        action_id: str,
        *,
        purpose: str,
        audience: str = CONNECTOR_ACTION_AUDIENCE,
    ) -> dict:
        with self.sessions.begin() as db:
            snapshot = db.get(ExecutionGrant, grant_id)
            if snapshot is None:
                raise not_found()
            # Connection is the first mutable trust-boundary lock everywhere.
            # Disconnect therefore cannot race between grant validation and
            # credential issuance.
            connection = db.scalar(
                select(Connection)
                .where(
                    Connection.id == snapshot.connection_id,
                    Connection.owner_id == snapshot.owner_id,
                )
                .with_for_update()
            )
            if connection is None:
                raise not_found()
            grant = db.scalar(
                select(ExecutionGrant)
                .where(
                    ExecutionGrant.id == grant_id,
                    ExecutionGrant.connection_id == connection.id,
                    ExecutionGrant.owner_id == connection.owner_id,
                )
                .with_for_update()
            )
            action = db.scalar(
                select(ExternalAction)
                .where(
                    ExternalAction.id == action_id,
                    ExternalAction.owner_id == connection.owner_id,
                    ExternalAction.connection_id == connection.id,
                )
                .with_for_update()
            )
            if grant is None or action is None:
                raise not_found()
            expected, contract = self._authorize_rows(
                action,
                connection,
                purpose=purpose,
                audience=audience,
            )
            if (
                grant.state != "active"
                or grant.action_id != action.id
                or grant.connection_id != connection.id
                or grant.purpose != purpose
                or grant.audience != contract.audience
                or grant.provider != expected["provider"]
                or grant.capability != expected["capability"]
                or grant.action_kind != expected["action_kind"]
                or grant.action_version != expected["action_version"]
                or grant.preview_hash != expected["preview_hash"]
                or list(grant.required_scopes or []) != expected["required_scopes"]
                or not hmac.compare_digest(
                    grant.destinations_sha256,
                    expected["destinations_sha256"],
                )
                or aware(grant.expires_at) <= utcnow()
            ):
                grant.state = "revoked"
                grant.revoked_at = utcnow()
                raise CoworkerError(
                    "connector_grant_invalid",
                    "The connector execution grant is no longer valid.",
                    409,
                )
            return self._dto(grant)

    def revoke_connection(self, owner_id: str, connection_id: str) -> None:
        with self.sessions.begin() as db:
            rows = db.scalars(
                select(ExecutionGrant)
                .where(
                    ExecutionGrant.owner_id == owner_id,
                    ExecutionGrant.connection_id == connection_id,
                    ExecutionGrant.state == "active",
                )
                .with_for_update()
            ).all()
            now = utcnow()
            for row in rows:
                row.state = "revoked"
                row.revoked_at = now
