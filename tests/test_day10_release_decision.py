"""Release decision must reject unsigned, simulated and mismatched evidence."""
from __future__ import annotations

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
           "capabilities": dict(capabilities),
           "action_providers": [], "reviewed_skills": {},
           "cohort": {"enforced": True, "max_users": 5, "configured_members": 0}}
    worker = {**proof(), "deployment_reference": "worker-image-sha256:abc"}
    schema = {**proof(), "migration_revision": "0069", "api_revision": "0069", "worker_revision": "0069"}
    ci = {**proof(), "required_checks": {name: "success" for name in
          ("test-and-build", "frontend", "coworker", "browser-qualification",
           "postgres-18-qualification", "governance-audit", "ci-merge-gate")},
          "workflow_run_url": "https://github.com/rumman52/Shuddho/actions/runs/123"}
    golden = {**proof(), "scenario": "integrated_multi_turn", "run_id": "golden-final",
              "turns": 5, "cancellation_checked": True, "owner_isolation_checked": True, "provider_model": "model-r"}
    first = {"release_id": RELEASE, "source_revision": "c" * 40,
             "rollout_manifest_sha256": "d" * 64, "run_kind": "first_run",
             "run_id": "day9-first", "scores": {"accepted": 28, "total": 40}}
    cells = [(w, l) for w, l in sorted(day10.CELLS)]
    holdout = {**proof(), "mode": "independent_human_holdout", "custody_established": True,
               "generation_identity_verified": True, "reviewers": ["human-D1", "human-D2"],
               "custody_receipt": {**proof(), "independent_d_controls_access": True,
                                   "developer_negative_read_denied": True},
               "cases": [{"id": f"{w}-{l}-{i}", "workflow": w, "language": l,
                          "accepted": True, "reviewer_scores": [7, 8],
                          "security_passed": True}
                         for w, l in cells for i in range(10)]}
    recovery = {**proof(), "scenarios": [dict(
        proof(), id=f"recovery-{i}", scenario=name,
        evidence_ref=f"https://evidence.example.test/recovery-{i}",
        execution="operated", observed_at=NOW, trace_sha256="e" * 64,
        unauthorized_access=False, unauthorized_mutation=False,
        boundaries={target: {"mode": "real", "instance": f"staging-{target}", "trace_sha256": "f" * 64}
                    for target in targets},
    ) for i, (name, targets) in OPERATED.items()]}
    approval = {**proof(), "explicit_separate_authorization": True,
                "reference": "founder-C-approved-change", "founder": "founder-signoff",
                "owner_c": "C-signoff", "max_users": 5}
    artifacts = {"api": api, "worker": worker, "schema": schema, "ci": ci, "golden": golden,
                 "day9_first_run": first, "holdout": holdout, "recovery": recovery,
                 "staging": {}, "quality": {**proof(), "provider_model": "model-r"},
                 "model": {**proof(), "provider_model": "model-r"}, "approval": approval}
    artifacts.update({key: proof() for key in day10.PROOFS})
    artifacts["rollback"].update(
        kill_switches_verified=["SHUDDHO_COWORKER_ENABLED=false",
                                "SHUDDHO_AGENT_RUNTIME_ENABLED=false"],
        capability_flags_after_rollback={key: False for key in day10.RUNTIME_CAPABILITY_KEYS},
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
        cross_owner_denied=True,
        both_directions_verified=True,
        denied_resource_types=["documents", "memory", "artifacts", "activity"],
    )
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
    lambda rollout, artifacts: rollout["capabilities"].update(projects=0),
])
def test_incomplete_or_unreviewed_capability_inventory_fails_closed(monkeypatch, mutation):
    rollout, artifacts = evidence()
    mutation(rollout, artifacts)
    result = decision(monkeypatch, rollout, artifacts)
    assert result["decision"] == "SOURCE_ONLY"
    assert "api_runtime_manifest_v2_exact_sha_and_flags" in result["blockers"]


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
    (lambda a: a["ci"]["required_checks"].update(**{"postgres-18-qualification": "failure"}), "final_head_ci"),
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
    pytest.param(lambda a: a["rollback"]["capability_flags_after_rollback"].update(browser=True), id="capability-still-enabled"),
    pytest.param(lambda a: a["rollback"]["capability_flags_after_rollback"].update(unreviewed=False), id="extra-capability"),
    pytest.param(lambda a: a["rollback"].update(api_reload_verified=False), id="api-reload-unverified"),
    pytest.param(lambda a: a["rollback"].pop("api_readback_evidence_ref"), id="api-readback-missing"),
    pytest.param(lambda a: a["rollback"].update(worker_reload_verified=False), id="worker-reload-unverified"),
    pytest.param(lambda a: a["rollback"].pop("worker_readback_evidence_ref"), id="worker-readback-missing"),
    pytest.param(lambda a: a["rollback"].update(outstanding_work_fenced=False), id="work-not-fenced"),
    pytest.param(lambda a: a["rollback"].update(ledger_consistency_verified=False), id="ledger-unverified"),
    pytest.param(lambda a: a["rollback"].pop("worker_stop_evidence_ref"), id="worker-stop-receipt-missing"),
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
