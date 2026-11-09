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
