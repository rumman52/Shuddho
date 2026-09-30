from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts.staging_release_evidence import (
    StagingReleaseEvidenceError,
    passed,
    release_context,
    sha256_file,
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
    record = passed(
        "recovery verified",
        context,
        now=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
    )
    assert record["status"] == "passed"
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
