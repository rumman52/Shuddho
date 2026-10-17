from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.errors import CoworkerError
from services.coworker.migrate import upgrade
from services.coworker.models import Task, WorkerInstance, utcnow
from services.coworker.repository import Repository
from services.coworker.schemas import ResearchOptions, TaskCreate
from services.coworker.task_workflow_versions import REVIEWED_RESEARCH_WORKFLOW_VERSION
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
    # Simulate an already-running legacy binary. New PostgreSQL inserts from
    # old binaries are blocked by the registration attestation trigger, but
    # existing rows must remain visible to drain and staging-evidence checks.
    old = str(uuid4())
    with repository.sessions.begin() as db:
        db.add(WorkerInstance(
            id=old,
            task_queue=repository.settings.task_queue,
            source_revision=OLD_REVISION,
            state="running",
            heartbeat_at=utcnow(),
        ))
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


def seed_active_research_task(
    repository: Repository,
    *,
    subject: str,
    agent_owned: bool = False,
    workflow_version: str | None = None,
) -> None:
    """Create a queued research Task and optionally model an unsafe persisted identity."""
    repository.settings = replace(
        repository.settings,
        research_services_enabled=True,
    )
    principal = Principal(ISSUER, subject, 0)
    repository.ensure_account(principal)
    task, created = repository.create_task(
        principal.account_id,
        TaskCreate(
            skill_id="research",
            instruction="Synthetic active research task for the CW-11 ledger gate.",
            notes="Ledger-only test; no provider dispatch.",
            output_language="en",
            research=ResearchOptions(query="synthetic staging ledger"),
        ),
        f"cw11-ledger-{subject}",
        enqueue=False,
    )
    assert created is True
    with repository.sessions.begin() as db:
        row = db.get(Task, task["id"])
        assert row is not None
        if agent_owned:
            # The historical Agent-owned Task has no reviewed identity Step.
            row.agent_run_id = f"synthetic-agent-run-{subject}"
        if workflow_version is not None:
            # Model an active reviewed-version Task missing its identity Step.
            row.workflow_version = workflow_version


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
    assert result["assertions"]["no_reviewed_task_ledger_blockers"] is True
    assert result["reviewed_task_ledger"]["decision"] == "TASK_LEDGER_CHECK_ONLY"
    assert result["reviewed_task_ledger"]["blockers"] == []
    assert result["reviewed_task_ledger"]["rollout_authorized"] is False
    assert any(
        item["event_type"] == "publication_selected"
        and item["metadata"]["generation"] == 1
        for item in result["control_events"]
    )


@pytest.mark.parametrize(
    ("render_payload", "message"),
    [
        (None, "expected a JSON object"),
        ({"schema_version": True, "verified": True}, "unsupported schema"),
        (
            {**valid_render_evidence(), "candidate_live_commit": "c" * 40},
            "candidate revision does not match",
        ),
        (
            {**valid_render_evidence(), "old_worker_instance_count": False},
            "legacy worker is stopped",
        ),
        (
            {**valid_render_evidence(), "provider_api_key": "must-not-be-echoed"},
            "missing or unexpected fields",
        ),
    ],
)
def test_collector_revalidates_external_render_evidence_at_boundary(
    staging_repository,
    render_payload,
    message,
):
    repository, settings = staging_repository
    # No publication is seeded: the expected failure proves payload validation
    # happens before any database-backed selection check.
    with pytest.raises(SystemExit, match=message):
        evidence.collect_evidence(
            repository,
            staging_settings(settings),
            expected_publication_version="research_reviewed_v1",
            old_source_revision=OLD_REVISION,
            render_evidence=render_payload,
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


@pytest.mark.parametrize(
    ("agent_owned", "workflow_version", "subject"),
    [
        (True, None, "ambiguous-legacy-agent"),
        (False, REVIEWED_RESEARCH_WORKFLOW_VERSION, "missing-reviewed-identity"),
    ],
)
def test_collector_blocks_task_ledger_classification_gaps(
    staging_repository,
    agent_owned,
    workflow_version,
    subject,
):
    repository, settings = staging_repository
    seed_release(repository)
    seed_active_research_task(
        repository,
        subject=subject,
        agent_owned=agent_owned,
        workflow_version=workflow_version,
    )

    with pytest.raises(
        CoworkerError,
        match="task ledger has active blockers",
    ):
        evidence.collect_evidence(
            repository,
            staging_settings(settings),
            expected_publication_version="research_reviewed_v1",
            old_source_revision=OLD_REVISION,
            render_evidence=valid_render_evidence(),
        )


def test_collector_blocks_drained_worker_without_timestamp(
    staging_repository,
):
    repository, settings = staging_repository
    seed_release(repository)
    old_row = next(
        row for row in repository.worker_inventory(task_queue=settings.task_queue)
        if row["source_revision"] == OLD_REVISION
    )
    with repository.sessions.begin() as db:
        row = db.get(WorkerInstance, old_row["id"])
        assert row is not None
        assert row.state == "drained"
        row.drained_at = None

    with pytest.raises(
        CoworkerError,
        match="legacy worker row is not explicitly drained",
    ):
        evidence.collect_evidence(
            repository,
            staging_settings(settings),
            expected_publication_version="research_reviewed_v1",
            old_source_revision=OLD_REVISION,
            render_evidence=valid_render_evidence(),
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
    # Simulate a pre-existing legacy binary that writes its old-format
    # inventory row without the current registration guard. The collector must
    # still detect the unsafe mixed-version fleet at the evidence boundary.
    with repository.sessions.begin() as db:
        db.add(WorkerInstance(
            id=str(uuid4()),
            task_queue=settings.task_queue,
            source_revision=OLD_REVISION,
            state="running",
            heartbeat_at=utcnow(),
        ))
    with pytest.raises(CoworkerError, match="incompatible worker"):
        evidence.collect_evidence(
            repository,
            staging_settings(settings),
            expected_publication_version="research_reviewed_v1",
            old_source_revision=OLD_REVISION,
            render_evidence=valid_render_evidence(),
        )

@pytest.mark.parametrize(
    ("revision", "state", "stale_heartbeat"),
    [
        ("c" * 40, "lost", False),
        ("c" * 40, "unexpected-state", False),
        (CANDIDATE_REVISION, "running", True),
    ],
)
def test_collector_blocks_lost_or_stale_worker_records(
    staging_repository,
    revision,
    state,
    stale_heartbeat,
):
    repository, settings = staging_repository
    seed_release(repository)
    # Insert a persisted row directly to model legacy/unknown worker records
    # that predate the current registration guard.
    worker_id = str(uuid4())
    heartbeat_at = (
        utcnow() - timedelta(hours=1)
        if stale_heartbeat
        else utcnow()
    )
    with repository.sessions.begin() as db:
        db.add(WorkerInstance(
            id=worker_id,
            task_queue=settings.task_queue,
            source_revision=revision,
            state=state,
            heartbeat_at=heartbeat_at,
        ))

    with pytest.raises(
        CoworkerError,
        match="lost, stale or unknown worker",
    ):
        evidence.collect_evidence(
            repository,
            staging_settings(settings),
            expected_publication_version="research_reviewed_v1",
            old_source_revision=OLD_REVISION,
            render_evidence=valid_render_evidence(),
        )

