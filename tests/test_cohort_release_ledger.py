from __future__ import annotations

import json

import pytest

from scripts.cohort_release_ledger import (
    ReleaseLedgerError,
    append_event,
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
