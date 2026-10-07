from __future__ import annotations

from copy import deepcopy

from scripts.core_agent_multilingual_eval import evaluate, load_cases

def cases():
    return load_cases(__import__("pathlib").Path("tests/fixtures/core_agent_multilingual_cases.jsonl"))

def test_phase8_multilingual_route_and_safety_equivalence_passes():
    result = evaluate(cases())
    assert result["pass_rate"] == 1.0
    assert result["failures"] == []
    assert result["equivalence_failures"] == []
    assert result["coverage_failures"] == []

def test_phase8_exact_bangla_reminder_matches_english_route():
    result = evaluate(cases())
    by_id = {item["id"]: item for item in result["results"]}
    assert by_id["reminder-bn"]["actual"] == by_id["reminder-en"]["actual"]

def test_phase8_code_mixed_email_ready_is_draft_not_send_authority():
    result = evaluate(cases())
    by_id = {item["id"]: item for item in result["results"]}
    mixed = by_id["email-draft-mixed"]["actual"]
    assert mixed["execution"] == "agent_run"
    assert mixed["capability"] == "email"
    assert mixed["tools"] == ["email.draft"]
    assert mixed["consequential"] is False

def test_phase8_multilingual_transaction_keeps_same_consequential_boundary():
    result = evaluate(cases())
    tx = [item for item in result["results"] if item["equivalence"] == "flight_booking"]
    assert tx
    assert all(item["actual"]["execution"] == "transactions" for item in tx)
    assert all(item["actual"]["capability"] == "transactions" for item in tx)
    assert all(item["actual"]["consequential"] is True for item in tx)
    assert all(item["actual"]["reason_code"] == "transaction_intent" for item in tx)

def test_phase8_equivalence_gate_detects_route_drift():
    value = deepcopy(cases())
    case = next(item for item in value if item["id"] == "reminder-bn")
    case["goal"] = "Create a project memo."
    result = evaluate(value)
    assert "reminder-bn" in result["failures"]
    assert "reminder" in result["equivalence_failures"]
