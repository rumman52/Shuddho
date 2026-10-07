from __future__ import annotations

from copy import deepcopy

from scripts.agent_long_horizon_eval import (
    REQUIRED_TARGETS,
    evaluate,
    load_cases,
)


def cases():
    return load_cases(__import__("pathlib").Path("tests/fixtures/agent_long_horizon_cases.jsonl"))


def test_phase7_long_horizon_fixture_passes_all_required_horizons_and_domains():
    result = evaluate(cases())

    assert result["scenario_completion_rate"] == 1.0
    assert result["milestone_completion_rate"] == 1.0
    assert result["long_horizon_completion_rate"] == 1.0
    assert result["transaction_completion_rate"] == 1.0
    assert result["target_step_coverage"] == list(REQUIRED_TARGETS)
    assert {
        "research",
        "document",
        "email",
        "meeting",
        "transaction",
    } <= set(result["workflow_coverage"])
    assert result["coverage_failures"] == []
    assert result["scenario_failures"] == []


def test_phase7_tracks_completion_rate_by_horizon_separately():
    result = evaluate(cases())

    assert result["completion_rate_by_target_steps"] == {
        "2": 1.0,
        "5": 1.0,
        "10": 1.0,
        "20": 1.0,
    }
    assert result["completion_rate_by_workflow"]["transaction"] == 1.0
    assert result["completion_rate_by_workflow"]["email"] == 1.0


def test_phase7_rejects_provider_mutation_before_human_approval():
    value = cases()
    email = next(case for case in value if case["workflow"] == "email")
    milestones = email["milestones"]
    approval_index = next(i for i, item in enumerate(milestones) if item["name"] == "human_approval")
    mutation_index = next(i for i, item in enumerate(milestones) if item["name"] == "provider_mutation")
    milestones[approval_index], milestones[mutation_index] = milestones[mutation_index], milestones[approval_index]
    for ordinal, item in enumerate(milestones, 1):
        item["ordinal"] = ordinal

    result = evaluate(value)
    email_result = next(item for item in result["results"] if item["workflow"] == "email")

    assert email_result["passed"] is False
    assert "approval_boundary_order" in email_result["failures"] or "provider_mutation_before_approval" in email_result["failures"]


def test_phase7_preserves_agent_tool_step_safety_ceiling():
    value = cases()
    research = next(case for case in value if case["workflow"] == "research")
    research["tool_steps"] = 9

    result = evaluate(value)
    research_result = next(item for item in result["results"] if item["id"] == research["id"])

    assert research_result["passed"] is False
    assert "tool_step_safety_limit" in research_result["failures"]
    assert result["tool_step_safety_limit"] == 8


def test_phase7_detects_missing_twenty_step_coverage():
    value = [
        case for case in cases()
        if case["target_steps"] != 20
    ]

    result = evaluate(value)

    assert "missing_target_20" in result["coverage_failures"]


def test_phase7_detects_incomplete_transaction_milestone():
    value = cases()
    transaction = next(case for case in value if case["workflow"] == "transaction")
    transaction["milestones"][-1]["state"] = "failed"

    result = evaluate(value)
    tx_result = next(item for item in result["results"] if item["workflow"] == "transaction")

    assert tx_result["completion_rate"] == 0.95
    assert tx_result["passed"] is False
    assert "milestone_completion" in tx_result["failures"]
    assert result["transaction_completion_rate"] == 0.0


def test_phase7_route_contract_failure_is_counted_as_scenario_failure():
    value = cases()
    document = next(case for case in value if case["workflow"] == "document")
    document["expected_route"] = deepcopy(document["expected_route"])
    document["expected_route"]["capability"] = "research"

    result = evaluate(value)
    item = next(row for row in result["results"] if row["id"] == document["id"])

    assert item["passed"] is False
    assert "route_contract" in item["failures"]
