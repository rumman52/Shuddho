from copy import deepcopy
from pathlib import Path
from scripts.coworker_quality_eval import evaluate_offline, live_settings, load_cases, score

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
