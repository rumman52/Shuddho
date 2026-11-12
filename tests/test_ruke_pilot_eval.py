"""Day 9 evidence-harness regressions. Test data is synthetic, never a benchmark."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from scripts.ruke_pilot_eval import (
    OPERATED, RUBRIC, EvidenceError, compare, external_heldout,
    immutable_write, main, position_map, prepare_blind, registry_cases,
    score_reviews, validate_manifest, verify_operations,
)


def tasks():
    return [
        {"case_id": f"synthetic-{workflow}-{lang}-{i}",
         "workflow": workflow, "language": lang}
        for workflow in ("research_brief", "project_report_email")
        for lang in ("bn", "en") for i in range(10)
    ]


def manifest():
    return {
        "schema_version": 1,
        "split": "holdout",
        "candidate_revision": "a" * 40,
        "corpus_sha256": "b" * 64,
        "source_set_sha256": "c" * 64,
        "candidate_product_version": "test-1",
        "candidate_model": "synthetic",
        "prompt_version": "synthetic-v1",
        "tool_version": "test-v1",
        "run_started_at": "2026-11-12T00:00:00Z",
        "time_limit_seconds": 60,
    }


def reviews_and_checks(cases=None):
    cases = cases or tasks()
    reviews, checks = [], []
    for c in cases:
        cid = c["case_id"]
        checks.append({"case_id": cid, "passed": True, "security_passed": True,
                       "output_sha256": "d" * 64})
        for reviewer in ("D1", "D2"):
            reviews.append({"case_id": cid, "reviewer_id": reviewer,
                            "scores": dict.fromkeys(RUBRIC, 2),
                            "source_supported": True, "evidence_note": "Fixture rationale"})
    return reviews, checks


def operations():
    return [
        {"row": i, "scenario": scenario, "candidate_revision": "a" * 40,
         "status": "pass", "execution": "operated",
         "unauthorized_access": False, "unauthorized_mutation": False,
         "trace_sha256": "e" * 64, "observed_at": "2026-11-12T00:00:00Z",
         "boundaries": {k: {"mode": "real", "instance": "synthetic-test-instance",
                           "trace_sha256": "f" * 64} for k in boundaries}}
        for i, (scenario, boundaries) in OPERATED.items()
    ]


def comparator():
    return {
        "product": "synthetic comparator", "product_version": "test-2026",
        "model": "synthetic", "run_started_at": "2026-11-12T00:00:00Z",
        "source_set_sha256": "c" * 64, "time_limit_seconds": 60,
    }


def blind_votes(cases=None):
    cases = cases or tasks()
    m = manifest()
    rows = []
    for case in cases:
        cid = case["case_id"]
        for position in ("AB", "BA"):
            mapping = position_map(cid, m["corpus_sha256"])[position]
            chosen = "A" if mapping[0] == "candidate" else "B"
            for reviewer in ("D1", "D2"):
                rows.append({"case_id": cid, "position": position, "reviewer_id": reviewer,
                             "preference": chosen, "evidence_note": "Factual support"})
    return rows


def test_development_registry_balanced_bound_to_real_existing_suite():
    cases = registry_cases()
    assert len(cases) == 40
    assert all(c["split"] == "development" and "expected_facts" not in c for c in cases)
    assert {c["language"] for c in cases} == {"bn", "en"}
    assert {c["workflow"] for c in cases} == {"research_brief", "project_report_email"}


def test_external_holdout_must_be_outside_repo_and_match_frozen_sha(tmp_path):
    held = tmp_path / "independent-test-only.jsonl"
    held.write_text("\n".join(json.dumps(x) for x in tasks()) + "\n")
    digest = hashlib.sha256(held.read_bytes()).hexdigest()
    assert len(external_heldout(held, corpus_sha256=digest)) == 40
    with pytest.raises(EvidenceError, match="hash mismatch"):
        external_heldout(held, corpus_sha256="0" * 64)
    with pytest.raises(EvidenceError, match="separate"):
        external_heldout(held, corpus_sha256=digest, repo_root=tmp_path)
    m = manifest()
    m["corpus_sha256"] = digest
    assert validate_manifest(m, held) == tasks()


def test_holdout_matrix_and_answer_key_prohibited(tmp_path):
    held = tmp_path / "test.jsonl"
    rows = tasks()
    rows[0]["expected_facts"] = [{"secret": "no"}]
    held.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    with pytest.raises(EvidenceError, match="answer keys"):
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest())
    rows[0].pop("expected_facts")
    rows[1]["case_id"] = rows[0]["case_id"]
    held.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    with pytest.raises(EvidenceError, match="distinct"):
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest())


def test_two_reviewers_full_rubric_accept_all_synthetic_cases():
    reviews, checks = reviews_and_checks()
    result = score_reviews(tasks(), reviews, [], checks)
    assert result["accepted"] == 40 and result["outcome_gate_pass"]
    assert len(result["by_cell"]) == 4
    assert all(x["accepted"] == 10 for x in result["by_cell"].values())


def test_no_zero_and_score_seven_required():
    reviews, checks = reviews_and_checks()
    for row in reviews:
        if row["case_id"] == tasks()[0]["case_id"]:
            row["scores"][RUBRIC[0]] = 0
    result = score_reviews(tasks(), reviews, [], checks)
    assert result["accepted"] == 39
    assert not result["results"][0]["accepted"]
    assert result["outcome_gate_pass"]  # other cases still meet 36/40, >=9/cell
    for row in reviews:
        if row["case_id"] == tasks()[1]["case_id"]:
            row["scores"][RUBRIC[0]] = 1
            row["scores"][RUBRIC[1]] = 1
    result = score_reviews(tasks(), reviews, [], checks)
    assert result["accepted"] == 38


def test_per_cell_gate_stricter_than_global():
    reviews, checks = reviews_and_checks()
    for row in reviews:
        if row["case_id"] in (tasks()[0]["case_id"], tasks()[1]["case_id"]):
            row["scores"][RUBRIC[0]] = 0
    result = score_reviews(tasks(), reviews, [], checks)
    assert result["accepted"] == 38 and not result["outcome_gate_pass"]


def test_unsupported_source_or_failed_security_cannot_be_outweighed():
    reviews, checks = reviews_and_checks()
    for row in reviews:
        if row["case_id"] == tasks()[0]["case_id"]:
            row["source_supported"] = False
    checks[1]["security_passed"] = False
    result = score_reviews(tasks(), reviews, [], checks)
    assert not result["results"][0]["accepted"]
    assert not result["results"][1]["accepted"]


def test_missing_or_duplicate_reviewers_and_bad_rubric_block():
    reviews, checks = reviews_and_checks()
    with pytest.raises(EvidenceError, match="exactly two"):
        score_reviews(tasks(), reviews[:-1], [], checks)
    bad = deepcopy(reviews)
    bad[0]["reviewer_id"] = "D2"
    with pytest.raises(EvidenceError, match="independent"):
        score_reviews(tasks(), bad, [], checks)
    bad = deepcopy(reviews)
    bad[0]["scores"][RUBRIC[0]] = True
    with pytest.raises(EvidenceError, match="four integers"):
        score_reviews(tasks(), bad, [], checks)


def test_adjudication_required_and_third_reviewer_must_be_separate():
    reviews, checks = reviews_and_checks()
    reviews[0]["scores"][RUBRIC[0]] = 1
    with pytest.raises(EvidenceError, match="wrong number"):
        score_reviews(tasks(), reviews, [], checks)
    adjudication = [{"case_id": tasks()[0]["case_id"], "adjudicator_id": "D3",
                     "scores": dict.fromkeys(RUBRIC, 2),
                     "source_supported": True, "evidence_note": "Evidence reconciled"}]
    assert score_reviews(tasks(), reviews, adjudication, checks)["disagreements_adjudicated"] == 1
    adjudication[0]["adjudicator_id"] = "D1"
    with pytest.raises(EvidenceError, match="separate adjudicator"):
        score_reviews(tasks(), reviews, adjudication, checks)


def test_operated_twenty_require_real_boundary_envelopes_and_no_unauthorized_effects():
    assert verify_operations(operations(), "a" * 40)["passed"] == 20
    rows = operations()
    del rows[10]["boundaries"]["temporal"]
    assert verify_operations(rows, "a" * 40)["failed_rows"] == [11]
    rows = operations()
    rows[1]["unauthorized_access"] = True
    assert verify_operations(rows, "a" * 40)["failed_rows"] == [2]
    rows = operations()
    rows[19]["status"] = "pending"
    assert verify_operations(rows, "a" * 40)["failed_rows"] == [20]


def test_operated_rows_reject_revision_mismatch_or_missing_row():
    rows = operations()
    with pytest.raises(EvidenceError, match="revision"):
        verify_operations(rows, "b" * 40)
    with pytest.raises(EvidenceError, match="wrong number"):
        verify_operations(rows[:-1], "a" * 40)


def test_position_swap_deterministic_and_disjoint():
    mapping = position_map("synthetic", "b" * 64)
    assert mapping["AB"] == tuple(reversed(mapping["BA"]))
    assert set(mapping["AB"]) == {"candidate", "competitor"}


def test_blind_comparison_rejects_missing_access_and_noncomparable_sources():
    assert not compare(tasks(), manifest(), None, None)["complete"]
    bad = comparator()
    bad["source_set_sha256"] = "9" * 64
    with pytest.raises(EvidenceError, match="comparable"):
        compare(tasks(), manifest(), bad, blind_votes())


def test_blind_comparison_uses_both_reviewers_and_swapped_positions():
    result = compare(tasks(), manifest(), comparator(), blind_votes())
    assert result["complete"] and result["wins"] == 40
    assert result["ties"] == result["losses"] == 0
    bad = blind_votes()[:-1]
    with pytest.raises(EvidenceError, match="both swapped"):
        compare(tasks(), manifest(), comparator(), bad)


def test_blind_disagreement_detected_instead_of_silent_vote_merge():
    bad = blind_votes()
    bad[0]["preference"] = "B" if bad[0]["preference"] == "A" else "A"
    result = compare(tasks(), manifest(), comparator(), bad)
    assert not result["complete"]
    assert result["position_swap_inconsistent_cases"] == [tasks()[0]["case_id"]]


def test_packet_has_both_positions_without_product_labels(tmp_path):
    values = [{"case_id": c["case_id"], "output": "candidate text"} for c in tasks()]
    other = [{"case_id": c["case_id"], "output": "competitor text"} for c in tasks()]
    packet = prepare_blind(tasks(), manifest(), values, other)
    assert len(packet) == 80
    for row in packet:
        assert row["response_a"] != row["response_b"]
        assert set(row) == {"case_id", "position", "response_a", "response_b"}


def test_first_run_evidence_never_overwritten(tmp_path):
    target = tmp_path / "first-run.json"
    digest = immutable_write(target, {"pass": False})
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        immutable_write(target, {"pass": True})
    assert json.loads(target.read_text()) == {"pass": False}


def test_cli_blocks_missing_independent_inputs(capsys):
    assert main(["validate-registry"]) == 0
    assert main(["evaluate"]) == 2
    assert "external frozen manifest" in capsys.readouterr().out


def test_fixture_is_not_a_production_operated_result():
    # The test creates syntactically valid envelopes but no PostgreSQL or
    # Temporal calls. The production evaluator explicitly marks these as
    # operator-submitted and never independently verified.
    faults = verify_operations(operations(), "a" * 40)
    assert faults["evidence_level"].startswith("operator_submitted")
