from __future__ import annotations

import json
import os
import stat
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
    write_private_json,
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



def test_write_private_json_creates_private_file_and_cleans_temporary_files(tmp_path):
    target = tmp_path / "state.json"
    payload = {"owner_id": "synthetic-owner", "resource": "staging"}

    write_private_json(target, payload)

    assert json.loads(target.read_text(encoding="utf-8")) == payload
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_write_private_json_refuses_to_overwrite_existing_evidence(tmp_path):
    target = tmp_path / "state.json"
    original = '{"owner_id":"original"}\n'
    target.write_text(original, encoding="utf-8")

    with pytest.raises(StagingReleaseEvidenceError, match="Refusing to overwrite"):
        write_private_json(target, {"owner_id": "replacement"})

    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob(".state.json.*.tmp")) == []
