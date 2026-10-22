"""Transaction activation must not authorize runtime flags beyond reviewed scope.

A passing test only proves the local release contract, not provider or staging qualification.
"""
from __future__ import annotations

import pytest

from scripts.transaction_capability_activation import (
    CAPABILITIES,
    TransactionCapabilityActivationError,
    validate_transaction_authority,
)

REVISION = "a" * 40
OPERATIONS = ["opentable:restaurant_reservation_create"]


def _case(selected: str, *, extra_enabled: tuple[str, ...] = ()):
    approved = {name: name == selected or name in extra_enabled for name in CAPABILITIES}
    reviewed = {
        "capabilities": {"personal_transactions": True, **approved},
        "transaction_operations": OPERATIONS,
    }
    authority = {
        "schema_version": 2,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "operations": OPERATIONS,
        **{spec["flag"]: approved[name] for name, spec in CAPABILITIES.items()},
    }
    return reviewed, authority


@pytest.mark.parametrize(
    ("selected", "unreviewed"),
    [
        (selected, other)
        for selected in CAPABILITIES
        for other in CAPABILITIES
        if other != selected
    ],
)
def test_unreviewed_additional_runtime_transaction_flag_is_rejected(selected, unreviewed):
    reviewed, authority = _case(selected)
    authority[CAPABILITIES[unreviewed]["flag"]] = True
    with pytest.raises(TransactionCapabilityActivationError, match="reviewed capability"):
        validate_transaction_authority(
            authority,
            deployment={"source_revision": REVISION},
            rollout=reviewed,
            capability=selected,
        )


@pytest.mark.parametrize("untrusted", [1, "true", None])
def test_runtime_flag_cannot_use_truthy_or_missing_nonboolean(untrusted):
    reviewed, authority = _case("restaurant_reservations")
    authority["shopping_checkout_enabled"] = untrusted
    with pytest.raises(TransactionCapabilityActivationError, match="reviewed capability"):
        validate_transaction_authority(
            authority,
            deployment={"source_revision": REVISION},
            rollout=reviewed,
            capability="restaurant_reservations",
        )


def test_explicitly_reviewed_multiple_transaction_capabilities_remain_valid():
    reviewed, authority = _case(
        "restaurant_reservations", extra_enabled=("shopping_checkout",)
    )
    assert (
        validate_transaction_authority(
            authority,
            deployment={"source_revision": REVISION},
            rollout=reviewed,
            capability="restaurant_reservations",
        )
        == authority
    )


def test_missing_target_approval_is_not_restored_by_runtime_self_report():
    reviewed, authority = _case("restaurant_reservations")
    reviewed["capabilities"]["restaurant_reservations"] = False
    with pytest.raises(TransactionCapabilityActivationError, match="reviewed capability"):
        validate_transaction_authority(
            authority,
            deployment={"source_revision": REVISION},
            rollout=reviewed,
            capability="restaurant_reservations",
        )
