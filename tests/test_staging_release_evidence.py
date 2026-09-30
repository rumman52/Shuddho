from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts.staging_release_evidence import (
    StagingReleaseEvidenceError,
    passed,
    prepared_release_context,
    release_context,
    sha256_file,
    validate_prepared_release_context,
)


def test_release_context_binds_rollout_and_deployed_revision(tmp_path):
    rollout = tmp_path / "rollout.json"
    rollout.write_text(
        json.dumps({"release_id": "coworker-cohort-001"}),
        encoding="utf-8",
    )
    context = release_context(
        SimpleNamespace(source_revision="a" * 40),
        rollout,
    )
    assert context == {
        "release_id": "coworker-cohort-001",
        "source_revision": "a" * 40,
        "rollout_manifest_sha256": sha256_file(rollout),
    }
    prepared = {
        **context,
        "exercise_started_at": "2026-09-30T11:30:00+00:00",
    }
    record = passed(
        "recovery verified",
        prepared,
        now=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
    )
    assert record["status"] == "passed"
    assert record["exercise_started_at"] == "2026-09-30T11:30:00+00:00"
    assert record["verified_at"] == "2026-09-30T12:00:00+00:00"
    assert record["source_revision"] == "a" * 40


def test_release_context_rejects_missing_revision(tmp_path):
    rollout = tmp_path / "rollout.json"
    rollout.write_text(
        json.dumps({"release_id": "coworker-cohort-001"}),
        encoding="utf-8",
    )
    with pytest.raises(StagingReleaseEvidenceError, match="source revision"):
        release_context(SimpleNamespace(source_revision=None), rollout)


def test_prepared_context_rejects_revision_or_rollout_relabel(tmp_path):
    rollout = tmp_path / "rollout.json"
    rollout.write_text(
        json.dumps({"release_id": "coworker-cohort-001"}),
        encoding="utf-8",
    )
    prepared = prepared_release_context(
        SimpleNamespace(source_revision="a" * 40),
        rollout,
        now=datetime(2026, 9, 30, 11, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(StagingReleaseEvidenceError, match="source_revision"):
        validate_prepared_release_context(
            prepared,
            SimpleNamespace(source_revision="b" * 40),
            rollout,
            now=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
        )

    other = tmp_path / "other-rollout.json"
    other.write_text(
        json.dumps({"release_id": "coworker-cohort-001", "marker": "new"}),
        encoding="utf-8",
    )
    with pytest.raises(StagingReleaseEvidenceError, match="rollout_manifest_sha256"):
        validate_prepared_release_context(
            prepared,
            SimpleNamespace(source_revision="a" * 40),
            other,
            now=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
        )
