"""Release decision must reject unsigned, simulated and mismatched evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from scripts import day10_release_decision as day10

REV = "a" * 40
HASH = "b" * 64
RELEASE = "rukh-pilot-001"
NOW = datetime.now(timezone.utc).isoformat()


def proof():
    return {"release_id": RELEASE, "source_revision": REV,
            "rollout_manifest_sha256": HASH, "status": "passed",
            "evidence_ref": "https://evidence.example.test/receipt", "verified_at": NOW}


def evidence():
    rollout = {"release_id": RELEASE, "environment": "production", "action_providers": [],
               "capabilities": {"coworker": True, "agent_runtime": True},
               "cohort": {"max_users": 5}}
    api = {"schema_version": 2, "source_revision": REV, "environment": "production",
           "capabilities": {"coworker": True, "agent_runtime": True, "browser": False},
           "action_providers": [], "reviewed_skills": {}}
    worker = {**proof(), "deployment_reference": "worker-image-sha256:abc"}
    schema = {**proof(), "migration_revision": "0069", "api_revision": "0069", "worker_revision": "0069"}
    ci = {**proof(), "required_checks": {name: "success" for name in
          ("test-and-build", "frontend", "coworker", "governance-audit", "ci-merge-gate")},
          "workflow_run_url": "https://github.com/rumman52/Shuddho/actions/runs/123"}
    golden = {**proof(), "scenario": "integrated_multi_turn", "run_id": "golden-final",
              "turns": 5, "cancellation_checked": True, "owner_isolation_checked": True}
    first = {"release_id": RELEASE, "source_revision": "c" * 40,
             "rollout_manifest_sha256": "d" * 64, "run_kind": "first_run",
             "run_id": "day9-first", "scores": {"accepted": 28, "total": 40}}
    cells = [(w, l) for w, l in sorted(day10.CELLS)]
    holdout = {**proof(), "mode": "independent_human_holdout", "custody_established": True,
               "generation_identity_verified": True, "reviewers": ["human-D1", "human-D2"],
               "cases": [{"id": f"{w}-{l}-{i}", "workflow": w, "language": l,
                          "accepted": True, "reviewer_scores": [7, 8]}
                         for w, l in cells for i in range(10)]}
    recovery = {**proof(), "scenarios": [dict(proof(), id=f"recovery-{i}") for i in range(20)]}
    approval = {**proof(), "explicit_separate_authorization": True,
                "reference": "founder-C-approved-change", "founder": "founder-signoff",
                "owner_c": "C-signoff", "max_users": 5}
    artifacts = {"api": api, "worker": worker, "schema": schema, "ci": ci, "golden": golden,
                 "day9_first_run": first, "holdout": holdout, "recovery": recovery,
                 "staging": {}, "quality": {**proof(), "provider_model": "model-r"},
                 "model": {**proof(), "provider_model": "model-r"}, "approval": approval}
    artifacts.update({key: proof() for key in day10.PROOFS})
    return rollout, artifacts


def decision(monkeypatch, rollout=None, artifacts=None):
    if rollout is None or artifacts is None:
        rollout, artifacts = evidence()
    monkeypatch.setattr(day10, "evaluate_release", lambda *a, **k: {"decision": "GO_CONTROLLED_COHORT"})
    return day10.decide(rollout, HASH, revision=REV, artifacts=artifacts)


def test_not_a_production_activation_even_when_qualified(monkeypatch):
    result = decision(monkeypatch)
    assert result["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"
    assert result["canonical_decision"] == "GO_CONTROLLED_COHORT"
    assert result["pilot_activated"] is False
    assert result["blockers"] == []


def test_missing_evidence_fails_closed(monkeypatch):
    rollout, _ = evidence()
    result = decision(monkeypatch, rollout, {})
    assert result["decision"] == "SOURCE_ONLY"
    assert "worker_exact_sha_and_deployment_receipt" in result["blockers"]
    assert "independent_day9_holdout_36_of_40" in result["blockers"]
    assert "canonical_GO_CONTROLLED_COHORT" in result["blockers"]


@pytest.mark.parametrize("mutation,blocked", [
    (lambda a: a["api"].update(source_revision="c" * 40), "api_runtime_manifest_v2_exact_sha_and_flags"),
    (lambda a: a["api"]["capabilities"].update(browser=True), "api_runtime_manifest_v2_exact_sha_and_flags"),
    (lambda a: a["api"].update(schema_version=1), "api_runtime_manifest_v2_exact_sha_and_flags"),
    (lambda a: a["schema"].update(worker_revision="0068"), "database_schema_api_worker_exact"),
    (lambda a: a["worker"].update(source_revision="c" * 40), "worker_exact_sha_and_deployment_receipt"),
    (lambda a: a["ci"]["required_checks"].update(coworker="skipped"), "final_head_ci"),
    (lambda a: a["rollback"].update(status="pending"), "operated_rollback"),
    (lambda a: a["golden"].update(turns=1), "final_sha_integrated_golden"),
    (lambda a: a["day9_first_run"].update(run_id="golden-final"), "separate_final_rerun"),
    (lambda a: a["day9_first_run"].pop("scores"), "preserved_day9_first_run"),
    (lambda a: a["holdout"].update(mode="offline_outputs_only"), "independent_day9_holdout_36_of_40"),
    (lambda a: a["holdout"]["cases"][0].update(reviewer_scores=[0,8]), "independent_day9_holdout_36_of_40"),
    (lambda a: a["holdout"]["cases"][0].update(accepted=True, reviewer_scores=[6,8]), "independent_day9_holdout_36_of_40"),
    (lambda a: a["recovery"]["scenarios"].pop(), "twenty_operated_recovery_scenarios"),
    (lambda a: a.pop("approval"), "separate_founder_and_C_pilot_authorization"),
    (lambda a: a["approval"].update(max_users=11), "separate_founder_and_C_pilot_authorization"),
])
def test_bad_identity_or_missing_gate_blocks(monkeypatch, mutation, blocked):
    rollout, artifacts = evidence()
    mutation(artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == ("STAGING_ONLY" if blocked == "separate_founder_and_C_pilot_authorization" else "SOURCE_ONLY")
    assert blocked in result["blockers"]


def test_cell_specific_threshold_is_not_only_global(monkeypatch):
    rollout, artifacts = evidence()
    for case in artifacts["holdout"]["cases"][:2]:
        case["accepted"] = False
    # 38/40 accepted globally but only 8/10 in a cell.
    assert "independent_day9_holdout_36_of_40" in decision(monkeypatch, rollout, artifacts)["blockers"]


def test_canonical_decision_is_not_overridable(monkeypatch):
    rollout, artifacts = evidence()
    monkeypatch.setattr(day10, "evaluate_release", lambda *a, **k: {"decision": "NO-GO"})
    result = day10.decide(rollout, HASH, revision=REV, artifacts=artifacts)
    assert result["canonical_decision"] == "NO-GO"
    assert result["decision"] == "SOURCE_ONLY"


def test_first_run_can_retain_original_pre_fix_manifest(monkeypatch):
    rollout, artifacts = evidence()
    assert artifacts["day9_first_run"]["rollout_manifest_sha256"] != HASH
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"


def test_only_authorization_missing_is_staging_only(monkeypatch):
    rollout, artifacts = evidence()
    del artifacts["approval"]
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "STAGING_ONLY"
    assert result["pilot_activated"] is False