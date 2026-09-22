"""Durable approvals and one external mutation attempt per approved action.

Lock order: account (user mutations), connection, action. Worker paths never
lock the account. PostgreSQL row locks are required for concurrent production.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, update

from .action_registry import action_spec, build_approval_scope, validate_approval_scope
from .action_schemas import ActionPrepare
from .action_security import TokenVault
from .errors import CoworkerError
from .models import Account, AuditEvent, Connection, ExternalAction, OAuthAttempt, utcnow
from .repository import aware, iso, not_found

TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}
MESSAGES = {
    "awaiting_approval": "Review every detail before approving.",
    "queued": "Approved. Waiting to execute.",
    "executing": "Contacting your connected service. Do not repeat this action.",
    "succeeded": "The provider confirmed this action. See the receipt below.",
    "failed": "The action was not completed. Review the connection and prepare a new action.",
    "cancelled": "Cancelled before execution.",
    "expired": "The approval window expired before execution. Prepare a new preview.",
    "outcome_unknown": "The provider result is uncertain. Check your Sent folder or calendar before creating another action. Shuddho will not automatically repeat it.",
}


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def connection_dto(row):
    return {"id": row.id, "provider": row.provider, "capability": row.capability,
            "email": row.email, "active": row.active, "created_at": iso(row.created_at)}


def action_dto(row):
    return {"id": row.id, "connection_id": row.connection_id, "kind": row.kind, "state": row.state,
            "preview": row.preview, "preview_hash": row.preview_hash, "message": MESSAGES[row.state],
            "receipt": row.receipt, "error_code": row.error_code, "created_at": iso(row.created_at),
            "expires_at": iso(row.expires_at), "approved_at": iso(row.approved_at) if row.approved_at else None,
            "finished_at": iso(row.finished_at) if row.finished_at else None}


class ActionRepository:
    def __init__(self, sessions, settings):
        self.sessions, self.settings = sessions, settings

    def enabled(self):
        if not self.settings.actions_enabled:
            raise CoworkerError("actions_disabled", "Email and calendar actions are not available in this deployment.", 503)

    def vault(self):
        return TokenVault(self.settings.connector_encryption_key)

    @staticmethod
    def _account(db, owner):
        if not db.scalar(select(Account).where(Account.id == owner).with_for_update()):
            raise not_found()

    @staticmethod
    def _audit(db, owner, resource, action):
        db.add(AuditEvent(id=str(uuid4()), owner_id=owner, resource_id=resource, action=action))

    @staticmethod
    def _connection(db, owner, connection_id):
        row = db.scalar(select(Connection).where(Connection.id == connection_id, Connection.owner_id == owner).with_for_update())
        if not row:
            raise not_found()
        return row

    @staticmethod
    def _action(db, owner, action_id, lock=True):
        query = select(ExternalAction).where(ExternalAction.id == action_id, ExternalAction.owner_id == owner)
        row = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if not row:
            raise not_found()
        return row

    def start_oauth(self, owner, capability, provider="google"):
        self.enabled()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        state_hash = hashlib.sha256(state.encode()).hexdigest()
        with self.sessions.begin() as db:
            self._account(db, owner)
            today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            if db.scalar(select(func.count()).select_from(OAuthAttempt).where(OAuthAttempt.owner_id == owner, OAuthAttempt.created_at >= today)) >= 20:
                raise CoworkerError("connection_limit", "Too many connection attempts today. Please try tomorrow.", 429)
            # One outstanding OAuth flow per account. Late callbacks cannot
            # replace a newer connection or undo a disconnect.
            db.execute(update(OAuthAttempt).where(OAuthAttempt.owner_id == owner).values(consumed=True, verifier_ciphertext=""))
            db.add(OAuthAttempt(state_hash=state_hash, owner_id=owner, capability=capability, provider=provider,
                               verifier_ciphertext=self.vault().seal({"verifier": verifier}, owner + ":oauth:" + state_hash),
                               expires_at=utcnow() + timedelta(minutes=10)))
        return state, verifier

    def consume_oauth(self, owner, state):
        self.enabled()
        state_hash = hashlib.sha256(state.encode()).hexdigest()
        with self.sessions.begin() as db:
            self._account(db, owner)
            row = db.scalar(select(OAuthAttempt).where(OAuthAttempt.state_hash == state_hash, OAuthAttempt.owner_id == owner).with_for_update())
            if not row or row.consumed or aware(row.expires_at) <= utcnow():
                raise CoworkerError("oauth_expired", "This connection request expired or was already used. Start again.", 409)
            value = self.vault().open(row.verifier_ciphertext, owner + ":oauth:" + state_hash)
            row.consumed, row.verifier_ciphertext = True, ""
            return {"state_hash": state_hash, "verifier": value["verifier"], "capability": row.capability, "provider": row.provider}

    def finish_connection(self, owner, attempt, profile, refresh_token, scopes):
        self.enabled()
        with self.sessions.begin() as db:
            self._account(db, owner)
            # Disconnect/new connect invalidates in-flight exchanges too.
            row = db.get(OAuthAttempt, attempt["state_hash"])
            if not row or aware(row.expires_at) <= utcnow():
                raise CoworkerError("oauth_expired", "Start a new connection request.", 409)
            latest = db.scalar(select(OAuthAttempt.state_hash).where(OAuthAttempt.owner_id == owner).order_by(OAuthAttempt.created_at.desc()).limit(1))
            if latest != row.state_hash:
                raise CoworkerError("oauth_expired", "A newer connection request replaced this one.", 409)
            old = db.scalars(select(Connection).where(
                Connection.owner_id == owner,
                Connection.capability == row.capability,
                Connection.provider == row.provider,
                Connection.active.is_(True),
            ).with_for_update()).all()
            for connection in old:
                self._disconnect(db, connection)
            connection_id = str(uuid4())
            if attempt.get("provider") != row.provider:
                raise CoworkerError("oauth_expired", "The connection provider changed. Start again.", 409)
            connection = Connection(id=connection_id, owner_id=owner, provider=row.provider, capability=attempt["capability"],
                                    subject=profile["sub"], email=profile["email"], scopes=scopes,
                                    token_ciphertext=self.vault().seal({"refresh_token": refresh_token}, owner + ":connection:" + connection_id))
            db.add(connection)
            row.expires_at = utcnow()  # Prevent a second finish after exchange.
            self._audit(db, owner, connection_id, "connection.created")
            db.flush()
            return connection_dto(connection)

    def connections(self, owner):
        with self.sessions() as db:
            return [connection_dto(row) for row in db.scalars(select(Connection).where(Connection.owner_id == owner, Connection.active.is_(True)).order_by(Connection.created_at.desc()))]

    def _disconnect(self, db, connection):
        connection.active, connection.token_ciphertext = False, ""
        for action in db.scalars(select(ExternalAction).where(ExternalAction.connection_id == connection.id, ExternalAction.state.in_(["awaiting_approval", "queued"])).with_for_update()):
            action.state, action.finished_at = "cancelled", utcnow()
            self._audit(db, connection.owner_id, action.id, "action.cancelled_disconnect")
        self._audit(db, connection.owner_id, connection.id, "connection.disconnected")

    def disconnect(self, owner, connection_id):
        with self.sessions.begin() as db:
            self._account(db, owner)
            row = self._connection(db, owner, connection_id)
            self._disconnect(db, row)
            db.execute(update(OAuthAttempt).where(OAuthAttempt.owner_id == owner).values(expires_at=utcnow(), consumed=True, verifier_ciphertext=""))
        return {"message": "Disconnected from Shuddho. Pending actions were cancelled; an action already executing may still finish. You can also revoke Shuddho in the connected provider's account settings."}

    def credentials(self, connection_id):
        # Internal worker/service call only; never serialized to an API.
        with self.sessions() as db:
            row = db.get(Connection, connection_id)
            if not row or not row.active:
                raise CoworkerError("connection_removed", "Reconnect your connected account.", 409)
            secret = self.vault().open(row.token_ciphertext, row.owner_id + ":connection:" + row.id)
            return {"refresh_token": secret["refresh_token"], "scopes": row.scopes}

    def rotate_token(self, connection_id, refresh_token):
        with self.sessions.begin() as db:
            row = db.scalar(select(Connection).where(Connection.id == connection_id).with_for_update())
            if row and row.active:
                row.token_ciphertext = self.vault().seal({"refresh_token": refresh_token}, row.owner_id + ":connection:" + row.id)

    def prepare(self, owner, request: ActionPrepare, key):
        body = request.model_dump(mode="json")
        fingerprint = digest(body)
        with self.sessions.begin() as db:
            self._account(db, owner)
            old = db.scalar(select(ExternalAction).where(ExternalAction.owner_id == owner, ExternalAction.idempotency_key == key))
            if old:
                if not hmac.compare_digest(old.fingerprint, fingerprint):
                    raise CoworkerError("idempotency_conflict", "These details changed. Prepare a fresh preview.", 409)
                return action_dto(old)
            self.enabled()
            connection = self._connection(db, owner, str(request.connection_id))
            if (
                connection.provider == "microsoft"
                and not self.settings.microsoft_actions_enabled
            ):
                raise CoworkerError(
                    "connection_provider_disabled",
                    "Microsoft actions are not enabled in this deployment.",
                    503,
                )
            spec = action_spec(request.payload.kind, connection.provider)
            capability = spec.capability
            if not connection.active or connection.capability != capability:
                raise CoworkerError("connection_removed", "Connect the matching service before preparing this action.", 409)
            today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            count = db.scalar(select(func.count()).select_from(ExternalAction).where(ExternalAction.owner_id == owner, ExternalAction.created_at >= today))
            if count >= 100:
                raise CoworkerError("preview_limit", "Your daily action-preview limit has been reached.", 429)
            if spec.requires_future_start:
                self._future(request.payload.start_at)
            action_id = str(uuid4())
            expires = utcnow() + timedelta(seconds=spec.approval_ttl_seconds)
            preview = {
                "version": 2,
                "provider": connection.provider,
                "connection_id": connection.id,
                "account": connection.email,
                "subject_id": connection.subject,
                "payload": body["payload"],
                **spec.policy_manifest(),
                "expires_at": iso(expires),
            }
            preview["approval_scope"] = build_approval_scope(preview)
            row = ExternalAction(id=action_id, owner_id=owner, connection_id=connection.id, idempotency_key=key,
                                 fingerprint=fingerprint, kind=request.payload.kind, preview=preview,
                                 preview_hash=digest(preview), expires_at=expires)
            db.add(row)
            self._audit(db, owner, action_id, "action.prepared")
            db.flush()
            return action_dto(row)

    @staticmethod
    def _future(start):
        if not utcnow() < start < utcnow() + timedelta(days=366):
            raise CoworkerError("event_time", "Choose a future event within the next year.", 422)

    def approve(self, owner, action_id, preview_hash):
        with self.sessions.begin() as db:
            self._account(db, owner)
            snapshot = self._action(db, owner, action_id, lock=False)
            connection = self._connection(db, owner, snapshot.connection_id)
            row = self._action(db, owner, action_id)
            if not hmac.compare_digest(row.preview_hash, preview_hash) or digest(row.preview) != row.preview_hash:
                raise CoworkerError("approval_changed", "The preview changed. Review it again before approving.", 409)
            spec = validate_approval_scope(row.preview)
            if row.approved_at:  # Replayed approval never dispatches a new action.
                return action_dto(row)
            self.enabled()
            if row.state != "awaiting_approval" or aware(row.expires_at) <= utcnow() or not connection.active:
                raise CoworkerError("approval_expired", "This preview is no longer available for approval. Prepare a new one.", 409)
            if spec.requires_future_start:
                from datetime import datetime
                self._future(datetime.fromisoformat(row.preview["payload"]["start_at"]))
            today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            count = db.scalar(select(func.count()).select_from(ExternalAction).where(ExternalAction.owner_id == owner, ExternalAction.approved_at >= today))
            if count >= self.settings.max_daily_actions:
                raise CoworkerError("action_limit", "Your daily email and calendar action limit has been reached.", 429)
            row.state, row.approved_at = "queued", utcnow()
            row.expires_at = min(
                aware(row.expires_at),
                utcnow() + timedelta(seconds=spec.execution_ttl_seconds),
            )
            self._audit(db, owner, action_id, "action.approved")
            return action_dto(row)

    def cancel(self, owner, action_id):
        with self.sessions.begin() as db:
            row = self._action(db, owner, action_id)
            if row.state in {"awaiting_approval", "queued"}:
                row.state, row.finished_at = "cancelled", utcnow()
                self._audit(db, owner, action_id, "action.cancelled")
            elif row.state != "cancelled":
                raise CoworkerError("execution_started", "Execution may already have started. Check the action result before making changes.", 409)
            return action_dto(row)

    def list(self, owner):
        with self.sessions() as db:
            return [action_dto(row) for row in db.scalars(select(ExternalAction).where(ExternalAction.owner_id == owner).order_by(ExternalAction.created_at.desc()).limit(50))]

    def get(self, owner, action_id):
        with self.sessions() as db:
            row = self._action(db, owner, action_id, lock=False)
            result = action_dto(row)
            result["audit"] = [{"action": event.action, "created_at": iso(event.created_at)} for event in db.scalars(
                select(AuditEvent).where(AuditEvent.owner_id == owner, AuditEvent.resource_id == action_id).order_by(AuditEvent.created_at))]
            return result

    def worker_get(self, action_id):
        with self.sessions() as db:
            row = db.get(ExternalAction, action_id)
            if not row:
                raise not_found()
            return action_dto(row)

    def reserve_reconciliation(self, owner, action_id):
        with self.sessions.begin() as db:
            row = self._action(db, owner, action_id)
            spec = validate_approval_scope(row.preview)
            if row.state != "outcome_unknown" or not spec.reconcile_supported:
                raise CoworkerError("reconciliation_unavailable", "This uncertain action cannot be reconciled with its connected service.", 409)
            checks = db.scalars(select(AuditEvent).where(AuditEvent.owner_id == owner, AuditEvent.resource_id == action_id,
                                AuditEvent.action == "action.reconciliation_requested").order_by(AuditEvent.created_at.desc()).limit(10)).all()
            if len(checks) >= 10 or checks and aware(checks[0].created_at) > utcnow() - timedelta(minutes=1):
                raise CoworkerError("reconciliation_limit", "Wait a minute between calendar checks. After ten checks, inspect Google Calendar directly.", 429)
            self._audit(db, owner, action_id, "action.reconciliation_requested")
            return action_dto(row)

    def claim_execution(self, action_id):
        """Commit BEFORE any provider mutation; no path resets this claim."""
        self.enabled()
        with self.sessions.begin() as db:
            snapshot = db.get(ExternalAction, action_id)
            if not snapshot:
                raise not_found()
            connection = self._connection(db, snapshot.owner_id, snapshot.connection_id)
            row = self._action(db, snapshot.owner_id, action_id)
            if row.state != "queued":
                return None
            if not connection.active:
                row.state, row.finished_at = "cancelled", utcnow()
                return None
            if aware(row.expires_at) <= utcnow():
                row.state, row.finished_at = "expired", utcnow()
                self._audit(db, row.owner_id, row.id, "action.expired")
                return None
            if (not row.approved_at or digest(row.preview) != row.preview_hash or
                    row.preview["connection_id"] != connection.id or row.preview["account"] != connection.email or
                    row.preview["subject_id"] != connection.subject):
                raise CoworkerError("approval_changed", "Action approval could not be verified.", 409)
            spec = validate_approval_scope(row.preview)
            if connection.provider not in spec.providers or connection.capability != spec.capability:
                raise CoworkerError("approval_changed", "Action authorization no longer matches the connection.", 409)
            if spec.requires_future_start:
                from datetime import datetime
                try:
                    self._future(datetime.fromisoformat(row.preview["payload"]["start_at"]))
                except CoworkerError:
                    row.state, row.finished_at, row.error_code = "failed", utcnow(), "event_time"
                    self._audit(db, row.owner_id, row.id, "action.failed")
                    return None
            row.state, row.started_at = "executing", utcnow()
            self._audit(db, row.owner_id, row.id, "action.execution_started")
            return action_dto(row)

    def finish(self, action_id, state, receipt=None, error_code=None, unstarted=False):
        if state not in {"succeeded", "failed", "outcome_unknown"}:
            raise ValueError("Invalid action result")
        with self.sessions.begin() as db:
            row = db.scalar(select(ExternalAction).where(ExternalAction.id == action_id).with_for_update())
            if not row or row.state not in {"queued", "executing", "outcome_unknown"} or unstarted and row.state != "queued":
                return
            # A late confirmed response may resolve a previously uncertain
            # attempt. Unknown outcomes never overwrite confirmed receipts.
            if state == "succeeded" and (not row.started_at or not receipt):
                raise ValueError("A provider receipt is required")
            if row.state == "queued" and state == "outcome_unknown":
                state = "failed"  # No execution claim: no provider mutation.
            row.state, row.receipt, row.error_code, row.finished_at = state, receipt, error_code, utcnow()
            self._audit(db, row.owner_id, row.id, "action." + state)

    def claim_outbox(self):
        now = utcnow()
        with self.sessions.begin() as db:
            for row in db.scalars(select(ExternalAction).where(ExternalAction.state.in_(["awaiting_approval", "queued"]), ExternalAction.expires_at <= now).with_for_update(skip_locked=True)):
                row.state, row.finished_at = "expired", now
                self._audit(db, row.owner_id, row.id, "action.expired")
            # A lost workflow/activity cannot leave a claimed send displaying
            # "executing" forever. Reconciliation is read-only afterward.
            for row in db.scalars(select(ExternalAction).where(ExternalAction.state == "executing", ExternalAction.started_at < now - timedelta(minutes=10)).with_for_update(skip_locked=True)):
                row.state, row.finished_at, row.error_code = "outcome_unknown", now, "worker_interrupted"
                self._audit(db, row.owner_id, row.id, "action.outcome_unknown")
            db.execute(update(OAuthAttempt).where(OAuthAttempt.expires_at <= now, OAuthAttempt.verifier_ciphertext != "").values(verifier_ciphertext="", consumed=True))
            if not self.settings.actions_enabled:
                return []
            rows = db.scalars(select(ExternalAction).where(
                ExternalAction.state == "queued",
                ExternalAction.delivered.is_(False),
                or_(ExternalAction.agent_run_id.is_(None), ExternalAction.agent_ready.is_(True)),
                or_(ExternalAction.lease_until.is_(None), ExternalAction.lease_until < now),
            ).order_by(ExternalAction.created_at).limit(20).with_for_update(skip_locked=True)).all()
            for row in rows:
                row.lease_until = now + timedelta(seconds=30)
            return [row.id for row in rows]

    def delivered(self, action_id):
        with self.sessions.begin() as db:
            db.execute(update(ExternalAction).where(ExternalAction.id == action_id).values(delivered=True))
