"""Transaction provider mutation safety guard.

Prevents duplicate provider mutations for the same approved execution identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


class DuplicateMutationAttempt(Exception):
    """Raised when an execution identity attempts a second mutation."""


@dataclass
class MutationRecord:
    execution_identity: str
    provider: str
    attempts: int = 0
    receipt_hash: str | None = None


class TransactionMutationGuard:
    """In-memory qualification guard.

    Production persistence should be backed by the transaction ledger. This
    class defines the invariant and is used by provider adapters/tests.
    """

    def __init__(self):
        self._records: dict[str, MutationRecord] = {}
        self._lock = Lock()

    def reserve_mutation(self, execution_identity: str, provider: str) -> MutationRecord:
        with self._lock:
            existing = self._records.get(execution_identity)
            if existing is not None:
                raise DuplicateMutationAttempt(execution_identity)

            record = MutationRecord(
                execution_identity=execution_identity,
                provider=provider,
                attempts=1,
            )
            self._records[execution_identity] = record
            return record

    def attach_receipt(self, execution_identity: str, receipt_hash: str) -> MutationRecord:
        with self._lock:
            record = self._records[execution_identity]
            record.receipt_hash = receipt_hash
            return record

    def get(self, execution_identity: str) -> MutationRecord | None:
        return self._records.get(execution_identity)
