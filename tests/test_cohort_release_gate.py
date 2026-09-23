import pytest

from scripts.cohort_release_gate import evaluate_release, validate_rollout


BASE_GATES = {
    "ci", "identity", "database", "storage", "temporal", "model", "quality",
    "backup_restore", "deletion", "parallel_restart", "fan_in", "flag_rollback",
    "cohort_admission",
}


def evidence(*, research=False, actions=False, microsoft=False, action_attachments=False, action_reminders=False, microsoft_action_reminders=False, action_recipients=False, action_selection=False, action_proposals=False):
    keys = set(BASE_GATES)
    if research:
        keys.add("research")
    if actions:
        keys.add("actions")
    if microsoft:
        keys.add("microsoft_actions")
    if action_attachments:
        keys.add("action_attachments")
    if action_reminders:
        keys.add("action_reminders_google")
    if microsoft_action_reminders:
        keys.add("action_reminders_microsoft")
    if action_recipients:
        keys.add("action_recipients")
    if action_selection:
        keys.add("action_selection")
    if action_proposals:
        keys.add("action_proposals")
    return {key: {"status": "passed", "evidence": "staging-proof"} for key in keys}


def rollout(*, research=False, actions=False, users=25, providers=None, action_attachments=False, action_reminders=False, action_recipients=False, action_selection=False, action_proposals=False):
    monitoring = {
        "queue_age": "queue-dashboard",
        "task_success": "task-dashboard",
        "provider_errors": "provider-alert",
        "latency": "latency-dashboard",
        "token_cost": "cost-dashboard",
        "storage_growth": "storage-dashboard",
        "agent_failures": "agent-alert",
    }
    if research:
        monitoring["research"] = "research-dashboard"
    if actions:
        monitoring["actions"] = "actions-dashboard"
    value = {
        "release_id": "coworker-cohort-001",
        "environment": "production",
        "cohort": {"reference": "cohort-ticket", "max_users": users},
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
            "research": research,
            "actions": actions,
            **({"action_attachments": True} if action_attachments else {}),
            **({"action_reminders": True} if action_reminders else {}),
            **({"action_recipients": True} if action_recipients else {}),
            **({"action_selection": True} if action_selection else {}),
            **({"action_proposals": True} if action_proposals else {}),
        },
        "rollback": {
            "runbook_reference": "rollback-runbook",
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
            **({
                "action_attachments_kill_switch": "SHUDDHO_ACTION_ATTACHMENTS_ENABLED=false",
            } if action_attachments else {}),
            **({
                "action_reminders_kill_switch": "SHUDDHO_ACTION_REMINDERS_ENABLED=false",
            } if action_reminders else {}),
            **({
                "action_recipients_kill_switch": "SHUDDHO_ACTION_RECIPIENTS_ENABLED=false",
            } if action_recipients else {}),
            **({
                "action_selection_kill_switch": "SHUDDHO_AGENT_ACTION_SELECTION_ENABLED=false",
            } if action_selection else {}),
            **({
                "action_proposals_kill_switch": "SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=false",
            } if action_proposals else {}),
        },
        "monitoring": monitoring,
        "incident": {
            "oncall_reference": "oncall-owner",
            "change_reference": "change-123",
        },
    }
    if providers is not None:
        value["action_providers"] = providers
    return value


def test_controlled_cohort_gate_go_without_optional_provider_capabilities():
    result = evaluate_release(evidence(), rollout())
    assert result["decision"] == "GO_CONTROLLED_COHORT"
    assert result["staging"]["missing"] == []
    assert result["rollout_failures"] == []
    assert result["required_provider_gates"] == {
        "research": False,
        "actions": False,
        "microsoft_actions": False,
    }
    assert result["action_providers"] == []


def test_provider_evidence_is_required_only_when_enabled():
    research_rollout = rollout(research=True)
    result = evaluate_release(evidence(), research_rollout)
    assert result["decision"] == "NO-GO"
    assert "research" in result["staging"]["missing"]

    result = evaluate_release(evidence(research=True), research_rollout)
    assert result["decision"] == "GO_CONTROLLED_COHORT"


def test_actions_require_live_actions_gate_and_monitoring():
    action_rollout = rollout(actions=True)
    action_rollout["monitoring"].pop("actions")
    result = evaluate_release(evidence(actions=True), action_rollout)
    assert result["decision"] == "NO-GO"
    assert "monitoring_shape" in result["rollout_failures"]


def test_first_cohort_is_bounded():
    result = evaluate_release(evidence(), rollout(users=26), max_cohort_users=25)
    assert result["decision"] == "NO-GO"
    assert "cohort_max_users" in result["rollout_failures"]


def test_rollout_dependencies_fail_closed():
    value = rollout()
    value["capabilities"]["agent_runtime"] = False
    assert "agent_dependency" in validate_rollout(value, max_cohort_users=25)

    value = rollout()
    value["capabilities"]["dependency_graph"] = False
    assert "parallel_dependency" in validate_rollout(value, max_cohort_users=25)

    value = rollout()
    value["capabilities"]["handoffs"] = False
    assert "multi_handoff_dependency" in validate_rollout(value, max_cohort_users=25)


def test_exact_kill_switches_are_required():
    value = rollout()
    value["rollback"]["parallel_kill_switch"] = "wrong"
    result = evaluate_release(evidence(), value)
    assert result["decision"] == "NO-GO"
    assert "parallel_kill_switch" in result["rollout_failures"]


def test_release_manifest_rejects_missing_operational_references():
    value = rollout()
    value["incident"]["oncall_reference"] = ""
    value["rollback"]["runbook_reference"] = ""
    result = evaluate_release(evidence(), value)
    assert result["decision"] == "NO-GO"
    assert "incident_oncall" in result["rollout_failures"]
    assert "rollback_runbook" in result["rollout_failures"]


def test_controlled_cohort_gate_requires_server_admission_evidence():
    value = evidence()
    value.pop("cohort_admission")
    result = evaluate_release(value, rollout())
    assert result["decision"] == "NO-GO"
    assert "cohort_admission" in result["staging"]["missing"]


def test_legacy_google_actions_remain_backward_compatible():
    result = evaluate_release(
        evidence(actions=True),
        rollout(actions=True),
    )
    assert result["decision"] == "GO_CONTROLLED_COHORT"
    assert result["required_provider_gates"]["microsoft_actions"] is False
    assert result["action_providers"] == ["google"]


def test_declared_microsoft_requires_independent_live_gate():
    value = rollout(
        actions=True,
        providers=["google", "microsoft"],
    )
    missing = evaluate_release(
        evidence(actions=True),
        value,
    )
    assert missing["decision"] == "NO-GO"
    assert missing["staging"]["missing"] == ["microsoft_actions"]
    assert missing["required_provider_gates"]["microsoft_actions"] is True
    assert missing["action_providers"] == ["google", "microsoft"]

    passed = evaluate_release(
        evidence(actions=True, microsoft=True),
        value,
    )
    assert passed["decision"] == "GO_CONTROLLED_COHORT"
    assert passed["staging"]["missing"] == []


@pytest.mark.parametrize("providers", [
    ["microsoft"],
    ["google", "google"],
    ["google", "slack"],
    "google",
])
def test_invalid_action_provider_declarations_fail_closed(providers):
    value = rollout(actions=True, providers=providers)
    failures = validate_rollout(value, max_cohort_users=25)
    assert "action_providers" in failures or "action_providers_google_required" in failures


def test_action_providers_cannot_be_declared_when_actions_are_disabled():
    value = rollout(actions=False, providers=["google"])
    failures = validate_rollout(value, max_cohort_users=25)
    assert "action_providers_without_actions" in failures


def test_action_selection_requires_its_own_live_gate_and_kill_switch():
    value = rollout(actions=True, action_selection=True)
    missing = evaluate_release(evidence(actions=True), value)
    assert missing["decision"] == "NO-GO"
    assert "action_selection" in missing["staging"]["missing"]
    assert missing["required_feature_gates"] == {
        "action_attachments": False,
        "action_reminders": False,
        "action_recipients": False,
        "action_selection": True,
        "action_proposals": False,
    }

    passed = evaluate_release(
        evidence(actions=True, action_selection=True),
        value,
    )
    assert passed["decision"] == "GO_CONTROLLED_COHORT"


def test_action_selection_dependency_is_fail_closed():
    value = rollout(actions=False, action_selection=True)
    failures = validate_rollout(value, max_cohort_users=25)
    assert "action_selection_dependency" in failures

    value = rollout(actions=True, action_selection=True)
    value["rollback"].pop("action_selection_kill_switch")
    failures = validate_rollout(value, max_cohort_users=25)
    assert "action_selection_kill_switch" in failures


def test_action_proposals_require_independent_gate_and_kill_switch():
    value = rollout(actions=True, action_proposals=True)
    missing = evaluate_release(evidence(actions=True), value)
    assert missing["decision"] == "NO-GO"
    assert "action_proposals" in missing["staging"]["missing"]
    assert missing["required_feature_gates"]["action_proposals"] is True

    passed = evaluate_release(
        evidence(actions=True, action_proposals=True),
        value,
    )
    assert passed["decision"] == "GO_CONTROLLED_COHORT"

    broken = rollout(actions=True, action_proposals=True)
    broken["rollback"].pop("action_proposals_kill_switch")
    assert "action_proposals_kill_switch" in validate_rollout(
        broken,
        max_cohort_users=25,
    )


def test_action_proposals_dependency_is_fail_closed():
    value = rollout(actions=False, action_proposals=True)
    failures = validate_rollout(value, max_cohort_users=25)
    assert "action_proposals_dependency" in failures


def test_action_attachments_require_independent_gate_dependency_and_kill_switch():
    value = rollout(actions=True, action_attachments=True)
    missing = evaluate_release(evidence(actions=True), value)
    assert missing["decision"] == "NO-GO"
    assert "action_attachments" in missing["staging"]["missing"]
    assert missing["required_feature_gates"]["action_attachments"] is True

    passed = evaluate_release(
        evidence(actions=True, action_attachments=True),
        value,
    )
    assert passed["decision"] == "GO_CONTROLLED_COHORT"

    broken = rollout(actions=True, action_attachments=True)
    broken["rollback"].pop("action_attachments_kill_switch")
    assert "action_attachments_kill_switch" in validate_rollout(
        broken,
        max_cohort_users=25,
    )

    no_artifacts = rollout(actions=True, action_attachments=True)
    no_artifacts["capabilities"]["artifact_services"] = False
    assert "action_attachments_dependency" in validate_rollout(
        no_artifacts,
        max_cohort_users=25,
    )


def test_calendar_reminders_require_live_provider_evidence_and_kill_switch():
    value = rollout(actions=True, action_reminders=True)
    assert validate_rollout(value, max_cohort_users=25) == []

    missing = evaluate_release(evidence(actions=True), value)
    assert missing["decision"] == "NO-GO"
    assert "action_reminders_google" in missing["staging"]["missing"]

    passed = evaluate_release(
        evidence(actions=True, action_reminders=True),
        value,
    )
    assert passed["decision"] == "GO_CONTROLLED_COHORT"

    microsoft_value = rollout(
        actions=True,
        providers=["google", "microsoft"],
        action_reminders=True,
    )
    missing_microsoft = evaluate_release(
        evidence(
            actions=True,
            microsoft=True,
            action_reminders=True,
        ),
        microsoft_value,
    )
    assert missing_microsoft["decision"] == "NO-GO"
    assert "action_reminders_microsoft" in missing_microsoft["staging"]["missing"]

    passed_microsoft = evaluate_release(
        evidence(
            actions=True,
            microsoft=True,
            action_reminders=True,
            microsoft_action_reminders=True,
        ),
        microsoft_value,
    )
    assert passed_microsoft["decision"] == "GO_CONTROLLED_COHORT"

    value["rollback"].pop("action_reminders_kill_switch")
    failures = validate_rollout(value, max_cohort_users=25)
    assert "action_reminders_kill_switch" in failures


def test_action_recipients_require_independent_gate_dependency_and_kill_switch():
    value = rollout(actions=True, action_recipients=True)
    missing = evaluate_release(evidence(actions=True), value)
    assert missing["decision"] == "NO-GO"
    assert "action_recipients" in missing["staging"]["missing"]
    assert missing["required_feature_gates"]["action_recipients"] is True

    passed = evaluate_release(
        evidence(actions=True, action_recipients=True),
        value,
    )
    assert passed["decision"] == "GO_CONTROLLED_COHORT"

    broken = rollout(actions=True, action_recipients=True)
    broken["rollback"].pop("action_recipients_kill_switch")
    assert "action_recipients_kill_switch" in validate_rollout(
        broken,
        max_cohort_users=25,
    )

    no_actions = rollout(actions=False, action_recipients=True)
    assert "action_recipients_dependency" in validate_rollout(
        no_actions,
        max_cohort_users=25,
    )


def test_document_sharing_cannot_enter_production_rollout_before_qualification():
    value = rollout(actions=True)
    value["capabilities"]["action_document_sharing"] = True
    failures = validate_rollout(value, max_cohort_users=25)
    assert "capabilities" in failures
