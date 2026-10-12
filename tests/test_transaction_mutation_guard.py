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
