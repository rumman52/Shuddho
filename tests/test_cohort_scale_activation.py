from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for scale activation tests")
pytest.importorskip("jwt", reason="Install the coworker extra for scale activation tests")

from scripts.cohort_scale_activation import (
    ScaleActivationError,
    build_evidence,
    require_deployed_configuration,
    validate_deployment_change,
    validate_operator_status,
    validate_provider_policy_activation,
    validate_scale_decision,
)


NOW = datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc)


def decision():
    return {
        "decision": "ELIGIBLE_FOR_BOUNDED_EXPANSION",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "current_max_users": 25,
        "proposed_stage": "cohort-40",
        "proposed_max_users": 40,
        "failures": [],
        "generated_at": "2026-09-22T12:00:00+00:00",
        "references": {"change_reference": "change-42"},
    }


def deployment():
    return {
        "release_id": "coworker-cohort-001",
        "change_reference": "change-42",
        "deployed_at": "2026-09-22T12:10:00+00:00",
        "stage": "cohort-40",
        "max_users": 40,
    }


def operator():
    return {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T12:20:00+00:00",
        "breaches": [],
    }


def settings(*, members=30, max_users=40, enforced=True, allowed="a", denied="b"):
    ids = {allowed}
    ids.update(f"member-{index}" for index in range(max(0, members - 1)))
    if denied in ids:
        ids.remove(denied)
    return SimpleNamespace(
        cohort_enforced=enforced,
        cohort_account_ids=frozenset(ids),
        cohort_max_users=max_users,
    )


def test_scale_activation_accepts_reviewed_deployment_shape():
    reviewed_at = validate_scale_decision(decision())
    deployed_at = validate_deployment_change(deployment(), decision(), not_before=reviewed_at)
    generated = validate_operator_status(
        operator(),
        decision(),
        not_before=deployed_at,
        freshness_minutes=30,
        now=NOW,
    )
    assert generated.isoformat() == "2026-09-22T12:20:00+00:00"
    require_deployed_configuration(settings(), decision(), "a", "b")


def test_scale_activation_rejects_wrong_deployed_ceiling():
    with pytest.raises(ScaleActivationError, match="max"):
        require_deployed_configuration(settings(max_users=41), decision(), "a", "b")


def test_scale_activation_requires_real_membership_expansion():
    with pytest.raises(ScaleActivationError, match="has not expanded"):
        require_deployed_configuration(settings(members=25), decision(), "a", "b")


def test_scale_activation_rejects_unreviewed_or_oversized_membership():
    with pytest.raises(ScaleActivationError, match="exceeds"):
        require_deployed_configuration(settings(members=41), decision(), "a", "b")


def test_scale_activation_requires_post_deploy_health():
    value = operator()
    value["generated_at"] = "2026-09-22T12:05:00+00:00"
    with pytest.raises(ScaleActivationError, match="after the deployment"):
        validate_operator_status(
            value,
            decision(),
            not_before=datetime(2026, 9, 22, 12, 10, tzinfo=timezone.utc),
            freshness_minutes=30,
            now=NOW,
        )


def test_scale_activation_rejects_wrong_change_reference():
    value = deployment()
    value["change_reference"] = "other-change"
    with pytest.raises(ScaleActivationError, match="reference"):
        validate_deployment_change(
            value,
            decision(),
            not_before=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        )


def test_activation_evidence_contains_only_aggregate_cohort_state(tmp_path):
    scale_path = tmp_path / "scale.json"
    deploy_path = tmp_path / "deploy.json"
    status_path = tmp_path / "status.json"
    policy_activation_path = tmp_path / "policy-activation.json"
    scale_path.write_text("{}", encoding="utf-8")
    deploy_path.write_text("{}", encoding="utf-8")
    status_path.write_text("{}", encoding="utf-8")
    policy_activation_path.write_text("{}", encoding="utf-8")
    value = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(members=30),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_activation_path,
        now=NOW,
    )
    assert value["status"] == "bounded_expansion_verified"
    assert value["configured_members"] == 30
    encoded = str(value)
    assert "member-1" not in encoded
    assert "cohort_account_ids" not in encoded


def test_scale_activation_requires_ledgered_provider_policy(monkeypatch, tmp_path):
    from scripts.cohort_release_ledger import (
        append_event,
        append_provider_policy_event,
        file_sha256,
    )
    import json

    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "k" * 32)
    ledger = tmp_path / "ledger.jsonl"

    rollout = tmp_path / "rollout.json"
    plan_path = tmp_path / "plan.json"
    progression = tmp_path / "progression.json"
    base_status = tmp_path / "base-status.json"
    rollout.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    }), encoding="utf-8")
    plan_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "cohort-25"}],
    }), encoding="utf-8")
    progression.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "HOLD",
        "current_stage": "cohort-25",
        "next_stage": None,
        "reasons": ["final_stage_reached"],
    }), encoding="utf-8")
    base_status.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    }), encoding="utf-8")
    append_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        event_type="hold",
        actor_reference="oncall",
        change_reference="cohort-25-hold",
        current_stage="cohort-25",
        next_stage=None,
        rollout=rollout,
        canary_plan=plan_path,
        progression_decision=progression,
        operator_status=base_status,
    )

    policy = tmp_path / "policy.json"
    deployment_path = tmp_path / "policy-deploy.json"
    status_path = tmp_path / "policy-status.json"
    activation_path = tmp_path / "policy-activation.json"
    policy.write_text(json.dumps({
        "decision": "ELIGIBLE_FOR_POLICY_REVIEW",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "proposed_stage": "cohort-40",
        "failures": [],
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "policy-change",
        "current_stage": "cohort-25",
        "proposed_stage": "cohort-40",
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    }), encoding="utf-8")
    activation_path.write_text(json.dumps({
        "status": "provider_policy_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "proposed_stage": "cohort-40",
        "change_reference": "policy-change",
        "artifact_sha256": {
            "provider_policy": file_sha256(policy),
            "deployment_change": file_sha256(deployment_path),
            "operator_status": file_sha256(status_path),
        },
    }), encoding="utf-8")

    with pytest.raises(ScaleActivationError, match="provider_policy_verified"):
        validate_provider_policy_activation(
            activation_path,
            ledger,
            decision(),
        )

    append_provider_policy_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="policy-change",
        current_stage="cohort-25",
        next_stage="cohort-40",
        provider_policy=policy,
        deployment_change=deployment_path,
        operator_status=status_path,
        policy_activation=activation_path,
    )
    value = validate_provider_policy_activation(
        activation_path,
        ledger,
        decision(),
    )
    assert value["status"] == "provider_policy_verified"
