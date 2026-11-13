import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import scripts.coworker_quality_eval as quality
from scripts.coworker_quality_eval import evaluate_live, evaluate_offline, live_settings, load_cases, score, strings

CASES=Path("tests/fixtures/coworker_quality_eval_cases.jsonl")

def loaded(): return load_cases(CASES)

def test_curated_multilingual_quality_fixture_passes():
    cases=loaded()
    r=evaluate_offline(cases)
    assert len(cases)>=10
    assert r["pass_rate"]==1.0
    assert r["required_fact_recall"]==1.0
    assert r["citation_source_precision"]==1.0
    assert r["citation_source_recall"]==1.0
    assert r["languages"]==["ar","bn","en","es"]
    assert r["by_language"]["bn"]["pass_rate"]==1.0
    assert r["by_language"]["en"]["pass_rate"]==1.0
    assert r["by_language"]["ar"]["required_fact_recall"]==1.0
    assert {"analysis_research","code","image_prompt","structured_data","creative_writing","summarisation","long_form_report","complex_planning"}.issubset(set(r["task_types"]))

def test_day6_two_workflow_quality_contracts_are_fail_closed():
    cases = {case["id"]: case for case in loaded()}
    research = cases["day6-bn-three-study-comparison"]
    report = cases["day6-en-reviewed-report-unsent-email"]
    assert score(research, research["draft"])["passed"]
    assert score(report, report["draft"])["passed"]
    assert {citation["source_id"] for finding in research["draft"]["findings"]
            for citation in finding["citations"]} == {"web-1", "web-2", "web-3"}
    assert report["draft"]["missing_information"] == ["Email recipient was not provided."]

    lost_paper = deepcopy(research["draft"])
    lost_paper["findings"].pop()
    assert not score(research, lost_paper)["checks"]["required_source_coverage"]

    invented_quote = deepcopy(research["draft"])
    invented_quote["findings"][0]["citations"][0]["quote"] = "An unobserved clinical result."
    assert not score(research, invented_quote)["checks"]["citation_validation"]

    missing_recipient_hidden = deepcopy(report["draft"])
    missing_recipient_hidden["missing_information"] = []
    assert not score(report, missing_recipient_hidden)["checks"]["missing_information_contract"]

    reported_as_sent = deepcopy(report["draft"])
    reported_as_sent["email"]["body"] += " Email was sent."
    assert not score(report, reported_as_sent)["checks"]["forbidden_claim_absence"]


def test_rejects_unsupported_claim():
    c=deepcopy(loaded()[0]); c["draft"]["report"]["summary"]+=" Budget is USD 15,000."
    r=score(c,c["draft"]); assert not r["passed"]; assert "USD 15,000" in r["found_forbidden_terms"]

def test_rejects_unsupplied_source():
    c=deepcopy(loaded()[0]); c["draft"]["report"]["sections"][0]["source_ids"]=["invented"]
    r=score(c,c["draft"]); assert not r["checks"]["source_reference_valid"]

def test_requires_missing_information():
    c=deepcopy(next(x for x in loaded() if x["id"]=="career-en-missing")); c["draft"]["missing_information"]=[]
    r=score(c,c["draft"]); assert not r["checks"]["missing_information_contract"]

def test_preserves_no_decision_contract():
    c=deepcopy(next(x for x in loaded() if x["id"]=="meeting-ar-no-decision")); c["draft"]["decisions"]=[{"text":"تم اعتماد القرار","source_ids":["notes"]}]
    r=score(c,c["draft"]); assert "decisions" in r["empty_path_failures"]


def test_live_quality_uses_reported_deepseek_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-quality-candidate")
    assert live_settings().deepseek_model == "deepseek-quality-candidate"


def test_rejects_a_task_type_mismatch():
    c=deepcopy(loaded()[0])
    c["expected_task_type"]="creative_writing"
    r=score(c,c["draft"])
    assert not r["checks"]["task_type_match"]


def test_research_fact_recall_excludes_verbatim_evidence_quote():
    case = deepcopy(next(c for c in loaded() if c["id"] == "research-en-exact-evidence"))
    assert score(case, case["draft"])["passed"]

    # A citation can be perfectly real even when the generated comparison
    # omitted the numbers and update date. Those are not authored facts.
    case["draft"]["findings"][0]["text"] = (
        "The retrieved dataset page was reviewed, but this summary omitted the confirmed details."
    )
    result = score(case, case["draft"])
    assert result["checks"]["schema_valid"]
    assert result["checks"]["citation_validation"]
    assert result["checks"]["required_source_coverage"]
    assert not result["checks"]["required_fact_preservation"]
    assert {"120 records", "1 October 2026"}.issubset(result["missing_required_terms"])
    assert not result["passed"]


def test_research_forbidden_term_only_inside_source_quote_is_not_an_authored_claim():
    case = deepcopy(next(c for c in loaded() if c["id"] == "research-en-exact-evidence"))
    quote = "An incorrect report had once stated 150 records."
    case["sources"][0]["text"] += " " + quote
    case["draft"]["findings"][0]["citations"].append(
        {"source_id": "web-1", "quote": quote}
    )
    result = score(case, case["draft"])
    assert result["checks"]["citation_validation"]
    assert result["checks"]["forbidden_claim_absence"]
    assert result["passed"]


def test_rejects_a_research_quote_not_present_in_the_source():
    c=deepcopy(next(x for x in loaded() if x["skill_id"]=="research"))
    c["draft"]["findings"][0]["citations"][0]["quote"]="An invented statement that is not in the source."
    r=score(c,c["draft"])
    assert not r["checks"]["citation_validation"]



def test_numeric_structured_values_count_as_required_facts():
    case = deepcopy(next(
        item for item in loaded()
        if item["id"] == "spreadsheet-en-regional-orders"
    ))
    case["draft"]["rows"][0][1] = 120.0
    case["draft"]["rows"][1][1] = 80.0

    result = score(case, case["draft"])
    assert result["checks"]["required_fact_preservation"]

    changed = deepcopy(case["draft"])
    changed["rows"][0][1] = 121.0
    changed_result = score(case, changed)
    assert not changed_result["checks"]["required_fact_preservation"]
    assert "120" in changed_result["missing_required_terms"]
    assert strings(True) == []



def test_live_quality_stops_when_total_token_budget_is_exceeded(monkeypatch):
    cases = loaded()[:2]
    instances = []
    calls = []

    class FakeDraftModel:
        def __init__(self, _settings, skill_id):
            self.case = cases[len(instances)]
            self.skill_id = skill_id
            instances.append(self)

        def messages(self, _request, _sources):
            return [{"role": "user", "content": "synthetic evaluation"}]

        async def generate(self, _messages, _language, _source_ids):
            calls.append(self.skill_id)
            return SimpleNamespace(
                draft=SimpleNamespace(model_dump=lambda: self.case["draft"]),
                total_tokens=10,
                latency_ms=5,
                generation_metadata=lambda **kwargs: {
                    "model": "test-model",
                    "prompt_version": "test-v1",
                    **kwargs,
                },
            )

    monkeypatch.setattr(quality, "DeepSeekDraftModel", FakeDraftModel)
    result = asyncio.run(evaluate_live(
        cases,
        max_total_tokens=5,
        max_total_cost_microusd=100,
        cost_rate_microusd_per_1k_tokens=1000,
    ))

    assert calls == [cases[0]["skill_id"]]
    assert result["budget_failures"] == ["total_token_budget"]
    assert result["total_tokens"] == 10
    assert result["estimated_cost_microusd"] == 10
    assert result["evaluation_complete"] is False


def test_live_quality_stops_when_token_usage_is_missing(monkeypatch):
    cases = loaded()[:2]
    calls = []

    class FakeDraftModel:
        def __init__(self, _settings, skill_id):
            self.skill_id = skill_id

        def messages(self, _request, _sources):
            return [{"role": "user", "content": "synthetic evaluation"}]

        async def generate(self, _messages, _language, _source_ids):
            calls.append(self.skill_id)
            return SimpleNamespace(
                draft=SimpleNamespace(model_dump=lambda: cases[0]["draft"]),
                total_tokens=None,
                latency_ms=5,
                generation_metadata=lambda **kwargs: {"model": "test-model", **kwargs},
            )

    monkeypatch.setattr(quality, "DeepSeekDraftModel", FakeDraftModel)
    result = asyncio.run(evaluate_live(
        cases,
        max_total_tokens=1000,
        max_total_cost_microusd=100,
        cost_rate_microusd_per_1k_tokens=1000,
    ))

    assert len(calls) == 1
    assert result["token_usage_complete"] is False
    assert "token_usage_incomplete" in result["budget_failures"]
    assert result["estimated_cost_microusd"] is None


def test_live_quality_requires_reviewed_positive_cost_rate():
    with pytest.raises(ValueError, match="positive token, cost and reviewed rate"):
        asyncio.run(evaluate_live(
            loaded()[:1],
            max_total_tokens=1000,
            max_total_cost_microusd=100,
            cost_rate_microusd_per_1k_tokens=0,
        ))



def test_live_quality_retains_known_tokens_when_latency_evidence_is_invalid(monkeypatch):
    cases = loaded()[:1]

    class FakeDraftModel:
        def __init__(self, _settings, skill_id):
            self.skill_id = skill_id

        def messages(self, _request, _sources):
            return [{"role": "user", "content": "synthetic evaluation"}]

        async def generate(self, _messages, _language, _source_ids):
            return SimpleNamespace(
                draft=SimpleNamespace(model_dump=lambda: cases[0]["draft"]),
                total_tokens=10,
                latency_ms=-1,
                generation_metadata=lambda **kwargs: {"model": "test-model", **kwargs},
            )

    monkeypatch.setattr(quality, "DeepSeekDraftModel", FakeDraftModel)
    result = asyncio.run(evaluate_live(
        cases,
        max_total_tokens=1000,
        max_total_cost_microusd=100,
        cost_rate_microusd_per_1k_tokens=1000,
    ))

    assert result["token_usage_complete"] is True
    assert result["total_tokens"] == 10
    assert result["estimated_cost_microusd"] == 10
    assert "invalid_latency_metadata" in result["budget_failures"]
