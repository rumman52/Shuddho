"""Release decision must reject unsigned, simulated and mismatched evidence."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from scripts import day10_release_decision as day10
from scripts.ruke_pilot_eval import OPERATED

REV = "a" * 40
HASH = "b" * 64
RELEASE = "rukh-pilot-001"
STARTED = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
STOPPED = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
RESTORED = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
NOW = datetime.now(timezone.utc).isoformat()


def proof():
    return {"release_id": RELEASE, "source_revision": REV,
            "rollout_manifest_sha256": HASH, "status": "passed",
            "evidence_ref": "https://evidence.example.test/receipt", "verified_at": NOW}


def evidence():
    # A schema-v2 release must enumerate every runtime capability (including false).
    capabilities = {key: key in {"coworker", "agent_runtime"}
                    for key in day10.RUNTIME_CAPABILITY_KEYS}
    rollout = {"release_id": RELEASE, "environment": "production", "action_providers": [],
               "capabilities": capabilities,
               "cohort": {"max_users": 5}}
    api = {"schema_version": 2, "source_revision": REV, "environment": "production",
           "build_digest": "sha256:" + "1" * 64,
           "capabilities": {**capabilities, "grounded_conversation_replies": capabilities["conversation_replies"]},
           "action_providers": [], "reviewed_skills": {},
           "cohort": {"enforced": True, "max_users": 5, "configured_members": 0}}
    worker = {**proof(), "deployment_reference": "worker-image-sha256:abc",
              "schema_version": 2, "environment": "production",
              "build_digest": "sha256:" + "2" * 64,
              "capabilities": dict(capabilities), "action_providers": []}
    schema = {**proof(), "migration_revision": "0069", "api_revision": "0069", "worker_revision": "0069"}
    ci = {**proof(), "required_checks": {name: "success" for name in
          ("test-and-build", "Frontend tests and builds", "coworker", "browser-qualification",
           "PostgreSQL 18 staging compatibility", "governance-audit", "ci-merge-gate")},
          "workflow_run_url": "https://github.com/rumman52/Shuddho/actions/runs/123"}
    golden = {**proof(), "scenario": "integrated_multi_turn", "run_id": "golden-final",
              "turns": 5, "cancellation_checked": True, "owner_isolation_checked": True, "provider_model": "model-r"}
    first = {"release_id": RELEASE, "source_revision": REV,
             "rollout_manifest_sha256": HASH, "run_kind": "first_run",
             "run_id": "day9-first", "run_started_at": "2026-11-12T00:00:00Z",
             "manifest_sha256": "f" * 64, "scores": {}}
    cells = [(w, l) for w, l in sorted(day10.CELLS)]
    holdout = {**proof(), "mode": "independent_human_holdout", "custody_established": True,
               "generation_identity_verified": True, "generation_identity_receipt_sha256": HASH,
               "reviewers": ["human-D1", "human-D2"],
               "custody_receipt": {**proof(), "independent_d_controls_access": True,
                                   "developer_negative_read_denied": True},
               "cases": [{"id": f"{w}-{l}-{i}", "workflow": w, "language": l,
                          "accepted": True, "reviewer_scores": [7, 8],
                          "reviewer_rubrics": [
                              {"reviewer_id": "human-D1", "source_supported": True, "scores": {
                                  "factual_source_fidelity": 2, "constraint_compliance": 2,
                                  "completeness_usefulness": 2, "language_quality": 1}},
                              {"reviewer_id": "human-D2", "source_supported": True, "scores": {
                                  "factual_source_fidelity": 2, "constraint_compliance": 2,
                                  "completeness_usefulness": 2, "language_quality": 2}},
                          ],
                          "final_rubric": {
                              "scores": dict.fromkeys(day10.RUBRIC, 2),
                              "source_supported": True,
                              "adjudicator_id": "human-d3",
                              "evidence_note_sha256": "e" * 64,
                          },
                          "security_passed": True}
                         for w, l in cells for i in range(10)]}
    # Synthetic release-bound receipts using the exact envelope emitted by
    # Day 9's verify_operations(), not arbitrary independent success claims.
    recovery = {
        "release_id": RELEASE, "source_revision": REV,
        "rollout_manifest_sha256": HASH,
        "manifest_sha256": first["manifest_sha256"],
        "scenarios": [{
            "id": f"day9-scenario-{i:02d}", "scenario": name,
            "release_id": RELEASE, "source_revision": REV,
            "rollout_manifest_sha256": HASH,
            "manifest_sha256": first["manifest_sha256"],
            "evidence_ref": "sha256:" + hashlib.sha256(f"synthetic-scenario-{i}".encode()).hexdigest(),
            "trace_sha256": hashlib.sha256(f"synthetic-scenario-{i}".encode()).hexdigest(),
            "verified_at": NOW, "observed_at": STARTED, "status": "passed",
            "execution": "operated", "unauthorized_access": False,
            "unauthorized_mutation": False,
            "boundaries": {
                target: {
                    "mode": "real", "instance": f"staging-{target}",
                    "trace_sha256": hashlib.sha256(
                        f"synthetic-boundary-{i}-{target}".encode()
                    ).hexdigest(),
                } for target in targets
            },
        } for i, (name, targets) in OPERATED.items()],
    }
    approval = {**proof(), "explicit_separate_authorization": True,
                "reference": "founder-C-approved-change", "founder": "founder-signoff",
                "owner_c": "C-signoff", "max_users": 5}
    artifacts = {"api": api, "worker": worker, "schema": schema, "ci": ci, "golden": golden,
                 "day9_first_run": first, "holdout": holdout, "recovery": recovery,
                 "staging": {}, "quality": {**proof(), "provider_model": "model-r"},
                 "model": {**proof(), "provider_model": "model-r"}, "approval": approval}
    artifacts.update({key: proof() for key in day10.PROOFS})
    artifacts["rollback"].update(
        kill_switches_verified=list(day10.EXPECTED_ROLLBACK.values()),
        capability_flags_after_rollback={**{key: False for key in day10.RUNTIME_CAPABILITY_KEYS}, "memory": True},
        new_admissions_stopped=True,
        api_reload_verified=True,
        api_readback_evidence_ref="https://evidence.example.test/api-readback",
        worker_reload_verified=True,
        worker_readback_evidence_ref="https://evidence.example.test/worker-readback",
        outstanding_work_fenced=True,
        ledger_consistency_verified=True,
        worker_stop_observed=True,
        worker_stop_evidence_ref="https://evidence.example.test/worker-stop",
        restoration_verified=True,
        safe_state_procedure_ref="https://evidence.example.test/safe-state-procedure",
        safe_state_source_revision="c" * 40,
        safe_state_deployment_reference="render:known-safe-deployment",
        safe_state_evidence_ref="https://evidence.example.test/safe-state",
        restored_data_retrievable=True,
        restored_data_probe_ref="https://evidence.example.test/restore-probe",
        rollback_started_at=STARTED,
        worker_stopped_at=STOPPED,
        safe_state_restored_at=RESTORED,
    )
    artifacts["cancellation"].update(
        cancelled_run_id="run-cancelled",
        inference_active_at_cancel=True,
        inference_started_at=STARTED,
        cancelled_at=STOPPED,
        terminal_state="cancelled",
        late_result_observed=True,
        late_result_observed_at=RESTORED,
        terminal_state_after_late_result="cancelled",
        late_side_effects=0,
    )
    artifacts["paused_schedule"].update(
        schedule_id="schedule-paused",
        paused_at=STARTED,
        next_due_at=STOPPED,
        observed_after_due_at=RESTORED,
        executions_while_paused=0,
        admitted_executions_while_paused=0,
    )
    artifacts["owner_isolation"].update(
        owner_a_ref="synthetic-A",
        owner_b_ref="synthetic-B",
        synthetic_owners_verified=True,
        cross_owner_denied=True,
        both_directions_verified=True,
        denied_resource_types=["documents", "memory", "artifacts", "activity"],
    )
    _bind_first_run_to_heldout_outcomes(artifacts)
    # Day 9 embeds the same original recovery object in its first-run report
    # and exports a separate Day 10 recovery file.
    artifacts["day9_first_run"]["day10_recovery"] = deepcopy(recovery)
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


@pytest.mark.parametrize("mutation", [
    lambda rollout, artifacts: artifacts["api"]["capabilities"].pop("projects"),
    lambda rollout, artifacts: artifacts["api"]["capabilities"].update(unreviewed_disabled=False),
    lambda rollout, artifacts: rollout["capabilities"].pop("projects"),
    lambda rollout, artifacts: rollout["capabilities"].update(unreviewed_disabled=False),
    lambda rollout, artifacts: artifacts["api"]["capabilities"].update(projects=0),
    lambda rollout, artifacts: artifacts["api"]["capabilities"].pop("grounded_conversation_replies"),
    lambda rollout, artifacts: artifacts["api"]["capabilities"].update(grounded_conversation_replies=True),
    lambda rollout, artifacts: artifacts["api"]["capabilities"].update(grounded_conversation_replies=0),
    lambda rollout, artifacts: rollout["capabilities"].update(projects=0),
])
def test_incomplete_or_unreviewed_capability_inventory_fails_closed(monkeypatch, mutation):
    rollout, artifacts = evidence()
    mutation(rollout, artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "api_runtime_manifest_v2_exact_sha_and_flags" in result["blockers"]


@pytest.mark.parametrize("mutation, blocker", [
    pytest.param(lambda a: a["api"].pop("build_digest"), "api_runtime_manifest_v2_exact_sha_and_flags",
                 id="api-build-omitted"),
    pytest.param(lambda a: a["api"].update(build_digest="sha256:invalid"),
                 "api_runtime_manifest_v2_exact_sha_and_flags", id="api-build-invalid"),
    pytest.param(lambda a: a["worker"].pop("build_digest"), "worker_exact_sha_and_deployment_receipt",
                 id="worker-build-omitted"),
    pytest.param(lambda a: a["worker"].update(build_digest="sha256:invalid"),
                 "worker_exact_sha_and_deployment_receipt", id="worker-build-invalid"),
    pytest.param(lambda a: a["worker"].update(schema_version=1),
                 "worker_exact_sha_and_deployment_receipt", id="worker-manifest-v1"),
    pytest.param(lambda a: a["worker"].update(environment="staging"),
                 "worker_exact_sha_and_deployment_receipt", id="worker-wrong-environment"),
    pytest.param(lambda a: a["worker"]["capabilities"].pop("memory"),
                 "worker_exact_sha_and_deployment_receipt", id="worker-missing-disabled-flag"),
    pytest.param(lambda a: a["worker"]["capabilities"].update(memory=True),
                 "worker_exact_sha_and_deployment_receipt", id="worker-enabled-disabled-flag"),
    pytest.param(lambda a: a["worker"]["capabilities"].update(unreviewed_disabled=False),
                 "worker_exact_sha_and_deployment_receipt", id="worker-extra-flag"),
    pytest.param(lambda a: a["worker"]["capabilities"].update(memory=0),
                 "worker_exact_sha_and_deployment_receipt", id="worker-nonboolean-flag"),
    pytest.param(lambda a: a["worker"].update(action_providers=["microsoft"]),
                 "worker_exact_sha_and_deployment_receipt", id="worker-provider-drift"),
])
def test_exact_build_identity_and_worker_runtime_manifest_required(monkeypatch, mutation, blocker):
    rollout, artifacts = evidence()
    mutation(artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert blocker in result["blockers"]


@pytest.mark.parametrize("canonical, old_alias", [
    ("Frontend tests and builds", "frontend"),
    ("PostgreSQL 18 staging compatibility", "postgres-18-qualification"),
])
def test_required_ci_requires_actual_github_check_names(monkeypatch, canonical, old_alias):
    rollout, artifacts = evidence()
    artifacts["ci"]["required_checks"].pop(canonical)
    artifacts["ci"]["required_checks"][old_alias] = "success"
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "final_head_ci" in result["blockers"]


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
    (lambda a: a["api"]["cohort"].update(enforced=False), "api_runtime_manifest_v2_exact_sha_and_flags"),
    (lambda a: a["api"]["cohort"].update(configured_members=6), "api_runtime_manifest_v2_exact_sha_and_flags"),
    (lambda a: a["rollback"].update(kill_switches_verified=[{}]), "operated_rollback"),
    (lambda a: a["approval"].update(max_users=6), "separate_founder_and_C_pilot_authorization"),
    (lambda a: a["schema"].update(worker_revision="0068"), "database_schema_api_worker_exact"),
    (lambda a: a["worker"].update(source_revision="c" * 40), "worker_exact_sha_and_deployment_receipt"),
    (lambda a: a["ci"]["required_checks"].update(coworker="skipped"), "final_head_ci"),
    (lambda a: a["ci"]["required_checks"].update(**{"browser-qualification": "skipped"}), "final_head_ci"),
    (lambda a: a["ci"]["required_checks"].update(**{"PostgreSQL 18 staging compatibility": "failure"}), "final_head_ci"),
    (lambda a: a["rollback"].update(status="pending"), "operated_rollback"),
    (lambda a: a["rollback"].update(worker_stop_observed=False), "operated_rollback"),
    (lambda a: a["cancellation"].update(late_side_effects=1), "operated_cancellation"),
    (lambda a: a["paused_schedule"].update(executions_while_paused=1), "operated_paused_schedule"),
    (lambda a: a["owner_isolation"].update(cross_owner_denied=False), "operated_owner_isolation"),
    (lambda a: a["golden"].update(provider_model="other"), "final_golden_provider_matches_live_gates"),
    (lambda a: a["holdout"]["custody_receipt"].update(developer_negative_read_denied=False), "independent_day9_holdout_36_of_40"),
    (lambda a: a["recovery"]["scenarios"][1].update(evidence_ref="https://evidence.example.test/recovery-1"), "twenty_operated_recovery_scenarios"),
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




def test_holdout_requires_independent_generation_identity_receipt_digest(monkeypatch):
    rollout, artifacts = evidence()
    artifacts["holdout"].pop("generation_identity_receipt_sha256")
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]

def test_rejected_case_can_preserve_zero_reviewer_total_but_accepted_case_cannot(monkeypatch):
    rollout, artifacts = evidence()
    row = artifacts["holdout"]["cases"][0]
    row["accepted"] = False
    row["reviewer_scores"] = [0, 8]
    row["reviewer_rubrics"][0]["scores"] = {dimension: 0 for dimension in day10.RUBRIC}
    preserved = artifacts["day9_first_run"]["scores"]
    preserved["cases"][0] = deepcopy(row)
    preserved["accepted"] = 39
    cell = row["workflow"] + "/" + row["language"]
    preserved["by_cell"][cell]["accepted"] = 9
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"
    row["accepted"] = True
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "SOURCE_ONLY"

def test_cell_specific_threshold_is_not_only_global(monkeypatch):
    rollout, artifacts = evidence()
    for case in artifacts["holdout"]["cases"][:2]:
        case["accepted"] = False
    # 38/40 accepted globally but only 8/10 in a cell.
    assert "independent_day9_holdout_36_of_40" in decision(monkeypatch, rollout, artifacts)["blockers"]


@pytest.mark.parametrize("second_identity", ["human-d1", "ｈｕｍａｎ-Ｄ１", " human-D2 "])
def test_release_holdout_rejects_reviewer_aliases_and_malformed_identity(monkeypatch, second_identity):
    rollout, artifacts = evidence()
    artifacts["holdout"]["reviewers"][1] = second_identity
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]


@pytest.mark.parametrize("scenario", ["unrelated_smoke_test", "private_upload_retrieval", None])
def test_release_requires_every_named_recovery_scenario(monkeypatch, scenario):
    rollout, artifacts = evidence()
    last = artifacts["recovery"]["scenarios"][-1]
    if scenario is None:
        last.pop("scenario")
    else:
        last["scenario"] = scenario
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "twenty_operated_recovery_scenarios" in result["blockers"]


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda row: row.pop("execution"), id="missing-execution"),
    pytest.param(lambda row: row.update(execution="simulated"), id="simulated"),
    pytest.param(lambda row: row.update(unauthorized_access=True), id="unauthorized-access"),
    pytest.param(lambda row: row.pop("unauthorized_mutation"), id="missing-mutation-verdict"),
    pytest.param(lambda row: row.update(unauthorized_mutation=0), id="nonboolean-mutation-verdict"),
    pytest.param(lambda row: row.update(trace_sha256=None), id="invalid-trace"),
    pytest.param(lambda row: row.update(observed_at="9998-01-01T00:00:00Z"), id="future-observation"),
    pytest.param(lambda row: row["boundaries"].pop("object_storage"), id="missing-object-storage"),
    pytest.param(lambda row: row["boundaries"]["postgres"].update(mode="mock"), id="mock-postgres"),
    pytest.param(lambda row: row["boundaries"]["temporal"].update(trace_sha256=None), id="invalid-temporal-trace"),
])
def test_release_requires_operated_recovery_traces(monkeypatch, mutate):
    rollout, artifacts = evidence()
    mutate(artifacts["recovery"]["scenarios"][-1])
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert result["blockers"] == ["twenty_operated_recovery_scenarios"]
    assert result["scorecard"]["recovery_passed"] is None


def test_canonical_decision_is_not_overridable(monkeypatch):
    rollout, artifacts = evidence()
    monkeypatch.setattr(day10, "evaluate_release", lambda *a, **k: {"decision": "NO-GO"})
    result = day10.decide(rollout, HASH, revision=REV, artifacts=artifacts)
    assert result["canonical_decision"] == "NO-GO"
    assert result["decision"] == "SOURCE_ONLY"


def test_legacy_first_run_is_retained_as_history_but_cannot_qualify_new_digest(monkeypatch):
    rollout, artifacts = evidence()
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"
    artifacts["day9_first_run"]["source_revision"] = "c" * 40
    artifacts["day9_first_run"]["rollout_manifest_sha256"] = "d" * 64
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"]


def test_only_authorization_missing_is_staging_only(monkeypatch):
    rollout, artifacts = evidence()
    del artifacts["approval"]
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "STAGING_ONLY"
    assert result["pilot_activated"] is False


@pytest.mark.parametrize("owner_c", [
    "founder-signoff",
    "FOUNDER-SIGNOFF",
    "ｆｏｕｎｄｅｒ-ｓｉｇｎｏｆｆ",
    " founder-signoff ",
    "operator\nC",
])
def test_release_requires_distinct_valid_pilot_approvers(monkeypatch, owner_c):
    rollout, artifacts = evidence()
    artifacts["approval"]["owner_c"] = owner_c
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "STAGING_ONLY"
    assert result["blockers"] == ["separate_founder_and_C_pilot_authorization"]
    assert result["pilot_activated"] is False


def test_rollout_less_than_five_is_not_pilot(monkeypatch):
    rollout, artifacts = evidence()
    rollout["cohort"]["max_users"] = 4
    artifacts["api"]["cohort"]["max_users"] = 4
    result = decision(monkeypatch, rollout, artifacts)
    assert "pilot_cohort_5_to_10" in result["blockers"]
    assert result["decision"] == "SOURCE_ONLY"

@pytest.mark.parametrize("security_result", [False, None, "true"])
def test_day10_security_failure_is_absolute_nogo_with_39_human_accepted(monkeypatch, security_result):
    """One unverified or failing security case blocks release even at 39/40 quality."""
    rollout, artifacts = evidence()
    case = artifacts["holdout"]["cases"][0]
    case["accepted"] = False
    if security_result is None:
        case.pop("security_passed")
    else:
        case["security_passed"] = security_result

    result = decision(monkeypatch, rollout, artifacts)

    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]
    assert result["pilot_activated"] is False


@pytest.mark.parametrize("mutation", [
    pytest.param(lambda a: a["rollback"].pop("new_admissions_stopped"), id="missing-admission-stop"),
    pytest.param(lambda a: a["rollback"].update(new_admissions_stopped=False), id="admissions-still-open"),
    pytest.param(lambda a: a["rollback"].pop("capability_flags_after_rollback"), id="missing-capability-readback"),
    pytest.param(lambda a: a["rollback"]["capability_flags_after_rollback"].update(coworker=True), id="pilot-capability-still-enabled"),
    pytest.param(lambda a: a["rollback"]["capability_flags_after_rollback"].update(conversations=True), id="required-off-capability-enabled"),
    pytest.param(lambda a: a["rollback"]["capability_flags_after_rollback"].update(memory="true"), id="non-boolean-capability-readback"),
    pytest.param(lambda a: a["rollback"]["capability_flags_after_rollback"].update(unreviewed=False), id="extra-capability"),
    pytest.param(lambda a: a["rollback"].update(api_reload_verified=False), id="api-reload-unverified"),
    pytest.param(lambda a: a["rollback"].pop("api_readback_evidence_ref"), id="api-readback-missing"),
    pytest.param(lambda a: a["rollback"].update(worker_reload_verified=False), id="worker-reload-unverified"),
    pytest.param(lambda a: a["rollback"].pop("worker_readback_evidence_ref"), id="worker-readback-missing"),
    pytest.param(lambda a: a["rollback"].update(outstanding_work_fenced=False), id="work-not-fenced"),
    pytest.param(lambda a: a["rollback"].update(ledger_consistency_verified=False), id="ledger-unverified"),
    pytest.param(lambda a: a["rollback"].pop("worker_stop_evidence_ref"), id="worker-stop-receipt-missing"),
    pytest.param(lambda a: a["rollback"]["kill_switches_verified"].remove(day10.EXPECTED_ROLLBACK["browser_push_kill_switch"]), id="browser-push-kill-switch-missing"),
    pytest.param(lambda a: a["rollback"]["kill_switches_verified"].remove(day10.EXPECTED_ROLLBACK["personal_goals_kill_switch"]), id="personal-goals-kill-switch-missing"),
    pytest.param(lambda a: a["rollback"].pop("safe_state_procedure_ref"), id="safe-state-procedure-missing"),
    pytest.param(lambda a: a["rollback"].pop("safe_state_source_revision"), id="safe-state-revision-missing"),
    pytest.param(lambda a: a["rollback"].update(safe_state_source_revision="not-a-sha"), id="safe-state-revision-invalid"),
    pytest.param(lambda a: a["rollback"].pop("safe_state_deployment_reference"), id="safe-state-deployment-missing"),
    pytest.param(lambda a: a["rollback"].update(restored_data_retrievable=False), id="restored-data-not-retrievable"),
    pytest.param(lambda a: a["rollback"].pop("restored_data_probe_ref"), id="restore-probe-missing"),
    pytest.param(lambda a: a["rollback"].update(worker_stopped_at="9999-01-01T00:00:00Z"), id="future-worker-stop"),
    pytest.param(lambda a: a["rollback"].update(safe_state_restored_at="2026-11-16T00:00:00Z"), id="restore-before-worker-stop"),
])
def test_day10_rollback_requires_complete_operated_restore_receipt(monkeypatch, mutation):
    rollout, artifacts = evidence()
    mutation(artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "operated_rollback" in result["blockers"]


@pytest.mark.parametrize("mutation", [
    pytest.param(lambda a: a["cancellation"].pop("inference_active_at_cancel"), id="missing-inference-state"),
    pytest.param(lambda a: a["cancellation"].update(inference_active_at_cancel=False), id="cancelled-outside-inference"),
    pytest.param(lambda a: a["cancellation"].pop("inference_started_at"), id="missing-inference-start"),
    pytest.param(lambda a: a["cancellation"].update(terminal_state="running"), id="not-terminal-cancelled"),
    pytest.param(lambda a: a["cancellation"].pop("late_result_observed"), id="missing-late-result"),
    pytest.param(lambda a: a["cancellation"].update(late_result_observed=False), id="late-result-not-observed"),
    pytest.param(lambda a: a["cancellation"].update(terminal_state_after_late_result="running"), id="late-result-revived-run"),
    pytest.param(lambda a: a["cancellation"].update(late_result_observed_at="2026-11-16T00:00:00Z"), id="late-result-before-cancel"),
    pytest.param(lambda a: a["cancellation"].update(
        inference_started_at="2026-11-16T00:00:00Z",
        cancelled_at="2026-11-15T00:00:00Z"), id="cancel-before-inference"),
])
def test_day10_cancellation_requires_real_inference_and_terminal_receipt(monkeypatch, mutation):
    rollout, artifacts = evidence()
    mutation(artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "operated_cancellation" in result["blockers"]


@pytest.mark.parametrize("mutation", [
    pytest.param(lambda a: a["paused_schedule"].pop("next_due_at"), id="missing-next-due"),
    pytest.param(lambda a: a["paused_schedule"].pop("observed_after_due_at"), id="missing-after-due-observation"),
    pytest.param(lambda a: a["paused_schedule"].update(
        paused_at="2026-11-16T00:00:00Z",
        next_due_at="2026-11-15T00:00:00Z"), id="pause-after-next-due"),
    pytest.param(lambda a: a["paused_schedule"].update(
        next_due_at="2026-11-16T00:00:00Z",
        observed_after_due_at="2026-11-15T23:59:00Z"), id="observation-before-next-due"),
    pytest.param(lambda a: a["paused_schedule"].update(admitted_executions_while_paused=1), id="admitted-while-paused"),
])
def test_day10_paused_schedule_requires_observed_due_time_and_zero_admissions(monkeypatch, mutation):
    rollout, artifacts = evidence()
    mutation(artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "operated_paused_schedule" in result["blockers"]


@pytest.mark.parametrize("mutation", [
    pytest.param(lambda a: a["owner_isolation"].pop("synthetic_owners_verified"), id="synthetic-owners-unverified"),
    pytest.param(lambda a: a["owner_isolation"].update(synthetic_owners_verified=False), id="real-owner-fixtures"),
    pytest.param(lambda a: a["owner_isolation"].pop("both_directions_verified"), id="missing-reverse-direction"),
    pytest.param(lambda a: a["owner_isolation"].update(both_directions_verified=False), id="one-way-only"),
    pytest.param(lambda a: a["owner_isolation"].update(
        denied_resource_types=["documents", "artifacts", "activity"]), id="memory-not-tested"),
    pytest.param(lambda a: a["owner_isolation"].update(
        denied_resource_types=["documents", "memory", "activity"]), id="artifacts-not-tested"),
])
def test_day10_owner_isolation_requires_all_resource_classes_and_both_directions(monkeypatch, mutation):
    rollout, artifacts = evidence()
    mutation(artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "operated_owner_isolation" in result["blockers"]


def test_day10_release_decision_cli_help_runs_without_evidence_files():
    result = subprocess.run(
        [sys.executable, "scripts/day10_release_decision.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    assert "--rollout" in result.stdout


@pytest.mark.parametrize("payload", [
    '{"status": "failed", "status": "passed"}',
    '{"cancellation": {"security_passed": false, "security_passed": true}}',
    '{"provider_usage": NaN}',
    '{"provider_usage": Infinity}',
    '{"provider_usage": 1e999}',
])
def test_day10_cli_evidence_input_rejects_ambiguous_or_nonfinite_json(tmp_path, payload):
    path = tmp_path / "untrusted.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot read untrusted.json"):
        day10.read_json(path)


def test_day10_cli_evidence_input_rejects_links_and_oversized_files(tmp_path):
    target = tmp_path / "safe.json"
    target.write_text('{"release_id": "synthetic"}', encoding="utf-8")
    assert day10.read_json(target) == {"release_id": "synthetic"}
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="Cannot read linked.json"):
        day10.read_json(link)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * 4_000_001)
    with pytest.raises(ValueError, match="Cannot read oversized.json"):
        day10.read_json(oversized)


def test_43_frozen_flags_and_derived_api_field_remain_separate_from_worker(monkeypatch):
    rollout, artifacts = evidence()
    assert len(rollout["capabilities"]) == 43
    assert len(artifacts["worker"]["capabilities"]) == 43
    assert len(artifacts["api"]["capabilities"]) == 44
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"

    artifacts["worker"]["capabilities"]["grounded_conversation_replies"] = False
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "worker_exact_sha_and_deployment_receipt" in result["blockers"]


def _bind_first_run_to_heldout_outcomes(artifacts):
    """Model the exact Day 9 evaluator pair, never fabricate live qualification."""
    holdout = artifacts["holdout"]
    holdout["manifest_sha256"] = "f" * 64
    for index, case in enumerate(holdout["cases"]):
        case["source_supported"] = True
        case["deterministic_pass"] = True
        case.update(
            run_id=f"first-attempt-{index}",
            output_sha256=f"{index + 1:064x}",
            attempt_status="succeeded",
            evidence_kind="draft_output",
            output_present=True,
            failure_code=None,
            failure_trace_sha256=None,
            attempt_started_at="2026-11-12T00:01:00Z",
            attempt_finished_at="2026-11-12T00:02:00Z",
        )
        for reviewer_index, reviewer in enumerate(case["reviewer_rubrics"]):
            reviewer.update(
                output_sha256=case["output_sha256"],
                reviewed_at=(
                    "2026-11-12T00:10:00Z" if reviewer_index == 0
                    else "2026-11-12T00:11:00Z"
                ),
                evidence_note_sha256="e" * 64,
            )
        case["final_rubric"].update(
            output_sha256=case["output_sha256"],
            adjudicated_at="2026-11-12T00:12:00Z",
        )
    by_cell = {
        f"{workflow}/{language}": {"total": 10, "accepted": 10}
        for workflow, language in sorted(day10.CELLS)
    }
    artifacts["day9_first_run"].update(
        source_revision=REV,
        rollout_manifest_sha256=HASH,
        manifest_sha256=holdout["manifest_sha256"],
        candidate_outputs_sha256="e" * 64,
        case_run_receipts=[
            {
                "case_id": case["id"], "release_id": RELEASE, "source_revision": REV,
                "rollout_manifest_sha256": HASH,
                "manifest_sha256": holdout["manifest_sha256"],
                **{field: case[field] for field in day10.ATTEMPT_FIELDS},
            }
            for case in holdout["cases"]
        ],
        scores={
            "total": 40,
            "accepted": 40,
            "by_cell": by_cell,
            "cases": deepcopy(holdout["cases"]),
        },
    )


@pytest.mark.parametrize(("field", "other"), [
    ("source_revision", "c" * 40),
    ("rollout_manifest_sha256", "d" * 64),
    ("manifest_sha256", "d" * 64),
])
def test_day10_rejects_first_run_bound_to_another_release_identity(monkeypatch, field, other):
    rollout, artifacts = evidence()
    _bind_first_run_to_heldout_outcomes(artifacts)
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"
    artifacts["day9_first_run"][field] = other
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"]


@pytest.mark.parametrize("field", ["first_run", "holdout"])
def test_day10_rejects_unverifiable_first_run_manifest_digest(monkeypatch, field):
    rollout, artifacts = evidence()
    _bind_first_run_to_heldout_outcomes(artifacts)
    if field == "first_run":
        artifacts["day9_first_run"].pop("manifest_sha256")
    else:
        artifacts["holdout"].pop("manifest_sha256")
    result = decision(monkeypatch, rollout, artifacts)
    assert "preserved_day9_first_run" in result["blockers"]


@pytest.mark.parametrize(("section", "field", "other"), [
    ("aggregate", "accepted", 39),
    ("aggregate", "total", 39),
    ("cell", "accepted", 9),
    ("cell", "total", 9),
    ("case", "accepted", False),
    ("case", "security_passed", False),
    ("case", "source_supported", False),
    ("case", "deterministic_pass", False),
    ("case", "id", "unrelated-case-id"),
    ("case", "reviewer_scores", [0, 0]),
    ("case", "reviewer_rubrics", []),
    ("case", "output_sha256", "0" * 64),
    ("case", "run_id", "other-run"),
    ("case", "attempt_status", "timed_out"),
])
def test_day10_rejects_disconnected_day9_scores_even_if_holdout_passes(
    monkeypatch, section, field, other
):
    rollout, artifacts = evidence()
    _bind_first_run_to_heldout_outcomes(artifacts)
    scores = artifacts["day9_first_run"]["scores"]
    if section == "aggregate":
        scores[field] = other
    elif section == "cell":
        scores["by_cell"]["research_brief/bn"][field] = other
    else:
        scores["cases"][0][field] = other
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "other_reviewer", "source_swap"])
def test_day10_rejects_incomplete_or_rebound_first_run_case_set(monkeypatch, mutation):
    rollout, artifacts = evidence()
    _bind_first_run_to_heldout_outcomes(artifacts)
    rows = artifacts["day9_first_run"]["scores"]["cases"]
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[0] = deepcopy(rows[1])
    elif mutation == "other_reviewer":
        rows[0]["reviewer_rubrics"][0]["reviewer_id"] = "unmatched-reviewer"
    else:
        artifacts["holdout"]["cases"][0]["id"] = "replaced-heldout-case"
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"]

@pytest.mark.parametrize(("target", "field", "value"), [
    ("first_run", "candidate_outputs_sha256", None),
    ("receipt", "source_revision", "c" * 40),
    ("receipt", "case_id", ["unhashable-case"]),
    ("receipt", "manifest_sha256", "d" * 64),
    ("receipt", "run_id", "other-run"),
    ("receipt", "output_sha256", "0" * 64),
    ("receipt", "output_present", False),
    ("receipt", "attempt_status", "timed_out"),
    ("receipt", "evidence_kind", "failure_record"),
    ("holdout", "output_sha256", "0" * 64),
    ("holdout", "run_id", "other-run"),
    ("holdout", "output_present", "true"),
    ("holdout", "attempt_status", "timed_out"),
])
def test_day10_rejects_unmatched_first_attempt_lineage(monkeypatch, target, field, value):
    rollout, artifacts = evidence()
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"
    if target == "first_run":
        artifacts["day9_first_run"][field] = value
    elif target == "receipt":
        artifacts["day9_first_run"]["case_run_receipts"][0][field] = value
    else:
        artifacts["holdout"]["cases"][0][field] = value
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"] or (
        target == "holdout" and "independent_day9_holdout_36_of_40" in result["blockers"]
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "replay_other_case"])
def test_day10_rejects_missing_or_reused_first_attempt_receipts(monkeypatch, mutation):
    rollout, artifacts = evidence()
    receipts = artifacts["day9_first_run"]["case_run_receipts"]
    if mutation == "missing":
        receipts.pop()
    elif mutation == "duplicate":
        receipts[1]["case_id"] = receipts[0]["case_id"]
    else:
        receipts[1]["run_id"] = receipts[0]["run_id"]
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"]


@pytest.mark.parametrize("status", ["failed", "timed_out"])
def test_day10_preserves_a_rejected_first_attempt_in_denominator(monkeypatch, status):
    rollout, artifacts = evidence()
    holdout_case = artifacts["holdout"]["cases"][0]
    score_case = artifacts["day9_first_run"]["scores"]["cases"][0]
    receipt = artifacts["day9_first_run"]["case_run_receipts"][0]
    for row in (holdout_case, score_case, receipt):
        row.update(
            attempt_status=status, evidence_kind="failure_record", output_present=False,
            failure_code="provider_timeout", failure_trace_sha256="9" * 64,
        )
    for row in (holdout_case, score_case):
        row["accepted"] = False
        row["deterministic_pass"] = False
    receipt.update(
        attempt_started_at="2026-11-12T00:01:00Z",
        attempt_finished_at="2026-11-12T00:02:00Z",
    )
    scores = artifacts["day9_first_run"]["scores"]
    scores["accepted"] = 39
    scores["by_cell"][holdout_case["workflow"] + "/" + holdout_case["language"]]["accepted"] = 9
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"
    assert result["scorecard"]["heldout_human_accepted"] == 39
    # Both original receipts must continue to report the actual failed first run.
    holdout_case["accepted"] = True
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "SOURCE_ONLY"


@pytest.mark.parametrize("mutation", [
    "missing_final", "bad_final_score", "unsupported_final", "missing_third",
    "reviewer_alias_third", "invalid_evidence_digest", "missing_reviewer_source",
    "unsupported_reviewer",
])
def test_day10_rejects_missing_or_forged_adjudication_lineage(
    monkeypatch, mutation
):
    rollout, artifacts = evidence()
    case = artifacts["holdout"]["cases"][0]
    if mutation == "missing_final":
        del case["final_rubric"]
    elif mutation == "bad_final_score":
        case["final_rubric"]["scores"][day10.RUBRIC[0]] = 0
    elif mutation == "unsupported_final":
        case["final_rubric"]["source_supported"] = False
    elif mutation == "missing_third":
        case["final_rubric"]["adjudicator_id"] = None
    elif mutation == "reviewer_alias_third":
        case["final_rubric"]["adjudicator_id"] = "human-D1"
    elif mutation == "invalid_evidence_digest":
        case["final_rubric"]["evidence_note_sha256"] = "bad"
    elif mutation == "missing_reviewer_source":
        del case["reviewer_rubrics"][0]["source_supported"]
    else:
        case["reviewer_rubrics"][0]["source_supported"] = False
    artifacts["day9_first_run"]["scores"]["cases"][0] = deepcopy(case)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]


def test_day10_rejects_adjudication_mismatch_between_first_run_and_holdout(monkeypatch):
    rollout, artifacts = evidence()
    artifacts["holdout"]["cases"][0]["final_rubric"]["evidence_note_sha256"] = "b" * 64
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"]


def test_day10_accepts_genuinely_unanimous_votes_without_fake_third_adjudicator(monkeypatch):
    rollout, artifacts = evidence()
    case = artifacts["holdout"]["cases"][0]
    case["reviewer_rubrics"][1]["scores"] = deepcopy(case["reviewer_rubrics"][0]["scores"])
    case["reviewer_scores"] = [7, 7]
    case["final_rubric"] = {
        "scores": deepcopy(case["reviewer_rubrics"][0]["scores"]),
        "source_supported": True,
        "adjudicator_id": None,
        "evidence_note_sha256": None,
        "output_sha256": case["output_sha256"],
        "adjudicated_at": None,
    }
    artifacts["day9_first_run"]["scores"]["cases"][0] = deepcopy(case)
    assert decision(monkeypatch, rollout, artifacts)["decision"] == "READY_FOR_OWNER_CONTROLLED_PILOT"


@pytest.mark.parametrize(("section", "field", "forged"), [
    ("reviewer", "output_sha256", "0" * 64),
    ("reviewer", "reviewed_at", "not-a-timestamp"),
    ("reviewer", "evidence_note_sha256", "not-a-sha"),
    ("adjudicator", "output_sha256", "0" * 64),
    ("adjudicator", "adjudicated_at", "2026-11-12T00:00:00Z"),
])
def test_day10_rejects_unbound_or_backdated_blind_review_receipts(
    monkeypatch, section, field, forged
):
    rollout, artifacts = evidence()
    case = artifacts["holdout"]["cases"][0]
    target = (case["reviewer_rubrics"][0] if section == "reviewer"
              else case["final_rubric"])
    target[field] = forged
    artifacts["day9_first_run"]["scores"]["cases"][0] = deepcopy(case)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]


def test_day10_rejects_review_later_than_adjudication_even_if_all_rubrics_pass(monkeypatch):
    rollout, artifacts = evidence()
    case = artifacts["holdout"]["cases"][0]
    case["reviewer_rubrics"][1]["reviewed_at"] = "2026-11-12T00:13:00Z"
    case["final_rubric"]["adjudicated_at"] = "2026-11-12T00:12:00Z"
    artifacts["day9_first_run"]["scores"]["cases"][0] = deepcopy(case)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]


@pytest.mark.parametrize("field", ["attempt_started_at", "attempt_finished_at"])
def test_day10_rejects_first_attempt_without_success_timestamps(monkeypatch, field):
    rollout, artifacts = evidence()
    first_case = artifacts["holdout"]["cases"][0]
    for row in (
        first_case, artifacts["day9_first_run"]["scores"]["cases"][0],
        artifacts["day9_first_run"]["case_run_receipts"][0],
    ):
        row.pop(field, None)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "preserved_day9_first_run" in result["blockers"]


def test_day10_rejects_pre_output_blind_review_even_when_adjudication_is_later(monkeypatch):
    rollout, artifacts = evidence()
    case = artifacts["holdout"]["cases"][0]
    case["reviewer_rubrics"][0]["reviewed_at"] = "2026-11-12T00:01:00Z"
    artifacts["day9_first_run"]["scores"]["cases"][0] = deepcopy(case)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]


def test_day10_rejects_rewritten_attempt_finish_even_if_both_scores_match(monkeypatch):
    rollout, artifacts = evidence()
    for row in (
        artifacts["holdout"]["cases"][0],
        artifacts["day9_first_run"]["scores"]["cases"][0],
        artifacts["day9_first_run"]["case_run_receipts"][0],
    ):
        row["attempt_finished_at"] = "2026-11-12T00:20:00Z"
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "independent_day9_holdout_36_of_40" in result["blockers"]


@pytest.mark.parametrize(("mutation", "why"), [
    (lambda evidence: evidence["recovery"].update(manifest_sha256="0" * 64),
     "foreign-manifest"),
    (lambda evidence: evidence["recovery"]["scenarios"][-1].update(
        observed_at=NOW, verified_at=STARTED
    ), "verified-before-observed"),
    (lambda evidence: evidence["recovery"]["scenarios"][-1].update(
        evidence_ref="https://example.test/unbound-recovery"
    ), "reference-not-trace-digest"),
    (lambda evidence: evidence["recovery"]["scenarios"][-1].update(
        id="unrelated-successful-recovery"
    ), "scenario-id-not-canonical"),
])
def test_day10_recovery_cannot_relabel_unbound_or_unordered_receipts(
    monkeypatch, mutation, why
):
    rollout, artifacts = evidence()
    mutation(artifacts)
    # Test the receipt validator independently of the original-report equality
    # check, so each mutation exercises the actual Day 9 evidence contract.
    assert not day10.recovery_ok(
        artifacts["recovery"], RELEASE, REV, HASH,
        manifest_sha256=artifacts["day9_first_run"]["manifest_sha256"],
    ), why
    # Even when all 20 rows claim success, Day 10 must independently verify
    # the receipt contract that Day 9 actually emits.
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY", why
    assert "twenty_operated_recovery_scenarios" in result["blockers"]


def test_day10_rejects_recovery_without_original_first_run_handoff(monkeypatch):
    rollout, artifacts = evidence()
    artifacts["day9_first_run"].pop("day10_recovery", None)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "twenty_operated_recovery_scenarios" in result["blockers"]


def test_day10_rejects_modified_recovery_after_original_first_run(monkeypatch):
    rollout, artifacts = evidence()
    # A separate recovery artifact cannot be replaced after Day 9 scoring,
    # even when the replacement has the same status, source and trace digest.
    row = artifacts["recovery"]["scenarios"][0]
    row["boundaries"]["postgres"]["instance"] = "different-postgres-instance"
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "twenty_operated_recovery_scenarios" in result["blockers"]


def test_day10_recovery_shape_rejects_noncustodial_operator_reference():
    _, artifacts = evidence()
    row = artifacts["recovery"]["scenarios"][0]
    row["evidence_ref"] = "https://example.test/unbound-recovery"
    assert not day10.recovery_ok(
        artifacts["recovery"], RELEASE, REV, HASH,
        manifest_sha256=artifacts["day9_first_run"]["manifest_sha256"],
    )
