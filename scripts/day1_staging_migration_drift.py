"""Read-only Day 1 check: compare a private staging migration readback to source.

The operator must independently authenticate the SQL readback. This tool neither
connects to PostgreSQL nor performs migrations, backup, restore, or activation.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "services/coworker/migrations/versions"
REVISION = re.compile(r"[0-9a-f]{40}\Z")
VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}\Z")
MAX_READBACK_BYTES = 32768


class MigrationDriftError(ValueError):
    """Incomplete or inconsistent source/readback evidence."""


def migration_graph(directory: Path = VERSIONS) -> dict[str, tuple[str, ...]]:
    """Read Alembic metadata as AST without importing or executing migration code."""
    graph: dict[str, tuple[str, ...]] = {}
    for path in sorted(directory.glob("[0-9]*.py")):
        metadata = {}
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                else:
                    continue
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                        if target.id in metadata:
                            raise MigrationDriftError("Duplicate migration metadata: " + path.name)
                        metadata[target.id] = ast.literal_eval(node.value)
        except (SyntaxError, UnicodeError, OSError, TypeError, ValueError) as exc:
            raise MigrationDriftError("Invalid source migration metadata: " + path.name) from exc
        revision = metadata.get("revision")
        parents = metadata.get("down_revision")
        if not isinstance(revision, str) or not revision or revision in graph or "down_revision" not in metadata:
            raise MigrationDriftError("Missing or duplicate migration revision: " + path.name)
        if parents is None:
            parent_ids = ()
        elif isinstance(parents, str):
            parent_ids = (parents,)
        elif isinstance(parents, tuple) and all(isinstance(p, str) for p in parents):
            parent_ids = parents
        else:
            raise MigrationDriftError("Invalid migration ancestry: " + path.name)
        if len(set(parent_ids)) != len(parent_ids) or revision in parent_ids:
            raise MigrationDriftError("Duplicate or self-referential migration parent: " + path.name)
        graph[revision] = parent_ids
    if not graph:
        raise MigrationDriftError("No source migrations found")
    missing = {p for parents in graph.values() for p in parents} - graph.keys()
    if missing:
        raise MigrationDriftError("Migration parent missing from source graph")
    return graph


def ordered_migrations(graph: dict[str, tuple[str, ...]]) -> tuple[str, list[str]]:
    """Check the full DAG, require one merged head, and return a stable order."""
    if not graph:
        raise MigrationDriftError("Migration graph is empty")
    children: dict[str, set[str]] = {revision: set() for revision in graph}
    degrees = {revision: len(parents) for revision, parents in graph.items()}
    for revision, parents in graph.items():
        for parent in parents:
            if parent not in graph:
                raise MigrationDriftError("Migration graph has an unknown parent")
            children[parent].add(revision)
    heads = set(graph) - {p for parents in graph.values() for p in parents}
    if len(heads) != 1:
        raise MigrationDriftError("Source must have exactly one merged migration head")
    ready = sorted(key for key, degree in degrees.items() if degree == 0)
    ordered = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            degrees[child] -= 1
            if degrees[child] == 0:
                ready.append(child)
                ready.sort()
    if len(ordered) != len(graph):
        raise MigrationDriftError("Source migration graph contains a cycle")
    head = next(iter(heads))
    ancestors = set()

    def visit(revision: str) -> None:
        if revision in ancestors:
            return
        ancestors.add(revision)
        for parent in graph[revision]:
            visit(parent)

    visit(head)
    if ancestors != set(graph):
        raise MigrationDriftError("Source contains revisions unreachable from its head")
    return head, ordered


def assess(readback: object, *, project_ref: str, source_revision: str,
           directory: Path = VERSIONS, now: datetime | None = None) -> dict:
    """Evidence consistency only; a matching readback is NOT staging qualification."""
    if not isinstance(source_revision, str) or not REVISION.fullmatch(source_revision):
        raise MigrationDriftError("Exact 40-character source Git SHA required")
    if not isinstance(project_ref, str) or not re.fullmatch(r"[a-z0-9]{20}", project_ref):
        raise MigrationDriftError("Expected staging Supabase project ref required")
    if not isinstance(readback, dict) or set(readback) != {
        "project_ref", "schema", "revision", "private_table_count", "postgres_version", "observed_at"
    }:
        raise MigrationDriftError("Readback must have the exact non-secret schema identity fields")
    if readback["project_ref"] != project_ref or readback["schema"] != "shuddho_coworker":
        raise MigrationDriftError("Readback project/schema identity mismatch")
    if type(readback["private_table_count"]) is not int or readback["private_table_count"] < 1:
        raise MigrationDriftError("Readback table count must be positive")
    if (not isinstance(readback["postgres_version"], str)
            or not VERSION.fullmatch(readback["postgres_version"])):
        raise MigrationDriftError("Readback PostgreSQL version is invalid")
    try:
        observed = datetime.fromisoformat(readback["observed_at"].replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        raise MigrationDriftError("Readback observation time is invalid") from None
    current_time = now or datetime.now(timezone.utc)
    if (observed.tzinfo is None or current_time.tzinfo is None
            or not current_time - timedelta(hours=24) <= observed <= current_time):
        raise MigrationDriftError("Readback timestamp must be timezone-aware and within 24 hours")
    graph = migration_graph(directory)
    head, ordered = ordered_migrations(graph)
    revision = readback["revision"]
    if not isinstance(revision, str) or revision not in graph:
        raise MigrationDriftError("Staging revision is not present in the source migration graph")
    deployed_ancestors = set()

    def visit(value: str) -> None:
        if value in deployed_ancestors:
            return
        deployed_ancestors.add(value)
        for parent in graph[value]:
            visit(parent)

    visit(revision)
    pending = [value for value in ordered if value not in deployed_ancestors]
    return {
        "source_revision": source_revision,
        "project_ref": project_ref,
        "database_revision": revision,
        "source_head": head,
        "pending_revisions": pending,
        "source_matches_readback": revision == head,
        "disposition": "SOURCE_ALIGNED_NOT_QUALIFIED" if revision == head else "MIGRATION_DRIFT_BLOCKS_PILOT",
        "independent_readback_authenticated_by_tool": False,
        "staging_qualified": False,
        "migration_authorized": False,
        "deployment_authorized": False,
        "observed_at": observed.astimezone(timezone.utc).isoformat(),
        "private_table_count": readback["private_table_count"],
        "postgres_version": readback["postgres_version"],
    }


def read_readback(path: Path) -> object:
    try:
        mode = path.lstat().st_mode
        if (not stat.S_ISREG(mode) or path.resolve().is_relative_to(ROOT)
                or path.stat().st_size > MAX_READBACK_BYTES):
            raise MigrationDriftError("Readback must be a bounded external regular file, not a link")

        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise MigrationDriftError("Duplicate readback JSON field")
                obj[key] = value
            return obj

        def no_constant(value):
            raise MigrationDriftError("Non-finite readback JSON value: " + value)

        def finite_float(value):
            result = float(value)
            if not math.isfinite(result):
                raise MigrationDriftError("Non-finite readback JSON number")
            return result

        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=no_constant, parse_float=finite_float)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise MigrationDriftError("Cannot read trustworthy bounded staging readback") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readback", required=True, type=Path)
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args(argv)
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                              capture_output=True, check=True).stdout.strip()
        if head != args.source_revision:
            raise MigrationDriftError("Source revision is not the exact checkout HEAD")
        report = assess(read_readback(args.readback), project_ref=args.project_ref,
                        source_revision=head)
    except (MigrationDriftError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Day 1 staging migration identity blocked: {error}\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["source_matches_readback"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
