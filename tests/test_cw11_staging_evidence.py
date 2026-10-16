from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.migrate import upgrade
from services.coworker.repository import Repository
from services.coworker.reviewed_skill_registry import (
    REVIEWED_RESEARCH_SKILL,
    build_pilot_publication,
)
import scripts.cw11_staging_evidence as evidence

ISSUER = "https://identity.example.test/auth/v1"
CANDIDATE_REVISION = "a" * 40
OLD_REVISION = "b" * 40


@pytest.fixture
def staging_repository(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'cw11-staging.sqlite3'}"
    upgrade(database_url)
    settings = Settings(
        database_url=database_url,
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        source_revision=CANDIDATE_REVISION,
        task_queue="cw11-staging-test-queue",
        search_provider="tavily",
        search_api_key="fixture-only",
    )
    repository = Repository(session_factory(database_url), settings)
    yield repository, settings
    repository.sessions.kw["bind"].dispose()


def valid_render_evidence() -> dict:
    return {
        "schema_version": 1,
        "old_worker_service_id": "srv-old",
        "candidate_worker_service_id": "srv-candidate",
        "old_source_revision": OLD_REVISION,
        "old_worker_live_commit": OLD_REVISION,
        "old_worker_instance_count": 0,
        "candidate_worker_instance_count": 1,
        "candidate_live_commit": CANDIDATE_REVISION,
        "verified": True,
    }


def seed_release(repository: Repository) -> None:
    candidate = repository.register_worker(
        task_queue=repository.settings.task_queue,
        source_revision=CANDIDATE_REVISION,
    )
    assert repository.heartbeat_worker(candidate) == "running"
    old = repository.register_worker(
        task_queue=repository.settings.task_queue,
        source_revision=OLD_REVISION,
    )
    assert repository.heartbeat_worker(old) == "running"
    repository.mark_worker_drained(old)
    publication = build_pilot_publication(
        source_revision=CANDIDATE_REVISION,
        publication_version="research_reviewed_v1",
    )
    repository.publish_reviewed_skill(
        publication,
        actor_reference="cw11-staging-test",
        reason="CW-11 staging collector test",
    )
    repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        publication["publication_version"],
        actor_reference="cw11-staging-test",
        reason="CW-11 staging collector selection test",
        worker_source_revision=CANDIDATE_REVISION,
    )


def staging_settings(settings: Settings) -> Settings:
    return replace(
        settings,
        environment="staging",
        storage_backend="s3",
        storage_bucket="shuddho-coworker-staging",
        storage_endpoint="https://storage.example.test",
    )


def test_collector_emits_verified_evidence_and_preserves_event_metadata(
    staging_repository,
    tmp_path,
):
    repository, settings = staging_repository
    seed_release(repository)
    render = valid_render_evidence()
    validate_settings = staging_settings(settings)

    result = evidence.collect_evidence(
        repository,
        validate_settings,
        expected_publication_version="research_reviewed_v1",
        old_source_revision=OLD_REVISION,
        render_evidence=render,
    )
    assert result["verified"] is True
    assert result["assertions"]["no_active_incompatible_workers"] is True
    assert any(
        item["event_type"] == "publication_selected"
        and item["metadata"]["generation"] == 1
        for item in result["control_events"]
    )


def test_render_evidence_rejects_unverified_or_malformed_payload():
    value = valid_render_evidence()
    value["verified"] = False
    with pytest.raises(SystemExit, match="unsupported schema or is not verified"):
        evidence.validate_render_evidence(
            value, OLD_REVISION, CANDIDATE_REVISION
        )

    value = valid_render_evidence()
    value["old_worker_service_id"] = value["candidate_worker_service_id"]
    with pytest.raises(SystemExit, match="two distinct worker services"):
        evidence.validate_render_evidence(
            value, OLD_REVISION, CANDIDATE_REVISION
        )


def test_collector_blocks_active_incompatible_worker(
    staging_repository,
):
    repository, settings = staging_repository
    candidate = repository.register_worker(
        task_queue=settings.task_queue,
        source_revision=CANDIDATE_REVISION,
    )
    repository.heartbeat_worker(candidate)
    repository.register_worker(
        task_queue=settings.task_queue,
        source_revision=OLD_REVISION,
    )
    publication = build_pilot_publication(
        source_revision=CANDIDATE_REVISION,
        publication_version="research_reviewed_v1",
    )
    repository.publish_reviewed_skill(
        publication,
        actor_reference="cw11-test",
        reason="CW-11 staging collector test",
    )
    repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        "research_reviewed_v1",
        actor_reference="cw11-test",
        reason="CW-11 staging collector selection test",
        worker_source_revision=CANDIDATE_REVISION,
    )
    with pytest.raises(Exception, match="incompatible worker"):
        evidence.collect_evidence(
            repository,
            staging_settings(settings),
            expected_publication_version="research_reviewed_v1",
            old_source_revision=OLD_REVISION,
            render_evidence=valid_render_evidence(),
        )
