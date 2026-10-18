"""Synthetic CW-02 evidence tests; passing locally does not certify live staging."""
import hashlib
import json
from scripts.transaction_chaos_matrix import (
    SCENARIOS, SCENARIO_CONTRACTS, NO_APPLIED_MUTATION, NO_DISPATCH, qualify, verify_evidence_files,
)


SAMPLE_CASES = {
    "model_429": (0, 0, "blocked"),
    "model_500": (0, 0, "blocked"),
    "model_timeout": (0, 0, "blocked"),
    "provider_401": (1, 0, "failed"),
    "provider_403": (1, 0, "failed"),
    "provider_429": (1, 0, "failed"),
    "provider_500": (1, 1, "uncertain"),
    "malformed_response": (1, 1, "uncertain"),
    "database_disconnect": (1, 1, "recovered"),
    "s3_disconnect": (0, 0, "failed"),
    "temporal_outage": (1, 1, "recovered"),
    "worker_crash": (1, 1, "recovered"),
    "api_crash": (0, 0, "recovered"),
    "duplicate_message": (0, 0, "recovered"),
    "lost_provider_response": (1, 1, "uncertain"),
    "approval_after_expiration": (0, 0, "blocked"),
}


def evidence():
    return {
        "schema_version": 1, "source_revision": "reviewed-head", "rollout_id": "staging-42",
        "scenarios": [
            {
                "id": name, "result": "passed", "environment": "staging",
                "test_run_id": f"run-{i}", "evidence_sha256": "a" * 64,
                "operator": "staging-test", "observed_at": "2026-10-12T00:00:00Z",
                "attempted_mutations": SAMPLE_CASES[name][0],
                "applied_mutations": SAMPLE_CASES[name][1],
                "outcome": SAMPLE_CASES[name][2],
                "evidence_file": f"{name}.json",
            }
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


def _bundle(tmp_path, doc):
    for row in doc["scenarios"]:
        data = {
            "scenario_id": row["id"], "source_revision": doc["source_revision"],
            "rollout_id": doc["rollout_id"], "test_run_id": row["test_run_id"],
            "observed_at": row["observed_at"],
            "attempted_mutations": row["attempted_mutations"],
            "applied_mutations": row["applied_mutations"],
            "outcome": row["outcome"],
            "provider_observation_source": "provider_sandbox",
            "provider_observation_reference": "synthetic-" + row["id"],
        }
        raw = json.dumps(data, sort_keys=True).encode()
        (tmp_path / row["evidence_file"]).write_bytes(raw)
        row["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    return doc


def test_applied_mutations_cannot_exceed_provider_dispatch():
    doc = evidence()
    doc["scenarios"][0]["applied_mutations"] = 1
    assert any("exceed attempts" in e for e in check(doc))


def test_denials_and_failed_model_decisions_never_mutate():
    for name in NO_APPLIED_MUTATION:
        doc = evidence()
        row = next(x for x in doc["scenarios"] if x["id"] == name)
        row["applied_mutations"] = 1
        assert any("expected zero applied" in e for e in check(doc))
    doc = evidence()
    next(x for x in doc["scenarios"] if x["id"] == "model_timeout")["attempted_mutations"] = 1
    assert any("expected zero provider dispatch" in e for e in check(doc))


def test_lost_provider_response_requires_one_submission_and_application():
    doc = evidence()
    next(x for x in doc["scenarios"] if x["id"] == "lost_provider_response")["applied_mutations"] = 0
    assert any("one submission" in e for e in check(doc))


def test_manifest_rejects_reused_run_and_invalid_timestamp():
    doc = evidence()
    doc["scenarios"][1]["test_run_id"] = doc["scenarios"][0]["test_run_id"]
    doc["scenarios"][0]["observed_at"] = "yesterday"
    assert any("duplicate test_run_id" in e for e in check(doc))
    assert any("timezone" in e for e in check(doc))


def test_hash_checked_synthetic_evidence_and_modified_body(tmp_path):
    doc = _bundle(tmp_path, evidence())
    assert check(doc) == []
    assert verify_evidence_files(doc, tmp_path) == []
    target = tmp_path / "provider_500.json"
    target.write_bytes(target.read_bytes() + b" ")
    assert any("hash mismatch" in e for e in verify_evidence_files(doc, tmp_path))


def test_evidence_identity_mismatch_rejected_even_if_hash_updated(tmp_path):
    doc = _bundle(tmp_path, evidence())
    target = tmp_path / "provider_500.json"
    data = json.loads(target.read_bytes())
    data["rollout_id"] = "different"
    raw = json.dumps(data).encode()
    target.write_bytes(raw)
    next(x for x in doc["scenarios"] if x["id"] == "provider_500")["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    assert any("identity/counter mismatch" in e for e in verify_evidence_files(doc, tmp_path))


def test_missing_or_symlink_evidence_rejected(tmp_path):
    doc = _bundle(tmp_path, evidence())
    target = tmp_path / "provider_500.json"
    target.unlink()
    assert any("missing or unsafe" in e for e in verify_evidence_files(doc, tmp_path))
    target.symlink_to(tmp_path / "model_429.json")
    assert any("missing or unsafe" in e for e in verify_evidence_files(doc, tmp_path))


def test_no_evidence_directory_fails_closed(tmp_path):
    assert "evidence directory does not exist" in verify_evidence_files(evidence(), tmp_path / "missing")


def test_contract_table_covers_all_scenarios_and_all_allowed_pairs_have_outcomes():
    assert set(SCENARIO_CONTRACTS) == set(SCENARIOS)
    for name, contract in SCENARIO_CONTRACTS.items():
        assert contract["allowed_counts"]
        assert set(contract["allowed_counts"]) == set(contract["outcomes_by_counts"])
        for pair in contract["allowed_counts"]:
            assert pair.count(":") == 1
            attempts, applied = (int(value) for value in pair.split(":"))
            assert attempts >= 0 and 0 <= applied <= attempts <= 1
            assert contract["outcomes_by_counts"][pair]


@pytest.mark.parametrize(
    "name,attempts,applied,outcome",
    [
        ("model_429", 1, 0, "failed"),
        ("provider_401", 1, 1, "failed"),
        ("provider_429", 2, 0, "failed"),
        ("provider_500", 1, 1, "confirmed"),
        ("malformed_response", 1, 1, "recovered"),
        ("database_disconnect", 1, 0, "recovered"),
        ("s3_disconnect", 1, 1, "confirmed"),
        ("temporal_outage", 0, 0, "recovered"),
        ("worker_crash", 1, 0, "uncertain"),
        ("api_crash", 1, 1, "recovered"),
        ("duplicate_message", 0, 0, "confirmed"),
        ("lost_provider_response", 1, 1, "recovered"),
        ("approval_after_expiration", 1, 0, "blocked"),
    ],
)
def test_scenario_contract_rejects_impossible_counts_or_outcomes(name, attempts, applied, outcome):
    doc = evidence()
    row = next(item for item in doc["scenarios"] if item["id"] == name)
    row["attempted_mutations"] = attempts
    row["applied_mutations"] = applied
    row["outcome"] = outcome
    problems = check(doc)
    assert any(name in problem and ("mutation counts" in problem or "outcome" in problem)
               for problem in problems), problems
