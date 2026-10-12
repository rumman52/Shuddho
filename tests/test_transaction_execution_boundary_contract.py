"""Transaction safety boundary contracts.

These regressions ensure transaction state cannot become a provider mutation
path without going through ExternalAction.
"""

from services.coworker.transaction_repository import SAFE_DOMAIN_TRANSITIONS


def test_safe_transaction_domain_states_do_not_enter_execution_states():
    execution_states = {
        "approved",
        "executing",
        "confirmed",
        "failed",
        "outcome_unknown",
    }

    for source, targets in SAFE_DOMAIN_TRANSITIONS.items():
        assert not execution_states.intersection(targets), (
            source,
            targets,
        )


def test_transaction_execution_boundary_is_explicit():
    # Execution ownership remains with ExternalAction. TransactionRepository
    # only advances review/domain intent states.
    assert "awaiting_approval" in SAFE_DOMAIN_TRANSITIONS
    assert "approved" not in SAFE_DOMAIN_TRANSITIONS["awaiting_approval"]
