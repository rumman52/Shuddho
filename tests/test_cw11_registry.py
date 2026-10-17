from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
import time
import pytest
pytest.importorskip("sqlalchemy", reason="Install the coworker extra for CW-11 tests")
pytest.importorskip("temporalio", reason="Install the coworker extra for CW-11 tests")

from sqlalchemy import select

from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.errors import CoworkerError
from services.coworker.migrate import upgrade
from services.coworker.models import ReviewedSkillPublication, ReviewedSkillRegistryEvent, Step, Task, WorkerInstance, utcnow
from services.coworker.task_workflow_versions import PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION
from services.coworker.reviewed_skill_registry import (
    REVIEWED_RESEARCH_SKILL,
    REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
    build_reviewed_publication,
)
from services.coworker.schemas import ResearchOptions, TaskCreate

ISSUER = "https://identity.example.test/auth/v1"
REV_A = "a" * 40
REV_B = "b" * 40


@pytest.fixture
def container(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'cw11.sqlite3'}",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        source_revision=REV_A,
        task_queue="cw11-test-queue",
        agent_runtime_enabled=True,
        research_services_enabled=True,
        agent_reviewed_research_skill_enabled=True,
        search_provider="tavily",
        search_api_key="fixture-only-search-key",
    )
    upgrade(settings.database_url)
    value = Container.create(settings)
    yield value
    value.repository.sessions.kw["bind"].dispose()


def account(container, subject="alice"):
    return container.repository.ensure_account(
        Principal(ISSUER, subject, int(time.time()) + 3600)
    )["account_id"]


def worker(container, revision: str):
    worker_id = container.repository.register_worker(
        task_queue=container.settings.task_queue,
        source_revision=revision,
    )
    assert container.repository.heartbeat_worker(worker_id) == "running"
    return worker_id


def publish(container, version: str, *, source_revision: str = REV_A, rollback_target: str | None = None):
    publication = build_reviewed_publication(
        skill_name=REVIEWED_RESEARCH_SKILL,
        publication_version=version,
        task_workflow_version=REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
        source_revision=source_revision,
        rollback_target_version=rollback_target,
    )
    return container.repository.publish_reviewed_skill(
        publication,
        actor_reference="cw11-test-operator",
        reason="CW-11 registry regression fixture",
    )


def reviewed_task(container, owner: str, key: str):
    run, _ = container.agent.create(
        owner,
        AgentRunCreate(goal="Research public evidence.", output_language="en"),
        key + "-run",
        tool_allowlist=["research.search"],
    )
    plan = container.agent.save_plan(owner, run["id"], [AgentPlanStep(
        tool="research.search",
        arguments={
            "instruction": "Research public evidence.",
            "notes": "",
            "document_ids": [],
            "output_language": "en",
            "query": "reliable public sources",
            "time_range": "any",
        },
    )])
    task, _ = container.repository.create_task(
        owner,
        TaskCreate(
            skill_id="research",
            instruction="Research public evidence.",
            research=ResearchOptions(query="reliable public sources"),
        ),
        key,
        enqueue=False,
        agent_run_id=run["id"],
        agent_step_id=plan["tool_invocations"][0]["step_id"],
    )
    return task


def test_registry_event_maps_reserved_metadata_column_without_reserved_orm_attribute(container):
    """Keep the legacy SQL column while avoiding SQLAlchemy's reserved attribute name."""
    assert ReviewedSkillRegistryEvent.__table__.c.metadata.name == "metadata"
    with container.repository.sessions.begin() as db:
        db.add(
            ReviewedSkillRegistryEvent(
                id="registry-event-metadata-regression",
                skill_name=REVIEWED_RESEARCH_SKILL,
                event_type="test_metadata",
                actor_reference="cw11-test-operator",
                reason="reserved ORM name regression",
                event_metadata={"revision": REV_A},
            )
        )

    history = container.repository.reviewed_control_history(limit=1)
    assert history[0]["event_type"] == "test_metadata"
    assert history[0]["metadata"] == {"revision": REV_A}


def test_publication_is_source_bound_and_not_auto_selected(container):
    mismatched = build_reviewed_publication(
        skill_name=REVIEWED_RESEARCH_SKILL,
        publication_version="research_reviewed_mismatch",
        task_workflow_version=REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
        source_revision=REV_B,
    )
    with pytest.raises(CoworkerError) as blocked:
        container.repository.publish_reviewed_skill(
            mismatched,
            actor_reference="cw11-test-operator",
            reason="must reject source mismatch",
        )
    assert blocked.value.code == "skill_worker_revision_mismatch"

    worker(container, REV_A)
    publish(container, "research_reviewed_unselected", source_revision=REV_A)
    assert container.repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL) is None
    publications = container.repository.list_reviewed_publications()
    assert publications[0]["publication_version"] == "research_reviewed_unselected"
    assert publications[0]["state"] == "published"
    with container.repository.sessions() as db:
        events = db.scalars(select(ReviewedSkillRegistryEvent)).all()
        assert [event.event_type for event in events] == ["publication_published"]


def test_selection_requires_compatible_fleet_and_never_auto_selects(container):
    old = worker(container, REV_B)
    publish(container, "research_reviewed_v0", source_revision=REV_A)
    with pytest.raises(CoworkerError) as blocked:
        container.repository.select_reviewed_skill(
            REVIEWED_RESEARCH_SKILL,
            "research_reviewed_v0",
            actor_reference="cw11-test-operator",
            reason="blocked mixed-version selection",
            worker_source_revision=REV_A,
        )
    assert blocked.value.code == "worker_fleet_incompatible"

    container.repository.mark_worker_drained(old)
    new = worker(container, REV_A)
    selected = container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        "research_reviewed_v0",
        actor_reference="cw11-test-operator",
        reason="initial compatible selection",
        worker_source_revision=REV_A,
    )
    assert selected["publication_version"] == "research_reviewed_v0"
    assert container.repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL)["publication_version"] == "research_reviewed_v0"
    with container.repository.sessions() as db:
        events = db.scalars(select(ReviewedSkillRegistryEvent).order_by(ReviewedSkillRegistryEvent.created_at)).all()
        assert [event.event_type for event in events] == [
            "publication_published", "worker_drained", "publication_selected",
        ]
    assert new


def test_worker_registration_fences_legacy_revision_and_allows_candidate_rollout(container):
    old_worker = worker(container, REV_A)
    publish(container, "research_registration_fence_v0", source_revision=REV_A)
    container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        "research_registration_fence_v0",
        actor_reference="cw11-test-operator",
        reason="seed the currently selected release",
        worker_source_revision=REV_A,
    )

    # A legacy revision cannot be introduced through the current runtime's
    # registration path after selection.
    with pytest.raises(CoworkerError) as blocked:
        container.repository.register_worker(
            task_queue=container.settings.task_queue,
            source_revision=REV_B,
        )
    assert blocked.value.code == "worker_fleet_incompatible"
    assert {
        row["source_revision"]
        for row in container.repository.worker_inventory(
            task_queue=container.settings.task_queue,
        )
    } == {REV_A}

    # A candidate deployment must be able to start while the old publication
    # remains selected; selection is the later gate that requires old workers
    # to finish draining before the new revision can be selected.
    container.settings = replace(container.settings, source_revision=REV_B)
    container.repository.settings = container.settings
    candidate_worker = container.repository.register_worker(
        task_queue=container.settings.task_queue,
        source_revision=REV_B,
    )
    assert container.repository.heartbeat_worker(candidate_worker) == "running"
    publish(container, "research_registration_fence_v1", source_revision=REV_B)

    with pytest.raises(CoworkerError) as mixed_fleet:
        container.repository.select_reviewed_skill(
            REVIEWED_RESEARCH_SKILL,
            "research_registration_fence_v1",
            actor_reference="cw11-test-operator",
            reason="candidate must wait for old worker drain",
            worker_source_revision=REV_B,
        )
    assert mixed_fleet.value.code == "worker_fleet_incompatible"
    assert (
        container.repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL)["publication_version"]
        == "research_registration_fence_v0"
    )

    container.repository.mark_worker_drained(old_worker)
    selected = container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        "research_registration_fence_v1",
        actor_reference="cw11-test-operator",
        reason="select after explicit old worker drain",
        worker_source_revision=REV_B,
    )
    assert selected["publication_version"] == "research_registration_fence_v1"

    # A separate task queue is not governed by this queue's reviewed selection.
    unrelated = container.repository.register_worker(
        task_queue="cw11-unrelated-queue",
        source_revision=REV_A,
    )
    assert any(
        row["id"] == unrelated and row["source_revision"] == REV_A
        for row in container.repository.worker_inventory(
            task_queue="cw11-unrelated-queue",
        )
    )


def test_selected_publication_remains_the_agent_gate_after_feature_flag_off(container):
    worker(container, REV_A)
    publish(container, "research_reviewed_flag_off", source_revision=REV_A)
    container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        "research_reviewed_flag_off",
        actor_reference="cw11-test-operator",
        reason="registry replaces mutable admission flag",
        worker_source_revision=REV_A,
    )
    disabled = replace(
        container.settings,
        agent_reviewed_research_skill_enabled=False,
    )
    container.settings = disabled
    container.repository.settings = disabled
    container.agent.settings = disabled
    owner = account(container, "flag-off")
    task = reviewed_task(container, owner, "flag-off-research")
    assert task["workflow_version"] == "work_research_reviewed_v2"
    container.repository.worker_task(task["id"], False)


def test_normal_selection_preserves_old_publication_but_rollback_revokes_it(container):
    worker(container, REV_A)
    publish(container, "research_reviewed_v0", source_revision=REV_A)
    publish(container, "research_reviewed_v1", source_revision=REV_A, rollback_target="research_reviewed_v0")

    container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL, "research_reviewed_v0",
        actor_reference="cw11-test-operator", reason="select baseline",
        worker_source_revision=REV_A,
    )
    container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL, "research_reviewed_v1",
        actor_reference="cw11-test-operator", reason="select candidate",
        worker_source_revision=REV_A,
    )
    with container.repository.sessions() as db:
        assert db.scalar(select(ReviewedSkillPublication).where(
            ReviewedSkillPublication.publication_version == "research_reviewed_v0"
        )).state == "published"

    owner = account(container)
    task = reviewed_task(container, owner, "rollback-bound-task")
    with container.repository.sessions() as db:
        pinned = db.get(Step, (task["id"], "reviewed_skill_identity")).output
    assert pinned["publication_version"] == "research_reviewed_v1"

    container.repository.rollback_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        "research_reviewed_v0",
        actor_reference="cw11-test-operator",
        reason="candidate rollback",
        worker_source_revision=REV_A,
    )
    with container.repository.sessions() as db:
        v1 = db.scalar(select(ReviewedSkillPublication).where(
            ReviewedSkillPublication.publication_version == "research_reviewed_v1"
        ))
        assert v1.state == "rolled_back"
    with pytest.raises(CoworkerError) as denied:
        container.repository.worker_task(task["id"], False)
    assert denied.value.code == "skill_manifest_unreviewed"


def test_worker_drain_stops_new_claims_and_requires_explicit_drained_state(container):
    old = worker(container, REV_B)
    new = worker(container, REV_A)
    assert container.repository.request_worker_drain(
        task_queue=container.settings.task_queue,
        source_revision=REV_B,
        actor_reference="cw11-test-operator",
        reason="mixed-version drain qualification",
    ) == 1
    assert container.repository.heartbeat_worker(old) == "draining"
    assert container.repository.claim_outbox(worker_id=old) == []
    with pytest.raises(CoworkerError) as incomplete:
        container.repository.assert_worker_drain_complete(
            task_queue=container.settings.task_queue,
            old_source_revision=REV_B,
        )
    assert incomplete.value.code == "worker_drain_incomplete"

    container.repository.mark_worker_drained(old)
    evidence = container.repository.assert_worker_drain_complete(
        task_queue=container.settings.task_queue,
        old_source_revision=REV_B,
    )
    assert evidence["verified"] is True
    with container.repository.sessions() as db:
        assert db.get(WorkerInstance, old).state == "drained"
        assert db.get(WorkerInstance, new).state == "running"


def test_legacy_migration_is_atomic_and_requires_no_search_attempt(container):
    old = worker(container, REV_B)
    worker(container, REV_A)
    container.repository.mark_worker_drained(old)
    publish(container, "research_reviewed_v0", source_revision=REV_A)
    publish(container, "research_reviewed_v1", source_revision=REV_A, rollback_target="research_reviewed_v0")
    container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL, "research_reviewed_v1",
        actor_reference="cw11-test-operator", reason="migration target",
        worker_source_revision=REV_A,
    )
    owner = account(container)
    safe = reviewed_task(container, owner, "legacy-safe")
    blocked = reviewed_task(container, owner, "legacy-blocked")
    with container.repository.sessions.begin() as db:
        for task_id in (safe["id"], blocked["id"]):
            task = db.get(Task, task_id)
            task.workflow_version = PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION
            identity = db.get(Step, (task_id, "reviewed_skill_identity"))
            publication_id = identity.output["publication_id"]
            publication = db.get(ReviewedSkillPublication, publication_id)
            identity.output = {
                "name": "research",
                "version": "work_research_v1",
                "tool": "research.search",
                "tool_version": "1",
                "review_sha256": publication.review_sha256,
            }
        db.add(Step(task_id=blocked["id"], phase="search_attempt", output={"state": "prepared"}))

    container.repository.mark_worker_drained(old)
    with pytest.raises(CoworkerError) as atomic_block:
        container.repository.migrate_legacy_reviewed_tasks(
            task_queue=container.settings.task_queue,
            old_source_revision=REV_B,
            publication_version="research_reviewed_v1",
            actor_reference="cw11-test-operator",
            reason="atomic legacy migration",
        )
    assert atomic_block.value.code == "skill_migration_blocked"
    with container.repository.sessions() as db:
        assert db.get(Task, safe["id"]).workflow_version == PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION
        assert db.get(Task, blocked["id"]).workflow_version == PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION


def test_legacy_migration_moves_only_reviewed_rows_after_drain(container):
    old = worker(container, REV_B)
    worker(container, REV_A)
    container.repository.mark_worker_drained(old)
    publish(container, "research_reviewed_v0", source_revision=REV_A)
    publish(container, "research_reviewed_v1", source_revision=REV_A, rollback_target="research_reviewed_v0")
    container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL, "research_reviewed_v1",
        actor_reference="cw11-test-operator", reason="migration target",
        worker_source_revision=REV_A,
    )
    owner = account(container)
    reviewed = reviewed_task(container, owner, "legacy-reviewed")
    with container.repository.sessions.begin() as db:
        task = db.get(Task, reviewed["id"])
        task.workflow_version = PRE_FENCE_REVIEWED_RESEARCH_WORKFLOW_VERSION
        identity = db.get(Step, (reviewed["id"], "reviewed_skill_identity"))
        publication_id = identity.output["publication_id"]
        publication = db.get(ReviewedSkillPublication, publication_id)
        identity.output = {
            "name": "research",
            "version": "work_research_v1",
            "tool": "research.search",
            "tool_version": "1",
            "review_sha256": publication.review_sha256,
        }
    container.repository.mark_worker_drained(old)
    result = container.repository.migrate_legacy_reviewed_tasks(
        task_queue=container.settings.task_queue,
        old_source_revision=REV_B,
        publication_version="research_reviewed_v1",
        actor_reference="cw11-test-operator",
        reason="safe historical migration",
    )
    assert result["verified"] is True
    assert result["migrated"] == 1
    with container.repository.sessions() as db:
        task = db.get(Task, reviewed["id"])
        assert task.workflow_version == "work_research_reviewed_v2"
        identity = db.get(Step, (reviewed["id"], "reviewed_skill_identity")).output
        assert identity["publication_version"] == "research_reviewed_v1"


@pytest.mark.parametrize("state,stale", [
    ("lost", False),
    ("unknown", False),
    ("drained", False),  # A lifecycle label without a completion timestamp.
    ("starting", True),
    ("running", True),
    ("draining", True),
])
@pytest.mark.parametrize("operation", ["select", "admit", "rollback"])
def test_uncertain_worker_cannot_authorize_reviewed_controls(container, state, stale, operation):
    worker(container, REV_A)
    publish(container, "baseline")
    publish(container, "candidate", rollback_target="baseline")
    repository = container.repository
    repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL, "candidate",
        actor_reference="operator", reason="establish selection",
        worker_source_revision=REV_A,
    )
    uncertain_id = worker(container, REV_A)
    with repository.sessions.begin() as db:
        row = db.get(WorkerInstance, uncertain_id)
        row.state = state
        if stale:
            row.heartbeat_at = utcnow() - timedelta(minutes=1)
    before = repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL)
    events_before = repository.reviewed_control_history()
    owner = account(container, "uncertain-fleet")
    with pytest.raises(CoworkerError) as blocked:
        if operation == "admit":
            reviewed_task(container, owner, "uncertain-admission")
        elif operation == "rollback":
            repository.rollback_reviewed_skill(
                REVIEWED_RESEARCH_SKILL, "baseline",
                actor_reference="operator", reason="must fail closed",
                worker_source_revision=REV_A,
            )
        else:
            repository.select_reviewed_skill(
                REVIEWED_RESEARCH_SKILL, "baseline",
                actor_reference="operator", reason="must fail closed",
                worker_source_revision=REV_A,
            )
    assert blocked.value.code == "worker_fleet_uncertain"
    assert repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL) == before
    assert repository.reviewed_control_history() == events_before
    with repository.sessions() as db:
        assert db.scalar(select(Task.id).where(Task.owner_id == owner)) is None
        assert all(row.state == "published" for row in db.scalars(select(ReviewedSkillPublication)))


@pytest.mark.parametrize("state", ["lost", "unknown", "drained", "running", "draining", "starting"])
@pytest.mark.parametrize("operation", ["verify", "migrate"])
def test_uncertain_legacy_worker_never_proves_drain(container, state, operation):
    old = worker(container, REV_B)
    worker(container, REV_A)
    with container.repository.sessions.begin() as db:
        row = db.get(WorkerInstance, old)
        row.state = state
        row.heartbeat_at = utcnow() - timedelta(minutes=1)
    with pytest.raises(CoworkerError) as blocked:
        if operation == "verify":
            container.repository.assert_worker_drain_complete(
                task_queue=container.settings.task_queue, old_source_revision=REV_B,
            )
        else:
            container.repository.migrate_legacy_reviewed_tasks(
                task_queue=container.settings.task_queue, old_source_revision=REV_B,
                publication_version="nonexistent",
                actor_reference="operator", reason="must fail before migration",
            )
    assert blocked.value.code == "worker_drain_incomplete"


def test_uncertain_worker_in_other_queue_does_not_block_selection(container):
    worker(container, REV_A)
    other = container.repository.register_worker(task_queue="other-queue", source_revision=REV_B)
    with container.repository.sessions.begin() as db:
        db.get(WorkerInstance, other).state = "lost"
    publish(container, "isolated-queue")
    selected = container.repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL, "isolated-queue",
        actor_reference="operator", reason="queue isolation",
        worker_source_revision=REV_A,
    )
    assert selected["publication_version"] == "isolated-queue"


@pytest.mark.parametrize("outcome", ["success", "shutdown_error", "shutdown_cancelled", "dispatcher_error", "heartbeat_error"])
def test_worker_publishes_drain_only_after_successful_temporal_shutdown(container, monkeypatch, outcome):
    from services.coworker import worker as worker_module

    events = []
    repository = container.repository
    mark_drained = repository.mark_worker_drained
    engine = repository.sessions.kw["bind"]
    dispose_engine = engine.dispose

    def publish_drain(worker_id):
        events.append("drained")
        mark_drained(worker_id)

    def dispose():
        events.append("disposed")
        dispose_engine()

    class ControlledWorker:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            events.append("polling")
            return self

        async def __aexit__(self, *args):
            events.append("shutdown_started")
            assert "drained" not in events, "Registry advertised drain before Temporal shutdown"
            if outcome == "shutdown_error":
                raise RuntimeError("shutdown failed")
            if outcome == "shutdown_cancelled":
                raise asyncio.CancelledError()
            events.append("shutdown_complete")

    async def connect(*args, **kwargs):
        return object()

    async def dispatch(self, stop):
        if outcome == "dispatcher_error":
            raise RuntimeError("dispatcher failed")
        if outcome == "heartbeat_error":
            await stop.wait()
        stop.set()

    async def heartbeat(container, worker_id, stop):
        if outcome == "heartbeat_error":
            stop.set()
            raise RuntimeError("heartbeat failed")
        await stop.wait()

    monkeypatch.setattr(worker_module.Settings, "from_env", lambda: container.settings)
    monkeypatch.setattr(worker_module.Container, "create", lambda settings: container)
    monkeypatch.setattr(worker_module.Client, "connect", connect)
    monkeypatch.setattr(worker_module, "Worker", ControlledWorker)
    monkeypatch.setattr(worker_module.Dispatcher, "run", dispatch)
    monkeypatch.setattr(worker_module, "_worker_registry_heartbeat", heartbeat)
    monkeypatch.setattr(repository, "mark_worker_drained", publish_drain)
    monkeypatch.setattr(engine, "dispose", dispose)

    async def run():
        # Avoid changing process-wide SIGTERM/SIGINT handlers in a unit test.
        monkeypatch.setattr(asyncio.get_running_loop(), "add_signal_handler", lambda *args: None)
        await worker_module.main()

    if outcome == "success":
        asyncio.run(run())
        assert events == ["polling", "shutdown_started", "shutdown_complete", "drained", "disposed"]
        assert repository.worker_inventory()[0]["state"] == "drained"
    else:
        expected_error = asyncio.CancelledError if outcome == "shutdown_cancelled" else RuntimeError
        with pytest.raises(expected_error):
            asyncio.run(run())
        assert "drained" not in events
        assert repository.worker_inventory()[0]["state"] != "drained"
        assert "disposed" in events


def test_failed_registry_heartbeat_stops_dispatch_without_claiming_drain(container, monkeypatch):
    from services.coworker import worker as worker_module

    def unavailable(worker_id):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(container.repository, "heartbeat_worker", unavailable)

    async def run():
        stop = asyncio.Event()
        with pytest.raises(RuntimeError, match="registry unavailable"):
            await worker_module._worker_registry_heartbeat(container, "unavailable", stop)
        assert stop.is_set()

    asyncio.run(run())


@pytest.mark.parametrize("state", ["lost", "unknown"])
def test_worker_heartbeat_and_drain_do_not_rehabilitate_uncertain_state(container, state):
    worker_id = worker(container, REV_B)
    with container.repository.sessions.begin() as db:
        db.get(WorkerInstance, worker_id).state = state
    assert container.repository.heartbeat_worker(worker_id) == "lost"
    container.repository.mark_worker_drained(worker_id)
    row = container.repository.worker_inventory()[0]
    assert row["state"] == state
    assert row["drained_at"] is None
