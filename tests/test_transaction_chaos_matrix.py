"""Fail-closed tests for the CW-02 scenario inventory."""
from scripts.transaction_chaos_matrix import SCENARIOS, qualify


def evidence():
    return {
        "schema_version": 1, "source_revision": "reviewed-head", "rollout_id": "staging-42",
        "scenarios": [
            {"id": name, "result": "passed", "environment": "staging",
             "test_run_id": f"run-{i}", "evidence_sha256": "a" * 64,
             "operator": "staging-test", "observed_at": "2026-10-12T00:00:00Z",
             "attempted_mutations": 1, "applied_mutations": 1, "outcome": "recovered"}
            for i, name in enumerate(SCENARIOS)
        ],
    }


def check(doc):
    return qualify(doc, expected_revision="reviewed-head", expected_rollout="staging-42")


def test_sixteen_unique_scenarios():
    assert len(SCENARIOS) == len(set(SCENARIOS)) == 16


def test_missing_and_duplicate_scenarios_rejected():
    doc = evidence()
    doc["scenarios"][-1] = doc["scenarios"][0]
    reasons = check(doc)
    assert any("duplicate scenario" in r for r in reasons)
    assert any("missing scenario" in r for r in reasons)


def test_revision_and_rollout_bound():
    doc = evidence()
    doc["source_revision"] = "other"
    doc["rollout_id"] = "other"
    assert "source_revision mismatch" in check(doc)
    assert "rollout_id mismatch" in check(doc)


def test_reject_bad_mutation_counter_and_digest():
    doc = evidence()
    doc["scenarios"][0]["applied_mutations"] = 2
    doc["scenarios"][0]["evidence_sha256"] = "bad"
    assert any("invalid mutation counters" in r for r in check(doc))
    assert any("evidence_sha256" in r for r in check(doc))


def test_reject_unqualified_or_nonstaging():
    doc = evidence()
    doc["scenarios"][0]["result"] = "pending"
    doc["scenarios"][1]["environment"] = "unit_test"
    assert any("result is not passed" in r for r in check(doc))
    assert any("staging environment" in r for r in check(doc))


def test_complete_structure_does_not_prove_real_qualification():
    assert check(evidence()) == []
