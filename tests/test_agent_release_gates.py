from scripts.agent_eval import evaluate_offline, load_cases
from scripts.staging_gate import evaluate


def test_agent_eval_fixture_passes_offline_contract():
    cases = load_cases(__import__("pathlib").Path("tests/fixtures/agent_eval_cases.jsonl"))
    result = evaluate_offline(cases)
    assert result["pass_rate"] == 1.0
    assert result["failed"] == 0


def test_staging_gate_is_no_go_without_live_evidence():
    result = evaluate({}, require_research=True, require_actions=True)
    assert result["decision"] == "NO-GO"
    assert "model" in result["missing"]
    assert "research" in result["missing"]
    assert "actions" in result["missing"]


def test_staging_gate_go_requires_every_requested_check():
    required = {
        "ci", "identity", "database", "storage", "temporal", "model", "backup_restore",
        "deletion", "parallel_restart", "fan_in", "flag_rollback", "research", "actions",
    }
    evidence = {key: {"status": "passed", "evidence": "staging-verification"} for key in required}
    result = evaluate(evidence, require_research=True, require_actions=True)
    assert result["decision"] == "GO"
    assert result["missing"] == []
