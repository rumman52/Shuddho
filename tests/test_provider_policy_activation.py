from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for provider policy activation tests")

from scripts.provider_policy_activation import (
    ProviderPolicyActivationError,
    build_evidence,
    require_deployed_policy,
    validate_deployment,
    validate_operator_status,
    validate_policy,
    validate_runtime_snapshot,
)


NOW = datetime(2026, 9, 22, 13, 30, tzinfo=timezone.utc)


def policy():
    return {
        "decision": "ELIGIBLE_FOR_POLICY_REVIEW",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "proposed_stage": "cohort-40",
        "proposed_max_users": 40,
        "failures": [],
        "generated_at": "2026-09-22T13:00:00+00:00",
        "proposed_policy": {
            "provider_max_concurrent_calls": 12,
            "provider_max_concurrent_per_workspace": 3,
            "provider_max_reserved_tokens": 1200000,
            "provider_max_reserved_tokens_per_workspace": 300000,
            "provider_daily_token_budget": 7500000,
            "daily_token_budget": 375000,
            "provider_lease_seconds": 120,
        },
    }


def settings(**overrides):
    values = dict(policy()["proposed_policy"])
    values.update(overrides)
    return SimpleNamespace(**values)


def operator():
    return {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T13:20:00+00:00",
        "breaches": [],
    }


def test_provider_policy_activation_accepts_exact_deployed_policy():
    validate_policy(policy())
    actual = require_deployed_policy(settings(), policy())
    assert actual == policy()["proposed_policy"]
    validate_runtime_snapshot({
        "active_calls": 4,
        "reserved_tokens": 250000,
        "daily_allocated_tokens": 900000,
    }, policy())


def test_provider_policy_activation_rejects_setting_drift():
    with pytest.raises(ProviderPolicyActivationError, match="provider_max_concurrent_calls"):
        require_deployed_policy(
            settings(provider_max_concurrent_calls=13),
            policy(),
        )


def test_provider_policy_activation_rejects_runtime_over_budget():
    with pytest.raises(ProviderPolicyActivationError, match="daily budget"):
        validate_runtime_snapshot({
            "active_calls": 4,
            "reserved_tokens": 250000,
            "daily_allocated_tokens": 8000000,
        }, policy())


def test_provider_policy_activation_requires_post_deploy_health():
    with pytest.raises(ProviderPolicyActivationError, match="after the provider policy deployment"):
        validate_operator_status(
            operator(),
            "coworker-cohort-001",
            not_before=datetime(2026, 9, 22, 13, 25, tzinfo=timezone.utc),
            freshness_minutes=30,
            now=NOW,
        )


def test_provider_policy_deployment_binds_exact_policy(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text("{}", encoding="utf-8")
    deployment = {
        "release_id": "coworker-cohort-001",
        "change_reference": "policy-change-1",
        "deployed_at": "2026-09-22T13:10:00+00:00",
        "current_stage": "cohort-25",
        "proposed_stage": "cohort-40",
        "provider_policy_sha256": __import__("hashlib").sha256(b"{}").hexdigest(),
    }
    result = validate_deployment(
        deployment,
        policy(),
        path,
        not_before=datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc),
    )
    assert result == datetime(2026, 9, 22, 13, 10, tzinfo=timezone.utc)


def test_provider_policy_evidence_contains_no_credentials(tmp_path):
    policy_path = tmp_path / "policy.json"
    deploy_path = tmp_path / "deploy.json"
    status_path = tmp_path / "status.json"
    for path in (policy_path, deploy_path, status_path):
        path.write_text("{}", encoding="utf-8")
    deployment = {
        "change_reference": "policy-change-1",
        "deployed_at": "2026-09-22T13:10:00+00:00",
    }
    value = build_evidence(
        policy=policy(),
        deployment=deployment,
        operator_status=operator(),
        actual_policy=policy()["proposed_policy"],
        runtime_snapshot={
            "active_calls": 1,
            "reserved_tokens": 100000,
            "daily_allocated_tokens": 500000,
        },
        policy_path=policy_path,
        deployment_path=deploy_path,
        operator_status_path=status_path,
        now=NOW,
    )
    encoded = str(value).lower()
    assert value["status"] == "provider_policy_verified"
    assert "api_key" not in encoded
    assert "account_id" not in encoded
