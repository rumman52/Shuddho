from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.cohort_release_ledger import (
    ACTION_PROPOSALS_ARTIFACT_KEYS,
    ACTION_PROPOSALS_SCHEMA_VERSION,
    ReleaseLedgerError,
    append_release_activation_bundle_event,
    canonical,
    read_entries,
    sign_entry,
    verify_entries,
)
from scripts.release_activation_bundle import (
    ReleaseActivationBundleError,
    verify_activation_bundle,
)
from scripts.release_contract import required_activation_requirements


KEY = b"k" * 32
RELEASE_ID = "coworker-cohort-001"
STAGE = "canary-5"


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rollout_value() -> dict:
    return {
        "release_id": RELEASE_ID,
        "environment": "production",
        "cohort": {
            "reference": "approved-cohort",
            "max_users": 25,
        },
        "action_providers": ["google"],
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
            "actions": True,
            "action_selection": False,
            "action_proposals": True,
            "action_attachments": False,
            "action_reminders": False,
            "action_recipients": False,
            "action_document_sharing": False,
            "action_email_threading": False,
            "action_social_publishing": False,
            "agent_linkedin_proposals": False,
        },
        "rollback": {
            "runbook_reference": "runbook-1",
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
            "action_selection_kill_switch": "SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false",
            "action_proposals_kill_switch": "SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false",
            "action_attachments_kill_switch": "SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false",
            "action_reminders_kill_switch": "SHUDDHO_ACTION_REMINDERS_ENABLED=false",
            "action_recipients_kill_switch": "SHUDDHO_ACTION_RECIPIENTS_ENABLED=false",
            "action_document_sharing_kill_switch": "SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED=false",
            "action_email_threading_kill_switch": "SHUDDHO_ACTION_EMAIL_THREADING_ENABLED=false",
            "action_social_publishing_kill_switch": "SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=false",
            "agent_linkedin_proposals_kill_switch": "SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED=false",
        },
        "monitoring": {
            "queue_age": "dashboard",
            "task_success": "dashboard",
            "provider_errors": "dashboard",
            "latency": "dashboard",
            "token_cost": "dashboard",
            "storage_growth": "dashboard",
            "agent_failures": "dashboard",
            "actions": "dashboard",
        },
        "incident": {
            "oncall_reference": "oncall-primary",
            "change_reference": "change-1",
        },
    }


def staging_value() -> dict:
    from scripts.release_contract import expected_staging_evidence_keys

    return {
        key: {
            "status": "passed",
            "evidence": "synthetic-evidence",
        }
        for key in expected_staging_evidence_keys()
    }


def signed_action_proposal_ledger(
    tmp_path: Path,
    activation_path: Path,
) -> Path:
    zeros = "0" * 64
    core = {
        "schema_version": ACTION_PROPOSALS_SCHEMA_VERSION,
        "sequence": 1,
        "created_at": "2026-09-24T12:00:00+00:00",
        "release_id": RELEASE_ID,
        "event_type": "action_proposals_verified",
        "actor_reference": "oncall-primary",
        "change_reference": "change-1",
        "current_stage": STAGE,
        "next_stage": None,
        "artifact_sha256": {
            "staging_evidence": "1" * 64,
            "rollout_manifest": "2" * 64,
            "deployment_change": "3" * 64,
            "operator_status": "4" * 64,
            "action_proposals_activation": file_hash(activation_path),
        },
        "previous_entry_hash": zeros,
    }
    assert set(core["artifact_sha256"]) == ACTION_PROPOSALS_ARTIFACT_KEYS
    entry_hash, tag = sign_entry(core, KEY)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps(
            {
                **core,
                "entry_hash": entry_hash,
                "hmac_sha256": tag,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return ledger


def bundle_files(tmp_path: Path):
    rollout_path = write_json(tmp_path / "rollout.json", rollout_value())
    staging_path = write_json(tmp_path / "staging.json", staging_value())
    activation_path = write_json(
        tmp_path / "action-proposals-activation.json",
        {
            "schema_version": 1,
            "status": "action_proposals_verified",
            "release_id": RELEASE_ID,
            "current_stage": STAGE,
            "artifact_sha256": {
                "rollout_manifest": file_hash(rollout_path),
            },
        },
    )
    ledger = signed_action_proposal_ledger(tmp_path, activation_path)
    return rollout_path, staging_path, activation_path, ledger


def test_required_activation_requirements_follow_reviewed_rollout():
    capabilities = rollout_value()["capabilities"]
    requirements = required_activation_requirements(
        capabilities,
        {"google"},
    )
    assert [item.key for item in requirements] == ["action_proposals"]


def test_release_activation_bundle_verifies_exact_attestation(
    tmp_path,
    monkeypatch,
):
    rollout, staging, activation, ledger = bundle_files(tmp_path)
    monkeypatch.setenv(
        "SHUDDHO_RELEASE_LEDGER_HMAC_KEY",
        KEY.decode("ascii"),
    )
    result = verify_activation_bundle(
        rollout_path=rollout,
        staging_evidence_path=staging,
        ledger_path=ledger,
        activation_paths={"action_proposals": activation},
        current_stage=STAGE,
    )
    assert result["status"] == "release_activation_bundle_verified"
    assert result["required_activation_keys"] == ["action_proposals"]
    assert result["activations"]["action_proposals"]["ledger_sequence"] == 1


def test_release_activation_bundle_rejects_missing_required_activation(
    tmp_path,
    monkeypatch,
):
    rollout, staging, _, ledger = bundle_files(tmp_path)
    monkeypatch.setenv(
        "SHUDDHO_RELEASE_LEDGER_HMAC_KEY",
        KEY.decode("ascii"),
    )
    with pytest.raises(
        ReleaseActivationBundleError,
        match="missing=action_proposals",
    ):
        verify_activation_bundle(
            rollout_path=rollout,
            staging_evidence_path=staging,
            ledger_path=ledger,
            activation_paths={},
            current_stage=STAGE,
        )


def test_schema_v16_binds_bundle_to_exact_verified_ledger_head(
    tmp_path,
    monkeypatch,
):
    rollout, staging, activation, ledger = bundle_files(tmp_path)
    monkeypatch.setenv(
        "SHUDDHO_RELEASE_LEDGER_HMAC_KEY",
        KEY.decode("ascii"),
    )
    bundle = verify_activation_bundle(
        rollout_path=rollout,
        staging_evidence_path=staging,
        ledger_path=ledger,
        activation_paths={"action_proposals": activation},
        current_stage=STAGE,
    )
    bundle_path = write_json(tmp_path / "bundle.json", bundle)

    entry = append_release_activation_bundle_event(
        ledger=ledger,
        key=KEY,
        release_id=RELEASE_ID,
        actor_reference="oncall-primary",
        change_reference="change-1",
        current_stage=STAGE,
        rollout_manifest=rollout,
        staging_evidence=staging,
        release_activation_bundle=bundle_path,
        created_at="2026-09-24T12:05:00+00:00",
    )
    assert entry["schema_version"] == 16
    assert entry["event_type"] == "release_activation_bundle_verified"
    assert verify_entries(read_entries(ledger), KEY)["entries"] == 2

    with pytest.raises(
        ReleaseLedgerError,
        match="changed after activation bundle verification",
    ):
        append_release_activation_bundle_event(
            ledger=ledger,
            key=KEY,
            release_id=RELEASE_ID,
            actor_reference="oncall-primary",
            change_reference="change-1",
            current_stage=STAGE,
            rollout_manifest=rollout,
            staging_evidence=staging,
            release_activation_bundle=bundle_path,
        )
