from copy import deepcopy
from pathlib import Path
from scripts.coworker_quality_eval import evaluate_offline, load_cases, score

CASES=Path("tests/fixtures/coworker_quality_eval_cases.jsonl")

def loaded(): return load_cases(CASES)

def test_curated_multilingual_quality_fixture_passes():
    r=evaluate_offline(loaded())
    assert r["pass_rate"]==1.0
    assert r["required_fact_recall"]==1.0
    assert r["languages"]==["ar","bn","en","es"]

def test_rejects_unsupported_claim():
    c=deepcopy(loaded()[0]); c["draft"]["report"]["summary"]+=" Budget is USD 15,000."
    r=score(c,c["draft"]); assert not r["passed"]; assert "USD 15,000" in r["found_forbidden_terms"]

def test_rejects_unsupplied_source():
    c=deepcopy(loaded()[0]); c["draft"]["report"]["sections"][0]["source_ids"]=["invented"]
    r=score(c,c["draft"]); assert not r["checks"]["source_reference_valid"]

def test_requires_missing_information():
    c=deepcopy(loaded()[-1]); c["draft"]["missing_information"]=[]
    r=score(c,c["draft"]); assert not r["checks"]["missing_information_contract"]

def test_preserves_no_decision_contract():
    c=deepcopy(next(x for x in loaded() if x["id"]=="meeting-ar-no-decision")); c["draft"]["decisions"]=[{"text":"تم اعتماد القرار","source_ids":["notes"]}]
    r=score(c,c["draft"]); assert "decisions" in r["empty_path_failures"]
