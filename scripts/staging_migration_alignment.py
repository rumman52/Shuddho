"""Read-only reconciliation of a verified staging backup against checked-in Alembic revisions.

Never executes migrations, connects to a database, or establishes release authority.
A verified backup can preserve an older schema while remaining unsafe to serve
the latest API and worker revision.
"""
from __future__ import annotations

import ast
from pathlib import Path
import re


VERSIONS = Path(__file__).resolve().parents[1] / "services/coworker/migrations/versions"
REVISION = re.compile(r"^[A-Za-z0-9_]{1,128}$")


class MigrationAlignmentError(RuntimeError):
    """The checked-in migration DAG cannot be trusted for source alignment."""


def _revision_metadata(path: Path) -> tuple[str, tuple[str, ...]]:
    try:
        raw = path.read_bytes()
        if not raw or len(raw) > 256_000:
            raise MigrationAlignmentError("Migration source is empty or oversized.")
        tree = ast.parse(raw, filename=str(path))
        values: dict[str, object] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                    if target.id in values:
                        raise MigrationAlignmentError("Duplicate Alembic metadata field.")
                    values[target.id] = ast.literal_eval(node.value)
    except (OSError, SyntaxError, ValueError, TypeError, RecursionError) as error:
        raise MigrationAlignmentError("Cannot safely parse Alembic metadata.") from error

    revision, parents = values.get("revision"), values.get("down_revision")
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise MigrationAlignmentError("Migration revision is absent or invalid.")
    if parents is None:
        parent_ids: tuple[str, ...] = ()
    elif isinstance(parents, str):
        parent_ids = (parents,)
    elif isinstance(parents, tuple) and all(isinstance(p, str) for p in parents):
        parent_ids = parents
    else:
        raise MigrationAlignmentError("Migration parents must be literal revision IDs.")
    if (len(set(parent_ids)) != len(parent_ids)
            or any(not REVISION.fullmatch(p) or p == revision for p in parent_ids)):
        raise MigrationAlignmentError("Migration has duplicate or invalid parents.")
    return revision, parent_ids


def migration_graph(versions: Path = VERSIONS) -> tuple[dict[str, tuple[str, ...]], str]:
    """Parse only literal Alembic revision metadata, never import migration code."""
    if not versions.is_dir():
        raise MigrationAlignmentError("Checked-in migration directory is unavailable.")
    files = sorted(path for path in versions.glob("*.py") if path.name != "__init__.py")
    if not 1 <= len(files) <= 500:
        raise MigrationAlignmentError("Migration inventory is empty or oversized.")
    graph: dict[str, tuple[str, ...]] = {}
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise MigrationAlignmentError("Migration source must be a regular file.")
        revision, parents = _revision_metadata(path)
        if revision in graph:
            raise MigrationAlignmentError("Duplicate migration revision.")
        graph[revision] = parents

    all_parents = {parent for parents in graph.values() for parent in parents}
    if not all_parents.issubset(graph):
        raise MigrationAlignmentError("Migration history has an absent parent.")
    heads = set(graph) - all_parents
    if len(heads) != 1:
        raise MigrationAlignmentError("Migration history must have exactly one head.")
    head = next(iter(heads))

    # All revisions must be reachable from the unique head, and the graph
    # must be acyclic. A disconnected cycle cannot masquerade as an old branch.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(revision: str) -> None:
        if revision in visiting:
            raise MigrationAlignmentError("Migration history contains a cycle.")
        if revision in visited:
            return
        visiting.add(revision)
        for parent in graph[revision]:
            visit(parent)
        visiting.remove(revision)
        visited.add(revision)

    visit(head)
    if len(visited) != len(graph):
        raise MigrationAlignmentError("Migration history contains an unreachable revision.")
    return graph, head


def source_schema_alignment(observed_revision: object, versions: Path = VERSIONS) -> dict:
    """Report source-vs-code schema identity; never claim migration authorization.

    A known older revision remains a valid backup source. It is not a current
    release schema. The pending list preserves parent-first dependency order,
    including both parents of an Alembic merge revision.
    """
    graph, head = migration_graph(versions)
    if not isinstance(observed_revision, str) or not REVISION.fullmatch(observed_revision):
        return {
            "status": "unrecognized_source_revision", "source_revision": None,
            "code_head": head, "source_is_current": False,
            "pending_migrations": None, "release_qualified": False,
        }
    if observed_revision not in graph:
        return {
            "status": "unrecognized_source_revision", "source_revision": observed_revision,
            "code_head": head, "source_is_current": False,
            "pending_migrations": None, "release_qualified": False,
        }

    applied: set[str] = set()

    def ancestors(node: str) -> None:
        if node in applied:
            return
        applied.add(node)
        for parent in graph[node]:
            ancestors(parent)

    ancestors(observed_revision)
    pending: list[str] = []
    visited: set[str] = set()

    def ordered(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        for parent in sorted(graph[node]):
            ordered(parent)
        if node not in applied:
            pending.append(node)

    ordered(head)
    current = observed_revision == head
    return {
        "status": "current" if current else "migration_required",
        "source_revision": observed_revision, "code_head": head,
        "source_is_current": current, "pending_migrations": pending,
        "release_qualified": False,
    }
