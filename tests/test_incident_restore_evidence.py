from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts.incident_restore_evidence import (
    IncidentRestoreEvidenceError,
    compile_incident_restore_evidence,
    sha256_file,
    validate_incident_restore_evidence,
)


RELEASE_ID = "coworker-cohort-001"
REVISION = "1" * 40
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def rollout(tmp_path):
    return write_json(
        tmp_path / "rollout.json",
        {"release_id": RELEASE_ID, "capabilities": {}},
    )


def staging(tmp_path, rollout_path, *, failed_check=None, revision=REVISION):
    rollout_sha = sha256_file(rollout_path)
    value = {
        key: {
            "status": "passed",
            "evidence": f"{key}-evidence",
            "verified_at": "2026-09-30T11:20:00+00:00",
            "release_id": RELEASE_ID,
            "source_revision": revision,
            "rollout_manifest_sha256": rollout_sha,
        }
        for key in (
            "backup_restore",
            "temporal",
            "parallel_restart",
            "fan_in",
            "flag_rollback",
        )
    }
    if failed_check:
        value[failed_check]["status"] = "pending"
    return write_json(tmp_path / "staging.json", value)


def review(tmp_path, **overrides):
    value = {
        "schema_version": 1,
        "release_id": RELEASE_ID,
        "source_revision": REVISION,
        "exercise_started_at": "2026-09-30T11:00:00+00:00",
        "exercise_completed_at": "2026-09-30T11:30:00+00:00",
        "rto_target_minutes": 60,
        "max_data_loss_seconds": 300,
        "observed_data_loss_seconds": 0,
        "incident_reference": "incident-drill-001",
        "backup_reference": "postgres/object-backup-001",
        "restore_reference": "isolated-restore-001",
        "temporal_restart_reference": "worker-restart-001",
        "rollback_reference": "rollback-drill-001",
        "reviewer_reference": "oncall-review-001",
        "failures": [],
    }
    value.update(overrides)
    return write_json(tmp_path / "review.json", value)


def test_compile_incident_restore_evidence_binds_review_and_staging(tmp_path):
    rollout_path = rollout(tmp_path)
    staging_path = staging(tmp_path, rollout_path)
    review_path = review(tmp_path)

    value = compile_incident_restore_evidence(
        rollout_path=rollout_path,
        staging_evidence_path=staging_path,
        review_path=review_path,
        now=NOW,
    )

    assert value["gate_decision"] == "PASS"
    assert value["observed_restore_minutes"] == 30
    assert all(value["checks"].values())
    assert value["rollout_manifest_sha256"] == sha256_file(rollout_path)
    assert value["staging_evidence_sha256"] == sha256_file(staging_path)
    assert value["review_sha256"] == sha256_file(review_path)

    generated, completed = validate_incident_restore_evidence(
        value,
        release_id=RELEASE_ID,
        rollout_sha256=value["rollout_manifest_sha256"],
        expected_source_revision=REVISION,
    )
    assert generated == NOW
    assert completed == datetime(2026, 9, 30, 11, 30, tzinfo=timezone.utc)


def test_compile_rejects_missing_controlled_recovery_gate(tmp_path):
    rollout_path = rollout(tmp_path)
    with pytest.raises(
        IncidentRestoreEvidenceError,
        match="backup_restore.*must be passed",
    ):
        compile_incident_restore_evidence(
            rollout_path=rollout_path,
            staging_evidence_path=staging(
                tmp_path,
                rollout_path,
                failed_check="backup_restore",
            ),
            review_path=review(tmp_path),
            now=NOW,
        )


def test_compile_rejects_rto_breach(tmp_path):
    rollout_path = rollout(tmp_path)
    with pytest.raises(IncidentRestoreEvidenceError, match="RTO target"):
        compile_incident_restore_evidence(
            rollout_path=rollout_path,
            staging_evidence_path=staging(tmp_path, rollout_path),
            review_path=review(
                tmp_path,
                exercise_started_at="2026-09-30T10:00:00+00:00",
                rto_target_minutes=60,
            ),
            now=NOW,
        )


def test_compile_rejects_data_loss_breach(tmp_path):
    rollout_path = rollout(tmp_path)
    with pytest.raises(IncidentRestoreEvidenceError, match="data-loss limit"):
        compile_incident_restore_evidence(
            rollout_path=rollout_path,
            staging_evidence_path=staging(tmp_path, rollout_path),
            review_path=review(
                tmp_path,
                max_data_loss_seconds=10,
                observed_data_loss_seconds=11,
            ),
            now=NOW,
        )


def test_validator_rejects_different_rollout_and_source_revision(tmp_path):
    rollout_path = rollout(tmp_path)
    value = compile_incident_restore_evidence(
        rollout_path=rollout_path,
        staging_evidence_path=staging(tmp_path, rollout_path),
        review_path=review(tmp_path),
        now=NOW,
    )
    with pytest.raises(IncidentRestoreEvidenceError, match="rollout manifest"):
        validate_incident_restore_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256="a" * 64,
            expected_source_revision=REVISION,
        )
    with pytest.raises(IncidentRestoreEvidenceError, match="source revision"):
        validate_incident_restore_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256=value["rollout_manifest_sha256"],
            expected_source_revision="2" * 40,
        )


def test_compile_rejects_old_staging_checks_with_fresh_review(tmp_path):
    rollout_path = rollout(tmp_path)
    staging_path = staging(tmp_path, rollout_path)
    value = json.loads(staging_path.read_text(encoding="utf-8"))
    value["backup_restore"]["verified_at"] = "2026-09-28T11:20:00+00:00"
    write_json(staging_path, value)
    with pytest.raises(IncidentRestoreEvidenceError, match="exercise window"):
        compile_incident_restore_evidence(
            rollout_path=rollout_path,
            staging_evidence_path=staging_path,
            review_path=review(tmp_path),
            now=NOW,
        )


def test_compile_rejects_staging_check_from_different_revision(tmp_path):
    rollout_path = rollout(tmp_path)
    with pytest.raises(IncidentRestoreEvidenceError, match="source revision"):
        compile_incident_restore_evidence(
            rollout_path=rollout_path,
            staging_evidence_path=staging(
                tmp_path,
                rollout_path,
                revision="2" * 40,
            ),
            review_path=review(tmp_path),
            now=NOW,
        )


def test_validator_recomputes_restore_duration_from_timestamps(tmp_path):
    rollout_path = rollout(tmp_path)
    value = compile_incident_restore_evidence(
        rollout_path=rollout_path,
        staging_evidence_path=staging(tmp_path, rollout_path),
        review_path=review(tmp_path),
        now=NOW,
    )
    value["observed_restore_minutes"] = 1.0
    with pytest.raises(IncidentRestoreEvidenceError, match="does not match its timestamps"):
        validate_incident_restore_evidence(
            value,
            release_id=RELEASE_ID,
            rollout_sha256=value["rollout_manifest_sha256"],
            expected_source_revision=REVISION,
        )


def test_compile_rejects_completion_after_compilation_time(tmp_path):
    rollout_path = rollout(tmp_path)
    with pytest.raises(IncidentRestoreEvidenceError, match="cannot be later"):
        compile_incident_restore_evidence(
            rollout_path=rollout_path,
            staging_evidence_path=staging(tmp_path, rollout_path),
            review_path=review(
                tmp_path,
                exercise_completed_at="2026-09-30T12:01:00+00:00",
            ),
            now=NOW,
        )
