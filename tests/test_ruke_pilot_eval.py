"""Day 9 evidence-harness regressions. Test data is synthetic, never a benchmark."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from scripts.staging_release_freeze import RUNTIME_CAPABILITY_KEYS
from scripts.day10_release_decision import holdout_ok, recovery_ok
from scripts.ruke_pilot_eval import (
    OPERATED, RUBRIC, EvidenceError, compare, comparison_evidence_recorded, external_heldout,
    candidate_ledger, canonical_sha256, custody_receipt_ok, day10_first_run_scores,
    day10_holdout_receipt, generation_identity_ok, immutable_write, main,
    position_map, prepare_blind, registry_cases, read_blinding_key, score_reviews, source_checks_ok,
    validate_candidate_identity, validate_candidate_readbacks, validate_evidence_binding,
    validate_manifest, verify_operations, read_json, read_jsonl, strict_json_loads,
)


BLIND_KEY = b"m" * 32  # Synthetic TEST secret; never use for operated comparisons.


def test_day9_json_reader_parses_exact_bytes_it_validated(tmp_path, monkeypatch):
    """A second pathname read must not replace the first validated evidence."""
    path = tmp_path / "evidence.json"
    path.write_text('{"release_id":"frozen"}', encoding="utf-8")
    original_read = Path.read_bytes

    def change_after_digest(self):
        data = original_read(self)
        if self == path:
            path.write_text('{"release_id":"substituted"}', encoding="utf-8")
        return data

    monkeypatch.setattr(Path, "read_bytes", change_after_digest)
    assert read_json(path) == {"release_id": "frozen"}


def test_day9_jsonl_reader_parses_exact_bytes_it_validated(tmp_path, monkeypatch):
    """A second pathname read must not replace JSONL after the bounded read."""
    path = tmp_path / "candidate.jsonl"
    path.write_text('{"case_id":"frozen"}\n', encoding="utf-8")
    original_read = Path.read_bytes

    def change_after_digest(self):
        data = original_read(self)
        if self == path:
            path.write_text('{"case_id":"substituted"}\n', encoding="utf-8")
        return data

    monkeypatch.setattr(Path, "read_bytes", change_after_digest)
    assert read_jsonl(path) == [{"case_id": "frozen"}]


def test_day9_holdout_parses_only_the_bytes_matching_frozen_digest(external_dir, monkeypatch):
    """Corrupting the second path-based parse cannot change a verified corpus."""
    rows = tasks()
    path = external_dir / "independent-heldout.jsonl"
    original = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(original, encoding="utf-8")
    path.chmod(0o444)
    expected_digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
    other = deepcopy(rows)
    other[0]["source_sha256"] = "e" * 64
    substituted = "".join(json.dumps(row, sort_keys=True) + "\n" for row in other)
    original_read_text = Path.read_text

    def changed_on_second_read(self, *args, **kwargs):
        if self == path:
            return substituted
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", changed_on_second_read)
    observed = external_heldout(
        path, corpus_sha256=expected_digest, custody_verified=True,
    )
    assert observed[0]["source_sha256"] == rows[0]["source_sha256"]




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


def _candidate_identity_base():
    return {
        "api_source_revision": "a" * 40,
        "worker_source_revision": "a" * 40,
        "api_build_digest": "sha256:" + "1" * 64,
        "worker_build_digest": "sha256:" + "2" * 64,
        "alembic_revision": "0070",
        "provider_id": "deepseek",
        "model_id": "synthetic",
        "prompt_registry_sha256": "3" * 64,
        "tool_registry_sha256": "4" * 64,
        "context_budget_bytes": 12_288,
        "runtime_capabilities": {key: False for key in RUNTIME_CAPABILITY_KEYS},
    }


def _readback_payloads(value):
    identity = value["candidate_identity"]
    common = {
        "release_id": value["release_id"],
        "alembic_revision": identity["alembic_revision"],
        "provider_id": identity["provider_id"],
        "model_id": identity["model_id"],
        "prompt_registry_sha256": identity["prompt_registry_sha256"],
        "tool_registry_sha256": identity["tool_registry_sha256"],
        "context_budget_bytes": identity["context_budget_bytes"],
        "rollout_manifest_sha256": value["rollout_manifest_sha256"],
        "runtime_capabilities": identity["runtime_capabilities"],
    }
    api = {
        **common, "source_revision": identity["api_source_revision"],
        "build_digest": identity["api_build_digest"],
    }
    worker = {
        **common, "source_revision": identity["worker_source_revision"],
        "build_digest": identity["worker_build_digest"],
    }
    schema = {
        "release_id": value["release_id"],
        "source_revision": value["candidate_revision"],
        "migration_revision": identity["alembic_revision"],
        "api_revision": identity["alembic_revision"],
        "worker_revision": identity["alembic_revision"],
        "rollout_manifest_sha256": value["rollout_manifest_sha256"],
    }
    return {"api": api, "worker": worker, "schema": schema}


def manifest():
    value = {
        "schema_version": 2,
        "split": "holdout",
        "release_id": "day9-test-release-001",
        "run_id": "day9-first-run-test-001",
        "candidate_revision": "a" * 40,
        "corpus_sha256": "b" * 64,
        "source_set_sha256": "c" * 64,
        "rollout_manifest_sha256": "d" * 64,
        "answer_key_sha256": "e" * 64,
        "rubric_sha256": "f" * 64,
        "candidate_product_version": "test-1",
        "candidate_model": "synthetic",
        "prompt_version": "synthetic-v1",
        "tool_version": "test-v1",
        "run_started_at": "2026-11-12T00:00:00Z",
        "time_limit_seconds": 60,
        "candidate_identity": _candidate_identity_base(),
    }
    payloads = _readback_payloads(value)
    value["candidate_identity"].update({
        "api_readback_sha256": canonical_sha256(payloads["api"]),
        "worker_readback_sha256": canonical_sha256(payloads["worker"]),
        "schema_readback_sha256": canonical_sha256(payloads["schema"]),
    })
    return value


def candidate_readbacks(value=None):
    value = value or manifest()
    return {
        role: {**payload, "readback_sha256": canonical_sha256(payload)}
        for role, payload in _readback_payloads(value).items()
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
                            "source_supported": True, "evidence_note": "Fixture rationale",
                            "output_sha256": "d" * 64,
                            "reviewed_at": "2026-11-12T00:10:00Z" if reviewer == "D1" else "2026-11-12T00:11:00Z"})
    return reviews, checks


def operations():
    return [
        {"row": i, "scenario": scenario, "candidate_revision": "a" * 40,
         "status": "pass", "execution": "operated",
         "unauthorized_access": False, "unauthorized_mutation": False,
         "trace_sha256": hashlib.sha256(f"scenario-{i}".encode()).hexdigest(),
         "evidence_ref": "sha256:" + hashlib.sha256(f"scenario-{i}".encode()).hexdigest(),
         "observed_at": "2026-11-12T00:00:00Z", "verified_at": "2026-11-12T00:01:00Z",
         "boundaries": {k: {"mode": "real", "instance": "synthetic-test-instance",
                           "trace_sha256": hashlib.sha256(f"boundary-{i}-{k}".encode()).hexdigest()} for k in boundaries}}
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





def test_candidate_outputs_bind_each_run_model_prompt_tool_budget_and_sources():
    value = manifest()
    rows = candidate_outputs_for_manifest(value)
    hashes, usage = candidate_ledger(tasks(), rows, manifest_sha256="a" * 64, manifest=value)
    assert len(hashes) == 40
    assert len(usage["case_run_receipts"]) == 40
    assert usage["total_tokens"] == 4000
    assert all(receipt["provider_id"] == "deepseek"
               and receipt["model_id"] == "synthetic"
               and receipt["source_refs"]
               and receipt["time_limit_seconds"] == 60
               for receipt in usage["case_run_receipts"])
    bad = candidate_outputs_for_manifest(value)
    bad[0]["model_id"] = "other-model"
    with pytest.raises(EvidenceError, match="run identity"):
        candidate_ledger(tasks(), bad, manifest_sha256="a" * 64, manifest=value)
    bad = candidate_outputs_for_manifest(value)
    bad[1]["run_id"] = bad[0]["run_id"]
    with pytest.raises(EvidenceError, match="run IDs"):
        candidate_ledger(tasks(), bad, manifest_sha256="a" * 64, manifest=value)
    bad = candidate_outputs_for_manifest(value)
    bad[2]["source_refs"] = []
    with pytest.raises(EvidenceError, match="source list"):
        candidate_ledger(tasks(), bad, manifest_sha256="a" * 64, manifest=value)


def test_generation_identity_receipt_and_day10_holdout_artifact_are_compatible():
    evidence = {"generation_identity_verified": True, "generation_identity_receipt_sha256": "a" * 64}
    assert generation_identity_ok(evidence)
    assert not generation_identity_ok({"generation_identity_verified": False,
                                       "generation_identity_receipt_sha256": "a" * 64})
    assert not generation_identity_ok({"generation_identity_verified": True,
                                       "generation_identity_receipt_sha256": "bad"})
    value = manifest()
    custody = {
        "custodian_id": "independent-D", "developer_id": "developer-A",
        "corpus_author_id": "corpus-author-B", "independent_operator_review": "verified",
        "custodian_positive_read_test": "allowed", "developer_negative_read_test": "denied",
        "exposure_history_reviewed": True, "replacement_of_exposed_cases": True,
        "frozen_inputs_sha256": value["corpus_sha256"],
        "frozen_answers_sha256": value["answer_key_sha256"],
        "rubric_sha256": value["rubric_sha256"],
        "exposure_history_sha256": "d" * 64, "access_log_sha256": "e" * 64,
        "receipt_sha256": "f" * 64, "verified_at": "2026-11-11T23:59:00Z",
    }
    reviews, checks = reviews_and_checks()
    output_hashes, usage = candidate_ledger(
        tasks(), candidate_outputs_for_manifest(value, manifest_digest="9" * 64),
        manifest_sha256="9" * 64, manifest=value,
    )
    for check in checks:
        check["output_sha256"] = output_hashes[check["case_id"]]
    for review in reviews:
        review["output_sha256"] = output_hashes[review["case_id"]]
    scores = score_reviews(tasks(), reviews, [], checks, output_hashes=output_hashes)
    artifact = day10_holdout_receipt(
        value, scores, custody, case_run_receipts=usage["case_run_receipts"],
        manifest_sha256="9" * 64,
        generation_identity_verified=True, generation_identity_receipt_sha256="a" * 64,
    )
    assert holdout_ok(artifact, value["release_id"], value["candidate_revision"],
                      value["rollout_manifest_sha256"])
    # Preserve all three pseudonymous claimed roles in the exact Day 9 ->
    # Day 10 custody handoff, without asserting real human authentication.
    assert {k: artifact["custody_receipt"][k] for k in (
        "custodian_id", "developer_id", "corpus_author_id",
    )} == {k: custody[k] for k in (
        "custodian_id", "developer_id", "corpus_author_id",
    )}
    assert all(row["attempt_status"] == "succeeded" and row["evidence_kind"] == "draft_output"
               and row["output_present"] is True and len(row["output_sha256"]) == 64
               and row["run_id"] for row in artifact["cases"])

def test_candidate_manifest_requires_exact_43_boolean_runtime_flags_and_identity():
    value = manifest()
    identity = validate_candidate_identity(value)
    assert len(identity["runtime_capabilities"]) == 43
    bad = deepcopy(value)
    bad["candidate_identity"]["runtime_capabilities"].pop(next(iter(bad["candidate_identity"]["runtime_capabilities"])))
    with pytest.raises(EvidenceError, match="exactly 43"):
        validate_candidate_identity(bad)
    bad = deepcopy(value)
    bad["candidate_identity"]["runtime_capabilities"][next(iter(bad["candidate_identity"]["runtime_capabilities"]))] = 1
    with pytest.raises(EvidenceError, match="exactly 43"):
        validate_candidate_identity(bad)
    bad = deepcopy(value)
    bad["candidate_identity"]["worker_source_revision"] = "b" * 40
    with pytest.raises(EvidenceError, match="source revisions"):
        validate_candidate_identity(bad)


def test_candidate_api_worker_and_schema_readbacks_match_and_hash_exactly():
    value = manifest()
    readbacks = candidate_readbacks(value)
    assert validate_candidate_readbacks(value, readbacks)["consistent"] is True
    bad = deepcopy(readbacks)
    bad["api"]["provider_id"] = "gemma"
    with pytest.raises(EvidenceError, match="does not match candidate manifest"):
        validate_candidate_readbacks(value, bad)
    bad = candidate_readbacks(value)
    bad["worker"]["runtime_capabilities"]["browser"] = True
    bad["worker"]["readback_sha256"] = canonical_sha256({
        key: item for key, item in bad["worker"].items() if key != "readback_sha256"
    })
    with pytest.raises(EvidenceError, match="does not match candidate manifest"):
        validate_candidate_readbacks(value, bad)



def test_evidence_json_must_bind_exact_manifest_digest():
    assert validate_evidence_binding({"manifest_sha256": "a" * 64}, "a" * 64)
    with pytest.raises(EvidenceError, match="not bound"):
        validate_evidence_binding({"manifest_sha256": "b" * 64}, "a" * 64)
    with pytest.raises(EvidenceError, match="must be an object"):
        validate_evidence_binding([], "a" * 64)


def test_blind_packet_and_competitor_are_bound_to_same_release_manifest():
    value = manifest()
    digest = "a" * 64
    candidate = [{"case_id": c["case_id"], "output": "candidate", "manifest_sha256": digest}
                 for c in tasks()]
    competitor_outputs = [{"case_id": c["case_id"], "output": "competitor", "manifest_sha256": digest}
                          for c in tasks()]
    packet = prepare_blind(tasks(), value, candidate, competitor_outputs,
                           blinding_key=BLIND_KEY, manifest_sha256=digest)
    assert len(packet) == 80
    competitor = comparator()
    competitor.update(manifest_sha256=digest, release_id=value["release_id"],
                      rollout_manifest_sha256=value["rollout_manifest_sha256"])
    assert compare(tasks(), value, competitor, blind_votes(), blinding_key=BLIND_KEY,
                   manifest_sha256=digest)["complete"]
    competitor["release_id"] = "different-release"
    with pytest.raises(EvidenceError, match="not bound"):
        compare(tasks(), value, competitor, blind_votes(), blinding_key=BLIND_KEY,
                manifest_sha256=digest)
    competitor_outputs[0]["manifest_sha256"] = "b" * 64
    with pytest.raises(EvidenceError, match="not bound"):
        prepare_blind(tasks(), value, candidate, competitor_outputs,
                      blinding_key=BLIND_KEY, manifest_sha256=digest)



def test_exact_head_ci_and_release_contract_must_be_reported_passed_before_holdout():
    value = manifest()
    evidence = {
        "required_repository_checks": {name: "success" for name in {
            "test-and-build", "Frontend tests and builds", "coworker", "browser-qualification",
            "PostgreSQL 18 staging compatibility", "governance-audit", "ci-merge-gate",
        }},
        "ci_source_revision": value["candidate_revision"],
        "ci_evidence_sha256": "a" * 64,
        "canonical_release_contract": "passed",
        "release_contract_source_revision": value["candidate_revision"],
        "release_contract_evidence_sha256": "b" * 64,
    }
    assert source_checks_ok(evidence, value)
    assert not source_checks_ok(dict(evidence, ci_source_revision="c" * 40), value)
    assert not source_checks_ok(dict(evidence, canonical_release_contract="failed"), value)
    failed_job = dict(evidence)
    failed_job["required_repository_checks"] = dict(evidence["required_repository_checks"], coworker="failure")
    assert not source_checks_ok(failed_job, value)

def test_custody_receipt_requires_distinct_people_both_read_tests_and_access_proofs():
    receipt = {
        "custodian_id": "independent-D",
        "developer_id": "developer-A",
        "corpus_author_id": "corpus-author-B",
        "independent_operator_review": "verified",
        "custodian_positive_read_test": "allowed",
        "developer_negative_read_test": "denied",
        "exposure_history_reviewed": True,
        "replacement_of_exposed_cases": True,
        "frozen_inputs_sha256": manifest()["corpus_sha256"],
        "frozen_answers_sha256": manifest()["answer_key_sha256"],
        "rubric_sha256": manifest()["rubric_sha256"],
        "exposure_history_sha256": "d" * 64,
        "access_log_sha256": "e" * 64,
        "receipt_sha256": "f" * 64,
        "verified_at": "2026-11-11T23:59:00Z",
    }
    value = manifest()
    assert custody_receipt_ok(receipt, value)
    assert not custody_receipt_ok(dict(receipt, custodian_id="developer-A"), value)
    # Textually different ID spellings must not falsely count as separate
    # custodian/developer humans, just as they cannot be separate reviewers.
    assert not custody_receipt_ok(dict(receipt, custodian_id="DEVELOPER-A"), value)
    assert not custody_receipt_ok(dict(receipt, custodian_id="ｄｅｖｅｌｏｐｅｒ－Ａ"), value)
    assert not custody_receipt_ok(dict(receipt, custodian_id=" developer-A "), value)
    assert not custody_receipt_ok(dict(receipt, developer_id=""), value)
    assert not custody_receipt_ok(dict(receipt, corpus_author_id="bad\nidentity"), value)
    assert not custody_receipt_ok(dict(receipt, custodian_positive_read_test="denied"), value)
    assert not custody_receipt_ok(dict(receipt, exposure_history_reviewed=False), value)
    assert not custody_receipt_ok(dict(receipt, access_log_sha256="not-a-digest"), value)
    assert not custody_receipt_ok(dict(receipt, frozen_inputs_sha256="0" * 64), value)


def test_holdout_manifest_cannot_read_corpus_before_explicit_custody_verification(tmp_path):
    value = manifest()
    absent = tmp_path / "must-not-be-opened.jsonl"
    with pytest.raises(EvidenceError, match="custody"):
        validate_manifest(value, absent)
    with pytest.raises(EvidenceError, match="custody"):
        external_heldout(absent, corpus_sha256=value["corpus_sha256"])

def test_legacy_manifest_is_readable_only_in_explicit_legacy_mode(external_dir):
    held = external_dir / "legacy-heldout.jsonl"
    held.write_text("\n".join(json.dumps(row) for row in tasks()) + "\n")
    held.chmod(0o444)
    legacy = manifest()
    legacy["schema_version"] = 1
    legacy["corpus_sha256"] = hashlib.sha256(held.read_bytes()).hexdigest()
    for key in ("release_id", "run_id", "rollout_manifest_sha256", "candidate_identity"):
        legacy.pop(key)
    with pytest.raises(EvidenceError, match="legacy manifest"):
        validate_manifest(legacy, held, custody_verified=True)
    assert len(validate_manifest(legacy, held, allow_legacy=True, custody_verified=True)) == 40




def test_operated_receipts_fail_without_unique_trace_reference_and_later_verification():
    rows = operations()
    rows[0]["evidence_ref"] = "sha256:" + "0" * 64
    rows[1]["verified_at"] = "not-a-timestamp"
    rows[2]["trace_sha256"] = rows[3]["trace_sha256"]
    rows[2]["evidence_ref"] = rows[3]["evidence_ref"]
    result = verify_operations(rows, "a" * 40)
    assert {1, 2} <= set(result["failed_rows"])
    assert len(result["failed_rows"]) == 3
    assert result["day10_recovery"]["scenarios"][0]["status"] == "failed"


def candidate_outputs_for_manifest(value, manifest_digest="a" * 64):
    from scripts.pilot_workflow_eval import load_suite
    suite = load_suite()
    reference = {row["case_id"]: row["draft"] for row in suite["reference_outputs"]}
    per_cell = {}
    for task in suite["cases"]:
        if task["split"] == "development":
            per_cell.setdefault((task["workflow"], task["language"]), reference[task["id"]])
    result = []
    for task in tasks():
        output = deepcopy(per_cell[(task["workflow"], task["language"])])
        refs = sorted({task["citation_id"]})
        identity = value["candidate_identity"]
        result.append({
            "case_id": task["case_id"], "output": output,
            "manifest_sha256": manifest_digest,
            "release_id": value["release_id"],
            "source_revision": value["candidate_revision"],
            "rollout_manifest_sha256": value["rollout_manifest_sha256"],
            "source_set_sha256": value["source_set_sha256"],
            "provider_id": identity["provider_id"], "model_id": identity["model_id"],
            "prompt_registry_sha256": identity["prompt_registry_sha256"],
            "tool_registry_sha256": identity["tool_registry_sha256"],
            "context_budget_bytes": identity["context_budget_bytes"],
            "time_limit_seconds": value["time_limit_seconds"],
            "run_id": "agent-run-" + task["case_id"],
            "source_refs": refs,
            "attempt_started_at": "2026-11-12T00:01:00Z",
            "attempt_finished_at": "2026-11-12T00:02:00Z",
            "telemetry": {"tokens": 100, "latency_ms": 500, "cost_microusd": 10},
        })
    return result

def test_candidate_outputs_require_exact_manifest_digest_when_bound():
    from scripts.pilot_workflow_eval import load_suite
    suite = load_suite()
    reference = {row["case_id"]: row["draft"] for row in suite["reference_outputs"]}
    per_cell = {}
    for task in suite["cases"]:
        if task["split"] == "development":
            per_cell.setdefault((task["workflow"], task["language"]), reference[task["id"]])
    rows = [{"case_id": task["case_id"],
             "output": deepcopy(per_cell[(task["workflow"], task["language"])]),
             "manifest_sha256": "a" * 64}
            for task in tasks()]
    hashes, _ = candidate_ledger(tasks(), rows, manifest_sha256="a" * 64)
    assert len(hashes) == 40
    rows[0]["manifest_sha256"] = "b" * 64
    with pytest.raises(EvidenceError, match="not bound"):
        candidate_ledger(tasks(), rows, manifest_sha256="a" * 64)


def test_operated_rows_require_exact_release_and_manifest_binding():
    rows = operations()
    for row in rows:
        row.update(manifest_sha256="a" * 64, release_id="release-1",
                   rollout_manifest_sha256="b" * 64)
    result = verify_operations(
        rows, "a" * 40, manifest_sha256="a" * 64,
        release_id="release-1", rollout_manifest_sha256="b" * 64,
    )
    assert result["fault_gate_pass"]
    recovery = result["day10_recovery"]
    assert recovery["release_id"] == "release-1"
    assert len(recovery["scenarios"]) == 20
    assert all(row["status"] == "passed" and row["evidence_ref"].startswith("sha256:")
               for row in recovery["scenarios"])
    assert recovery_ok(recovery, "release-1", "a" * 40, "b" * 64)
    rows[0]["manifest_sha256"] = "c" * 64
    with pytest.raises(EvidenceError, match="not bound"):
        verify_operations(rows, "a" * 40, manifest_sha256="a" * 64)


def test_day10_first_run_scores_include_per_case_security_and_two_reviewer_scores():
    reviews, checks = reviews_and_checks()
    scores = score_reviews(tasks(), reviews, [], checks)
    receipt = day10_first_run_scores(scores)
    assert receipt["accepted"] == 40 and receipt["total"] == 40
    assert len(receipt["cases"]) == 40
    assert all(row["security_passed"] is True and row["reviewer_scores"] == [8, 8]
               for row in receipt["cases"])
    assert scores["reviewers"] == ["d1", "d2"]

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
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest(), custody_verified=True)


def test_external_holdout_must_be_outside_repo_and_match_frozen_sha(external_dir):
    held = external_dir / "independent-test-only.jsonl"
    held.write_text("\n".join(json.dumps(x) for x in tasks()) + "\n")
    digest = hashlib.sha256(held.read_bytes()).hexdigest()
    with pytest.raises(EvidenceError, match="read-only"):
        external_heldout(held, corpus_sha256=digest, custody_verified=True)
    held.chmod(0o444)
    assert len(external_heldout(held, corpus_sha256=digest, custody_verified=True)) == 40
    with pytest.raises(EvidenceError, match="hash mismatch"):
        external_heldout(held, corpus_sha256="0" * 64, custody_verified=True)
    with pytest.raises(EvidenceError, match="separate"):
        external_heldout(held, corpus_sha256=digest, repo_root=external_dir, custody_verified=True)
    m = manifest()
    m["corpus_sha256"] = digest
    assert validate_manifest(m, held, custody_verified=True) == tasks()


def test_holdout_matrix_and_answer_key_prohibited(external_dir):
    held = external_dir / "test.jsonl"
    rows = tasks()
    rows[0]["expected_facts"] = [{"secret": "no"}]
    held.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    held.chmod(0o444)
    with pytest.raises(EvidenceError, match="answer keys"):
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest(), custody_verified=True)
    rows[0].pop("expected_facts")
    rows[1]["case_id"] = rows[0]["case_id"]
    held.chmod(0o644)
    held.write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    held.chmod(0o444)
    with pytest.raises(EvidenceError, match="distinct"):
        external_heldout(held, corpus_sha256=hashlib.sha256(held.read_bytes()).hexdigest(), custody_verified=True)


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
    for review in reviews:
        review["output_sha256"] = hashes[review["case_id"]]
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
        external_heldout(path, corpus_sha256=digest, custody_verified=True)


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



def test_each_original_reviewer_must_meet_seven_of_eight_without_zero_even_after_adjudication():
    cases = tasks()
    reviews, checks = reviews_and_checks(cases)
    reviews[0]["scores"][RUBRIC[0]] = 0
    adjudication = [{
        "case_id": cases[0]["case_id"], "adjudicator_id": "D3",
        "scores": dict.fromkeys(RUBRIC, 2), "source_supported": True,
        "evidence_note": "Independent adjudication preserves both original reviewer ratings",
        "output_sha256": "d" * 64, "adjudicated_at": "2026-11-12T00:12:00Z",
    }]
    result = score_reviews(cases, reviews, adjudication, checks)
    assert result["results"][0]["reviewer_scores"] == [6, 8]
    assert result["results"][0]["accepted"] is False
    assert result["results"][0]["reviewer_rubrics"][0]["scores"][RUBRIC[0]] == 0
    assert result["accepted"] == 39


def test_competitor_access_gap_is_recorded_without_fabricating_a_comparison():
    unrecorded = compare(tasks(), manifest(), None, None)
    assert unrecorded["complete"] is False
    assert not comparison_evidence_recorded(unrecorded)
    gap = compare(tasks(), manifest(), None, None, access_gap="No competitor seat was available during the frozen evaluation window")
    assert gap["complete"] is False
    assert gap["gap_reason"] == "competitor_access_unavailable"
    assert comparison_evidence_recorded(gap)
    assert not comparison_evidence_recorded({"complete": False, "comparison_gap": "some evidence missing", "gap_reason": "incomplete_evidence"})

def test_unsupported_source_or_failed_security_cannot_be_outweighed():
    reviews, checks = reviews_and_checks()
    for row in reviews:
        if row["case_id"] == tasks()[0]["case_id"]:
            row["source_supported"] = False
    checks[1]["security_passed"] = False
    result = score_reviews(tasks(), reviews, [], checks)
    assert not result["results"][0]["accepted"]
    assert not result["results"][1]["accepted"]



def test_security_failure_is_absolute_nogo_even_when_quality_threshold_passes():
    reviews, checks = reviews_and_checks()
    compromised = tasks()[0]["case_id"]
    checks[0]["security_passed"] = False
    result = score_reviews(tasks(), reviews, [], checks)
    assert result["accepted"] == 39
    assert all(cell["accepted"] >= 9 for cell in result["by_cell"].values())
    assert result["outcome_gate_pass"] is False
    assert result["security_gate_pass"] is False
    assert result["security_failed_cases"] == [compromised]


def test_nonsecurity_deterministic_failure_can_use_one_case_quality_tolerance():
    reviews, checks = reviews_and_checks()
    checks[0]["passed"] = False
    result = score_reviews(tasks(), reviews, [], checks)
    assert result["accepted"] == 39
    assert result["outcome_gate_pass"] is True
    assert result["security_gate_pass"] is True
    assert result["security_failed_cases"] == []


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
                     "source_supported": True, "evidence_note": "Evidence reconciled",
        "output_sha256": "d" * 64, "adjudicated_at": "2026-11-12T00:12:00Z"}]
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
                       "source_supported": True, "evidence_note": "Synthetic reasoning",
        "output_sha256": "d" * 64, "adjudicated_at": "2026-11-12T00:12:00Z"}]
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


@pytest.mark.parametrize("boundary", [None, "postgres"])
def test_operated_rows_fail_closed_for_nonstring_trace_hashes(boundary):
    rows = operations()
    row = rows[0]
    trace = row if boundary is None else row["boundaries"][boundary]
    trace["trace_sha256"] = None
    assert verify_operations(rows, "a" * 40)["failed_rows"] == [1]


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


@pytest.mark.parametrize("payload", [
    '{"security_passed": true, "security_passed": false}',
    '{"nested": {"status": "failed", "status": "passed"}}',
    '{"security_passed": NaN}',
    '{"security_passed": Infinity}',
    '{"security_passed": -Infinity}',
    '{"usage": 1e999}',
])
def test_pilot_evidence_json_rejects_duplicate_keys_and_nonfinite_numbers(payload):
    with pytest.raises(EvidenceError):
        strict_json_loads(payload)


def test_pilot_jsonl_rejects_ambiguous_rows(tmp_path):
    path = tmp_path / "ambiguous-evidence.jsonl"
    path.write_text(
        '{"case_id": "example", "security_passed": false, "security_passed": true}' + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EvidenceError):
        read_jsonl(path)


def test_pilot_strict_json_retains_valid_bangla_and_boolean_data():
    assert strict_json_loads('{"ভাষা": "বাংলা", "security_passed": true}') == {
        "ভাষা": "বাংলা", "security_passed": True,
    }


def _day9_synthetic_failed_attempt(value, *, status="timed_out"):
    """Synthetic first attempt with no draft, but a distinct release-bound trace."""
    rows = candidate_outputs_for_manifest(value)
    row = rows[0]
    row.update({
        "attempt_status": status,
        "output": None,
        "source_refs": [],
        "failure_code": "provider_timeout" if status == "timed_out" else "provider_error",
        "trace_sha256": "9" * 64,
        "attempt_started_at": "2026-11-12T00:00:00Z",
        "attempt_finished_at": "2026-11-12T00:01:00Z",
    })
    return rows


@pytest.mark.parametrize("status", ["failed", "timed_out"])
def test_day9_failed_first_attempt_is_preserved_in_all_forty_and_cannot_be_accepted(status):
    value = manifest()
    rows = _day9_synthetic_failed_attempt(value, status=status)
    hashes, usage = candidate_ledger(tasks(), rows, manifest_sha256="a" * 64, manifest=value)
    failed_case_id = rows[0]["case_id"]
    assert len(hashes) == len(usage["case_run_receipts"]) == 40
    assert usage["failed_case_ids"] == [failed_case_id]
    receipt = next(item for item in usage["case_run_receipts"] if item["case_id"] == failed_case_id)
    assert receipt["attempt_status"] == status
    assert receipt["evidence_kind"] == "failure_record"
    assert receipt["output_present"] is False
    assert receipt["failure_trace_sha256"] == "9" * 64
    assert receipt["output_sha256"] == hashes[failed_case_id]

    reviews, checks = reviews_and_checks()
    for check in checks:
        check["output_sha256"] = hashes[check["case_id"]]
    for review in reviews:
        review["output_sha256"] = hashes[review["case_id"]]
    checks[0]["passed"] = False
    scored = score_reviews(
        tasks(), reviews, [], checks, output_hashes=hashes,
        failed_case_ids=set(usage["failed_case_ids"]),
    )
    assert len(scored["results"]) == 40
    assert scored["accepted"] == 39
    assert scored["results"][0]["accepted"] is False
    assert scored["by_cell"]["research_brief/bn"]["accepted"] == 9
    assert scored["outcome_gate_pass"]  # A single honest failure stays in the denominator.
    # A false success attestation must never turn the missing output into a pass.
    checks[0]["passed"] = True
    with pytest.raises(EvidenceError, match="failed first attempt.*deterministic"):
        score_reviews(
            tasks(), reviews, [], checks, output_hashes=hashes,
            failed_case_ids=set(usage["failed_case_ids"]),
        )


@pytest.mark.parametrize(("mutation", "match"), [
    ("missing_trace", "trace"),
    ("non_hex_trace", "trace"),
    ("missing_code", "failure code"),
    ("forged_output", "no draft"),
    ("stale_refs", "source refs"),
    ("inverted_timestamps", "timestamps"),
    ("missing_timestamp", "timestamps"),
    ("unknown_status", "attempt status"),
])
def test_day9_first_attempt_failure_evidence_fails_closed_on_ambiguous_rows(mutation, match):
    value = manifest()
    rows = _day9_synthetic_failed_attempt(value)
    failed = rows[0]
    if mutation == "missing_trace":
        failed.pop("trace_sha256")
    elif mutation == "non_hex_trace":
        failed["trace_sha256"] = "not-a-digest"
    elif mutation == "missing_code":
        failed["failure_code"] = ""
    elif mutation == "forged_output":
        failed["output"] = candidate_outputs_for_manifest(value)[0]["output"]
    elif mutation == "stale_refs":
        failed["source_refs"] = ["web-1"]
    elif mutation == "inverted_timestamps":
        failed["attempt_finished_at"] = "2026-11-11T23:59:00Z"
    elif mutation == "missing_timestamp":
        failed.pop("attempt_started_at")
    else:
        failed["attempt_status"] = "pretend_success"
    with pytest.raises(EvidenceError, match=match):
        candidate_ledger(tasks(), rows, manifest_sha256="a" * 64, manifest=value)


def test_day9_first_attempt_failure_record_is_bound_to_unique_run_and_trace():
    value = manifest()
    rows = _day9_synthetic_failed_attempt(value)
    first_hashes, _ = candidate_ledger(tasks(), rows, manifest_sha256="a" * 64, manifest=value)
    changed = deepcopy(rows)
    changed[0]["trace_sha256"] = "8" * 64
    changed_hashes, _ = candidate_ledger(tasks(), changed, manifest_sha256="a" * 64, manifest=value)
    assert first_hashes[rows[0]["case_id"]] != changed_hashes[rows[0]["case_id"]]
    changed[0]["run_id"] = changed[1]["run_id"]
    with pytest.raises(EvidenceError, match="run IDs"):
        candidate_ledger(tasks(), changed, manifest_sha256="a" * 64, manifest=value)

def test_day9_first_attempt_scoring_handoff_rejects_missing_or_rebound_receipts():
    value = manifest()
    reviews, checks = reviews_and_checks()
    scores = score_reviews(tasks(), reviews, [], checks)
    _, usage = candidate_ledger(
        tasks(), candidate_outputs_for_manifest(value), manifest_sha256="a" * 64, manifest=value,
    )
    receipts = usage["case_run_receipts"]
    report = day10_first_run_scores(scores, case_run_receipts=receipts)
    assert len(report["cases"]) == 40
    assert report["cases"][0]["run_id"] == receipts[0]["run_id"]
    assert report["cases"][0]["output_sha256"] == receipts[0]["output_sha256"]
    with pytest.raises(EvidenceError, match="wrong number"):
        day10_first_run_scores(scores, case_run_receipts=receipts[:-1])
    wrong = deepcopy(receipts)
    wrong[1]["case_id"] = wrong[0]["case_id"]
    with pytest.raises(EvidenceError, match="duplicate"):
        day10_first_run_scores(scores, case_run_receipts=wrong)


def test_day9_failed_attempt_handoff_retains_failure_digest_and_never_accepts():
    value = manifest()
    candidate = _day9_synthetic_failed_attempt(value)
    hashes, usage = candidate_ledger(
        tasks(), candidate, manifest_sha256="a" * 64, manifest=value,
    )
    reviews, checks = reviews_and_checks()
    for check in checks:
        check["output_sha256"] = hashes[check["case_id"]]
    for review in reviews:
        review["output_sha256"] = hashes[review["case_id"]]
    checks[0]["passed"] = False
    scores = score_reviews(
        tasks(), reviews, [], checks, output_hashes=hashes,
        failed_case_ids=set(usage["failed_case_ids"]),
    )
    report = day10_first_run_scores(scores, case_run_receipts=usage["case_run_receipts"])
    failed = report["cases"][0]
    assert failed["accepted"] is False
    assert failed["attempt_status"] == "timed_out"
    assert failed["output_present"] is False
    assert failed["evidence_kind"] == "failure_record"
    assert failed["failure_trace_sha256"] == "9" * 64
    assert failed["output_sha256"] == hashes[failed["id"]]


def test_day9_adjudication_receipt_preserves_independent_final_rubric_and_original_votes():
    cases = tasks()
    reviews, checks = reviews_and_checks(cases)
    reviews[0]["scores"][RUBRIC[0]] = 1
    resolution = [{
        "case_id": cases[0]["case_id"], "adjudicator_id": "D3",
        "scores": {dimension: (0 if dimension == RUBRIC[0] else 2) for dimension in RUBRIC},
        "source_supported": True, "evidence_note": "Private adjudication reasoning",
        "output_sha256": "d" * 64, "adjudicated_at": "2026-11-12T00:12:00Z",
    }]
    scored = score_reviews(cases, reviews, resolution, checks)
    first = scored["results"][0]
    assert first["accepted"] is False
    assert first["reviewer_scores"] == [7, 8]
    assert first["reviewer_rubrics"][0]["source_supported"] is True
    assert first["final_rubric"] == {
        "scores": resolution[0]["scores"],
        "source_supported": True,
        "adjudicator_id": "d3",
        "evidence_note_sha256": hashlib.sha256(b"Private adjudication reasoning").hexdigest(),
        "output_sha256": "d" * 64,
        "adjudicated_at": "2026-11-12T00:12:00Z",
    }
    handed_off = day10_first_run_scores(scored)
    assert handed_off["cases"][0]["final_rubric"] == first["final_rubric"]
    # The independent decision and the two original reviewer votes survive
    # without exposing the text of the private evidence note.
    assert handed_off["cases"][0]["reviewer_rubrics"] == first["reviewer_rubrics"]


def test_day9_unanimous_reviews_preserve_unadjudicated_final_rubric():
    reviews, checks = reviews_and_checks()
    scored = score_reviews(tasks(), reviews, [], checks)
    row = scored["results"][0]
    assert row["final_rubric"] == {
        "scores": dict.fromkeys(RUBRIC, 2),
        "source_supported": True,
        "adjudicator_id": None,
        "evidence_note_sha256": None,
        "output_sha256": "d" * 64,
        "adjudicated_at": None,
    }


def test_day9_one_reviewer_unsupported_source_cannot_be_reaccepted_by_adjudication():
    cases = tasks()
    reviews, checks = reviews_and_checks(cases)
    reviews[0]["source_supported"] = False
    resolution = [{
        "case_id": cases[0]["case_id"], "adjudicator_id": "D3",
        "scores": dict.fromkeys(RUBRIC, 2),
        "source_supported": True, "evidence_note": "Final review disagrees on source",
        "output_sha256": "d" * 64, "adjudicated_at": "2026-11-12T00:12:00Z",
    }]
    scored = score_reviews(cases, reviews, resolution, checks)
    assert scored["results"][0]["accepted"] is False
    assert scored["results"][0]["reviewer_rubrics"][0]["source_supported"] is False


def test_original_blind_review_handoff_binds_output_hash_and_private_rationale():
    cases = tasks()
    reviews, checks = reviews_and_checks(cases)
    for review in reviews:
        review["output_sha256"] = "d" * 64
        review["reviewed_at"] = "2026-11-12T00:10:00Z"
    scored = score_reviews(cases, reviews, [], checks)
    first = scored["results"][0]["reviewer_rubrics"][0]
    assert first["output_sha256"] == checks[0]["output_sha256"]
    assert first["reviewed_at"] == "2026-11-12T00:10:00Z"
    assert first["evidence_note_sha256"] == hashlib.sha256(b"Fixture rationale").hexdigest()
    assert "evidence_note" not in first


def test_original_blind_reviewer_cannot_rate_a_substituted_output():
    reviews, checks = reviews_and_checks()
    for review in reviews:
        review["output_sha256"] = "d" * 64
        review["reviewed_at"] = "2026-11-12T00:10:00Z"
    reviews[0]["output_sha256"] = "e" * 64
    with pytest.raises(EvidenceError, match="review output"):
        score_reviews(tasks(), reviews, [], checks)


def test_adjudication_must_follow_original_recorded_blind_reviews():
    cases = tasks()
    reviews, checks = reviews_and_checks(cases)
    for review in reviews:
        review["output_sha256"] = "d" * 64
        review["reviewed_at"] = "2026-11-12T00:10:00Z"
    reviews[0]["scores"][RUBRIC[0]] = 1
    adjudication = [{
        "case_id": cases[0]["case_id"], "adjudicator_id": "D3",
        "scores": dict.fromkeys(RUBRIC, 2),
        "source_supported": True,
        "evidence_note": "Independent final rationale",
        "output_sha256": "d" * 64,
        "adjudicated_at": "2026-11-12T00:09:00Z",
    }]
    with pytest.raises(EvidenceError, match="adjudication timestamp"):
        score_reviews(cases, reviews, adjudication, checks)


@pytest.mark.parametrize("mutation", [
    lambda row: row.pop("attempt_started_at", None),
    lambda row: row.pop("attempt_finished_at", None),
    lambda row: row.update(attempt_started_at="2026-11-12T00:03:00Z",
                           attempt_finished_at="2026-11-12T00:02:00Z"),
    lambda row: row.update(attempt_started_at="2026-11-11T23:59:00Z"),
])
def test_successful_first_attempt_requires_complete_ordered_post_manifest_times(mutation):
    value = manifest()
    candidates = candidate_outputs_for_manifest(value)
    mutation(candidates[0])
    with pytest.raises(EvidenceError, match="attempt timestamps"):
        candidate_ledger(tasks(), candidates, manifest_sha256="a" * 64, manifest=value)


def test_blind_reviews_cannot_predate_original_attempt_finish():
    value = manifest()
    hashes, usage = candidate_ledger(
        tasks(), candidate_outputs_for_manifest(value),
        manifest_sha256="a" * 64, manifest=value,
    )
    reviews, checks = reviews_and_checks()
    for row in checks:
        row["output_sha256"] = hashes[row["case_id"]]
    for row in reviews:
        row["output_sha256"] = hashes[row["case_id"]]
    reviews[0]["reviewed_at"] = "2026-11-12T00:01:00Z"
    with pytest.raises(EvidenceError, match="review.*attempt"):
        score_reviews(
            tasks(), reviews, [], checks, output_hashes=hashes,
            case_run_receipts=usage["case_run_receipts"],
        )


def test_operated_recovery_cannot_predate_frozen_candidate_run():
    rows = operations()
    # The operation claims matching source/manifest but occurred before
    # the frozen candidate's run_started_at: it must not earn Day 9 credit.
    rows[0]["observed_at"] = "2026-11-11T23:59:59Z"
    result = verify_operations(
        rows, "a" * 40,
        run_started_at=manifest()["run_started_at"],
    )
    assert result["failed_rows"] == [1]
    assert result["passed"] == 19
    assert result["fault_gate_pass"] is False
    # No failed recovery scenario may silently disappear from the 20-case ledger.
    assert len(result["day10_recovery"]["scenarios"]) == 20


def test_operated_recovery_allows_same_instant_as_manifest_freeze():
    rows = operations()
    result = verify_operations(
        rows, "a" * 40,
        run_started_at=manifest()["run_started_at"],
    )
    assert result["fault_gate_pass"] is True
    assert result["passed"] == 20


@pytest.mark.parametrize("verified_at", [
    "2026-11-12T00:00:00Z",       # exactly at freeze, not before it
    "2026-11-12T00:00:01Z",       # after the 40-case clock begins
    "2026-11-12T06:00:01+06:00",  # equivalent later instant, different offset
])
def test_day9_custody_must_be_authenticated_before_frozen_run(verified_at):
    """A retrospective access receipt must never qualify the first holdout."""
    frozen = manifest()
    receipt = {
        "custodian_id": "independent-D",
        "developer_id": "developer-A",
        "corpus_author_id": "corpus-author-B",
        "independent_operator_review": "verified",
        "custodian_positive_read_test": "allowed",
        "developer_negative_read_test": "denied",
        "exposure_history_reviewed": True,
        "replacement_of_exposed_cases": True,
        "frozen_inputs_sha256": frozen["corpus_sha256"],
        "frozen_answers_sha256": frozen["answer_key_sha256"],
        "rubric_sha256": frozen["rubric_sha256"],
        "exposure_history_sha256": "d" * 64,
        "access_log_sha256": "e" * 64,
        "receipt_sha256": "f" * 64,
        "verified_at": verified_at,
    }
    assert not custody_receipt_ok(receipt, frozen)
    # A direct Day 10 holdout export must not claim custody is established
    # when its independent access check allegedly happened after the freeze.
    reviews, checks = reviews_and_checks()
    hashes, usage = candidate_ledger(
        tasks(), candidate_outputs_for_manifest(frozen, manifest_digest="9" * 64),
        manifest_sha256="9" * 64, manifest=frozen,
    )
    for check in checks:
        check["output_sha256"] = hashes[check["case_id"]]
    for review in reviews:
        review["output_sha256"] = hashes[review["case_id"]]
    scores = score_reviews(tasks(), reviews, [], checks, output_hashes=hashes)
    # Export uses the original custody validator; no network or humans mocked.
    artifact = day10_holdout_receipt(
        frozen, scores, receipt, case_run_receipts=usage["case_run_receipts"],
        manifest_sha256="9" * 64,
        generation_identity_verified=True,
        generation_identity_receipt_sha256="a" * 64,
    )
    assert artifact["custody_established"] is False
    assert artifact["custody_receipt"]["status"] == "failed"


def test_day9_custody_before_freeze_accepts_timezone_normalization():
    frozen = manifest()
    receipt = {
        "custodian_id": "independent-D", "developer_id": "developer-A",
        "corpus_author_id": "corpus-author-B",
        "independent_operator_review": "verified",
        "custodian_positive_read_test": "allowed",
        "developer_negative_read_test": "denied",
        "exposure_history_reviewed": True, "replacement_of_exposed_cases": True,
        "frozen_inputs_sha256": frozen["corpus_sha256"],
        "frozen_answers_sha256": frozen["answer_key_sha256"],
        "rubric_sha256": frozen["rubric_sha256"],
        "exposure_history_sha256": "d" * 64, "access_log_sha256": "e" * 64,
        "receipt_sha256": "f" * 64, "verified_at": "2026-11-12T05:59:59+06:00",
    }
    assert custody_receipt_ok(receipt, frozen)
