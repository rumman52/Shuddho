from dataclasses import FrozenInstanceError
from concurrent.futures import ThreadPoolExecutor

import pytest

from services.coworker.transaction_mutation_guard import (
    DuplicateMutationAttempt,
    TransactionMutationGuard,
)


def test_execution_identity_allows_single_provider_mutation():
    guard = TransactionMutationGuard()

    guard.reserve_mutation("exec-1", "sandbox")

    try:
        guard.reserve_mutation("exec-1", "sandbox")
        assert False
    except DuplicateMutationAttempt:
        assert True


def test_receipt_binds_to_execution_identity():
    guard = TransactionMutationGuard()

    guard.reserve_mutation("exec-2", "sandbox")
    record = guard.attach_receipt("exec-2", "receipt-sha")

    assert record.receipt_hash == "receipt-sha"


def test_tx04_receipt_binding_does_not_change_after_first_verified_receipt():
    guard = TransactionMutationGuard()
    guard.reserve_mutation("exec-receipt", "sandbox")
    first = guard.attach_receipt("exec-receipt", "receipt-original")
    replay = guard.attach_receipt("exec-receipt", "receipt-original")
    assert replay == first
    with pytest.raises(ValueError, match="receipt"):
        guard.attach_receipt("exec-receipt", "receipt-forged")
    assert guard.get("exec-receipt").receipt_hash == "receipt-original"
    assert guard.get("exec-receipt").attempts == 1


def test_tx04_callers_cannot_rewrite_reserved_execution_or_receipt():
    guard = TransactionMutationGuard()
    exposed = guard.reserve_mutation("exec-read", "sandbox")
    with pytest.raises(FrozenInstanceError):
        exposed.attempts = 0
    with pytest.raises(FrozenInstanceError):
        exposed.provider = "impostor"
    guard.attach_receipt("exec-read", "receipt-real")
    with pytest.raises(FrozenInstanceError):
        guard.get("exec-read").receipt_hash = "receipt-fake"
    assert guard.get("exec-read").receipt_hash == "receipt-real"


def test_tx04_concurrent_duplicate_reservations_allow_one_mutation():
    guard = TransactionMutationGuard()
    def reserve():
        try:
            guard.reserve_mutation("exec-race", "sandbox")
            return "reserved"
        except DuplicateMutationAttempt:
            return "duplicate"
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(lambda _: reserve(), range(60)))
    assert outcomes.count("reserved") == 1
    assert outcomes.count("duplicate") == 59
    assert guard.get("exec-race").attempts == 1
