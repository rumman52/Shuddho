from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import func, select

from .config import Settings
from .errors import CoworkerError
from .models import (
    Account,
    AuditEvent,
    Connection,
    Transaction,
    TransactionEvent,
    TransactionRevision,
    Workspace,
    utcnow,
)
from .repository import iso, not_found


TransactionState = Literal[
    "draft",
    "terms_ready",
    "awaiting_review",
    "awaiting_approval",
    "approved",
    "executing",
    "confirmed",
    "cancelled",
    "expired",
    "failed",
    "outcome_unknown",
]

TRANSACTION_STATES = frozenset({
    "draft",
    "terms_ready",
    "awaiting_review",
    "awaiting_approval",
    "approved",
    "executing",
    "confirmed",
    "cancelled",
    "expired",
    "failed",
    "outcome_unknown",
})

# TX-02 deliberately exposes only business-state transitions that cannot perform
# a provider mutation. Approval/execution/result states are reserved for later
# capability-specific code that can prove immutable approval and provider evidence.
SAFE_DOMAIN_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"terms_ready", "awaiting_review", "cancelled", "expired"}),
    "terms_ready": frozenset({"awaiting_review", "cancelled", "expired"}),
    "awaiting_review": frozenset({"terms_ready", "awaiting_approval", "cancelled", "expired"}),
    "awaiting_approval": frozenset({"awaiting_review", "cancelled", "expired"}),
}

RESERVED_EXECUTION_STATES = frozenset({
    "approved",
    "executing",
    "confirmed",
    "failed",
    "outcome_unknown",
})

TERMINAL_STATES = frozenset({
    "confirmed",
    "cancelled",
    "expired",
    "failed",
    "outcome_unknown",
})


@dataclass(frozen=True)
class TransactionDraft:
    """Trusted-server input for creating business transaction intent.

    TX-02 does not mount this type on the public API. Future capability services
    must construct it after validating their own typed request contracts.
    """

    transaction_kind: str
    provider: str
    connection_id: str | None = None
    currency: str | None = None
    counterparty: str | None = None
    expires_at: datetime | None = None


class TransactionRepository:
    """Owner-scoped durable transaction business state.

    ExternalAction remains the only consequential execution primitive. This
    repository cannot approve or execute provider mutations.
    """

    def __init__(self, sessions, settings: Settings):
        self.sessions = sessions
        self.settings = settings

    def _require_enabled(self) -> None:
        if not self.settings.personal_transactions_enabled:
            raise CoworkerError(
                "personal_transactions_disabled",
                "Personal transaction workflows are not enabled in this deployment.",
                503,
            )

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        db.add(
            AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=resource,
                action=action,
            )
        )

    @staticmethod
    def _workspace(db, owner: str) -> str:
        workspace = db.scalar(
            select(Workspace.id).where(Workspace.owner_id == owner)
        )
        if workspace is None:
            raise not_found()
        return workspace

    @staticmethod
    def _transaction(
        db,
        owner: str,
        transaction_id: str,
        *,
        lock: bool = False,
    ) -> Transaction:
        query = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.owner_id == owner,
        )
        if lock:
            query = query.with_for_update()
        value = db.scalar(query)
        if value is None:
            raise not_found()
        return value

    @staticmethod
    def _normalize_currency(currency: str | None) -> str | None:
        if currency is None:
            return None
        value = currency.strip().upper()
        if len(value) != 3 or not value.isalpha() or not value.isascii():
            raise CoworkerError(
                "transaction_currency_invalid",
                "Transaction currency must be a three-letter ASCII currency code.",
                409,
            )
        return value

    @staticmethod
    def _safe_kind(value: str) -> str:
        normalized = value.strip().lower()
        if (
            not normalized
            or len(normalized) > 40
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in normalized)
        ):
            raise CoworkerError(
                "transaction_kind_invalid",
                "The transaction kind is not registered in a safe canonical form.",
                409,
            )
        return normalized

    @staticmethod
    def _safe_provider(value: str) -> str:
        normalized = value.strip().lower()
        if (
            not normalized
            or len(normalized) > 40
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in normalized)
        ):
            raise CoworkerError(
                "transaction_provider_invalid",
                "The transaction provider identity is invalid.",
                409,
            )
        return normalized

    @staticmethod
    def _snapshot(row: Transaction) -> dict:
        return {
            "transaction_kind": row.transaction_kind,
            "provider": row.provider,
            "connection_id": row.connection_id,
            "provider_account_ref": row.provider_account_ref,
            "state": row.state,
            "currency": row.currency,
            "counterparty": row.counterparty,
            "expires_at": iso(row.expires_at) if row.expires_at is not None else None,
        }

    def _record_revision(self, db, row: Transaction) -> None:
        db.add(
            TransactionRevision(
                transaction_id=row.id,
                revision=row.revision,
                owner_id=row.owner_id,
                snapshot=self._snapshot(row),
            )
        )

    @staticmethod
    def _next_event_sequence(db, row: Transaction) -> int:
        return int(
            db.scalar(
                select(func.coalesce(func.max(TransactionEvent.sequence), 0)).where(
                    TransactionEvent.transaction_id == row.id,
                    TransactionEvent.owner_id == row.owner_id,
                )
            )
            or 0
        ) + 1

    def _record_event(
        self,
        db,
        row: Transaction,
        event_type: str,
        *,
        details: dict | None = None,
    ) -> None:
        db.add(
            TransactionEvent(
                transaction_id=row.id,
                sequence=self._next_event_sequence(db, row),
                owner_id=row.owner_id,
                revision=row.revision,
                state=row.state,
                event_type=event_type,
                details=dict(details or {}),
            )
        )

    @staticmethod
    def _fingerprint(value: dict) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    def _connection_identity(
        self,
        db,
        owner: str,
        connection_id: str | None,
        provider: str,
    ) -> tuple[str | None, str | None]:
        if connection_id is None:
            return None, None
        connection = db.scalar(
            select(Connection).where(
                Connection.id == connection_id,
                Connection.owner_id == owner,
            )
        )
        if connection is None:
            raise not_found()
        if not connection.active:
            raise CoworkerError(
                "connection_removed",
                "The connected service is no longer available.",
                409,
            )
        if connection.provider != provider:
            raise CoworkerError(
                "transaction_provider_mismatch",
                "The transaction provider must match the server-owned connection.",
                409,
            )
        return connection.id, connection.subject

    def _dto(self, row: Transaction) -> dict:
        return {
            "id": row.id,
            "transaction_kind": row.transaction_kind,
            "provider": row.provider,
            "connection_id": row.connection_id,
            "provider_account_ref": row.provider_account_ref,
            "state": row.state,
            "revision": row.revision,
            "currency": row.currency,
            "counterparty": row.counterparty,
            "expires_at": iso(row.expires_at) if row.expires_at is not None else None,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
        }

    def create(
        self,
        owner: str,
        draft: TransactionDraft,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        transaction_kind = self._safe_kind(draft.transaction_kind)
        provider = self._safe_provider(draft.provider)
        currency = self._normalize_currency(draft.currency)
        canonical = {
            "transaction_kind": transaction_kind,
            "provider": provider,
            "connection_id": draft.connection_id,
            "currency": currency,
            "counterparty": draft.counterparty,
            "expires_at": draft.expires_at.isoformat() if draft.expires_at else None,
        }
        fingerprint = self._fingerprint(canonical)
        with self.sessions.begin() as db:
            if db.scalar(
                select(Account.id).where(Account.id == owner).with_for_update()
            ) is None:
                raise not_found()
            previous = db.scalar(
                select(Transaction).where(
                    Transaction.owner_id == owner,
                    Transaction.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if previous.fingerprint != fingerprint:
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different transaction intent.",
                        409,
                    )
                return self._dto(previous), False

            connection_id, provider_account_ref = self._connection_identity(
                db,
                owner,
                draft.connection_id,
                provider,
            )
            now = utcnow()
            row = Transaction(
                id=str(uuid4()),
                owner_id=owner,
                workspace_id=self._workspace(db, owner),
                connection_id=connection_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                transaction_kind=transaction_kind,
                provider=provider,
                provider_account_ref=provider_account_ref,
                state="draft",
                revision=1,
                currency=currency,
                counterparty=draft.counterparty,
                expires_at=draft.expires_at,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            self._record_revision(db, row)
            self._record_event(db, row, "transaction_created")
            self._audit(db, owner, row.id, "transaction_created")
            return self._dto(row), True

    def list(self, owner: str, limit: int = 100) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            rows = db.scalars(
                select(Transaction)
                .where(Transaction.owner_id == owner)
                .order_by(Transaction.updated_at.desc())
                .limit(max(1, min(limit, 100)))
            ).all()
            return [self._dto(row) for row in rows]

    def get(self, owner: str, transaction_id: str) -> dict:
        self._require_enabled()
        with self.sessions() as db:
            return self._dto(self._transaction(db, owner, transaction_id))

    def revisions(self, owner: str, transaction_id: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            self._transaction(db, owner, transaction_id)
            rows = db.scalars(
                select(TransactionRevision)
                .where(
                    TransactionRevision.transaction_id == transaction_id,
                    TransactionRevision.owner_id == owner,
                )
                .order_by(TransactionRevision.revision)
            ).all()
            return [
                {
                    "revision": row.revision,
                    "snapshot": dict(row.snapshot),
                    "created_at": iso(row.created_at),
                }
                for row in rows
            ]

    def events(self, owner: str, transaction_id: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            self._transaction(db, owner, transaction_id)
            rows = db.scalars(
                select(TransactionEvent)
                .where(
                    TransactionEvent.transaction_id == transaction_id,
                    TransactionEvent.owner_id == owner,
                )
                .order_by(TransactionEvent.sequence)
            ).all()
            return [
                {
                    "sequence": row.sequence,
                    "revision": row.revision,
                    "state": row.state,
                    "event_type": row.event_type,
                    "details": dict(row.details or {}),
                    "created_at": iso(row.created_at),
                }
                for row in rows
            ]

    @staticmethod
    def _check_revision(row: Transaction, expected_revision: int) -> None:
        if row.revision != expected_revision:
            raise CoworkerError(
                "transaction_revision_conflict",
                "This transaction changed. Review the latest revision before continuing.",
                409,
            )

    def transition(
        self,
        owner: str,
        transaction_id: str,
        expected_revision: int,
        target: TransactionState,
    ) -> dict:
        self._require_enabled()
        if target not in TRANSACTION_STATES:
            raise CoworkerError(
                "transaction_state_invalid",
                "The requested transaction state is invalid.",
                409,
            )
        if target in RESERVED_EXECUTION_STATES:
            raise CoworkerError(
                "transaction_execution_boundary",
                "This state requires a separately reviewed approval/execution contract.",
                409,
            )
        with self.sessions.begin() as db:
            row = self._transaction(db, owner, transaction_id, lock=True)
            self._check_revision(row, expected_revision)
            allowed = SAFE_DOMAIN_TRANSITIONS.get(row.state, frozenset())
            if target not in allowed:
                raise CoworkerError(
                    "transaction_transition_invalid",
                    f"Transaction state {row.state!r} cannot transition to {target!r}.",
                    409,
                )
            row.state = target
            row.revision += 1
            row.updated_at = utcnow()
            self._record_revision(db, row)
            self._record_event(
                db,
                row,
                "transaction_state_changed",
                details={"target": target},
            )
            self._audit(db, owner, row.id, f"transaction_{target}")
            return self._dto(row)
