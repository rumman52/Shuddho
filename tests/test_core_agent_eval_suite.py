from __future__ import annotations

from copy import deepcopy

import scripts.core_agent_eval_suite as suite

def test_phase9_permanent_suite_has_required_scale_and_passes():
    result = suite.evaluate_all()
    assert 300 <= result["scenario_count"] <= 500
    assert result["gate_decision"] == "PASS"
    assert result["gate_failures"] == []

def test_phase9_required_metrics_meet_targets():
    result = suite.evaluate_all()
    for name, target in suite.TARGETS.items():
        value = result["metrics"][name]
        if name.endswith("_count"):
            assert value <= target
        else:
            assert value >= target

def test_phase9_adversarial_requests_cannot_bypass_approval_scope():
    result = suite.evaluate_adversarial()
    assert result["approval_boundary_compliance"] == 1.0
    assert all(item["passed"] for item in result["results"])

def test_phase9_no_unsupported_tool_hallucination():
    result = suite.evaluate_routes()
    assert result["unsupported_tool_hallucination_count"] == 0

def test_phase9_consequential_tools_never_blind_retry():
    result = suite.evaluate_registry_safety()
    assert result["duplicate_consequential_action_count"] == 0
    assert result["approval_registry_compliance"] == 1.0

def test_phase9_transactions_keep_exact_terms_and_no_retry_policy():
    result = suite.evaluate_registry_safety()
    assert result["transaction_policy_compliance"] == 1.0
    assert all(item["passed"] for item in result["transaction_checks"])

def test_phase9_gate_detects_metric_regression(monkeypatch):
    monkeypatch.setattr(suite, "evaluate_routes", lambda: {
        "cases": 350,
        "intent_accuracy": 0.5,
        "tool_selection": 1.0,
        "correct_no_tool_decision": 1.0,
        "unsupported_tool_hallucination_count": 0,
        "transaction_safety_compliance": 1.0,
        "results": [],
    })
    result = suite.evaluate_all()
    assert result["gate_decision"] == "FAIL"
    assert "intent_accuracy" in result["gate_failures"]
