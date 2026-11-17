"""Day 1: distinguish staging backup integrity from current Alembic identity."""
import json
from pathlib import Path

import pytest

from scripts.staging_migration_alignment import (
    MigrationAlignmentError, main, migration_graph, source_schema_alignment,
)


def seeded_versions(directory: Path) -> Path:
    directory.mkdir()
    versions = {
        "0070": ("0070", None),
        "0071": ("0071", "0070"),
        "0071_project_scoped_goals": ("0071_project_scoped_goals", "0070"),
        "0072_merge_0071_heads": (
            "0072_merge_0071_heads", ("0071", "0071_project_scoped_goals")
        ),
    }
    for name, (revision, parents) in versions.items():
        (directory / (name + ".py")).write_text(
            "revision = " + repr(revision) + "\n"
            + "down_revision = " + repr(parents) + "\n",
            encoding="utf-8",
        )
    return directory


def test_actual_migration_graph_flags_the_observed_staging_0070_as_older():
    graph, head = migration_graph()
    assert head == "0072_merge_0071_heads"
    assert set(graph[head]) == {"0071", "0071_project_scoped_goals"}
    outcome = source_schema_alignment("0070")
    assert outcome == {
        "status": "migration_required",
        "source_revision": "0070",
        "code_head": head,
        "source_is_current": False,
        "pending_migrations": [
            "0071", "0071_project_scoped_goals", "0072_merge_0071_heads"
        ],
        "release_qualified": False,
    }


@pytest.mark.parametrize(("observed", "status", "pending"), [
    ("0070", "migration_required", ["0071", "0071_project_scoped_goals", "0072_merge_0071_heads"]),
    ("0071", "migration_required", ["0071_project_scoped_goals", "0072_merge_0071_heads"]),
    ("0071_project_scoped_goals", "migration_required", ["0071", "0072_merge_0071_heads"]),
    ("0072_merge_0071_heads", "current", []),
    ("unknown", "unrecognized_source_revision", None),
    (None, "unrecognized_source_revision", None),
])
def test_branch_aware_alignment_remains_read_only_and_never_qualifies_release(
    tmp_path, observed, status, pending,
):
    versions = seeded_versions(tmp_path / "versions")
    outcome = source_schema_alignment(observed, versions)
    assert outcome["status"] == status
    assert outcome["pending_migrations"] == pending
    assert outcome["source_is_current"] is (status == "current")
    assert outcome["release_qualified"] is False
    assert outcome["code_head"] == "0072_merge_0071_heads"


@pytest.mark.parametrize(("file", "contents", "reason"), [
    ("0071.py", "revision='0070'\ndown_revision=None\n", "Duplicate migration revision"),
    ("0071.py", "revision='0071'\ndown_revision='missing'\n", "absent parent"),
    ("0071.py", "revision='0071'\ndown_revision=('0070','0070')\n", "duplicate or invalid parents"),
    ("0072_merge_0071_heads.py", "revision='0072_merge_0071_heads'\ndown_revision=None\n", "exactly one head"),
    ("0071.py", "revision='0071'\n", "Missing Alembic metadata"),
    ("0071.py", "revision='0071'\ndown_revision=make_parent()\n", "Cannot safely parse"),
])
def test_malformed_or_ambiguous_history_fails_closed(tmp_path, file, contents, reason):
    versions = seeded_versions(tmp_path / "versions")
    (versions / file).write_text(contents, encoding="utf-8")
    with pytest.raises(MigrationAlignmentError, match=reason):
        migration_graph(versions)


def test_unreachable_cycle_is_rejected_even_if_a_valid_head_exists(tmp_path):
    versions = seeded_versions(tmp_path / "versions")
    (versions / "cycle_a.py").write_text(
        "revision='cycle_a'\ndown_revision='cycle_b'\n", encoding="utf-8"
    )
    (versions / "cycle_b.py").write_text(
        "revision='cycle_b'\ndown_revision='cycle_a'\n", encoding="utf-8"
    )
    with pytest.raises(MigrationAlignmentError, match="unreachable revision"):
        migration_graph(versions)


def test_non_literal_migration_code_is_never_executed(tmp_path):
    versions = seeded_versions(tmp_path / "versions")
    marker = tmp_path / "unexpected_side_effect"
    source = versions / "0070.py"
    source.write_text(
        "open(" + repr(str(marker)) + ", 'w').write('unsafe')\n"
        "revision='0070'\ndown_revision=None\n",
        encoding="utf-8",
    )
    assert migration_graph(versions)[1] == "0072_merge_0071_heads"
    assert not marker.exists()


def test_missing_directory_and_symlink_migrations_fail_closed(tmp_path):
    with pytest.raises(MigrationAlignmentError, match="unavailable"):
        migration_graph(tmp_path / "does-not-exist")
    versions = seeded_versions(tmp_path / "versions")
    (versions / "link.py").symlink_to(versions / "0070.py")
    with pytest.raises(MigrationAlignmentError, match="regular file"):
        migration_graph(versions)


def test_read_only_cli_reports_stale_migration_as_failure_without_claiming_access(capsys):
    assert main(["--observed-revision", "0070"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "migration_required"
    assert report["code_head"] == "0072_merge_0071_heads"
    assert report["observation_authenticity_verified"] is False
    assert report["release_qualified"] is False


def test_read_only_cli_current_revision_does_not_imply_release_approval(capsys):
    assert main(["--observed-revision", "0072_merge_0071_heads"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source_is_current"] is True
    assert report["observation_authenticity_verified"] is False
    assert report["release_qualified"] is False
