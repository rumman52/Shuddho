from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from .connector_actions import ConnectorFailure
from .connector_read_schemas import ConnectorReadGrantCreate
from .connector_registry import CONNECTOR_READ_AUDIENCE, connector_read_capability
from .errors import CoworkerError
from .models import (
    Account,
    AuditEvent,
    Connection,
    ConnectorCursor,
    ConnectorReadGrant,
    ConnectorSnapshot,
    utcnow,
)
from .repository import aware, iso, not_found


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _version_newer(capability: str, incoming: str, current: str) -> bool:
    if incoming == current:
        return False
    if capability == "email_read" and incoming.isdecimal() and current.isdecimal():
        return int(incoming) > int(current)
    try:
        left = datetime.fromisoformat(incoming.replace("Z", "+00:00"))
        right = datetime.fromisoformat(current.replace("Z", "+00:00"))
        return left > right
    except (ValueError, TypeError):
        return incoming > current


class ConnectorReadRepository:
    def __init__(self, sessions, settings, permission_gateway):
        self.sessions = sessions
        self.settings = settings
        self.permission_gateway = permission_gateway

    @staticmethod
    def _grant_dto(row: ConnectorReadGrant) -> dict:
        return {
            "id": row.id,
            "connection_id": row.connection_id,
            "provider": row.provider,
            "capability": row.capability,
            "operation": row.operation,
            "version": row.contract_version,
            "purpose": row.purpose,
            "destination": row.destination,
            "state": row.state,
            "expires_at": iso(row.expires_at),
            "created_at": iso(row.created_at),
            "revoked_at": iso(row.revoked_at) if row.revoked_at else None,
        }

    def create(
        self,
        owner: str,
        request: ConnectorReadGrantCreate,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        if not self.settings.connector_reads_enabled:
            raise CoworkerError(
                "connector_reads_disabled",
                "Connected reads are not enabled in this deployment.",
                503,
            )
        connection_id = str(request.connection_id)
        with self.sessions() as db:
            connection = db.scalar(select(Connection).where(
                Connection.id == connection_id,
                Connection.owner_id == owner,
                Connection.active.is_(True),
            ))
            if connection is None:
                raise not_found()
            capability = connection.capability
        authorization = self.permission_gateway.validate_read_connection(
            owner,
            connection_id,
            capability=capability,
            audience=CONNECTOR_READ_AUDIENCE,
        )
        payload = {
            "connection_id": connection_id,
            "capability": capability,
            "purpose": request.purpose,
            "destination": request.destination,
            "expires_at": request.expires_at.astimezone(timezone.utc).isoformat(),
        }
        fingerprint = _digest(payload)
        with self.sessions.begin() as db:
            if db.get(Account, owner) is None:
                raise not_found()
            previous = db.scalar(select(ConnectorReadGrant).where(
                ConnectorReadGrant.owner_id == owner,
                ConnectorReadGrant.idempotency_key == idempotency_key,
            ))
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different connected read authorization.",
                        409,
                    )
                return self._grant_dto(previous), False
            grant = ConnectorReadGrant(
                id=str(uuid4()),
                owner_id=owner,
                connection_id=connection_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                provider=authorization["provider"],
                capability=authorization["capability"],
                operation=authorization["operation"],
                contract_version=authorization["version"],
                audience=authorization["audience"],
                required_scopes=authorization["required_scopes"],
                purpose=request.purpose,
                destination=request.destination,
                expires_at=request.expires_at,
            )
            db.add(grant)
            db.flush()
            db.add(ConnectorCursor(
                grant_id=grant.id,
                owner_id=owner,
                connection_id=connection_id,
                provider=grant.provider,
                capability=grant.capability,
                cursor=None,
            ))
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=grant.id,
                action="connector_read_grant.created",
            ))
            return self._grant_dto(grant), True

    def get(self, owner: str, grant_id: str, *, lock: bool = False) -> dict:
        with self.sessions() as db:
            query = select(ConnectorReadGrant).where(
                ConnectorReadGrant.id == grant_id,
                ConnectorReadGrant.owner_id == owner,
            )
            if lock:
                query = query.with_for_update()
            row = db.scalar(query)
            if row is None:
                raise not_found()
            return self._grant_dto(row)

    def list(self, owner: str) -> list[dict]:
        with self.sessions() as db:
            rows = db.scalars(select(ConnectorReadGrant).where(
                ConnectorReadGrant.owner_id == owner,
            ).order_by(ConnectorReadGrant.created_at.desc())).all()
            return [self._grant_dto(row) for row in rows]

    def revoke(self, owner: str, grant_id: str) -> dict:
        with self.sessions.begin() as db:
            row = db.scalar(select(ConnectorReadGrant).where(
                ConnectorReadGrant.id == grant_id,
                ConnectorReadGrant.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            if row.state == "active":
                row.state = "revoked"
                row.revoked_at = utcnow()
                db.add(AuditEvent(
                    id=str(uuid4()),
                    owner_id=owner,
                    resource_id=row.id,
                    action="connector_read_grant.revoked",
                ))
            return self._grant_dto(row)

    def cursor(self, owner: str, grant_id: str) -> dict:
        self.permission_gateway.validate_read_grant(
            owner,
            grant_id,
            audience=CONNECTOR_READ_AUDIENCE,
        )
        with self.sessions() as db:
            row = db.scalar(select(ConnectorCursor).where(
                ConnectorCursor.grant_id == grant_id,
                ConnectorCursor.owner_id == owner,
            ))
            if row is None:
                raise not_found()
            return {
                "cursor": row.cursor,
                "generation": row.generation,
                "state": row.state,
            }

    def reset_cursor(self, owner: str, grant_id: str) -> None:
        with self.sessions.begin() as db:
            row = db.scalar(select(ConnectorCursor).where(
                ConnectorCursor.grant_id == grant_id,
                ConnectorCursor.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            row.cursor = None
            row.generation += 1
            row.state = "recovering"
            row.updated_at = utcnow()
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=grant_id,
                action="connector_read_cursor.reset",
            ))

    def apply_sync(
        self,
        owner: str,
        grant_id: str,
        expected_cursor: str | None,
        result: dict,
    ) -> dict:
        next_cursor = result.get("cursor")
        changes = result.get("changes")
        if not isinstance(next_cursor, str) or not next_cursor or not isinstance(changes, list):
            raise CoworkerError(
                "connector_read_response_invalid",
                "The connected service returned an invalid sync response.",
                502,
            )
        with self.sessions.begin() as db:
            grant = db.scalar(select(ConnectorReadGrant).where(
                ConnectorReadGrant.id == grant_id,
                ConnectorReadGrant.owner_id == owner,
            ).with_for_update())
            cursor = db.scalar(select(ConnectorCursor).where(
                ConnectorCursor.grant_id == grant_id,
                ConnectorCursor.owner_id == owner,
            ).with_for_update())
            if grant is None or cursor is None:
                raise not_found()
            if grant.state != "active" or aware(grant.expires_at) <= utcnow():
                raise CoworkerError(
                    "connector_read_revoked",
                    "This connected read authorization is no longer active.",
                    409,
                )
            if cursor.cursor != expected_cursor:
                raise CoworkerError(
                    "connector_sync_conflict",
                    "A newer connector sync already advanced this cursor.",
                    409,
                )
            inserted = updated = deleted = ignored = 0
            for change in changes:
                if not isinstance(change, dict):
                    ignored += 1
                    continue
                resource_id = change.get("resource_id")
                version = change.get("provider_version")
                state = change.get("state")
                payload = change.get("payload")
                if (
                    not isinstance(resource_id, str)
                    or not resource_id
                    or len(resource_id) > 512
                    or not isinstance(version, str)
                    or not version
                    or len(version) > 128
                    or state not in {"active", "deleted"}
                    or not isinstance(payload, dict)
                ):
                    ignored += 1
                    continue
                current = db.scalar(select(ConnectorSnapshot).where(
                    ConnectorSnapshot.grant_id == grant_id,
                    ConnectorSnapshot.provider_resource_id == resource_id,
                ).with_for_update())
                payload_hash = _digest(payload)
                if current is None:
                    current = ConnectorSnapshot(
                        id=str(uuid4()),
                        owner_id=owner,
                        grant_id=grant_id,
                        connection_id=grant.connection_id,
                        provider=grant.provider,
                        capability=grant.capability,
                        provider_resource_id=resource_id,
                        provider_version=version,
                        content_sha256=payload_hash,
                        payload=payload,
                        state=state,
                    )
                    db.add(current)
                    inserted += 1
                    if state == "deleted":
                        deleted += 1
                    continue
                if not _version_newer(grant.capability, version, current.provider_version):
                    if (
                        version == current.provider_version
                        and payload_hash == current.content_sha256
                        and state == current.state
                    ):
                        ignored += 1
                        continue
                    ignored += 1
                    continue
                current.provider_version = version
                current.content_sha256 = payload_hash
                current.payload = payload
                current.state = state
                current.observed_at = utcnow()
                current.updated_at = utcnow()
                updated += 1
                if state == "deleted":
                    deleted += 1
            cursor.cursor = next_cursor
            cursor.state = "active"
            cursor.last_sync_at = utcnow()
            cursor.updated_at = utcnow()
            db.add(AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=grant_id,
                action="connector_read.synced",
            ))
            return {
                "grant_id": grant_id,
                "cursor_generation": cursor.generation,
                "inserted": inserted,
                "updated": updated,
                "deleted": deleted,
                "ignored": ignored,
                "synced_at": iso(cursor.last_sync_at),
            }

    def snapshots(
        self,
        owner: str,
        grant_id: str,
        *,
        limit: int = 20,
    ) -> list[dict]:
        self.permission_gateway.validate_read_grant(
            owner,
            grant_id,
            audience=CONNECTOR_READ_AUDIENCE,
        )
        with self.sessions() as db:
            rows = db.scalars(select(ConnectorSnapshot).where(
                ConnectorSnapshot.owner_id == owner,
                ConnectorSnapshot.grant_id == grant_id,
                ConnectorSnapshot.state == "active",
            ).order_by(ConnectorSnapshot.updated_at.desc()).limit(max(1, min(limit, 50)))).all()
            return [{
                "id": row.id,
                "grant_id": row.grant_id,
                "provider": row.provider,
                "capability": row.capability,
                "provider_resource_id": row.provider_resource_id,
                "provider_version": row.provider_version,
                "sha256": row.content_sha256,
                "payload": row.payload,
                "updated_at": iso(row.updated_at),
            } for row in rows]


class ConnectorReadService:
    def __init__(self, repository: ConnectorReadRepository, credential_broker):
        self.repo = repository
        self.credential_broker = credential_broker

    async def sync(
        self,
        owner: str,
        grant_id: str,
        *,
        force_full: bool = False,
        max_items: int = 30,
    ) -> dict:
        grant, adapter, token = await self.credential_broker.issue_read_access(
            owner,
            grant_id,
            audience=CONNECTOR_READ_AUDIENCE,
        )
        if not hasattr(adapter, "read_connected"):
            raise CoworkerError(
                "connector_read_provider_unavailable",
                "This provider does not support connected reads in this deployment.",
                503,
            )
        cursor_state = await asyncio.to_thread(self.repo.cursor, owner, grant_id)
        cursor = None if force_full else cursor_state["cursor"]
        recovered = False
        try:
            result = await adapter.read_connected(
                grant["capability"],
                token,
                cursor,
                max_items,
            )
        except ConnectorFailure as error:
            if getattr(error, "code", "") != "provider_cursor_invalid" or cursor is None:
                raise CoworkerError(
                    "connector_read_failed",
                    "The connected service could not be synchronized.",
                    503,
                ) from None
            await asyncio.to_thread(self.repo.reset_cursor, owner, grant_id)
            recovered = True
            cursor = None
            result = await adapter.read_connected(
                grant["capability"],
                token,
                None,
                max_items,
            )
        summary = await asyncio.to_thread(
            self.repo.apply_sync,
            owner,
            grant_id,
            cursor,
            result,
        )
        return summary | {
            "provider": grant["provider"],
            "capability": grant["capability"],
            "cursor_recovered": recovered,
        }
