"""Day 9 evidence-harness regressions. Test data is synthetic, never a benchmark."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from scripts.ruke_pilot_eval import (
    OPERATED, RUBRIC, EvidenceError, compare, external_heldout,
    candidate_ledger, immutable_write, main, position_map, prepare_blind, registry_cases,
    read_blinding_key,
    score_reviews, validate_manifest, verify_operations,
)


BLIND_KEY = b"m" * 32  # Synthetic TEST secret; never use for operated comparisons.


def tasks():
    return [
        {"case_id": f"synthetic-{workflow}-{lang}-{i}",
         "workflow": workflow, "language": lang,
         "instruction": "Synthetic source-grounded task for harness testing only",
         "source_id": "synthetic-source", "citation_id": "web-1",
         "source_sha256": "f" * 64, "max_output_bytes": 24000}
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
            mapping = position_map(cid, m["corpus_sha256"], blinding_key=BLIND_KEY)[position]
            chosen = "A" if mapping[0] == "candidate" else "B"
            for reviewer in ("D1", "D2"):
                rows.append({"case_id": cid, "position": position, "reviewer_id": reviewer,
                             "preference": chosen, "evidence_note": "Factual support"})
    return rows


@pytest.fixture
def external_dir():
    # This repository intentionally redirects pytest tmp_path into the checkout.
    # External custody validation must exercise a path genuinely outside it.
    with tempfile.TemporaryDirectory(prefix="ruke-day9-test-", dir="/tmp") as folder:
        yield Path(folder)


def test_development_registry_balanced_bound_to_real_existing_suite():
    cases = registry_cases()
    assert len(cases) == 40
    assert all(c["split"] == "development" and "expected_facts" not in c for c in cases)
    assert {c["language"] for c in cases} == {"bn", "en"}
    assert {c["workflow"] for c in cases} == {"research_brief", "project_report_email"}


def test_registry_rejects_instruction_or_source_digest_rewrite(tmp_path):
    from scripts.ruke_pilot_eval import REGISTRY
    rows = [json.loads(line) for line in REGISTRY.read_text().splitlines() if line]
    rows[0]["instruction"] += " Unreviewed instruction injection."
    target = tmp_path / "rewritten-registry.jsonl"
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n")
    with pytest.raises(EvidenceError, match="binding changed"):
        registry_cases(target)
    rows[0]["instruction"] = [json.loads(line) for line in REGISTRY.read_text().splitlines() if line][0]["instruction"]
    rows[0]["source_sha256"] = "0" * 64
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n")
    with pytest.raises(EvidenceError, match="binding changed"):
        registry_cases(target)


def test_external_holdout_missing_prompt_and_source_is_rejected(external_dir):
    rows = tasks()
    rows[0].pop("instruction")
    held = external_dir / "incomplete-tasks.jsonl"
    held.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    held.chmod(0o444)
    with pytest.raises(EvidenceError, match="instruction/source contract"):
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest())


def test_external_holdout_must_be_outside_repo_and_match_frozen_sha(external_dir):
    held = external_dir / "independent-test-only.jsonl"
    held.write_text("\n".join(json.dumps(x) for x in tasks()) + "\n")
    digest = hashlib.sha256(held.read_bytes()).hexdigest()
    with pytest.raises(EvidenceError, match="read-only"):
        external_heldout(held, corpus_sha256=digest)
    held.chmod(0o444)
    assert len(external_heldout(held, corpus_sha256=digest)) == 40
    with pytest.raises(EvidenceError, match="hash mismatch"):
        external_heldout(held, corpus_sha256="0" * 64)
    with pytest.raises(EvidenceError, match="separate"):
        external_heldout(held, corpus_sha256=digest, repo_root=external_dir)
    m = manifest()
    m["corpus_sha256"] = digest
    assert validate_manifest(m, held) == tasks()


def test_holdout_matrix_and_answer_key_prohibited(external_dir):
    held = external_dir / "test.jsonl"
    rows = tasks()
    rows[0]["expected_facts"] = [{"secret": "no"}]
    held.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    held.chmod(0o444)
    with pytest.raises(EvidenceError, match="answer keys"):
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest())
    rows[0].pop("expected_facts")
    rows[1]["case_id"] = rows[0]["case_id"]
    held.chmod(0o644)
    held.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    held.chmod(0o444)
    with pytest.raises(EvidenceError, match="distinct"):
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest())


def test_candidate_outputs_bound_to_exact_bytes_and_unknown_usage():
    # Reuse *development* calibration shapes only to exercise schema validation,
    # not as holdout outcomes or as model-generated quality evidence.
    from scripts.pilot_workflow_eval import load_suite
    suite = load_suite()
    reference = {row["case_id"]: row["draft"] for row in suite["reference_outputs"]}
    per_cell = {}
    for task in suite["cases"]:
        if task["split"] == "development":
            per_cell.setdefault((task["workflow"], task["language"]), reference[task["id"]])
    rows = [{"case_id": task["case_id"],
             "output": deepcopy(per_cell[(task["workflow"], task["language"])])}
            for task in tasks()]
    hashes, usage = candidate_ledger(tasks(), rows)
    assert len(hashes) == 40 and usage["reported_cost_microusd"] is None
    reviews, checks = reviews_and_checks()
    for row in checks:
        row["output_sha256"] = hashes[row["case_id"]]
    assert score_reviews(tasks(), reviews, [], checks, output_hashes=hashes)["accepted"] == 40
    checks[0]["output_sha256"] = "0" * 64
    with pytest.raises(EvidenceError, match="not bound"):
        score_reviews(tasks(), reviews, [], checks, output_hashes=hashes)
    for row in rows:
        row["telemetry"] = {"tokens": 3, "latency_ms": 12, "cost_microusd": 10}
    hashes, usage = candidate_ledger(tasks(), rows)
    assert usage["usage_complete"] and usage["reported_cost_microusd"] == 400
    rows[0]["telemetry"]["tokens"] = False
    with pytest.raises(EvidenceError, match="telemetry"):
        candidate_ledger(tasks(), rows)
    rows[0]["telemetry"]["tokens"] = 3
    rows[0]["output"]["output_language"] = "xx"
    with pytest.raises(EvidenceError, match="language/citation"):
        candidate_ledger(tasks(), rows)
    rows[0]["output"] = {}
    with pytest.raises(EvidenceError, match="production draft schema"):
        candidate_ledger(tasks(), rows)


def test_external_holdout_rejects_exposed_development_prompt_and_source(external_dir):
    # Renaming a development task does not create genuinely unseen test data.
    cases = tasks()
    exposed = registry_cases()[0]
    matching = next(row for row in cases
                    if row["workflow"] == exposed["workflow"]
                    and row["language"] == exposed["language"])
    matching["instruction"] = exposed["instruction"]
    matching["source_sha256"] = exposed["source_sha256"]
    path = external_dir / "relabelled-development-task.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in cases) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.chmod(0o444)
    with pytest.raises(EvidenceError, match="exposed"):
        external_heldout(path, corpus_sha256=digest)


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


def test_rubric_rejects_missing_or_impersonated_third_adjudicator():
    cases = tasks()
    reviews, checks = reviews_and_checks(cases)
    reviews[0]["scores"][RUBRIC[0]] = 1
    for fake in (None, "", " ", "D1 ", "d1", "D２"):
        resolution = [{"case_id": cases[0]["case_id"], "adjudicator_id": fake,
                       "scores": dict.fromkeys(RUBRIC, 2),
                       "source_supported": True, "evidence_note": "Synthetic reasoning"}]
        with pytest.raises(EvidenceError, match="separate adjudicator"):
            score_reviews(cases, reviews, resolution, checks)


def test_rubric_rejects_casefolded_duplicate_reviewer_identity():
    reviews, checks = reviews_and_checks()
    for row in reviews:
        if row["reviewer_id"] == "D2":
            row["reviewer_id"] = "d1"
    with pytest.raises(EvidenceError, match="independent"):
        score_reviews(tasks(), reviews, [], checks)


def test_blind_votes_reject_casefolded_duplicate_reviewer_and_adjudicator_alias():
    votes = blind_votes()
    for row in votes:
        if row["reviewer_id"] == "D2":
            row["reviewer_id"] = "d1"
    with pytest.raises(EvidenceError, match="duplicate|reviewers"):
        compare(tasks(), manifest(), comparator(), votes, blinding_key=BLIND_KEY)

    votes = blind_votes()
    votes[0]["preference"] = "B" if votes[0]["preference"] == "A" else "A"
    cid = tasks()[0]["case_id"]
    for fake in ("D1 ", "d1", "D２"):
        resolution = [{"case_id": cid, "adjudicator_id": fake, "position": "AB",
                       "preference": "tie", "evidence_note": "Synthetic rationale"}]
        with pytest.raises(EvidenceError, match="independent third"):
            compare(tasks(), manifest(), comparator(), votes, resolution, blinding_key=BLIND_KEY)


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


def test_blinding_secret_must_be_private_and_external(external_dir):
    path = external_dir / "blind.key"
    path.write_bytes(BLIND_KEY)
    with pytest.raises(EvidenceError, match="private to D"):
        read_blinding_key(path)
    path.chmod(0o600)
    assert read_blinding_key(path) == BLIND_KEY
    assert any(
        position_map(task["case_id"], manifest()["corpus_sha256"], blinding_key=BLIND_KEY) !=
        position_map(task["case_id"], manifest()["corpus_sha256"], blinding_key=b"n" * 32)
        for task in tasks()
    )
    with pytest.raises(EvidenceError, match="secret 32-byte"):
        position_map("case", "b" * 64, blinding_key=b"")


def test_position_swap_deterministic_and_disjoint():
    mapping = position_map("synthetic", "b" * 64, blinding_key=BLIND_KEY)
    assert mapping["AB"] == tuple(reversed(mapping["BA"]))
    assert set(mapping["AB"]) == {"candidate", "competitor"}


def test_blind_comparison_rejects_missing_access_and_noncomparable_sources():
    assert not compare(tasks(), manifest(), None, None)["complete"]
    bad = comparator()
    bad["source_set_sha256"] = "9" * 64
    with pytest.raises(EvidenceError, match="comparable"):
        compare(tasks(), manifest(), bad, blind_votes(), blinding_key=BLIND_KEY)


def test_blind_comparison_uses_both_reviewers_and_swapped_positions():
    result = compare(tasks(), manifest(), comparator(), blind_votes(), blinding_key=BLIND_KEY)
    assert result["complete"] and result["wins"] == 40
    assert result["ties"] == result["losses"] == 0
    bad = blind_votes()[:-1]
    with pytest.raises(EvidenceError, match="both swapped"):
        compare(tasks(), manifest(), comparator(), bad, blinding_key=BLIND_KEY)


def test_blind_disagreement_detected_instead_of_silent_vote_merge():
    bad = blind_votes()
    bad[0]["preference"] = "B" if bad[0]["preference"] == "A" else "A"
    result = compare(tasks(), manifest(), comparator(), bad, blinding_key=BLIND_KEY)
    assert not result["complete"]
    assert result["position_swap_inconsistent_cases"] == [tasks()[0]["case_id"]]


def test_blind_comparative_disagreement_requires_independent_adjudicator():
    judgments = blind_votes()
    judgments[0]["preference"] = "B" if judgments[0]["preference"] == "A" else "A"
    cid = tasks()[0]["case_id"]
    unresolved = compare(tasks(), manifest(), comparator(), judgments, blinding_key=BLIND_KEY)
    assert not unresolved["complete"] and unresolved["remaining_disagreements"] == [cid]
    resolution = {"case_id": cid, "adjudicator_id": "D3", "position": "AB",
                  "preference": ("A" if position_map(cid, manifest()["corpus_sha256"], blinding_key=BLIND_KEY)["AB"][0] == "candidate" else "B"),
                  "evidence_note": "Separate evaluation of source-grounded factual claims"}
    accepted = compare(tasks(), manifest(), comparator(), judgments, [resolution], blinding_key=BLIND_KEY)
    assert accepted["complete"] and accepted["disagreements_adjudicated"] == 1
    assert accepted["wins"] == 40
    denial = dict(resolution, adjudicator_id="D1")
    with pytest.raises(EvidenceError, match="independent third"):
        compare(tasks(), manifest(), comparator(), judgments, [denial], blinding_key=BLIND_KEY)
    with pytest.raises(EvidenceError, match="duplicate"):
        compare(tasks(), manifest(), comparator(), judgments, [resolution, resolution], blinding_key=BLIND_KEY)


def test_packet_has_both_positions_without_product_labels(tmp_path):
    values = [{"case_id": c["case_id"], "output": "candidate text"} for c in tasks()]
    other = [{"case_id": c["case_id"], "output": "competitor text"} for c in tasks()]
    packet = prepare_blind(tasks(), manifest(), values, other, blinding_key=BLIND_KEY)
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


def test_cli_failure_preserves_first_run_and_cannot_overwrite(external_dir, capsys):
    result_path = external_dir / "failed-first-run.json"
    assert main(["evaluate", "--report", str(result_path)]) == 2
    first_bytes = result_path.read_bytes()
    result = json.loads(first_bytes)
    assert result["qualified"] is False and result["release_authorization"] is False
    assert result["result_kind"] == "operator_submitted_first_run"
    assert main(["evaluate", "--report", str(result_path), "--regression-rerun"]) == 2
    assert result_path.read_bytes() == first_bytes


def test_fixture_is_not_a_production_operated_result():
    # The test creates syntactically valid envelopes but no PostgreSQL or
    # Temporal calls. The production evaluator explicitly marks these as
    # operator-submitted and never independently verified.
    faults = verify_operations(operations(), "a" * 40)
    assert faults["evidence_level"].startswith("operator_submitted")
