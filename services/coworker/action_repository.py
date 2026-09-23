"""Durable approvals and one external mutation attempt per approved action.

Lock order: account (user mutations), connection, action. Worker paths never
lock the account. PostgreSQL row locks are required for concurrent production.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, update

from .action_registry import action_spec, build_approval_scope, validate_approval_scope
from .action_schemas import ActionPrepare
from .action_security import TokenVault
from .errors import CoworkerError
from .models import Account, ActionProposal, Artifact, AuditEvent, Connection, ExternalAction, OAuthAttempt, utcnow
from .repository import aware, iso, not_found

TERMINAL = {"succeeded", "failed", "cancelled", "expired", "outcome_unknown"}

ATTACHMENT_MAX_COUNT = 3
ATTACHMENT_MAX_TOTAL_BYTES = 2 * 1024 * 1024
ATTACHMENT_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
}

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

    def _optional_feature_error(self, spec):
        if spec.attachments_allowed and not self.settings.action_attachments_enabled:
            return (
                "action_attachments_disabled",
                "Email attachments are not enabled in this deployment.",
            )
        if spec.reminders != "none" and not self.settings.action_reminders_enabled:
            return (
                "action_reminders_disabled",
                "Calendar reminders are not enabled in this deployment.",
            )
        return None

    def _require_optional_feature(self, spec):
        failure = self._optional_feature_error(spec)
        if failure is not None:
            raise CoworkerError(failure[0], failure[1], 503)

    @staticmethod
    def _require_live_reminder(payload):
        if payload.get("kind") != "calendar_create_with_reminder":
            return
        try:
            start = datetime.fromisoformat(payload["start_at"])
            minutes = int(payload["reminder_minutes_before_start"])
        except (KeyError, TypeError, ValueError):
            raise CoworkerError(
                "reminder_time",
                "The approved reminder timing is invalid.",
                422,
            ) from None
        if start - timedelta(minutes=minutes) <= utcnow():
            raise CoworkerError(
                "reminder_time",
                "Choose a reminder that is still in the future.",
                422,
            )

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


    @staticmethod
    def _attachment_manifest(db, owner, attachment_ids):
        ids = [str(value) for value in attachment_ids]
        if not ids:
            return []
        if len(ids) > ATTACHMENT_MAX_COUNT or len(ids) != len(set(ids)):
            raise CoworkerError(
                "attachment_invalid",
                "Choose up to three unique Shuddho artifacts.",
                422,
            )
        rows = db.scalars(select(Artifact).where(
            Artifact.owner_id == owner,
            Artifact.id.in_(ids),
        )).all()
        by_id = {row.id: row for row in rows}
        if set(by_id) != set(ids):
            raise not_found()
        result = []
        total = 0
        for artifact_id in ids:
            row = by_id[artifact_id]
            base_type = row.content_type.split(";", 1)[0].strip().lower()
            extension = ATTACHMENT_CONTENT_TYPES.get(base_type)
            if (
                extension is None
                or not row.filename.lower().endswith(extension)
                or row.byte_size < 1
            ):
                raise CoworkerError(
                    "attachment_type",
                    "This Shuddho artifact cannot be attached to email.",
                    415,
                )
            total += row.byte_size
            if total > ATTACHMENT_MAX_TOTAL_BYTES:
                raise CoworkerError(
                    "attachment_size",
                    "Selected attachments exceed the 2 MB action limit.",
                    413,
                )
            result.append({
                "id": row.id,
                "filename": row.filename,
                "content_type": base_type,
                "byte_size": row.byte_size,
                "sha256": row.sha256,
            })
        return result

    def execution_attachments(self, action):
        validate_approval_scope(action["preview"])
        manifest = action["preview"].get("attachments", [])
        if action["kind"] != "email_send_with_attachments":
            if manifest != []:
                raise CoworkerError(
                    "approval_changed",
                    "Unexpected attachments were found on this action.",
                    409,
                )
            return []
        with self.sessions() as db:
            current = self._attachment_manifest(
                db,
                action["owner_id"],
                [item["id"] for item in manifest],
            )
            if not hmac.compare_digest(
                digest({"attachments": current}),
                digest({"attachments": manifest}),
            ):
                raise CoworkerError(
                    "attachment_changed",
                    "An approved attachment changed or is no longer available.",
                    409,
                )
            rows = {
                row.id: row
                for row in db.scalars(select(Artifact).where(
                    Artifact.owner_id == action["owner_id"],
                    Artifact.id.in_([item["id"] for item in manifest]),
                ))
            }
            return [
                dict(item) | {"object_key": rows[item["id"]].object_key}
                for item in manifest
            ]

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
            self._require_optional_feature(spec)
            attachments = self._attachment_manifest(
                db,
                owner,
                request.attachment_ids,
            )
            if bool(attachments) != spec.attachments_allowed:
                raise CoworkerError(
                    "attachment_invalid",
                    "Attachment selection does not match this action.",
                    422,
                )
            capability = spec.capability
            if not connection.active or connection.capability != capability:
                raise CoworkerError("connection_removed", "Connect the matching service before preparing this action.", 409)
            today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            count = db.scalar(select(func.count()).select_from(ExternalAction).where(ExternalAction.owner_id == owner, ExternalAction.created_at >= today))
            if count >= 100:
                raise CoworkerError("preview_limit", "Your daily action-preview limit has been reached.", 429)
            if spec.requires_future_start:
                self._future(request.payload.start_at)
                self._require_live_reminder(body["payload"])
            action_id = str(uuid4())
            expires = utcnow() + timedelta(seconds=spec.approval_ttl_seconds)
            preview = {
                "version": 3 if spec.attachments_allowed else 2,
                "provider": connection.provider,
                "connection_id": connection.id,
                "account": connection.email,
                "subject_id": connection.subject,
                "payload": body["payload"],
                **spec.policy_manifest(),
                "attachments": attachments,
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

    def promote_proposal(
        self,
        owner: str,
        run_id: str,
        proposal_id: str,
        proposal_hash: str,
        connection_id: str,
    ):
        if not self.settings.agent_action_proposals_enabled:
            raise CoworkerError(
                "action_proposals_disabled",
                "Agent action proposals are not enabled in this deployment.",
                503,
            )
        self.enabled()
        with self.sessions.begin() as db:
            self._account(db, owner)
            proposal = db.scalar(select(ActionProposal).where(
                ActionProposal.id == proposal_id,
                ActionProposal.owner_id == owner,
                ActionProposal.agent_run_id == run_id,
            ).with_for_update())
            if proposal is None:
                raise not_found()
            if not hmac.compare_digest(proposal.proposal_hash, proposal_hash):
                raise CoworkerError(
                    "proposal_changed",
                    "This proposal changed. Review it again before promoting.",
                    409,
                )
            if proposal.state == "promoted":
                if (
                    proposal.promotion_connection_id != connection_id
                    or not proposal.promoted_action_id
                ):
                    raise CoworkerError(
                        "proposal_already_promoted",
                        "This proposal was already promoted with a different connection.",
                        409,
                    )
                action = self._action(
                    db,
                    owner,
                    proposal.promoted_action_id,
                    lock=False,
                )
                return action_dto(action)
            if proposal.state == "suggested" and aware(proposal.expires_at) <= utcnow():
                proposal.state = "expired"
            if proposal.state in {"dismissed", "expired"}:
                raise CoworkerError(
                    "proposal_unavailable",
                    "This proposal is no longer available for promotion.",
                    409,
                )
            if proposal.state == "promoting":
                if proposal.promotion_connection_id != connection_id:
                    raise CoworkerError(
                        "proposal_promotion_in_progress",
                        "This proposal is already being promoted with another connection.",
                        409,
                    )
            elif proposal.state == "suggested":
                proposal.state = "promoting"
                proposal.promotion_connection_id = connection_id
                self._audit(
                    db,
                    owner,
                    proposal.id,
                    "agent_action_proposal_promotion_reserved",
                )
            else:
                raise CoworkerError(
                    "proposal_unavailable",
                    "This proposal is not available for promotion.",
                    409,
                )
            payload = dict(proposal.payload)

        try:
            request = ActionPrepare.model_validate({
                "connection_id": connection_id,
                "payload": payload,
            })
            action = self.prepare(
                owner,
                request,
                "agent-proposal:" + proposal_id,
            )
        except Exception:
            with self.sessions.begin() as db:
                proposal = db.scalar(select(ActionProposal).where(
                    ActionProposal.id == proposal_id,
                    ActionProposal.owner_id == owner,
                    ActionProposal.agent_run_id == run_id,
                ).with_for_update())
                if (
                    proposal is not None
                    and proposal.state == "promoting"
                    and proposal.promoted_action_id is None
                    and proposal.promotion_connection_id == connection_id
                ):
                    proposal.state = "suggested"
                    proposal.promotion_connection_id = None
            raise

        with self.sessions.begin() as db:
            proposal = db.scalar(select(ActionProposal).where(
                ActionProposal.id == proposal_id,
                ActionProposal.owner_id == owner,
                ActionProposal.agent_run_id == run_id,
            ).with_for_update())
            if proposal is None:
                raise not_found()
            if proposal.state == "promoted":
                if proposal.promoted_action_id != action["id"]:
                    raise CoworkerError(
                        "proposal_promotion_conflict",
                        "This proposal promotion could not be reconciled.",
                        409,
                    )
                return action
            if (
                proposal.state != "promoting"
                or proposal.promotion_connection_id != connection_id
            ):
                raise CoworkerError(
                    "proposal_promotion_conflict",
                    "This proposal promotion could not be reconciled.",
                    409,
                )
            proposal.state = "promoted"
            proposal.promoted_action_id = action["id"]
            proposal.promoted_at = utcnow()
            self._audit(
                db,
                owner,
                proposal.id,
                "agent_action_proposal_promoted",
            )
            return action

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
            self._require_optional_feature(spec)
            if row.state != "awaiting_approval" or aware(row.expires_at) <= utcnow() or not connection.active:
                raise CoworkerError("approval_expired", "This preview is no longer available for approval. Prepare a new one.", 409)
            if spec.requires_future_start:
                self._future(datetime.fromisoformat(row.preview["payload"]["start_at"]))
                self._require_live_reminder(row.preview["payload"])
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
            return action_dto(row) | {"owner_id": row.owner_id}

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
            optional_failure = self._optional_feature_error(spec)
            if optional_failure is not None:
                row.state, row.finished_at, row.error_code = (
                    "cancelled",
                    utcnow(),
                    optional_failure[0],
                )
                self._audit(db, row.owner_id, row.id, "action.cancelled")
                return None
            if spec.requires_future_start:
                try:
                    self._future(datetime.fromisoformat(row.preview["payload"]["start_at"]))
                    self._require_live_reminder(row.preview["payload"])
                except CoworkerError as error:
                    row.state, row.finished_at, row.error_code = (
                        "failed",
                        utcnow(),
                        error.code,
                    )
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
