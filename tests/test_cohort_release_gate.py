from scripts.cohort_release_gate import evaluate_release, validate_rollout


BASE_GATES = {
    "ci", "identity", "database", "storage", "temporal", "model",
    "backup_restore", "deletion", "parallel_restart", "fan_in", "flag_rollback",
    "cohort_admission",
}


def evidence(*, research=False, actions=False):
    keys = set(BASE_GATES)
    if research:
        keys.add("research")
    if actions:
        keys.add("actions")
    return {key: {"status": "passed", "evidence": "staging-proof"} for key in keys}


def rollout(*, research=False, actions=False, users=25):
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
    return {
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
        },
        "rollback": {
            "runbook_reference": "rollback-runbook",
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
        },
        "monitoring": monitoring,
        "incident": {
            "oncall_reference": "oncall-owner",
            "change_reference": "change-123",
        },
    }


def test_controlled_cohort_gate_go_without_optional_provider_capabilities():
    result = evaluate_release(evidence(), rollout())
    assert result["decision"] == "GO_CONTROLLED_COHORT"
    assert result["staging"]["missing"] == []
    assert result["rollout_failures"] == []
    assert result["required_provider_gates"] == {"research": False, "actions": False}


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
