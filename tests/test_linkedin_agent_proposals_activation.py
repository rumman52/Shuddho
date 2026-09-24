from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.linkedin_agent_proposals_activation import (
    LinkedInAgentProposalsActivationError,
    build_evidence,
    canonical_sha256,
    validate_runtime_manifest,
    validate_staging,
)


NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


def runtime():
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
        "action_attachments": False,
        "action_reminders": False,
        "action_recipients": False,
        "action_document_sharing": False,
        "action_email_threading": False,
        "action_social_publishing": True,
        "action_selection": False,
        "action_proposals": True,
        "agent_linkedin_proposals": True,
    }
    return {
        "schema_version": 1,
        "source_revision": "a" * 40,
        "environment": "production",
        "capabilities": capabilities,
        "action_providers": ["google", "linkedin"],
        "cohort": {
            "enforced": True,
            "configured_members": 5,
            "max_users": 25,
        },
    }


def rollout():
    value = runtime()
    return {
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "capabilities": value["capabilities"],
        "action_providers": value["action_providers"],
        "cohort_max_users": 25,
        "change_reference": "linkedin-agent-proposals-1",
    }


def deployment():
    return {
        "release_id": "coworker-cohort-001",
        "change_reference": "linkedin-agent-proposals-1",
        "current_stage": "canary-5",
        "deployed_at": "2026-09-24T11:50:00+00:00",
        "source_revision": "a" * 40,
    }


def test_staging_requires_timestamped_dedicated_linkedin_proposal_proof():
    evidence = {
        "agent_linkedin_proposals": {
            "status": "passed",
            "evidence": "live inert LinkedIn proposal proof",
            "verified_at": "2026-09-24T11:45:00+00:00",
        }
    }
    verified = validate_staging(evidence, now=NOW, max_age_minutes=30)
    assert verified.isoformat() == "2026-09-24T11:45:00+00:00"

    evidence["agent_linkedin_proposals"]["status"] = "failed"
    with pytest.raises(LinkedInAgentProposalsActivationError, match="not passed"):
        validate_staging(evidence, now=NOW, max_age_minutes=30)


def test_runtime_manifest_requires_full_nested_authority_chain():
    value = runtime()
    result = validate_runtime_manifest(
        value,
        deployment=deployment(),
        rollout=rollout(),
    )
    assert result["capabilities"]["agent_linkedin_proposals"] is True

    value["capabilities"]["action_proposals"] = False
    with pytest.raises(
        LinkedInAgentProposalsActivationError,
        match="exactly match reviewed rollout",
    ):
        validate_runtime_manifest(
            value,
            deployment=deployment(),
            rollout=rollout(),
        )


def test_activation_evidence_hashes_exact_runtime_snapshot(tmp_path):
    staging = tmp_path / "staging.json"
    rollout_path = tmp_path / "rollout.json"
    deployment_path = tmp_path / "deployment.json"
    status = tmp_path / "status.json"
    for path in (staging, rollout_path, deployment_path, status):
        path.write_text("{}", encoding="utf-8")
    value = runtime()
    evidence = build_evidence(
        deployment=deployment(),
        staging_path=staging,
        rollout_path=rollout_path,
        deployment_path=deployment_path,
        operator_status_path=status,
        runtime=value,
        operator_status={"generated_at": "2026-09-24T11:55:00+00:00"},
        now=NOW,
    )
    assert evidence["status"] == "agent_linkedin_proposals_verified"
    assert evidence["runtime_manifest_sha256"] == canonical_sha256(value)
