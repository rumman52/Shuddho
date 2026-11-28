"""Validate that Coworker revisions form one reachable Alembic head.

Read migration metadata with the Python standard library so this guard runs in
both the lightweight core CI and the Coworker-extra CI environments.
"""
from __future__ import annotations

import ast
from pathlib import Path


VERSIONS = Path(__file__).resolve().parents[1] / (
    "services/coworker/migrations/versions"
)


def _revisions() -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for path in sorted(VERSIONS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        metadata: dict[str, object] = {}
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
                    metadata[target.id] = ast.literal_eval(node.value)
        assert "revision" in metadata and "down_revision" in metadata, path.name
        revision = metadata["revision"]
        parents = metadata["down_revision"]
        assert isinstance(revision, str) and revision not in graph, path.name
        if parents is None:
            parent_ids: tuple[str, ...] = ()
        elif isinstance(parents, str):
            parent_ids = (parents,)
        else:
            assert isinstance(parents, tuple) and all(isinstance(p, str) for p in parents)
            parent_ids = parents
        graph[revision] = parent_ids
    return graph


def test_coworker_migrations_have_one_head_and_preserve_both_0071_parents():
    graph = _revisions()
    all_parents = {parent for parents in graph.values() for parent in parents}
    assert all_parents <= set(graph), "Missing down_revision in migration history"
    assert set(graph) - all_parents == {"0073_worker_runtime_identity"}
    assert set(graph["0073_worker_runtime_identity"]) == {"0072_merge_0071_heads"}
    assert set(graph["0072_merge_0071_heads"]) == {"0071", "0071_project_scoped_goals"}
