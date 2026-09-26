from __future__ import annotations

import json
from pathlib import Path

from scripts.cohort_release_gate import validate_rollout
from scripts.release_contract import (
    CONDITIONAL_GATES,
    ACTIVATION_REQUIREMENTS,
    OPTIONAL_CAPABILITY_KEYS,
    expected_rollout_capability_keys,
    expected_staging_evidence_keys,
    normalize_capabilities,
    required_activation_requirements,
    required_conditional_gate_ids,
)
from scripts.release_contract_check import validate_templates


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_checked_in_release_templates_match_canonical_contract():
    staging = load("docs/staging-evidence.template.json")
    rollout = load("docs/cohort-rollout.template.json")
    assert validate_templates(staging, rollout) == []
    assert set(staging) == expected_staging_evidence_keys()
    assert set(rollout["capabilities"]) == expected_rollout_capability_keys()


def test_every_optional_capability_has_a_registered_staging_gate():
    assert OPTIONAL_CAPABILITY_KEYS
    covered = {
        key
        for key in CONDITIONAL_GATES
        if key not in {"research", "actions", "microsoft_actions"}
    }
    assert {
        "action_attachments",
        "action_reminders_google",
        "action_reminders_microsoft",
        "action_recipients",
        "action_document_sharing",
        "action_email_threading",
        "action_social_publishing",
        "agent_linkedin_proposals",
        "action_selection",
        "action_proposals",
        "personal_goals",
        "automations",
        "runtime_v3",
        "context_retrieval",
        "connector_trust_boundary",
        "connector_reads",
        "connector_reads_microsoft",
        "browser",
    } == covered



def test_connector_reads_require_pa05_context_runtime_google_and_staging_evidence():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["actions"] = True
    rollout["capabilities"]["connector_trust_boundary"] = True
    rollout["capabilities"]["agent_runtime"] = True
    rollout["capabilities"]["intelligent_planner"] = True
    rollout["capabilities"]["runtime_v3"] = True
    rollout["capabilities"]["memory"] = True
    rollout["capabilities"]["context_retrieval"] = True
    rollout["capabilities"]["connector_reads"] = True
    rollout["action_providers"] = ["google"]
    rollout["monitoring"]["actions"] = "actions-dashboard"
    assert "connector_reads" in required_conditional_gate_ids(
        rollout["capabilities"], {"google"}
    )
    assert "connector_reads_microsoft" in required_conditional_gate_ids(
        rollout["capabilities"], {"google", "microsoft"}
    )
    assert "connector_reads_microsoft" not in required_conditional_gate_ids(
        rollout["capabilities"], {"google"}
    )
    rollout["capabilities"]["context_retrieval"] = False
    assert "connector_reads_dependency" in validate_rollout(
        rollout, max_cohort_users=25
    )


def test_browser_requires_runtime_v3_trust_boundary_and_staging_evidence():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["actions"] = True
    rollout["capabilities"]["connector_trust_boundary"] = True
    rollout["capabilities"]["agent_runtime"] = True
    rollout["capabilities"]["intelligent_planner"] = True
    rollout["capabilities"]["runtime_v3"] = True
    rollout["capabilities"]["browser"] = True
    rollout["action_providers"] = ["google"]
    rollout["monitoring"]["actions"] = "actions-dashboard"
    assert "browser" in required_conditional_gate_ids(
        rollout["capabilities"], {"google"}
    )
    rollout["capabilities"]["runtime_v3"] = False
    assert "browser_dependency" in validate_rollout(
        rollout, max_cohort_users=25
    )


def test_connector_trust_boundary_requires_actions_and_staging_evidence():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["actions"] = True
    rollout["capabilities"]["connector_trust_boundary"] = True
    rollout["monitoring"]["actions"] = "actions-dashboard"
    assert "connector_trust_boundary" in required_conditional_gate_ids(
        rollout["capabilities"], {"google"}
    )
    rollout["capabilities"]["actions"] = False
    assert "connector_trust_boundary_dependency" in validate_rollout(
        rollout, max_cohort_users=25
    )

def test_personal_goals_require_agent_runtime_and_staging_evidence():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["personal_goals"] = True
    assert "personal_goals" in required_conditional_gate_ids(
        rollout["capabilities"], set()
    )
    rollout["capabilities"]["agent_runtime"] = False
    assert "personal_goals_dependency" in validate_rollout(rollout, max_cohort_users=25)


def test_automations_require_goals_agent_runtime_and_staging_evidence():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["personal_goals"] = True
    rollout["capabilities"]["automations"] = True
    assert "automations" in required_conditional_gate_ids(
        rollout["capabilities"], set()
    )
    rollout["capabilities"]["personal_goals"] = False
    assert "automations_dependency" in validate_rollout(rollout, max_cohort_users=25)


def test_runtime_v3_requires_agent_runtime_planner_and_staging_evidence():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["runtime_v3"] = True
    assert "runtime_v3" in required_conditional_gate_ids(
        rollout["capabilities"], set()
    )
    rollout["capabilities"]["intelligent_planner"] = False
    assert "runtime_v3_dependency" in validate_rollout(rollout, max_cohort_users=25)



def test_context_retrieval_requires_runtime_v3_and_staging_evidence():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["runtime_v3"] = True
    rollout["capabilities"]["memory"] = True
    rollout["capabilities"]["context_retrieval"] = True
    assert "context_retrieval" in required_conditional_gate_ids(
        rollout["capabilities"], set()
    )
    rollout["capabilities"]["runtime_v3"] = False
    assert "context_retrieval_dependency" in validate_rollout(
        rollout, max_cohort_users=25
    )

def test_required_gate_resolution_is_provider_aware_and_ordered():
    capabilities = {
        "research": True,
        "actions": True,
        "action_reminders": True,
        "action_social_publishing": True,
        "agent_linkedin_proposals": False,
    }
    assert required_conditional_gate_ids(
        capabilities,
        {"google", "microsoft", "linkedin"},
    ) == (
        "research",
        "actions",
        "microsoft_actions",
        "action_reminders_google",
        "action_reminders_microsoft",
        "action_social_publishing",
    )


def test_capability_normalization_defaults_every_optional_capability_off():
    value = {
        "coworker": True,
        "actions": True,
        "action_proposals": True,
    }
    normalized = normalize_capabilities(value)

    assert normalized["coworker"] is True
    assert normalized["actions"] is True
    assert normalized["action_proposals"] is True
    for capability in OPTIONAL_CAPABILITY_KEYS - {"action_proposals"}:
        assert normalized[capability] is False
    assert value == {
        "coworker": True,
        "actions": True,
        "action_proposals": True,
    }


def test_template_checker_fails_when_new_gate_is_missing():
    staging = load("docs/staging-evidence.template.json")
    rollout = load("docs/cohort-rollout.template.json")
    staging.pop("agent_linkedin_proposals")
    assert "staging_keys" in validate_templates(staging, rollout)


def test_linkedin_capability_cannot_use_legacy_google_provider_fallback():
    rollout = load("docs/cohort-rollout.template.json")
    rollout["capabilities"]["actions"] = True
    rollout["capabilities"]["action_social_publishing"] = True
    rollout.pop("action_providers")
    rollout["monitoring"]["actions"] = "actions-dashboard"
    failures = validate_rollout(rollout, max_cohort_users=25)
    assert "action_social_publishing_provider" in failures


def test_every_optional_capability_has_exactly_one_activation_requirement():
    capability_requirements = [
        item.capability
        for item in ACTIVATION_REQUIREMENTS
        if item.capability is not None
    ]
    assert set(capability_requirements) == OPTIONAL_CAPABILITY_KEYS
    assert len(capability_requirements) == len(OPTIONAL_CAPABILITY_KEYS)


def test_microsoft_activation_requirement_is_provider_aware():
    capabilities = {
        "actions": True,
        "action_proposals": False,
    }
    assert [
        item.key
        for item in required_activation_requirements(
            capabilities,
            {"google"},
        )
    ] == []
    assert [
        item.key
        for item in required_activation_requirements(
            capabilities,
            {"google", "microsoft"},
        )
    ] == ["microsoft_actions"]
