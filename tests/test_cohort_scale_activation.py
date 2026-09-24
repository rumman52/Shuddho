from datetime import datetime, timezone
from types import SimpleNamespace

import hashlib
import pytest
import json

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for scale activation tests")
pytest.importorskip("jwt", reason="Install the coworker extra for scale activation tests")

from scripts.cohort_scale_activation import (
    ScaleActivationError,
    build_evidence,
    require_deployed_configuration,
    validate_deployment_change,
    validate_operator_status,
    validate_provider_policy_activation,
    validate_microsoft_rollout_activation,
    validate_action_selection_activation,
    validate_action_proposals_activation,
    validate_action_attachments_activation,
    validate_action_recipients_activation,
    validate_action_document_sharing_activation,
    validate_action_email_threading_activation,
    validate_action_social_publishing_activation,
    validate_agent_linkedin_proposals_activation,
    validate_release_activation_bundle,
    validate_scale_decision,
    sha256_file,
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


def settings(*, members=30, max_users=40, enforced=True, allowed="a", denied="b", microsoft=False, action_selection=False, action_proposals=False, action_attachments=False, action_reminders=False, action_recipients=False, action_document_sharing=False, action_email_threading=False, action_social_publishing=False, agent_linkedin_proposals=False):
    ids = {allowed}
    ids.update(f"member-{index}" for index in range(max(0, members - 1)))
    if denied in ids:
        ids.remove(denied)
    return SimpleNamespace(
        cohort_enforced=enforced,
        cohort_account_ids=frozenset(ids),
        cohort_max_users=max_users,
        microsoft_actions_enabled=microsoft,
        agent_action_selection_enabled=action_selection,
        agent_action_proposals_enabled=action_proposals,
        action_attachments_enabled=action_attachments,
        action_reminders_enabled=action_reminders,
        action_recipients_enabled=action_recipients,
        action_document_sharing_enabled=action_document_sharing,
        action_email_threading_enabled=action_email_threading,
        action_social_publishing_enabled=action_social_publishing,
        agent_linkedin_proposals_enabled=agent_linkedin_proposals,
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


def microsoft_activation_file(tmp_path):
    path = tmp_path / "microsoft-rollout-activation.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "status": "microsoft_rollout_verified",
        "release_id": "coworker-cohort-001",
        "verified_at": "2026-09-22T12:00:00+00:00",
        "change_reference": "microsoft-change-1",
        "deployed_at": "2026-09-22T11:50:00+00:00",
        "frontend_base_url": "https://staging.example.com",
        "frontend_source_revision": "abcdef1234567",
        "backend": {
            "actions_enabled": True,
            "microsoft_actions_enabled": True,
        },
        "frontend": {
            "coworker_enabled": True,
            "microsoft_actions_enabled": True,
        },
        "artifact_sha256": {
            "staging_evidence": "a" * 64,
            "operator_status": "b" * 64,
        },
    }), encoding="utf-8")
    return path


def seed_microsoft_rollout_ledger(monkeypatch, tmp_path, activation_path):
    from scripts.cohort_release_ledger import (
        append_event,
        append_microsoft_rollout_event,
        file_sha256,
    )
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "k" * 32)
    ledger = tmp_path / "microsoft-ledger.jsonl"

    rollout = tmp_path / "microsoft-base-rollout.json"
    plan_path = tmp_path / "microsoft-plan.json"
    progression = tmp_path / "microsoft-progression.json"
    base_status = tmp_path / "microsoft-base-status.json"
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
    }), encoding="utf-8")
    base_status.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
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

    staging = tmp_path / "microsoft-staging.json"
    deployment_path = tmp_path / "microsoft-deploy.json"
    status_path = tmp_path / "microsoft-status.json"
    staging.write_text(json.dumps({
        "microsoft_actions": {
            "status": "passed",
            "evidence": "live Microsoft actions passed",
            "verified_at": "2026-09-22T11:40:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "microsoft-change-1",
        "deployed_at": "2026-09-22T11:50:00+00:00",
        "frontend_base_url": "https://staging.example.com",
        "frontend_source_revision": "abcdef1234567",
        "staging_evidence_sha256": file_sha256(staging),
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T11:55:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["artifact_sha256"] = {
        "staging_evidence": file_sha256(staging),
        "operator_status": file_sha256(status_path),
    }
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    append_microsoft_rollout_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="microsoft-change-1",
        current_stage="cohort-25",
        staging_evidence=staging,
        deployment_change=deployment_path,
        operator_status=status_path,
        rollout_activation=activation_path,
    )
    return ledger


def test_google_only_scale_activation_does_not_require_microsoft_proof(tmp_path):
    missing = tmp_path / "missing.json"
    assert validate_microsoft_rollout_activation(
        missing,
        tmp_path / "missing-ledger.jsonl",
        decision(),
        settings(microsoft=False),
    ) is None


def test_microsoft_enabled_scale_activation_requires_argument(tmp_path):
    with pytest.raises(ScaleActivationError, match="required"):
        validate_microsoft_rollout_activation(
            None,
            tmp_path / "ledger.jsonl",
            decision(),
            settings(microsoft=True),
        )


def test_microsoft_enabled_scale_activation_requires_matching_schema_v6(monkeypatch, tmp_path):
    activation = microsoft_activation_file(tmp_path)
    ledger = seed_microsoft_rollout_ledger(monkeypatch, tmp_path, activation)
    value = validate_microsoft_rollout_activation(
        activation,
        ledger,
        decision(),
        settings(microsoft=True),
    )
    assert value["status"] == "microsoft_rollout_verified"

    changed = json.loads(activation.read_text(encoding="utf-8"))
    changed["verified_at"] = "2026-09-22T12:01:00+00:00"
    activation.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ScaleActivationError, match="schema-v6"):
        validate_microsoft_rollout_activation(
            activation,
            ledger,
            decision(),
            settings(microsoft=True),
        )


def test_activation_evidence_binds_microsoft_proof_only_when_enabled(tmp_path):
    scale_path = tmp_path / "scale.json"
    deploy_path = tmp_path / "deploy.json"
    status_path = tmp_path / "status.json"
    policy_path = tmp_path / "policy.json"
    microsoft_path = tmp_path / "microsoft.json"
    for path in (scale_path, deploy_path, status_path, policy_path, microsoft_path):
        path.write_text("{}", encoding="utf-8")

    google_only = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(microsoft=False),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        microsoft_rollout_activation_path=None,
        now=NOW,
    )
    assert "microsoft_rollout_activation" not in google_only["artifact_sha256"]

    microsoft = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(microsoft=True),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        microsoft_rollout_activation_path=microsoft_path,
        now=NOW,
    )
    assert "microsoft_rollout_activation" in microsoft["artifact_sha256"]


def action_selection_activation_file(tmp_path):
    path = tmp_path / "action-selection-activation.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "status": "action_selection_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "verified_at": "2026-09-22T12:00:00+00:00",
        "change_reference": "action-selection-change-1",
        "deployed_at": "2026-09-22T11:50:00+00:00",
        "operator_status_generated_at": "2026-09-22T11:55:00+00:00",
        "runtime": {
            "coworker_enabled": True,
            "agent_runtime_enabled": True,
            "intelligent_planner_enabled": True,
            "actions_enabled": True,
            "action_selection_enabled": True,
            "cohort_enforced": True,
            "cohort_members_configured": 25,
            "cohort_max_users": 25,
        },
        "artifact_sha256": {
            "staging_evidence": "a" * 64,
            "deployment_change": "b" * 64,
            "operator_status": "c" * 64,
        },
    }), encoding="utf-8")
    return path


def seed_action_selection_ledger(monkeypatch, tmp_path, activation_path):
    from scripts.cohort_release_ledger import (
        append_action_selection_event,
        append_event,
        file_sha256,
    )
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "k" * 32)
    ledger = tmp_path / "action-selection-ledger.jsonl"

    rollout_path = tmp_path / "action-selection-rollout.json"
    plan_path = tmp_path / "action-selection-plan.json"
    progression_path = tmp_path / "action-selection-progression.json"
    base_status_path = tmp_path / "action-selection-base-status.json"
    rollout_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    }), encoding="utf-8")
    plan_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "cohort-25"}],
    }), encoding="utf-8")
    progression_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "HOLD",
        "current_stage": "cohort-25",
        "next_stage": None,
    }), encoding="utf-8")
    base_status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
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
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression_path,
        operator_status=base_status_path,
    )

    staging_path = tmp_path / "action-selection-staging.json"
    deployment_path = tmp_path / "action-selection-deployment.json"
    status_path = tmp_path / "action-selection-status.json"
    staging_path.write_text(json.dumps({
        "action_selection": {
            "status": "passed",
            "evidence": "live selection paused at approval",
            "verified_at": "2026-09-22T11:40:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "action-selection-change-1",
        "current_stage": "cohort-25",
        "deployed_at": "2026-09-22T11:50:00+00:00",
        "staging_evidence_sha256": file_sha256(staging_path),
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T11:55:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["artifact_sha256"] = {
        "staging_evidence": file_sha256(staging_path),
        "deployment_change": file_sha256(deployment_path),
        "operator_status": file_sha256(status_path),
    }
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    entry = append_action_selection_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="action-selection-change-1",
        current_stage="cohort-25",
        staging_evidence=staging_path,
        deployment_change=deployment_path,
        operator_status=status_path,
        action_selection_activation=activation_path,
    )
    return ledger, entry


def test_action_selection_disabled_scale_does_not_require_proof(tmp_path):
    assert validate_action_selection_activation(
        tmp_path / "missing.json",
        tmp_path / "missing-ledger.jsonl",
        decision(),
        settings(action_selection=False),
    ) is None


def test_action_selection_enabled_scale_requires_exact_schema_v7(monkeypatch, tmp_path):
    activation = action_selection_activation_file(tmp_path)
    ledger, entry = seed_action_selection_ledger(
        monkeypatch,
        tmp_path,
        activation,
    )
    result = validate_action_selection_activation(
        activation,
        ledger,
        decision(),
        settings(action_selection=True),
    )
    assert result["ledger_sequence"] == entry["sequence"]
    assert result["ledger_entry_hash"] == entry["entry_hash"]

    changed = json.loads(activation.read_text(encoding="utf-8"))
    changed["verified_at"] = "2026-09-22T12:01:00+00:00"
    activation.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ScaleActivationError, match="Release ledger verification failed"):
        validate_action_selection_activation(
            activation,
            ledger,
            decision(),
            settings(action_selection=True),
        )


def test_scale_v3_evidence_preserves_action_selection_attestation(tmp_path):
    scale_path = tmp_path / "scale-v2.json"
    deploy_path = tmp_path / "deploy-v2.json"
    status_path = tmp_path / "status-v2.json"
    policy_path = tmp_path / "policy-v2.json"
    action_path = tmp_path / "action-selection-v2.json"
    for item in (scale_path, deploy_path, status_path, policy_path, action_path):
        item.write_text("{}", encoding="utf-8")

    attestation = {
        "ledger_sequence": 9,
        "ledger_entry_hash": "d" * 64,
    }
    value = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(action_selection=True),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        action_selection_activation_path=action_path,
        action_selection_attestation=attestation,
        now=NOW,
    )
    assert value["schema_version"] == 3
    assert value["runtime_requirements"]["action_selection_enabled"] is True
    assert value["runtime_requirements"]["action_proposals_enabled"] is False
    assert value["action_selection"] == attestation
    assert (
        value["artifact_sha256"]["action_selection_activation"]
        == sha256_file(action_path)
    )

def action_proposals_activation_file(tmp_path):
    capabilities = {
        "coworker": True,
        "work_services": True,
        "artifact_services": True,
        "agent_runtime": True,
        "intelligent_planner": True,
        "memory": False,
        "handoffs": True,
        "multi_handoffs": True,
        "dependency_graph": True,
        "parallel_execution": True,
        "outcome_replan": True,
        "research": False,
        "actions": True,
        "action_selection": False,
        "action_proposals": True,
    }
    runtime = {
        "schema_version": 1,
        "source_revision": "a" * 40,
        "environment": "production",
        "capabilities": capabilities,
        "action_providers": ["google"],
        "cohort": {
            "enforced": True,
            "configured_members": 25,
            "max_users": 25,
        },
    }
    runtime_hash = hashlib.sha256(json.dumps(
        runtime,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    path = tmp_path / "action-proposals-scale-activation.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "status": "action_proposals_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "verified_at": "2026-09-23T05:40:00+00:00",
        "change_reference": "action-proposals-change-1",
        "deployed_at": "2026-09-23T05:30:00+00:00",
        "source_revision": "a" * 40,
        "operator_status_generated_at": "2026-09-23T05:35:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": runtime_hash,
        "artifact_sha256": {
            "staging_evidence": "a" * 64,
            "rollout_manifest": "b" * 64,
            "deployment_change": "c" * 64,
            "operator_status": "d" * 64,
        },
    }), encoding="utf-8")
    return path


def seed_action_proposals_scale_ledger(monkeypatch, tmp_path, activation_path):
    from scripts.cohort_release_ledger import (
        append_action_proposals_event,
        append_event,
        file_sha256,
    )
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "k" * 32)
    ledger = tmp_path / "action-proposals-scale-ledger.jsonl"

    rollout_path = tmp_path / "proposal-scale-rollout.json"
    plan_path = tmp_path / "proposal-scale-plan.json"
    progression_path = tmp_path / "proposal-scale-progression.json"
    base_status_path = tmp_path / "proposal-scale-base-status.json"
    capabilities = {
        "coworker": True,
        "work_services": True,
        "artifact_services": True,
        "agent_runtime": True,
        "intelligent_planner": True,
        "memory": False,
        "handoffs": True,
        "multi_handoffs": True,
        "dependency_graph": True,
        "parallel_execution": True,
        "outcome_replan": True,
        "research": False,
        "actions": True,
        "action_selection": False,
        "action_proposals": True,
    }
    rollout_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {"reference": "approved-cohort", "max_users": 25},
        "capabilities": capabilities,
        "action_providers": ["google"],
        "rollback": {
            "action_proposals_kill_switch":
                "SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false",
        },
        "incident": {"change_reference": "action-proposals-change-1"},
    }), encoding="utf-8")
    plan_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "cohort-25"}],
    }), encoding="utf-8")
    progression_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "HOLD",
        "current_stage": "cohort-25",
        "next_stage": None,
    }), encoding="utf-8")
    base_status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
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
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression_path,
        operator_status=base_status_path,
    )

    staging_path = tmp_path / "proposal-scale-staging.json"
    deployment_path = tmp_path / "proposal-scale-deployment.json"
    status_path = tmp_path / "proposal-scale-status.json"
    staging_path.write_text(json.dumps({
        "action_proposals": {
            "status": "passed",
            "evidence": "fresh inert proposal validation",
            "verified_at": "2026-09-23T05:20:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "action-proposals-change-1",
        "current_stage": "cohort-25",
        "deployed_at": "2026-09-23T05:30:00+00:00",
        "source_revision": "a" * 40,
        "staging_evidence_sha256": file_sha256(staging_path),
        "rollout_manifest_sha256": file_sha256(rollout_path),
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-23T05:35:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["artifact_sha256"] = {
        "staging_evidence": file_sha256(staging_path),
        "rollout_manifest": file_sha256(rollout_path),
        "deployment_change": file_sha256(deployment_path),
        "operator_status": file_sha256(status_path),
    }
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    entry = append_action_proposals_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="action-proposals-change-1",
        current_stage="cohort-25",
        staging_evidence=staging_path,
        rollout_manifest=rollout_path,
        deployment_change=deployment_path,
        operator_status=status_path,
        action_proposals_activation=activation_path,
    )
    return ledger, entry


def test_action_proposals_disabled_scale_does_not_require_proof(tmp_path):
    assert validate_action_proposals_activation(
        tmp_path / "missing.json",
        tmp_path / "missing-ledger.jsonl",
        decision(),
        settings(action_proposals=False),
    ) is None


def test_action_proposals_enabled_scale_requires_exact_schema_v8(monkeypatch, tmp_path):
    activation = action_proposals_activation_file(tmp_path)
    ledger, entry = seed_action_proposals_scale_ledger(
        monkeypatch,
        tmp_path,
        activation,
    )
    result = validate_action_proposals_activation(
        activation,
        ledger,
        decision(),
        settings(action_proposals=True),
    )
    assert result["ledger_sequence"] == entry["sequence"]
    assert result["ledger_entry_hash"] == entry["entry_hash"]

    changed = json.loads(activation.read_text(encoding="utf-8"))
    changed["verified_at"] = "2026-09-23T05:41:00+00:00"
    activation.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ScaleActivationError, match="Release ledger verification failed"):
        validate_action_proposals_activation(
            activation,
            ledger,
            decision(),
            settings(action_proposals=True),
        )


def test_scale_v3_evidence_binds_action_proposals_attestation(tmp_path):
    scale_path = tmp_path / "scale-v3.json"
    deploy_path = tmp_path / "deploy-v3.json"
    status_path = tmp_path / "status-v3.json"
    policy_path = tmp_path / "policy-v3.json"
    proposals_path = tmp_path / "action-proposals-v3.json"
    for item in (scale_path, deploy_path, status_path, policy_path, proposals_path):
        item.write_text("{}", encoding="utf-8")

    attestation = {
        "ledger_sequence": 10,
        "ledger_entry_hash": "e" * 64,
    }
    value = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(action_proposals=True),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        action_proposals_activation_path=proposals_path,
        action_proposals_attestation=attestation,
        now=NOW,
    )
    assert value["schema_version"] == 3
    assert value["runtime_requirements"]["action_proposals_enabled"] is True
    assert value["action_proposals"] == attestation
    assert (
        value["artifact_sha256"]["action_proposals_activation"]
        == sha256_file(proposals_path)
    )



def action_attachments_activation_file(tmp_path):
    capabilities = {
        "coworker": True,
        "work_services": True,
        "artifact_services": True,
        "agent_runtime": True,
        "intelligent_planner": True,
        "memory": False,
        "handoffs": True,
        "multi_handoffs": True,
        "dependency_graph": True,
        "parallel_execution": True,
        "outcome_replan": True,
        "research": False,
        "actions": True,
        "action_attachments": True,
        "action_selection": False,
        "action_proposals": False,
    }
    runtime = {
        "schema_version": 1,
        "source_revision": "b" * 40,
        "environment": "production",
        "capabilities": capabilities,
        "action_providers": ["google"],
        "cohort": {
            "enforced": True,
            "configured_members": 25,
            "max_users": 25,
        },
    }
    path = tmp_path / "action-attachments-scale-activation.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "status": "action_attachments_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "verified_at": "2026-09-23T06:20:00+00:00",
        "change_reference": "action-attachments-change-1",
        "deployed_at": "2026-09-23T06:10:00+00:00",
        "source_revision": "b" * 40,
        "operator_status_generated_at": "2026-09-23T06:15:00+00:00",
        "runtime": runtime,
        "runtime_manifest_sha256": hashlib.sha256(json.dumps(
            runtime,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")).hexdigest(),
        "artifact_sha256": {
            "staging_evidence": "a" * 64,
            "rollout_manifest": "b" * 64,
            "deployment_change": "c" * 64,
            "operator_status": "d" * 64,
        },
    }), encoding="utf-8")
    return path


def seed_action_attachments_scale_ledger(monkeypatch, tmp_path, activation_path):
    from scripts.cohort_release_ledger import (
        append_action_attachments_event,
        append_event,
        file_sha256,
    )

    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", "k" * 32)
    ledger = tmp_path / "action-attachments-scale-ledger.jsonl"

    rollout_path = tmp_path / "attachment-scale-rollout.json"
    plan_path = tmp_path / "attachment-scale-plan.json"
    progression_path = tmp_path / "attachment-scale-progression.json"
    base_status_path = tmp_path / "attachment-scale-base-status.json"
    capabilities = {
        "coworker": True,
        "work_services": True,
        "artifact_services": True,
        "agent_runtime": True,
        "intelligent_planner": True,
        "memory": False,
        "handoffs": True,
        "multi_handoffs": True,
        "dependency_graph": True,
        "parallel_execution": True,
        "outcome_replan": True,
        "research": False,
        "actions": True,
        "action_attachments": True,
        "action_selection": False,
        "action_proposals": False,
    }
    rollout_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {"reference": "approved-cohort", "max_users": 25},
        "capabilities": capabilities,
        "action_providers": ["google"],
        "rollback": {
            "action_attachments_kill_switch":
                "SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false",
        },
        "incident": {"change_reference": "action-attachments-change-1"},
    }), encoding="utf-8")
    plan_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "cohort-25"}],
    }), encoding="utf-8")
    progression_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "HOLD",
        "current_stage": "cohort-25",
        "next_stage": None,
    }), encoding="utf-8")
    base_status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
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
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression_path,
        operator_status=base_status_path,
    )

    staging_path = tmp_path / "attachment-scale-staging.json"
    deployment_path = tmp_path / "attachment-scale-deployment.json"
    status_path = tmp_path / "attachment-scale-status.json"
    staging_path.write_text(json.dumps({
        "action_attachments": {
            "status": "passed",
            "evidence": "fresh synthetic attachment validation",
            "verified_at": "2026-09-23T06:00:00+00:00",
        },
    }), encoding="utf-8")
    deployment_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "change_reference": "action-attachments-change-1",
        "current_stage": "cohort-25",
        "deployed_at": "2026-09-23T06:10:00+00:00",
        "source_revision": "b" * 40,
        "staging_evidence_sha256": file_sha256(staging_path),
        "rollout_manifest_sha256": file_sha256(rollout_path),
    }), encoding="utf-8")
    status_path.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-23T06:15:00+00:00",
        "breaches": [],
    }), encoding="utf-8")
    value = json.loads(activation_path.read_text(encoding="utf-8"))
    value["artifact_sha256"] = {
        "staging_evidence": file_sha256(staging_path),
        "rollout_manifest": file_sha256(rollout_path),
        "deployment_change": file_sha256(deployment_path),
        "operator_status": file_sha256(status_path),
    }
    activation_path.write_text(json.dumps(value), encoding="utf-8")

    entry = append_action_attachments_event(
        ledger=ledger,
        key=b"k" * 32,
        release_id="coworker-cohort-001",
        actor_reference="oncall",
        change_reference="action-attachments-change-1",
        current_stage="cohort-25",
        staging_evidence=staging_path,
        rollout_manifest=rollout_path,
        deployment_change=deployment_path,
        operator_status=status_path,
        action_attachments_activation=activation_path,
    )
    return ledger, entry


def test_action_attachments_disabled_scale_does_not_require_proof(tmp_path):
    assert validate_action_attachments_activation(
        tmp_path / "missing.json",
        tmp_path / "missing-ledger.jsonl",
        decision(),
        settings(action_attachments=False),
    ) is None


def test_action_attachments_enabled_scale_requires_exact_schema_v9(
    monkeypatch,
    tmp_path,
):
    activation = action_attachments_activation_file(tmp_path)
    ledger, entry = seed_action_attachments_scale_ledger(
        monkeypatch,
        tmp_path,
        activation,
    )
    result = validate_action_attachments_activation(
        activation,
        ledger,
        decision(),
        settings(action_attachments=True),
    )
    assert result["ledger_sequence"] == entry["sequence"]
    assert result["ledger_entry_hash"] == entry["entry_hash"]

    changed = json.loads(activation.read_text(encoding="utf-8"))
    changed["verified_at"] = "2026-09-23T06:21:00+00:00"
    activation.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ScaleActivationError, match="Release ledger verification failed"):
        validate_action_attachments_activation(
            activation,
            ledger,
            decision(),
            settings(action_attachments=True),
        )


def test_scale_v4_evidence_binds_action_attachments_attestation(tmp_path):
    scale_path = tmp_path / "scale-v4.json"
    deploy_path = tmp_path / "deploy-v4.json"
    status_path = tmp_path / "status-v4.json"
    policy_path = tmp_path / "policy-v4.json"
    attachments_path = tmp_path / "action-attachments-v4.json"
    for item in (
        scale_path,
        deploy_path,
        status_path,
        policy_path,
        attachments_path,
    ):
        item.write_text("{}", encoding="utf-8")

    attestation = {
        "ledger_sequence": 11,
        "ledger_entry_hash": "f" * 64,
    }
    value = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(action_attachments=True),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        action_attachments_activation_path=attachments_path,
        action_attachments_attestation=attestation,
        now=NOW,
    )
    assert value["schema_version"] == 4
    assert value["runtime_requirements"]["action_attachments_enabled"] is True
    assert value["action_attachments"] == attestation
    assert (
        value["artifact_sha256"]["action_attachments_activation"]
        == sha256_file(attachments_path)
    )


def test_action_recipients_scale_activation_is_optional_when_disabled(tmp_path):
    assert validate_action_recipients_activation(
        None,
        tmp_path / "missing-ledger.jsonl",
        decision(),
        settings(action_recipients=False),
    ) is None


def test_action_recipients_scale_activation_requires_attested_activation(tmp_path):
    with pytest.raises(ScaleActivationError, match="action-recipients-activation"):
        validate_action_recipients_activation(
            None,
            tmp_path / "ledger.jsonl",
            decision(),
            settings(action_recipients=True),
        )


def test_schema_v6_scale_evidence_requires_recipient_attestation(tmp_path):
    scale_path = tmp_path / "scale-v6.json"
    deploy_path = tmp_path / "deploy-v6.json"
    status_path = tmp_path / "status-v6.json"
    policy_path = tmp_path / "policy-v6.json"
    recipient_path = tmp_path / "recipient-v6.json"
    for path in (scale_path, deploy_path, status_path, policy_path, recipient_path):
        path.write_text("{}", encoding="utf-8")

    with pytest.raises(ScaleActivationError, match="ledger attestation"):
        build_evidence(
            decision=decision(),
            deployment=deployment(),
            operator_status=operator(),
            settings=settings(action_recipients=True),
            scale_decision_path=scale_path,
            deployment_change_path=deploy_path,
            operator_status_path=status_path,
            provider_policy_activation_path=policy_path,
            action_recipients_activation_path=recipient_path,
            action_recipients_attestation=None,
            now=NOW,
        )

    evidence = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(action_recipients=True),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        action_recipients_activation_path=recipient_path,
        action_recipients_attestation={
            "ledger_sequence": 11,
            "ledger_entry_hash": "a" * 64,
        },
        now=NOW,
    )
    assert evidence["schema_version"] == 6
    assert evidence["runtime_requirements"]["action_recipients_enabled"] is True
    assert evidence["action_recipients"]["ledger_sequence"] == 11
    assert evidence["artifact_sha256"]["action_recipients_activation"] == sha256_file(recipient_path)


def test_document_sharing_scale_activation_is_optional_when_disabled(tmp_path):
    assert validate_action_document_sharing_activation(
        None,
        tmp_path / "missing-ledger.jsonl",
        decision(),
        settings(action_document_sharing=False),
    ) is None


def test_document_sharing_scale_activation_requires_attested_activation(tmp_path):
    with pytest.raises(ScaleActivationError, match="action-document-sharing-activation"):
        validate_action_document_sharing_activation(
            None,
            tmp_path / "ledger.jsonl",
            decision(),
            settings(action_document_sharing=True),
        )


def test_schema_v7_scale_evidence_requires_document_sharing_attestation(tmp_path):
    scale_path = tmp_path / "scale-v7.json"
    deploy_path = tmp_path / "deploy-v7.json"
    status_path = tmp_path / "status-v7.json"
    policy_path = tmp_path / "policy-v7.json"
    document_path = tmp_path / "document-v7.json"
    for path in (scale_path, deploy_path, status_path, policy_path, document_path):
        path.write_text("{}", encoding="utf-8")

    with pytest.raises(ScaleActivationError, match="ledger attestation"):
        build_evidence(
            decision=decision(),
            deployment=deployment(),
            operator_status=operator(),
            settings=settings(action_document_sharing=True),
            scale_decision_path=scale_path,
            deployment_change_path=deploy_path,
            operator_status_path=status_path,
            provider_policy_activation_path=policy_path,
            action_document_sharing_activation_path=document_path,
            action_document_sharing_attestation=None,
            now=NOW,
        )

    evidence = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(action_document_sharing=True),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        action_document_sharing_activation_path=document_path,
        action_document_sharing_attestation={
            "ledger_sequence": 12,
            "ledger_entry_hash": "b" * 64,
        },
        now=NOW,
    )
    assert evidence["schema_version"] == 7
    assert evidence["runtime_requirements"]["action_document_sharing_enabled"] is True
    assert evidence["runtime_requirements"]["action_recipients_enabled"] is False
    assert evidence["action_document_sharing"]["ledger_sequence"] == 12
    assert evidence["artifact_sha256"]["action_document_sharing_activation"] == sha256_file(document_path)


def test_email_threading_scale_activation_is_optional_when_disabled(tmp_path):
    assert validate_action_email_threading_activation(
        None,
        tmp_path / "missing-ledger.jsonl",
        decision(),
        settings(action_email_threading=False),
    ) is None


def test_email_threading_scale_activation_requires_attested_activation(tmp_path):
    with pytest.raises(ScaleActivationError, match="action-email-threading-activation"):
        validate_action_email_threading_activation(
            None,
            tmp_path / "ledger.jsonl",
            decision(),
            settings(action_email_threading=True),
        )


def test_schema_v8_scale_evidence_requires_email_threading_attestation(tmp_path):
    scale_path = tmp_path / "scale-v8.json"
    deploy_path = tmp_path / "deploy-v8.json"
    status_path = tmp_path / "status-v8.json"
    policy_path = tmp_path / "policy-v8.json"
    threading_path = tmp_path / "threading-v8.json"
    for path in (scale_path, deploy_path, status_path, policy_path, threading_path):
        path.write_text("{}", encoding="utf-8")

    with pytest.raises(ScaleActivationError, match="ledger attestation"):
        build_evidence(
            decision=decision(),
            deployment=deployment(),
            operator_status=operator(),
            settings=settings(action_email_threading=True),
            scale_decision_path=scale_path,
            deployment_change_path=deploy_path,
            operator_status_path=status_path,
            provider_policy_activation_path=policy_path,
            action_email_threading_activation_path=threading_path,
            action_email_threading_attestation=None,
            now=NOW,
        )

    evidence = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(action_email_threading=True),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        action_email_threading_activation_path=threading_path,
        action_email_threading_attestation={
            "ledger_sequence": 13,
            "ledger_entry_hash": "c" * 64,
        },
        now=NOW,
    )
    assert evidence["schema_version"] == 8
    assert evidence["runtime_requirements"]["action_email_threading_enabled"] is True
    assert evidence["runtime_requirements"]["action_document_sharing_enabled"] is False
    assert evidence["action_email_threading"]["ledger_sequence"] == 13
    assert evidence["artifact_sha256"]["action_email_threading_activation"] == sha256_file(threading_path)



def test_social_publishing_scale_requires_activation_and_v14_ledger(tmp_path):
    with pytest.raises(ScaleActivationError, match="required"):
        validate_action_social_publishing_activation(
            None,
            tmp_path / "ledger.jsonl",
            decision(),
            settings(action_social_publishing=True),
        )
    assert validate_action_social_publishing_activation(
        None,
        tmp_path / "ledger.jsonl",
        decision(),
        settings(action_social_publishing=False),
    ) is None


def test_linkedin_agent_proposal_scale_requires_schema_v15_activation(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    assert validate_agent_linkedin_proposals_activation(
        None,
        ledger,
        decision(),
        settings(agent_linkedin_proposals=False),
    ) is None

    with pytest.raises(ScaleActivationError, match="agent-linkedin-proposals-activation"):
        validate_agent_linkedin_proposals_activation(
            None,
            ledger,
            decision(),
            settings(
                action_proposals=True,
                action_social_publishing=True,
                agent_linkedin_proposals=True,
            ),
        )


def test_scale_v10_evidence_binds_linkedin_agent_proposal_attestation(tmp_path):
    scale_path = tmp_path / "scale-v10.json"
    deploy_path = tmp_path / "deploy-v10.json"
    status_path = tmp_path / "status-v10.json"
    policy_path = tmp_path / "policy-v10.json"
    proposals_path = tmp_path / "proposals-v10.json"
    social_path = tmp_path / "social-v10.json"
    linkedin_path = tmp_path / "linkedin-agent-v10.json"
    for item in (
        scale_path,
        deploy_path,
        status_path,
        policy_path,
        proposals_path,
        social_path,
        linkedin_path,
    ):
        item.write_text("{}", encoding="utf-8")

    evidence = build_evidence(
        decision=decision(),
        deployment=deployment(),
        operator_status=operator(),
        settings=settings(
            action_proposals=True,
            action_social_publishing=True,
            agent_linkedin_proposals=True,
        ),
        scale_decision_path=scale_path,
        deployment_change_path=deploy_path,
        operator_status_path=status_path,
        provider_policy_activation_path=policy_path,
        action_proposals_activation_path=proposals_path,
        action_proposals_attestation={
            "ledger_sequence": 8,
            "ledger_entry_hash": "8" * 64,
        },
        action_social_publishing_activation_path=social_path,
        action_social_publishing_attestation={
            "ledger_sequence": 14,
            "ledger_entry_hash": "e" * 64,
        },
        agent_linkedin_proposals_activation_path=linkedin_path,
        agent_linkedin_proposals_attestation={
            "ledger_sequence": 15,
            "ledger_entry_hash": "f" * 64,
        },
        now=NOW,
    )
    assert evidence["schema_version"] == 10
    assert evidence["runtime_requirements"]["agent_linkedin_proposals_enabled"] is True
    assert evidence["agent_linkedin_proposals"]["ledger_sequence"] == 15
    assert evidence["artifact_sha256"]["agent_linkedin_proposals_activation"] == sha256_file(linkedin_path)


def _valid_scale_rollout():
    return {
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {"reference": "approved-cohort", "max_users": 25},
        "action_providers": [],
        "capabilities": {
            "coworker": True,
            "work_services": True,
            "artifact_services": True,
            "agent_runtime": True,
            "intelligent_planner": True,
            "memory": False,
            "handoffs": True,
            "multi_handoffs": True,
            "dependency_graph": True,
            "parallel_execution": True,
            "outcome_replan": True,
            "research": False,
            "actions": False,
        },
        "rollback": {
            "runbook_reference": "runbook-1",
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
        },
        "monitoring": {
            "queue_age": "dashboard",
            "task_success": "dashboard",
            "provider_errors": "dashboard",
            "latency": "dashboard",
            "token_cost": "dashboard",
            "storage_growth": "dashboard",
            "agent_failures": "dashboard",
        },
        "incident": {
            "oncall_reference": "oncall-primary",
            "change_reference": "change-42",
        },
    }


def test_scale_rejects_release_bundle_for_different_rollout(tmp_path):
    rollout_path = tmp_path / "current-rollout.json"
    rollout_path.write_text(json.dumps(_valid_scale_rollout()), encoding="utf-8")
    bundle_path = tmp_path / "release-activation-bundle.json"
    bundle_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "release_activation_bundle_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "rollout_manifest_sha256": "0" * 64,
    }), encoding="utf-8")

    with pytest.raises(
        ScaleActivationError,
        match="does not bind the current rollout manifest",
    ):
        validate_release_activation_bundle(
            bundle_path,
            tmp_path / "unused-ledger.jsonl",
            decision(),
            rollout_path,
        )


def test_scale_rejects_decision_from_different_rollout(tmp_path):
    rollout_path = tmp_path / "current-rollout-decision.json"
    rollout_path.write_text(json.dumps(_valid_scale_rollout()), encoding="utf-8")
    rollout_hash = sha256_file(rollout_path)
    bundle_path = tmp_path / "release-activation-bundle-decision.json"
    bundle_path.write_text(json.dumps({
        "schema_version": 1,
        "status": "release_activation_bundle_verified",
        "release_id": "coworker-cohort-001",
        "current_stage": "cohort-25",
        "rollout_manifest_sha256": rollout_hash,
    }), encoding="utf-8")
    decision_value = decision()
    decision_value["rollout_manifest_sha256"] = "0" * 64

    with pytest.raises(
        ScaleActivationError,
        match="Scale decision does not bind the current rollout manifest",
    ):
        validate_release_activation_bundle(
            bundle_path,
            tmp_path / "unused-ledger.jsonl",
            decision_value,
            rollout_path,
        )
