from __future__ import annotations

import json
from pathlib import Path

from scripts.cohort_release_gate import validate_rollout
from scripts.release_contract import (
    CONDITIONAL_GATES,
    OPTIONAL_CAPABILITY_KEYS,
    expected_rollout_capability_keys,
    expected_staging_evidence_keys,
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
    } == covered


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
