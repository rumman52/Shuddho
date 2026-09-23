"""Owner-scoped recipient shortcuts for explicitly reviewed actions.

The directory never resolves a model-generated name and never reaches a provider.
A selected entry is copied into the ordinary action payload as an exact email
address before the immutable approval preview is created.
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, or_, select

from .config import Settings
from .errors import CoworkerError
from .models import Account, ActionRecipient, AuditEvent, utcnow
from .recipient_schemas import RecipientUpsert
from .repository import iso, not_found


def recipient_name_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def recipient_dto(row: ActionRecipient) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "email": row.email,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


class RecipientRepository:
    def __init__(self, sessions, settings: Settings):
        self.sessions, self.settings = sessions, settings

    def _enabled(self) -> None:
        if not self.settings.action_recipients_enabled:
            raise CoworkerError(
                "action_recipients_disabled",
                "Saved action recipients are not enabled in this deployment.",
                409,
            )

    @staticmethod
    def _account(db, owner: str) -> None:
        if db.scalar(select(Account.id).where(Account.id == owner).with_for_update()) is None:
            raise not_found()

    @staticmethod
    def _row(db, owner: str, recipient_id: str) -> ActionRecipient:
        row = db.scalar(select(ActionRecipient).where(
            ActionRecipient.id == recipient_id,
            ActionRecipient.owner_id == owner,
        ).with_for_update())
        if row is None:
            raise not_found()
        return row

    @staticmethod
    def _audit(db, owner: str, recipient_id: str, action: str) -> None:
        db.add(AuditEvent(
            id=str(uuid4()),
            owner_id=owner,
            resource_id=recipient_id,
            action=action,
        ))

    @staticmethod
    def _conflict(db, owner: str, name_key: str, email_key: str, *, exclude_id: str | None = None) -> bool:
        query = select(ActionRecipient.id).where(
            ActionRecipient.owner_id == owner,
            or_(
                ActionRecipient.name_key == name_key,
                ActionRecipient.email_key == email_key,
            ),
        )
        if exclude_id is not None:
            query = query.where(ActionRecipient.id != exclude_id)
        return db.scalar(query.limit(1)) is not None

    def list(self, owner: str) -> list[dict]:
        with self.sessions() as db:
            rows = db.scalars(select(ActionRecipient).where(
                ActionRecipient.owner_id == owner,
            ).order_by(ActionRecipient.name_key, ActionRecipient.id).limit(
                self.settings.max_action_recipients,
            )).all()
            return [recipient_dto(row) for row in rows]

    def create(self, owner: str, request: RecipientUpsert) -> dict:
        self._enabled()
        name_key = recipient_name_key(request.name)
        email_key = request.email.casefold()
        with self.sessions.begin() as db:
            self._account(db, owner)
            count = db.scalar(select(func.count()).select_from(ActionRecipient).where(
                ActionRecipient.owner_id == owner,
            ))
            if count >= self.settings.max_action_recipients:
                raise CoworkerError(
                    "action_recipient_limit",
                    "Your saved recipient limit has been reached.",
                    429,
                )
            if self._conflict(db, owner, name_key, email_key):
                raise CoworkerError(
                    "action_recipient_conflict",
                    "A saved recipient already uses this name or email address.",
                    409,
                )
            row = ActionRecipient(
                id=str(uuid4()),
                owner_id=owner,
                name=request.name,
                name_key=name_key,
                email=request.email,
                email_key=email_key,
            )
            db.add(row)
            self._audit(db, owner, row.id, "action_recipient.created")
            db.flush()
            return recipient_dto(row)

    def update(self, owner: str, recipient_id: str, request: RecipientUpsert) -> dict:
        self._enabled()
        name_key = recipient_name_key(request.name)
        email_key = request.email.casefold()
        with self.sessions.begin() as db:
            self._account(db, owner)
            row = self._row(db, owner, recipient_id)
            if self._conflict(db, owner, name_key, email_key, exclude_id=row.id):
                raise CoworkerError(
                    "action_recipient_conflict",
                    "A saved recipient already uses this name or email address.",
                    409,
                )
            row.name = request.name
            row.name_key = name_key
            row.email = request.email
            row.email_key = email_key
            row.updated_at = utcnow()
            self._audit(db, owner, row.id, "action_recipient.updated")
            return recipient_dto(row)

    def delete(self, owner: str, recipient_id: str) -> dict:
        # Keep deletion available after a feature rollback so stored personal
        # data is never stranded behind an enablement flag.
        with self.sessions.begin() as db:
            self._account(db, owner)
            row = self._row(db, owner, recipient_id)
            db.delete(row)
            self._audit(db, owner, recipient_id, "action_recipient.deleted")
        return {"deleted": True, "id": recipient_id}
