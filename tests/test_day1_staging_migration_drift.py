"""Offline Day 1 source/readback tests; never imply migration or staging succeeded."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from scripts.day1_staging_migration_drift import (
    MigrationDriftError, assess, migration_graph, ordered_migrations, read_readback,
)

NOW = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
SOURCE = "a" * 40
PROJECT = "bsmbvjenpvcyfjzwtuax"


def receipt(revision="0070"):
    return {
        "project_ref": PROJECT,
        "schema": "shuddho_coworker",
        "revision": revision,
        "private_table_count": 84,
        "postgres_version": "17.11",
        "observed_at": (NOW - timedelta(minutes=5)).isoformat(),
    }


def make_migrations(tmp_path):
    path = tmp_path / "versions"
    path.mkdir()
    for filename, revision, parents in [
        ("0070.py", "0070", "0069"),
        ("0069.py", "0069", None),
        ("0071_provider.py", "0071", "0070"),
        ("0071_project.py", "0071_project_scoped_goals", "0070"),
        ("0072_merge.py", "0072_merge_0071_heads", ("0071", "0071_project_scoped_goals")),
    ]:
        (path / filename).write_text(f"revision = {revision!r}\ndown_revision = {parents!r}\n", encoding="utf-8")
    return path


def test_source_schema_drift_report_preserves_both_pending_0071_branches(tmp_path):
    folder = make_migrations(tmp_path)
    result = assess(receipt(), project_ref=PROJECT, source_revision=SOURCE, directory=folder, now=NOW)
    assert result["source_head"] == "0072_merge_0071_heads"
    assert result["pending_revisions"] == ["0071", "0071_project_scoped_goals", "0072_merge_0071_heads"]
    assert result["disposition"] == "MIGRATION_DRIFT_BLOCKS_PILOT"
    assert result["staging_qualified"] is False
    assert result["deployment_authorized"] is False
    assert result["independent_readback_authenticated_by_tool"] is False


def test_matching_revision_still_cannot_claim_live_qualification(tmp_path):
    folder = make_migrations(tmp_path)
    result = assess(receipt("0072_merge_0071_heads"), project_ref=PROJECT,
                    source_revision=SOURCE, directory=folder, now=NOW)
    assert result["source_matches_readback"] is True
    assert result["pending_revisions"] == []
    assert result["disposition"] == "SOURCE_ALIGNED_NOT_QUALIFIED"
    assert result["staging_qualified"] is False
    assert result["migration_authorized"] is False


@pytest.mark.parametrize("change", [
    {"project_ref": "x" * 20}, {"schema": "public"}, {"revision": "not-a-revision"},
    {"private_table_count": True}, {"private_table_count": 0}, {"postgres_version": "unknown"},
    {"observed_at": "2026-11-18T08:00:01Z"}, {"observed_at": "2026-11-17T00:00:00Z"},
    {"observed_at": "2026-11-18T08:00:00"}, {"observed_at": None},
])
def test_identity_fail_closed(tmp_path, change):
    folder = make_migrations(tmp_path)
    with pytest.raises(MigrationDriftError):
        assess({**receipt(), **change}, project_ref=PROJECT, source_revision=SOURCE,
               directory=folder, now=NOW)


def test_extra_or_missing_readback_field_rejected(tmp_path):
    folder = make_migrations(tmp_path)
    with pytest.raises(MigrationDriftError, match="exact"):
        assess({**receipt(), "migration_approved": True}, project_ref=PROJECT,
               source_revision=SOURCE, directory=folder, now=NOW)
    wrong = receipt()
    del wrong["observed_at"]
    with pytest.raises(MigrationDriftError, match="exact"):
        assess(wrong, project_ref=PROJECT, source_revision=SOURCE, directory=folder, now=NOW)


def test_source_graph_rejects_unmerged_heads_and_cycle(tmp_path):
    path = make_migrations(tmp_path)
    (path / "0072_merge.py").unlink()
    with pytest.raises(MigrationDriftError, match="one merged"):
        ordered_migrations(migration_graph(path))
    (path / "0070.py").write_text('revision = "0070"\ndown_revision = "0071"\n', encoding="utf-8")
    with pytest.raises(MigrationDriftError, match="one merged"):
        ordered_migrations(migration_graph(path))


def test_duplicate_metadata_and_missing_parent_fail_closed(tmp_path):
    path = make_migrations(tmp_path)
    (path / "0070.py").write_text('revision = "0070"\nrevision = "0070"\ndown_revision = "0069"\n')
    with pytest.raises(MigrationDriftError, match="metadata"):
        migration_graph(path)
    (path / "0070.py").write_text('revision = "0070"\ndown_revision = "missing"\n')
    with pytest.raises(MigrationDriftError, match="missing"):
        migration_graph(path)


def test_readback_reader_rejects_symlinks_oversize_and_ambiguous_json():
    # CI's pytest --basetemp lives inside the checkout. Use an independently
    # placed temporary folder so the valid fixture respects the production
    # rule that operator readbacks must never be developer-checkout files.
    with TemporaryDirectory(prefix="shuddho-day1-readback-") as directory:
        external = Path(directory)
        good = external / "proof.json"
        good.write_text(json.dumps(receipt()), encoding="utf-8")
        assert read_readback(good) == receipt()
        link = external / "link.json"
        link.symlink_to(good)
        with pytest.raises(MigrationDriftError):
            read_readback(link)
        good.write_text('{"revision":"0070","revision":"0072"}', encoding="utf-8")
        with pytest.raises(MigrationDriftError):
            read_readback(good)
        good.write_text('{"value": 1e999}', encoding="utf-8")
        with pytest.raises(MigrationDriftError):
            read_readback(good)
        good.write_bytes(b" " * 32769)
        with pytest.raises(MigrationDriftError):
            read_readback(good)


def test_external_readback_rejects_symlink_swap_at_open(monkeypatch):
    """A pathname passing lstat must not be reopened through an attacker symlink."""
    with TemporaryDirectory(prefix="shuddho-day1-race-") as directory:
        folder = Path(directory)
        submitted = folder / "submitted.json"
        replacement = folder / "replacement.json"
        submitted.write_text(json.dumps(receipt()), encoding="utf-8")
        replacement.write_text(json.dumps(receipt("0072_merge_0071_heads")), encoding="utf-8")

        real_open = os.open
        swapped = False

        def swap_at_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if Path(path) == submitted and not swapped:
                swapped = True
                submitted.unlink()
                submitted.symlink_to(replacement)
            return real_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", swap_at_open)
        with pytest.raises(MigrationDriftError, match="readback|regular|link"):
            read_readback(submitted)
        assert swapped


def test_external_readback_rejects_growth_after_inode_size_check(monkeypatch):
    """An inode growing after fstat must not bypass the hard input-byte bound."""
    from scripts.day1_staging_migration_drift import MAX_READBACK_BYTES

    with TemporaryDirectory(prefix="shuddho-day1-grow-") as directory:
        target = Path(directory) / "submitted.json"
        original = json.dumps(receipt()).encode("utf-8")
        target.write_bytes(original)
        real_read = os.read
        grew = False

        def grow_before_read(fd, size):
            nonlocal grew
            if not grew:
                grew = True
                target.write_bytes(original + b" " * (MAX_READBACK_BYTES + 1))
            return real_read(fd, size)

        monkeypatch.setattr(os, "read", grow_before_read)
        with pytest.raises(MigrationDriftError, match="readback|size|bounded"):
            read_readback(target)
        assert grew


def test_real_migration_graph_has_both_parents_of_unified_head():
    graph = migration_graph()
    head, _ = ordered_migrations(graph)
    assert head == "0072_merge_0071_heads"
    assert set(graph[head]) == {"0071", "0071_project_scoped_goals"}
