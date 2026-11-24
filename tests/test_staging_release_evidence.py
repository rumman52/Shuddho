from __future__ import annotations

import hashlib
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



def test_release_context_digest_is_of_exact_parsed_rollout_bytes(tmp_path, monkeypatch):
    """A manifest rewritten just before the former second read must not relabel its digest."""
    rollout = tmp_path / "rollout.json"
    original = json.dumps({"release_id": "first-reviewed-release"}).encode("utf-8")
    changed = json.dumps({"release_id": "second-unreviewed-release"}).encode("utf-8")
    rollout.write_bytes(original)

    real_open = type(rollout).open
    switched = False

    def change_at_later_open(self, mode="r", *args, **kwargs):
        nonlocal switched
        if self == rollout and mode == "rb":
            switched = True
            rollout.write_bytes(changed)
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(type(rollout), "open", change_at_later_open)
    context = release_context(SimpleNamespace(source_revision="a" * 40), rollout)
    assert context["release_id"] == "first-reviewed-release"
    assert context["rollout_manifest_sha256"] == hashlib.sha256(original).hexdigest()


def test_release_context_rejects_rollout_symlink(tmp_path):
    actual = tmp_path / "actual.json"
    actual.write_text(json.dumps({"release_id": "release"}), encoding="utf-8")
    rollout = tmp_path / "rollout.json"
    rollout.symlink_to(actual)
    with pytest.raises(StagingReleaseEvidenceError, match="rollout|manifest|regular|link"):
        release_context(SimpleNamespace(source_revision="a" * 40), rollout)


def test_release_context_rejects_oversized_rollout(tmp_path):
    rollout = tmp_path / "rollout.json"
    rollout.write_text(
        json.dumps({"release_id": "release", "padding": "x" * 2_100_000}),
        encoding="utf-8",
    )
    with pytest.raises(StagingReleaseEvidenceError, match="rollout|manifest|size|bound"):
        release_context(SimpleNamespace(source_revision="a" * 40), rollout)


@pytest.mark.parametrize("raw", [
    '{"release_id":"first","release_id":"second"}',
    '{"release_id":"valid","metadata":{"first":1,"first":2}}',
    '{"release_id":"valid","unrelated":NaN}',
    '{"release_id":"valid","unrelated":1e999}',
])
def test_release_context_rejects_ambiguous_or_nonfinite_rollout(tmp_path, raw):
    rollout = tmp_path / "rollout.json"
    rollout.write_text(raw, encoding="utf-8")
    with pytest.raises(StagingReleaseEvidenceError, match="rollout|manifest|duplicate|finite"):
        release_context(SimpleNamespace(source_revision="a" * 40), rollout)


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



@pytest.mark.parametrize("mutation", ["equal_length_rewrite", "append", "after_eof"])
def test_rollout_manifest_rejects_in_place_mutation_during_single_descriptor_read(
    tmp_path, monkeypatch, mutation,
):
    """A single fd prevents pathname swaps, not in-place torn/replaced evidence."""
    rollout = tmp_path / "rollout.json"
    original = b'{"release_id":"reviewed"}'
    replacement = b'{"release_id":"forged!!"}'
    assert len(original) == len(replacement)
    rollout.write_bytes(original)
    inode = rollout.stat().st_ino
    real_read = os.read
    mutated = False

    def change_inode_content(fd, size):
        nonlocal mutated
        if os.fstat(fd).st_ino != inode or mutated:
            return real_read(fd, size)
        if mutation == "after_eof":
            raw = real_read(fd, size)
            if raw:
                return raw
            # The old reader returned the formerly valid bytes and digest even
            # after the source had changed immediately before descriptor close.
            rollout.write_bytes(replacement)
            mutated = True
            return raw
        if mutation == "equal_length_rewrite":
            rollout.write_bytes(replacement)
        else:
            with rollout.open("ab") as out:
                out.write(b"  ")
        mutated = True
        return real_read(fd, size)

    monkeypatch.setattr(os, "read", change_inode_content)
    with pytest.raises(StagingReleaseEvidenceError, match="changed|size|rollout"):
        release_context(SimpleNamespace(source_revision="a" * 40), rollout)
    assert mutated, "The mutation must run against the manifest descriptor"
