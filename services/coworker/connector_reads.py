from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select

from .connector_actions import ConnectorFailure
from .connector_read_schemas import ConnectorReadGrantCreate
from .connector_registry import CONNECTOR_READ_AUDIENCE, connector_read_capability
from .errors import CoworkerError
from .models import (
    Account,
    AuditEvent,
    Connection,
    ConnectorCursor,
    ConnectorEvent,
    ConnectorReadGrant,
    ConnectorSnapshot,
    ConnectorSubscription,
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


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sequence_newer(incoming: str | None, current: str | None) -> bool:
    if incoming is None:
        return current is None
    if current is None:
        return True
    if incoming.isdecimal() and current.isdecimal():
        return int(incoming) > int(current)
    return incoming > current


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
        state = row.state
        if state == "active" and aware(row.expires_at) <= utcnow():
            state = "expired"
        return {
            "id": row.id,
            "connection_id": row.connection_id,
            "provider": row.provider,
            "capability": row.capability,
            "operation": row.operation,
            "version": row.contract_version,
            "purpose": row.purpose,
            "destination": row.destination,
            "state": state,
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

    def reserve_subscription(
        self,
        owner: str,
        grant_id: str,
        *,
        kind: str,
        provider_subscription_id: str | None,
        token_hash: str | None,
    ) -> dict:
        self.permission_gateway.validate_read_grant(
            owner, grant_id, audience=CONNECTOR_READ_AUDIENCE
        )
        with self.sessions.begin() as db:
            grant = db.scalar(select(ConnectorReadGrant).where(
                ConnectorReadGrant.id == grant_id,
                ConnectorReadGrant.owner_id == owner,
                ConnectorReadGrant.state == "active",
            ).with_for_update())
            if grant is None:
                raise not_found()
            generation = (db.scalar(select(func.max(ConnectorSubscription.generation)).where(
                ConnectorSubscription.grant_id == grant_id,
            )) or 0) + 1
            row = ConnectorSubscription(
                id=str(uuid4()),
                owner_id=owner,
                grant_id=grant_id,
                connection_id=grant.connection_id,
                provider=grant.provider,
                capability=grant.capability,
                kind=kind,
                generation=generation,
                state="pending",
                provider_subscription_id=provider_subscription_id,
                token_hash=token_hash,
            )
            db.add(row)
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="connector_subscription.reserved",
            ))
            db.flush()
            return self._subscription_dto(row)

    @staticmethod
    def _subscription_dto(row: ConnectorSubscription) -> dict:
        return {
            "id": row.id,
            "grant_id": row.grant_id,
            "connection_id": row.connection_id,
            "provider": row.provider,
            "capability": row.capability,
            "kind": row.kind,
            "generation": row.generation,
            "state": row.state,
            "provider_subscription_id": row.provider_subscription_id,
            "provider_resource_id": row.provider_resource_id,
            "expires_at": iso(row.expires_at) if row.expires_at else None,
            "renew_after": iso(row.renew_after) if row.renew_after else None,
            "attempts": row.attempts,
            "last_error_code": row.last_error_code,
        }

    def latest_subscription(self, owner: str, grant_id: str) -> dict | None:
        with self.sessions() as db:
            row = db.scalar(select(ConnectorSubscription).where(
                ConnectorSubscription.owner_id == owner,
                ConnectorSubscription.grant_id == grant_id,
                ConnectorSubscription.state.in_(["pending", "active", "renewing"]),
            ).order_by(ConnectorSubscription.generation.desc()).limit(1))
            return self._subscription_dto(row) if row else None

    def activate_subscription(
        self,
        owner: str,
        subscription_id: str,
        *,
        provider_subscription_id: str | None,
        provider_resource_id: str | None,
        expires_at: datetime,
        renew_after: datetime,
        replaced_subscription_id: str | None = None,
    ) -> dict:
        with self.sessions.begin() as db:
            row = db.scalar(select(ConnectorSubscription).where(
                ConnectorSubscription.id == subscription_id,
                ConnectorSubscription.owner_id == owner,
            ).with_for_update())
            if row is None:
                raise not_found()
            row.provider_subscription_id = provider_subscription_id or row.provider_subscription_id
            row.provider_resource_id = provider_resource_id
            row.expires_at = expires_at
            row.renew_after = renew_after
            row.state = "active"
            row.claim_until = None
            row.last_error_code = None
            row.updated_at = utcnow()
            if replaced_subscription_id:
                old = db.scalar(select(ConnectorSubscription).where(
                    ConnectorSubscription.id == replaced_subscription_id,
                    ConnectorSubscription.owner_id == owner,
                    ConnectorSubscription.grant_id == row.grant_id,
                ).with_for_update())
                if old is not None and old.id != row.id:
                    old.state = "superseded"
                    old.claim_until = None
                    old.updated_at = utcnow()
            db.add(AuditEvent(
                id=str(uuid4()), owner_id=owner, resource_id=row.id,
                action="connector_subscription.active",
            ))
            return self._subscription_dto(row)

    def subscription_failed(self, owner: str, subscription_id: str, code: str) -> None:
        with self.sessions.begin() as db:
            row = db.scalar(select(ConnectorSubscription).where(
                ConnectorSubscription.id == subscription_id,
                ConnectorSubscription.owner_id == owner,
            ).with_for_update())
            if row is None:
                return
            row.attempts += 1
            row.last_error_code = code[:60]
            row.claim_until = None
            row.state = "failed" if row.attempts >= 8 else "pending"
            row.renew_after = utcnow() + timedelta(seconds=min(900, 2 ** min(row.attempts, 9)))
            row.updated_at = utcnow()

    def claim_renewals(self, limit: int = 10) -> list[dict]:
        if not self.settings.connector_reads_enabled:
            return []
        now = utcnow()
        with self.sessions.begin() as db:
            rows = db.scalars(select(ConnectorSubscription).join(
                ConnectorReadGrant, ConnectorReadGrant.id == ConnectorSubscription.grant_id
            ).where(
                ConnectorReadGrant.state == "active",
                ConnectorReadGrant.expires_at > now,
                ConnectorSubscription.state.in_(["active", "pending", "renewing"]),
                ConnectorSubscription.renew_after.is_not(None),
                ConnectorSubscription.renew_after <= now,
                ((ConnectorSubscription.claim_until.is_(None)) | (ConnectorSubscription.claim_until < now)),
                ConnectorSubscription.attempts < 8,
            ).order_by(ConnectorSubscription.renew_after).limit(limit).with_for_update()).all()
            result = []
            for row in rows:
                row.state = "renewing"
                row.claim_until = now + timedelta(minutes=2)
                row.updated_at = now
                result.append(self._subscription_dto(row) | {"owner_id": row.owner_id})
            return result

    def enqueue_gmail_event(
        self,
        *,
        subscription_name: str,
        email: str,
        message_id: str,
        history_id: str,
        payload_sha256: str,
    ) -> int:
        now = utcnow()
        accepted = 0
        with self.sessions.begin() as db:
            rows = db.scalars(select(ConnectorSubscription).join(
                Connection, Connection.id == ConnectorSubscription.connection_id
            ).join(
                ConnectorReadGrant, ConnectorReadGrant.id == ConnectorSubscription.grant_id
            ).where(
                ConnectorSubscription.provider == "google",
                ConnectorSubscription.capability == "email_read",
                ConnectorSubscription.provider_subscription_id == subscription_name,
                ConnectorSubscription.state.in_(["pending", "active", "renewing"]),
                Connection.active.is_(True),
                func.lower(Connection.email) == email.casefold(),
                ConnectorReadGrant.state == "active",
                ConnectorReadGrant.expires_at > now,
            )).all()
            for row in rows:
                exists = db.scalar(select(ConnectorEvent.id).where(
                    ConnectorEvent.subscription_id == row.id,
                    ConnectorEvent.provider_event_id == message_id,
                ))
                if exists:
                    continue
                db.add(ConnectorEvent(
                    id=str(uuid4()), owner_id=row.owner_id, grant_id=row.grant_id,
                    subscription_id=row.id, provider="google", capability=row.capability,
                    provider_event_id=message_id, provider_cursor_hint=history_id,
                    payload_sha256=payload_sha256,
                ))
                accepted += 1
        return accepted

    def enqueue_calendar_event(
        self,
        *,
        channel_id: str,
        channel_token: str,
        resource_id: str,
        message_number: str,
        resource_state: str,
        payload_sha256: str,
    ) -> bool:
        now = utcnow()
        with self.sessions.begin() as db:
            row = db.scalar(select(ConnectorSubscription).join(
                ConnectorReadGrant, ConnectorReadGrant.id == ConnectorSubscription.grant_id
            ).where(
                ConnectorSubscription.provider == "google",
                ConnectorSubscription.capability == "calendar_read",
                ConnectorSubscription.provider_subscription_id == channel_id,
                ConnectorSubscription.state.in_(["pending", "active", "renewing"]),
                ConnectorReadGrant.state == "active",
                ConnectorReadGrant.expires_at > now,
            ).order_by(ConnectorSubscription.generation.desc()).limit(1))
            if row is None or not row.token_hash or not hmac.compare_digest(
                row.token_hash, _token_hash(channel_token)
            ):
                return False
            if row.provider_resource_id and row.provider_resource_id != resource_id:
                return False
            event_id = message_number
            if db.scalar(select(ConnectorEvent.id).where(
                ConnectorEvent.subscription_id == row.id,
                ConnectorEvent.provider_event_id == event_id,
            )):
                return True
            state = "processed" if resource_state == "sync" else "pending"
            event = ConnectorEvent(
                id=str(uuid4()), owner_id=row.owner_id, grant_id=row.grant_id,
                subscription_id=row.id, provider="google", capability=row.capability,
                provider_event_id=event_id, provider_sequence=message_number,
                payload_sha256=payload_sha256, state=state,
                processed_at=now if state == "processed" else None,
            )
            db.add(event)
            return True

    def claim_events(self, limit: int = 20) -> list[dict]:
        if not self.settings.connector_reads_enabled:
            return []
        now = utcnow()
        with self.sessions.begin() as db:
            rows = db.scalars(select(ConnectorEvent).where(
                ConnectorEvent.state.in_(["pending", "retry"]),
                ConnectorEvent.available_at <= now,
                ((ConnectorEvent.claim_until.is_(None)) | (ConnectorEvent.claim_until < now)),
                ConnectorEvent.attempts < 8,
            ).order_by(ConnectorEvent.received_at).limit(limit).with_for_update()).all()
            result = []
            for row in rows:
                row.state = "processing"
                row.claim_until = now + timedelta(minutes=2)
                row.attempts += 1
                result.append({
                    "id": row.id,
                    "owner_id": row.owner_id,
                    "grant_id": row.grant_id,
                    "subscription_id": row.subscription_id,
                    "capability": row.capability,
                    "provider_sequence": row.provider_sequence,
                    "provider_cursor_hint": row.provider_cursor_hint,
                })
            return result

    def event_is_stale(self, event: dict) -> bool:
        with self.sessions() as db:
            sub = db.get(ConnectorSubscription, event["subscription_id"])
            if sub is None:
                return True
            if event.get("provider_sequence") and sub.last_event_sequence:
                return not _sequence_newer(
                    event["provider_sequence"], sub.last_event_sequence
                )
            if event.get("provider_cursor_hint"):
                cursor = db.get(ConnectorCursor, event["grant_id"])
                hint = event["provider_cursor_hint"]
                if (
                    cursor is not None and cursor.cursor
                    and hint.isdecimal() and cursor.cursor.isdecimal()
                ):
                    return int(hint) <= int(cursor.cursor)
            return False

    def finish_event(self, event_id: str, *, ignored: bool = False) -> None:
        with self.sessions.begin() as db:
            row = db.scalar(select(ConnectorEvent).where(
                ConnectorEvent.id == event_id,
            ).with_for_update())
            if row is None:
                return
            row.state = "ignored" if ignored else "processed"
            row.processed_at = utcnow()
            row.claim_until = None
            row.last_error_code = None
            sub = db.scalar(select(ConnectorSubscription).where(
                ConnectorSubscription.id == row.subscription_id,
            ).with_for_update())
            if (
                sub is not None and row.provider_sequence
                and _sequence_newer(row.provider_sequence, sub.last_event_sequence)
            ):
                sub.last_event_sequence = row.provider_sequence
                sub.updated_at = utcnow()

    def fail_event(self, event_id: str, code: str) -> None:
        with self.sessions.begin() as db:
            row = db.scalar(select(ConnectorEvent).where(
                ConnectorEvent.id == event_id,
            ).with_for_update())
            if row is None:
                return
            row.last_error_code = code[:60]
            row.claim_until = None
            if row.attempts >= 8:
                row.state = "failed"
            else:
                row.state = "retry"
                row.available_at = utcnow() + timedelta(
                    seconds=min(900, 2 ** min(row.attempts, 9))
                )

    def revoke_subscriptions(self, owner: str, grant_id: str) -> list[dict]:
        with self.sessions.begin() as db:
            rows = db.scalars(select(ConnectorSubscription).where(
                ConnectorSubscription.owner_id == owner,
                ConnectorSubscription.grant_id == grant_id,
                ConnectorSubscription.state.in_(["pending", "active", "renewing"]),
            ).with_for_update()).all()
            result = [self._subscription_dto(row) for row in rows]
            for row in rows:
                row.state = "revoked"
                row.claim_until = None
                row.updated_at = utcnow()
            return result



class ConnectorReadService:
    def __init__(self, repository: ConnectorReadRepository, credential_broker, push_verifier=None):
        self.repo = repository
        self.credential_broker = credential_broker
        self.push_verifier = push_verifier

    @staticmethod
    def _expiry(ms: int | None, fallback_hours: int = 24) -> datetime:
        if ms is None:
            return utcnow() + timedelta(hours=fallback_hours)
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    @staticmethod
    def _renew_after(capability: str, expires_at: datetime) -> datetime:
        now = utcnow()
        if capability == "email_read":
            return min(now + timedelta(hours=24), expires_at - timedelta(hours=24))
        return max(now + timedelta(minutes=15), expires_at - timedelta(hours=6))

    async def subscribe(
        self,
        owner: str,
        grant_id: str,
        *,
        replace_subscription_id: str | None = None,
    ) -> dict:
        grant, adapter, token = await self.credential_broker.issue_read_access(
            owner, grant_id, audience=CONNECTOR_READ_AUDIENCE,
        )
        settings = self.repo.settings
        if grant["provider"] != "google" or not hasattr(adapter, "start_read_watch"):
            raise CoworkerError(
                "connector_subscription_unavailable",
                "This provider does not support event subscriptions in this deployment.",
                503,
            )
        if not settings.connector_webhook_base_url:
            raise CoworkerError(
                "connector_subscription_unconfigured",
                "Connected event delivery is not configured in this deployment.",
                503,
            )
        channel_id = str(uuid4())
        channel_token = secrets.token_urlsafe(32)
        if grant["capability"] == "email_read":
            if not all((
                settings.google_gmail_pubsub_topic,
                settings.google_gmail_pubsub_subscription,
                settings.google_gmail_push_audience,
                settings.google_gmail_push_service_account,
            )):
                raise CoworkerError(
                    "connector_subscription_unconfigured",
                    "Gmail event delivery is not configured in this deployment.",
                    503,
                )
            provider_subscription_id = settings.google_gmail_pubsub_subscription
            callback_url = settings.connector_webhook_base_url + "/api/v1/connectors/google/gmail/events"
            token_hash = None
            kind = "gmail_pubsub"
        elif grant["capability"] == "calendar_read":
            provider_subscription_id = channel_id
            callback_url = settings.connector_webhook_base_url + "/api/v1/connectors/google/calendar/events"
            token_hash = _token_hash(channel_token)
            kind = "calendar_webhook"
        else:
            raise CoworkerError("connector_read_unregistered", "This read capability is not registered.", 409)
        reserved = await asyncio.to_thread(
            self.repo.reserve_subscription,
            owner, grant_id, kind=kind,
            provider_subscription_id=provider_subscription_id,
            token_hash=token_hash,
        )
        try:
            provider = await adapter.start_read_watch(
                grant["capability"], token,
                channel_id=channel_id,
                callback_url=callback_url,
                channel_token=channel_token,
                gmail_topic=settings.google_gmail_pubsub_topic,
            )
            expires_at = self._expiry(
                provider.get("expires_at_ms"),
                fallback_hours=24 if grant["capability"] == "calendar_read" else 168,
            )
            active = await asyncio.to_thread(
                self.repo.activate_subscription,
                owner, reserved["id"],
                provider_subscription_id=(
                    provider.get("provider_subscription_id")
                    or provider_subscription_id
                ),
                provider_resource_id=provider.get("provider_resource_id"),
                expires_at=expires_at,
                renew_after=self._renew_after(grant["capability"], expires_at),
                replaced_subscription_id=replace_subscription_id,
            )
            return active
        except Exception:
            await asyncio.to_thread(
                self.repo.subscription_failed,
                owner, reserved["id"], "provider_subscription_failed",
            )
            raise

    async def revoke(self, owner: str, grant_id: str) -> dict:
        access = None
        try:
            access = await self.credential_broker.issue_read_access(
                owner, grant_id, audience=CONNECTOR_READ_AUDIENCE,
            )
        except Exception:
            access = None
        subscriptions = await asyncio.to_thread(
            self.repo.revoke_subscriptions, owner, grant_id
        )
        grant = await asyncio.to_thread(self.repo.revoke, owner, grant_id)
        if access is not None:
            _verified, adapter, token = access
            for sub in subscriptions:
                try:
                    await adapter.stop_read_watch(
                        sub["capability"], token,
                        provider_subscription_id=sub["provider_subscription_id"],
                        provider_resource_id=sub["provider_resource_id"],
                    )
                except Exception:
                    pass
        return grant

    async def process_event(self, event: dict) -> None:
        if await asyncio.to_thread(self.repo.event_is_stale, event):
            await asyncio.to_thread(self.repo.finish_event, event["id"], ignored=True)
            return
        try:
            await self.sync(event["owner_id"], event["grant_id"])
        except CoworkerError as error:
            if error.code in {
                "connector_read_revoked", "connector_read_expired",
                "connection_removed", "not_found",
            }:
                await asyncio.to_thread(self.repo.finish_event, event["id"], ignored=True)
                return
            await asyncio.to_thread(self.repo.fail_event, event["id"], error.code)
            return
        except Exception:
            await asyncio.to_thread(
                self.repo.fail_event, event["id"], "connector_event_sync_failed"
            )
            return
        await asyncio.to_thread(self.repo.finish_event, event["id"])

    async def renew_subscription(self, value: dict) -> None:
        try:
            await self.subscribe(
                value["owner_id"], value["grant_id"],
                replace_subscription_id=value["id"],
            )
        except Exception:
            await asyncio.to_thread(
                self.repo.subscription_failed,
                value["owner_id"], value["id"], "subscription_renewal_failed",
            )


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
        if force_full and cursor_state["cursor"] is not None:
            await asyncio.to_thread(self.repo.reset_cursor, owner, grant_id)
            cursor_state = await asyncio.to_thread(self.repo.cursor, owner, grant_id)
        cursor = cursor_state["cursor"]
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
