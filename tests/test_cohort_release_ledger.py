from __future__ import annotations

import json

import pytest

from scripts.cohort_release_ledger import (
    ReleaseLedgerError,
    append_event,
    append_rollback_event,
    append_recovery_event,
    file_sha256,
    read_entries,
    verify_entries,
)


KEY = b"k" * 32


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def artifacts(tmp_path, *, decision="HOLD", current_stage="canary-5", next_stage="canary-10"):
    rollout = write_json(tmp_path / "rollout.json", {
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    })
    plan = write_json(tmp_path / "plan.json", {
        "release_id": "coworker-cohort-001",
        "stages": [
            {"name": "canary-5"},
            {"name": "canary-10"},
            {"name": "cohort-25"},
        ],
    })
    progression = write_json(tmp_path / "progression.json", {
        "release_id": "coworker-cohort-001",
        "decision": decision,
        "current_stage": current_stage,
        "next_stage": next_stage,
    })
    status = write_json(tmp_path / "status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT" if decision != "STOP_ROLLOUT" else "STOP_ROLLOUT",
    })
    return rollout, plan, progression, status


def append(ledger, files, *, event_type="hold", current_stage="canary-5", next_stage="canary-10", created_at="2026-09-22T06:00:00+00:00"):
    rollout, plan, progression, status = files
    return append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type=event_type,
        actor_reference="oncall-primary",
        change_reference="change-123",
        current_stage=current_stage,
        next_stage=next_stage,
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=status,
        created_at=created_at,
    )


def test_append_and_verify_hash_chained_release_events(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    first = append(ledger, artifacts(tmp_path))
    assert first["sequence"] == 1
    assert first["previous_entry_hash"] == "0" * 64

    files = artifacts(
        tmp_path,
        decision="ELIGIBLE_FOR_EXPANSION",
        current_stage="canary-5",
        next_stage="canary-10",
    )
    second = append(
        ledger,
        files,
        event_type="stage_approved",
        created_at="2026-09-22T06:30:00+00:00",
    )
    assert second["sequence"] == 2
    assert second["previous_entry_hash"] == first["entry_hash"]

    result = verify_entries(read_entries(ledger), KEY)
    assert result == {
        "entries": 2,
        "release_id": "coworker-cohort-001",
        "head_entry_hash": second["entry_hash"],
        "verified": True,
    }


def test_tampered_entry_content_is_detected(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    append(ledger, artifacts(tmp_path))
    row = json.loads(ledger.read_text(encoding="utf-8"))
    row["change_reference"] = "tampered-change"
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseLedgerError, match="hash does not match"):
        verify_entries(read_entries(ledger), KEY)


def test_wrong_hmac_key_is_rejected(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    append(ledger, artifacts(tmp_path))
    with pytest.raises(ReleaseLedgerError, match="HMAC verification failed"):
        verify_entries(read_entries(ledger), b"x" * 32)


def test_artifact_hashes_bind_exact_input_files(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    files = artifacts(tmp_path)
    entry = append(ledger, files)
    files[0].write_text('{"release_id":"coworker-cohort-001","cohort":{"max_users":10}}', encoding="utf-8")
    assert entry["artifact_sha256"]["rollout_manifest"] != __import__("hashlib").sha256(files[0].read_bytes()).hexdigest()


def test_event_type_must_match_progression_decision(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    files = artifacts(
        tmp_path,
        decision="STOP_ROLLOUT",
        current_stage="canary-5",
        next_stage=None,
    )
    with pytest.raises(ReleaseLedgerError, match="requires progression decision"):
        append(
            ledger,
            files,
            event_type="hold",
            current_stage="canary-5",
            next_stage=None,
        )


def test_expansion_can_target_only_the_next_planned_stage(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    files = artifacts(
        tmp_path,
        decision="ELIGIBLE_FOR_EXPANSION",
        current_stage="canary-5",
        next_stage="cohort-25",
    )
    with pytest.raises(ReleaseLedgerError, match="immediately following"):
        append(
            ledger,
            files,
            event_type="stage_approved",
            current_stage="canary-5",
            next_stage="cohort-25",
        )


def test_one_ledger_cannot_mix_release_ids(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    append(ledger, artifacts(tmp_path))
    files = list(artifacts(tmp_path))
    for path in files:
        value = json.loads(path.read_text(encoding="utf-8"))
        value["release_id"] = "coworker-cohort-002"
        path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ReleaseLedgerError, match="Ledger release_id"):
        append_event(
            ledger=ledger,
            key=KEY,
            release_id="coworker-cohort-002",
            event_type="hold",
            actor_reference="oncall-primary",
            change_reference="change-456",
            current_stage="canary-5",
            next_stage="canary-10",
            rollout=files[0],
            canary_plan=files[1],
            progression_decision=files[2],
            operator_status=files[3],
            created_at="2026-09-22T07:00:00+00:00",
        )


def rollback_files(tmp_path):
    rollout = write_json(tmp_path / "rollback-rollout.json", {
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    })
    plan = write_json(tmp_path / "rollback-plan.json", {
        "release_id": "coworker-cohort-001",
        "stages": [
            {"name": "canary-5"},
            {"name": "canary-10"},
            {"name": "cohort-25"},
        ],
    })
    progression = write_json(tmp_path / "rollback-progression.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
        "current_stage": "canary-5",
        "next_stage": None,
    })
    stop_status = write_json(tmp_path / "rollback-stop-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
    })
    post_status = write_json(tmp_path / "rollback-post-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    completion = write_json(tmp_path / "rollback-completion.json", {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout),
            "operator_status": file_sha256(post_status),
        },
    })
    return rollout, plan, progression, stop_status, post_status, completion


def test_schema_v2_rollback_completion_chains_after_v1_stop(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    rollout, plan, progression, stop_status, post_status, completion = rollback_files(tmp_path)

    stop = append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=stop_status,
        created_at="2026-09-22T07:00:00+00:00",
    )
    completed = append_rollback_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=post_status,
        rollback_completion=completion,
        created_at="2026-09-22T07:20:00+00:00",
    )

    assert stop["schema_version"] == 1
    assert completed["schema_version"] == 2
    assert completed["event_type"] == "rollback_completed"
    assert completed["previous_entry_hash"] == stop["entry_hash"]
    assert completed["artifact_sha256"]["rollback_completion"] == file_sha256(completion)

    result = verify_entries(read_entries(ledger), KEY)
    assert result["entries"] == 2
    assert result["head_entry_hash"] == completed["entry_hash"]
    assert result["verified"] is True


def test_rollback_completion_requires_prior_stop(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    rollout, plan, progression, _stop_status, post_status, completion = rollback_files(tmp_path)
    with pytest.raises(ReleaseLedgerError, match="earlier stop_rollout"):
        append_rollback_event(
            ledger=ledger,
            key=KEY,
            release_id="coworker-cohort-001",
            actor_reference="oncall-primary",
            change_reference="incident-123",
            current_stage="canary-5",
            rollout=rollout,
            canary_plan=plan,
            progression_decision=progression,
            operator_status=post_status,
            rollback_completion=completion,
        )


def test_rollback_completion_must_bind_same_stop_artifacts(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    rollout, plan, progression, stop_status, post_status, completion = rollback_files(tmp_path)
    append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=stop_status,
    )
    plan.write_text(json.dumps({
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "canary-5"}, {"name": "cohort-25"}],
    }), encoding="utf-8")

    with pytest.raises(ReleaseLedgerError, match="same canary_plan"):
        append_rollback_event(
            ledger=ledger,
            key=KEY,
            release_id="coworker-cohort-001",
            actor_reference="oncall-primary",
            change_reference="incident-123",
            current_stage="canary-5",
            rollout=rollout,
            canary_plan=plan,
            progression_decision=progression,
            operator_status=post_status,
            rollback_completion=completion,
        )


def recovery_files(tmp_path):
    rollout = write_json(tmp_path / "recovery-rollout.json", {
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    })
    plan = write_json(tmp_path / "recovery-plan.json", {
        "release_id": "coworker-cohort-001",
        "stages": [
            {"name": "canary-5"},
            {"name": "canary-10"},
            {"name": "cohort-25"},
        ],
    })
    progression = write_json(tmp_path / "recovery-progression.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
        "current_stage": "canary-5",
        "next_stage": None,
    })
    stop_status = write_json(tmp_path / "recovery-stop-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
    })
    rollback_status = write_json(tmp_path / "recovery-rollback-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    rollback_completion = write_json(tmp_path / "recovery-rollback-completion.json", {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout),
            "operator_status": file_sha256(rollback_status),
        },
    })
    recovery_status = write_json(tmp_path / "recovery-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    recovery_verification = write_json(tmp_path / "recovery-verification.json", {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "recovery_verified",
        "current_stage": "canary-5",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout),
            "canary_plan": file_sha256(plan),
            "rollback_completion": file_sha256(rollback_completion),
            "operator_status": file_sha256(recovery_status),
        },
    })
    return (
        rollout,
        plan,
        progression,
        stop_status,
        rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    )


def test_schema_v3_recovery_chains_after_v2_rollback(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    (
        rollout,
        plan,
        progression,
        stop_status,
        rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    ) = recovery_files(tmp_path)

    stop = append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=stop_status,
        created_at="2026-09-22T07:00:00+00:00",
    )
    rollback_entry = append_rollback_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=rollback_status,
        rollback_completion=rollback_completion,
        created_at="2026-09-22T07:20:00+00:00",
    )
    recovered = append_recovery_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=recovery_status,
        rollback_completion=rollback_completion,
        recovery_verification=recovery_verification,
        created_at="2026-09-22T08:00:00+00:00",
    )

    assert stop["schema_version"] == 1
    assert rollback_entry["schema_version"] == 2
    assert recovered["schema_version"] == 3
    assert recovered["event_type"] == "recovery_verified"
    assert recovered["previous_entry_hash"] == rollback_entry["entry_hash"]
    assert recovered["artifact_sha256"]["recovery_verification"] == file_sha256(recovery_verification)
    assert verify_entries(read_entries(ledger), KEY)["head_entry_hash"] == recovered["entry_hash"]


def test_recovery_requires_prior_rollback_completion(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    (
        rollout,
        plan,
        progression,
        stop_status,
        _rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    ) = recovery_files(tmp_path)
    append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=stop_status,
    )
    with pytest.raises(ReleaseLedgerError, match="earlier rollback_completed"):
        append_recovery_event(
            ledger=ledger,
            key=KEY,
            release_id="coworker-cohort-001",
            actor_reference="oncall-primary",
            change_reference="incident-123",
            current_stage="canary-5",
            rollout=rollout,
            canary_plan=plan,
            progression_decision=progression,
            operator_status=recovery_status,
            rollback_completion=rollback_completion,
            recovery_verification=recovery_verification,
        )


def test_recovery_must_bind_ledger_recorded_rollback_artifact(tmp_path):
    ledger = tmp_path / "release-ledger.jsonl"
    (
        rollout,
        plan,
        progression,
        stop_status,
        rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    ) = recovery_files(tmp_path)
    append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=stop_status,
    )
    append_rollback_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-123",
        current_stage="canary-5",
        rollout=rollout,
        canary_plan=plan,
        progression_decision=progression,
        operator_status=rollback_status,
        rollback_completion=rollback_completion,
    )
    rollback_completion.write_text(json.dumps({
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout),
            "operator_status": file_sha256(rollback_status),
        },
        "changed": True,
    }), encoding="utf-8")

    with pytest.raises(ReleaseLedgerError, match="rollback-completion artifact recorded"):
        append_recovery_event(
            ledger=ledger,
            key=KEY,
            release_id="coworker-cohort-001",
            actor_reference="oncall-primary",
            change_reference="incident-123",
            current_stage="canary-5",
            rollout=rollout,
            canary_plan=plan,
            progression_decision=progression,
            operator_status=recovery_status,
            rollback_completion=rollback_completion,
            recovery_verification=recovery_verification,
        )
