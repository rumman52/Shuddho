from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

REVISION = "a" * 40


def _build_inputs(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "shuddho-test"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "fastapi"\nversion = "0.115.0"\n',
        encoding="utf-8",
    )


def test_build_digest_is_deterministic_and_binds_every_build_input(tmp_path):
    from services.coworker.runtime_identity import compute_build_digest

    _build_inputs(tmp_path)
    inputs = {
        "root": tmp_path,
        "source_revision": REVISION,
        "distributions": [("fastapi", "0.115.0"), ("sqlalchemy", "2.0.36")],
        "python_implementation": "CPython",
        "python_version": "3.11.9",
        "platform_identity": "linux-x86_64",
    }
    first = compute_build_digest(**inputs)
    assert first == compute_build_digest(**inputs)
    assert len(first) == 64 and set(first) <= set("0123456789abcdef")

    changed_lock = tmp_path / "uv.lock"
    changed_lock.write_text(changed_lock.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
    assert compute_build_digest(**inputs) != first

    changed_distributions = {**inputs, "distributions": [("fastapi", "0.115.0"), ("sqlalchemy", "2.0.37")]}
    assert compute_build_digest(**changed_distributions) != first

    changed_source = {**inputs, "source_revision": "b" * 40}
    assert compute_build_digest(**changed_source) != first


def test_build_digest_rejects_symlink_inputs_and_invalid_source_revision(tmp_path):
    from services.coworker.runtime_identity import compute_build_digest

    _build_inputs(tmp_path)
    (tmp_path / "uv.lock").unlink()
    (tmp_path / "external.lock").write_text("not a project lockfile", encoding="utf-8")
    (tmp_path / "uv.lock").symlink_to(tmp_path / "external.lock")
    with pytest.raises(ValueError, match="regular|symlink|build input"):
        compute_build_digest(root=tmp_path, source_revision=REVISION)

    (tmp_path / "uv.lock").unlink()
    _build_inputs(tmp_path)
    with pytest.raises(ValueError, match="source revision"):
        compute_build_digest(root=tmp_path, source_revision="not-a-revision")


def test_runtime_identity_binds_build_schema_model_queue_and_capability_registry(tmp_path):
    from services.coworker.config import Settings
    from services.coworker.runtime_identity import build_runtime_identity
    from scripts.staging_release_freeze import canonical_sha256

    _build_inputs(tmp_path)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.sqlite3'}",
        auth_issuer="https://identity.example.test/auth/v1",
        environment="staging",
        storage_backend="local",
        source_revision=REVISION,
        task_queue="shuddho-documents-v1",
        cohort_enforced=True,
        cohort_account_ids=frozenset({"synthetic-owner-a"}),
        cohort_max_users=5,
        chat_provider="deepseek",
        deepseek_model="deepseek-flash",
    )

    class Repository:
        def current_schema_revision(self):
            return "0073_worker_runtime_identity"

        def reviewed_skill_runtime_manifest(self):
            return {"research": {
                "state": "unselected", "publication_version": None,
                "publication_sha256": None, "review_sha256": None,
                "source_revision": None, "task_workflow_version": None,
                "generation": None,
            }}

    distributions = [("fastapi", "0.115.0"), ("sqlalchemy", "2.0.36")]
    identity = build_runtime_identity(
        settings, Repository(), root=tmp_path, distributions=distributions,
        python_implementation="CPython", python_version="3.11.9",
        platform_identity="linux-x86_64",
    )
    expected = {key: value for key, value in identity.items() if key != "runtime_identity_sha256"}
    assert identity["schema_version"] == 3
    assert identity["source_revision"] == REVISION
    assert identity["schema_revision"] == "0073_worker_runtime_identity"
    assert identity["model_provider"] == "deepseek"
    assert identity["model_id"] == "deepseek-flash"
    assert identity["task_queue"] == "shuddho-documents-v1"
    assert identity["build_digest"] == identity["build_digest"].lower()
    assert identity["runtime_identity_sha256"] == canonical_sha256(expected)

    changed = build_runtime_identity(
        replace(settings, deepseek_model="deepseek-next"),
        Repository(), root=tmp_path, distributions=distributions,
        python_implementation="CPython", python_version="3.11.9",
        platform_identity="linux-x86_64",
    )
    assert changed["runtime_identity_sha256"] != identity["runtime_identity_sha256"]


def test_runtime_manifest_v3_is_registered_without_replacing_v2():
    from services.coworker.api import router

    paths = {route.path for route in router.routes}
    assert "/api/v1/runtime-manifest" in paths
    assert "/api/v1/runtime-manifest/v3" in paths


def test_worker_registry_persists_immutable_release_identity_columns():
    from services.coworker.models import WorkerInstance

    columns = set(WorkerInstance.__table__.columns.keys())
    assert {
        "build_digest", "schema_revision", "model_provider",
        "model_id", "runtime_identity_sha256",
    } <= columns


def test_worker_runtime_identity_migration_is_the_single_alembic_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["0073_worker_runtime_identity"]
    migration = script.get_revision("0073_worker_runtime_identity")
    assert migration.down_revision == "0072_merge_0071_heads"
