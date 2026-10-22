"""Regression: activation manifests must match JSON types, not just Python ==.

JSON true/false and JSON numbers are distinct even though Python considers
True == 1, False == 0 and 25 == 25.0. A runtime cannot substitute
numeric flags or schema versions for reviewed release evidence.
"""
from __future__ import annotations

import copy

import pytest

from scripts.transaction_capability_activation import (
    TransactionCapabilityActivationError,
    validate_runtime_manifest,
    validate_transaction_authority,
)

REVISION = "a" * 40
OPERATION = "opentable:restaurant_reservation_create"


def reviewed():
    return {
        "environment": "production",
        "capabilities": {
            "actions": True,
            "connector_trust_boundary": True,
            "personal_transactions": True,
            "restaurant_reservations": True,
            "shopping_checkout": False,
            "travel_booking": False,
        },
        "action_providers": ["google", "opentable"],
        "transaction_operations": [OPERATION],
        "cohort_max_users": 25,
    }


def runtime(rollout):
    return {
        "schema_version": 1,
        "source_revision": REVISION,
        "environment": rollout["environment"],
        "capabilities": copy.deepcopy(rollout["capabilities"]),
        "action_providers": list(rollout["action_providers"]),
        "cohort": {
            "enforced": True,
            "configured_members": 1,
            "max_users": rollout["cohort_max_users"],
        },
    }


def authority(rollout):
    return {
        "schema_version": 2,
        "source_revision": REVISION,
        "personal_transactions_enabled": True,
        "restaurant_reservations_enabled": True,
        "shopping_checkout_enabled": False,
        "travel_booking_enabled": False,
        "operations": list(rollout["transaction_operations"]),
    }


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("schema_version", True), ("schema_version", 1.0)],
)
def test_runtime_rejects_noninteger_schema_version(field, replacement):
    rollout = reviewed()
    evidence = runtime(rollout)
    evidence[field] = replacement
    with pytest.raises(TransactionCapabilityActivationError):
        validate_runtime_manifest(
            evidence, deployment={"source_revision": REVISION}, rollout=rollout
        )


@pytest.mark.parametrize(
    ("flag", "replacement"),
    [
        ("actions", 1),
        ("restaurant_reservations", 1),
        ("shopping_checkout", 0),
        ("travel_booking", 0),
    ],
)
def test_runtime_rejects_numeric_substitution_for_capability_boolean(flag, replacement):
    rollout = reviewed()
    evidence = runtime(rollout)
    evidence["capabilities"][flag] = replacement
    with pytest.raises(TransactionCapabilityActivationError):
        validate_runtime_manifest(
            evidence, deployment={"source_revision": REVISION}, rollout=rollout
        )


@pytest.mark.parametrize("replacement", [25.0, "25"])
def test_runtime_rejects_nonnative_cohort_max_users(replacement):
    rollout = reviewed()
    evidence = runtime(rollout)
    evidence["cohort"]["max_users"] = replacement
    with pytest.raises(TransactionCapabilityActivationError):
        validate_runtime_manifest(
            evidence, deployment={"source_revision": REVISION}, rollout=rollout
        )


def test_runtime_rejects_boolean_cohort_max_users():
    rollout = reviewed()
    rollout["cohort_max_users"] = 1
    evidence = runtime(rollout)
    evidence["cohort"]["max_users"] = True
    with pytest.raises(TransactionCapabilityActivationError):
        validate_runtime_manifest(
            evidence, deployment={"source_revision": REVISION}, rollout=rollout
        )


def test_authority_rejects_float_schema_version():
    rollout = reviewed()
    evidence = authority(rollout)
    evidence["schema_version"] = 2.0
    with pytest.raises(TransactionCapabilityActivationError):
        validate_transaction_authority(
            evidence,
            deployment={"source_revision": REVISION},
            rollout=rollout,
            capability="restaurant_reservations",
        )


def test_correctly_typed_activation_manifests_remain_accepted():
    rollout = reviewed()
    assert validate_runtime_manifest(
        runtime(rollout),
        deployment={"source_revision": REVISION},
        rollout=rollout,
    )["schema_version"] == 1
    assert validate_transaction_authority(
        authority(rollout),
        deployment={"source_revision": REVISION},
        rollout=rollout,
        capability="restaurant_reservations",
    )["schema_version"] == 2
