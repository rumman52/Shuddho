from scripts.agent_eval import evaluate_offline, load_cases
from scripts.staging_gate import REQUIRED_GATES, evaluate


def test_agent_eval_fixture_passes_offline_contract():
    cases = load_cases(__import__("pathlib").Path("tests/fixtures/agent_eval_cases.jsonl"))
    result = evaluate_offline(cases)
    assert result["pass_rate"] == 1.0
    assert result["failed"] == 0


def test_staging_gate_is_no_go_without_live_evidence():
    result = evaluate({}, require_research=True, require_actions=True)
    assert result["decision"] == "NO-GO"
    assert "model" in result["missing"]
    assert "quality" in result["missing"]
    assert "research" in result["missing"]
    assert "actions" in result["missing"]


def test_staging_gate_go_requires_every_requested_check():
    required = {
        "ci", "identity", "database", "storage", "temporal", "model", "quality", "backup_restore",
        "deletion", "parallel_restart", "fan_in", "flag_rollback", "research", "actions", "microsoft_actions",
    }
    evidence = {key: {"status": "passed", "evidence": "staging-verification"} for key in required}
    result = evaluate(
        evidence,
        require_research=True,
        require_actions=True,
        require_microsoft_actions=True,
    )
    assert result["decision"] == "GO"
    assert result["missing"] == []


def test_microsoft_staging_gate_is_independent_from_google_actions():
    required = set(REQUIRED_GATES)
    evidence = {
        key: {"status": "passed", "evidence": "staging-verification"}
        for key in required
    }
    evidence["actions"] = {
        "status": "passed",
        "evidence": "google actions passed",
    }
    result = evaluate(
        evidence,
        require_research=False,
        require_actions=True,
        require_microsoft_actions=True,
    )
    assert result["decision"] == "NO-GO"
    assert result["missing"] == ["microsoft_actions"]

    evidence["microsoft_actions"] = {
        "status": "passed",
        "evidence": "microsoft actions passed",
    }
    result = evaluate(
        evidence,
        require_research=False,
        require_actions=True,
        require_microsoft_actions=True,
    )
    assert result["decision"] == "GO"


def test_action_selection_staging_gate_is_independent():
    evidence = {
        key: {"status": "passed", "evidence": "staging-verification"}
        for key in REQUIRED_GATES
    }
    result = evaluate(
        evidence,
        require_research=False,
        require_actions=False,
        require_action_selection=True,
    )
    assert result["decision"] == "NO-GO"
    assert result["missing"] == ["action_selection"]

    evidence["action_selection"] = {
        "status": "passed",
        "evidence": "opaque handle selection paused for approval",
    }
    result = evaluate(
        evidence,
        require_research=False,
        require_actions=False,
        require_action_selection=True,
    )
    assert result["decision"] == "GO"
