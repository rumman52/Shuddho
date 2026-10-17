"""Deterministic PostgreSQL lock-order regressions for the CW-11 skill registry."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event, current_thread
from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for CW-11 tests")

from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError

from services.coworker.models import ReviewedSkillPublication, ReviewedSkillSelection, WorkerInstance
from services.coworker.errors import CoworkerError
from services.coworker.models import WorkerClaim, utcnow
from services.coworker.reviewed_skill_registry import WORKER_HEARTBEAT_TTL_SECONDS
from services.coworker.worker_claims import add_worker_claim, lock_running_worker
from services.coworker.reviewed_skill_registry import (
    REVIEWED_RESEARCH_SKILL,
    REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
    build_reviewed_publication,
)
from test_coworker_postgres import repository

pytestmark = [
    pytest.mark.coworker_integration,
    pytest.mark.skipif(
        not os.getenv("SHUDDHO_TEST_POSTGRES_URL"),
        reason="Dedicated PostgreSQL test database required",
    ),
]

REVISION = "a" * 40


@pytest.mark.parametrize("contender", ["admission", "rollback"])
def test_selection_uses_consistent_postgres_registry_lock_order(repository, contender):
    """Force select to hold worker rows before a competing control can lock selection.

    Before the fix, admission/rollback locked selection and publication first,
    then waited for worker rows. Selection held worker rows and waited for the
    selection row: a deterministic PostgreSQL lock cycle. The corrected order
    makes the contender wait without holding registry rows.
    """
    engine = repository.sessions.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("This regression requires PostgreSQL row locks")

    queue = "cw11-lock-" + uuid4().hex
    repository.settings = replace(
        repository.settings,
        task_queue=queue,
        source_revision=REVISION,
    )

    # This test shares the CI PostgreSQL schema with later test modules.
    # Save the global selection so the concurrency race cannot leak state.
    with repository.sessions() as db:
        previous_row = db.scalar(select(ReviewedSkillSelection).where(
            ReviewedSkillSelection.skill_name == REVIEWED_RESEARCH_SKILL,
        ))
        previous_selection = None if previous_row is None else {
            "publication_id": previous_row.publication_id,
            "generation": previous_row.generation,
            "state": previous_row.state,
            "updated_by": previous_row.updated_by,
            "reason": previous_row.reason,
            "updated_at": previous_row.updated_at,
        }

    suffix = uuid4().hex[:12]
    baseline_version = f"baseline_{suffix}"
    candidate_version = f"candidate_{suffix}"
    next_version = f"next_{suffix}"

    def publish(version: str, rollback_target: str | None = None) -> dict:
        value = build_reviewed_publication(
            skill_name=REVIEWED_RESEARCH_SKILL,
            publication_version=version,
            task_workflow_version=REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
            source_revision=REVISION,
            rollback_target_version=rollback_target,
        )
        repository.publish_reviewed_skill(
            value,
            actor_reference="cw11-lock-order-test",
            reason="Deterministic PostgreSQL lock-order regression",
        )
        return value

    baseline = publish(baseline_version)
    candidate = publish(candidate_version, baseline_version)
    next_publication = publish(next_version, baseline_version)
    assert baseline["review_sha256"] == candidate["review_sha256"] == next_publication["review_sha256"]
    with repository.sessions() as db:
        test_publication_ids = set(db.scalars(select(ReviewedSkillPublication.id).where(
            ReviewedSkillPublication.skill_name == REVIEWED_RESEARCH_SKILL,
            ReviewedSkillPublication.publication_version.in_(
                [baseline_version, candidate_version, next_version],
            ),
        )).all())

    worker_id = repository.register_worker(task_queue=queue, source_revision=REVISION)
    assert repository.heartbeat_worker(worker_id) == "running"
    repository.select_reviewed_skill(
        REVIEWED_RESEARCH_SKILL,
        candidate_version,
        actor_reference="cw11-lock-order-test",
        reason="Seed the current selection",
        worker_source_revision=REVISION,
    )

    worker_rows_held = Event()
    contender_holds_selection = Event()
    original_fleet_check = repository._require_compatible_worker_fleet

    def coordinated_fleet_check(db, *, task_queue, required_source_revision):
        result = original_fleet_check(
            db,
            task_queue=task_queue,
            required_source_revision=required_source_revision,
        )
        if current_thread().name == "cw11-select":
            worker_rows_held.set()
            # Under the old order, admission/rollback can lock selection before
            # waiting for these worker rows. Under the new order it cannot.
            contender_holds_selection.wait(timeout=2.0)
        return result

    def observe_selection_lock(conn, cursor, statement, parameters, context, executemany):
        normalized = " ".join(statement.lower().split())
        if (
            current_thread().name == "cw11-contender"
            and "cw_reviewed_skill_selections" in normalized
            and "for update" in normalized
        ):
            contender_holds_selection.set()

    def select_next():
        current_thread().name = "cw11-select"
        return repository.select_reviewed_skill(
            REVIEWED_RESEARCH_SKILL,
            next_version,
            actor_reference="cw11-lock-order-test",
            reason="Concurrent selection",
            worker_source_revision=REVISION,
        )

    def run_contender():
        current_thread().name = "cw11-contender"
        if contender == "rollback":
            return repository.rollback_reviewed_skill(
                REVIEWED_RESEARCH_SKILL,
                baseline_version,
                actor_reference="cw11-lock-order-test",
                reason="Concurrent explicit rollback",
                worker_source_revision=REVISION,
            )
        with repository.sessions.begin() as db:
            binding = repository._require_selected_reviewed_publication(
                db, candidate["review_sha256"],
            )
            return binding.publication_version

    event.listen(engine, "after_cursor_execute", observe_selection_lock)
    repository._require_compatible_worker_fleet = coordinated_fleet_check
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            selected_future = pool.submit(select_next)
            assert worker_rows_held.wait(timeout=5), "Selection did not acquire worker rows"
            contender_future = pool.submit(run_contender)

            selected = selected_future.result(timeout=12)
            contender_result = contender_future.result(timeout=12)

        assert selected["publication_version"] == next_version
        if contender == "admission":
            assert contender_result == next_version
            expected_final = next_version
        else:
            assert contender_result["publication_version"] == baseline_version
            expected_final = baseline_version
        assert repository.selected_reviewed_skill(REVIEWED_RESEARCH_SKILL)["publication_version"] == expected_final
    finally:
        event.remove(engine, "after_cursor_execute", observe_selection_lock)
        repository._require_compatible_worker_fleet = original_fleet_check
        # Restore/delete the single global selection row so later PostgreSQL
        # tests see the same registry state they would have seen without this test.
        with repository.sessions.begin() as db:
            current_selection = db.scalar(select(ReviewedSkillSelection).where(
                ReviewedSkillSelection.skill_name == REVIEWED_RESEARCH_SKILL,
            ).with_for_update().execution_options(populate_existing=True))
            if (
                current_selection is not None
                and current_selection.publication_id in test_publication_ids
            ):
                if previous_selection is None:
                    db.delete(current_selection)
                else:
                    for field, value in previous_selection.items():
                        setattr(current_selection, field, value)
            elif current_selection is None and previous_selection is not None:
                db.add(ReviewedSkillSelection(
                    skill_name=REVIEWED_RESEARCH_SKILL,
                    **previous_selection,
                ))



def test_worker_registration_cannot_phantom_after_registry_fleet_snapshot(repository):
    """Serialize queue membership with selection and reject a post-selection old worker."""
    engine = repository.sessions.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("This regression requires PostgreSQL advisory transaction locks")

    original_settings = repository.settings
    original_fleet_check = repository._require_compatible_worker_fleet
    queue = "cw11-registration-" + uuid4().hex
    repository.settings = replace(
        repository.settings,
        task_queue=queue,
        source_revision=REVISION,
    )

    previous_selection = None
    selection_snapshot_saved = False
    published_id = None
    listener_added = False
    allow_selection_commit = Event()

    def restore_selection():
        with repository.sessions.begin() as db:
            current_selection = db.scalar(select(ReviewedSkillSelection).where(
                ReviewedSkillSelection.skill_name == REVIEWED_RESEARCH_SKILL,
            ).with_for_update().execution_options(populate_existing=True))
            if current_selection is not None and published_id is not None and current_selection.publication_id == published_id:
                if previous_selection is None:
                    db.delete(current_selection)
                else:
                    for field, value in previous_selection.items():
                        setattr(current_selection, field, value)
            elif current_selection is None and previous_selection is not None:
                db.add(ReviewedSkillSelection(
                    skill_name=REVIEWED_RESEARCH_SKILL,
                    **previous_selection,
                ))

    try:
        with repository.sessions.begin() as db:
            previous_row = db.scalar(select(ReviewedSkillSelection).where(
                ReviewedSkillSelection.skill_name == REVIEWED_RESEARCH_SKILL,
            ).with_for_update())
            if previous_row is not None:
                previous_selection = {
                    "publication_id": previous_row.publication_id,
                    "generation": previous_row.generation,
                    "state": previous_row.state,
                    "updated_by": previous_row.updated_by,
                    "reason": previous_row.reason,
                    "updated_at": previous_row.updated_at,
                }
                db.delete(previous_row)
        selection_snapshot_saved = True

        version = "registration_race_" + uuid4().hex[:12]
        publication = build_reviewed_publication(
            skill_name=REVIEWED_RESEARCH_SKILL,
            publication_version=version,
            task_workflow_version=REVIEWED_RESEARCH_TASK_WORKFLOW_VERSION,
            source_revision=REVISION,
        )
        published = repository.publish_reviewed_skill(
            publication,
            actor_reference="cw11-registration-race-test",
            reason="Deterministic worker registration/fleet snapshot race",
        )
        published_id = published["id"]
        compatible_worker = repository.register_worker(
            task_queue=queue,
            source_revision=REVISION,
        )
        assert repository.heartbeat_worker(compatible_worker) == "running"

        fleet_snapshot_taken = Event()
        registration_lock_attempted = Event()
        registration_finished = Event()

        def coordinated_fleet_check(db, *, task_queue, required_source_revision):
            result = original_fleet_check(
                db,
                task_queue=task_queue,
                required_source_revision=required_source_revision,
            )
            if current_thread().name == "cw11-select-registration-race":
                fleet_snapshot_taken.set()
                if not allow_selection_commit.wait(timeout=8):
                    raise RuntimeError("test failed to release the fleet snapshot")
            return result

        def observe_registration_lock(conn, cursor, statement, parameters, context, executemany):
            if (
                current_thread().name == "cw11-register-race"
                and "pg_advisory_xact_lock" in statement.lower()
            ):
                registration_lock_attempted.set()

        def select_publication():
            current_thread().name = "cw11-select-registration-race"
            return repository.select_reviewed_skill(
                REVIEWED_RESEARCH_SKILL,
                version,
                actor_reference="cw11-registration-race-test",
                reason="Select while an incompatible worker attempts registration",
                worker_source_revision=REVISION,
            )

        def register_incompatible_worker():
            current_thread().name = "cw11-register-race"
            try:
                repository.register_worker(
                    task_queue=queue,
                    source_revision="b" * 40,
                )
            except CoworkerError as exc:
                return exc.code
            finally:
                registration_finished.set()
            return "registered"

        event.listen(engine, "before_cursor_execute", observe_registration_lock)
        listener_added = True
        repository._require_compatible_worker_fleet = coordinated_fleet_check
        with ThreadPoolExecutor(max_workers=2) as pool:
            selected_future = pool.submit(select_publication)
            assert fleet_snapshot_taken.wait(timeout=5), "selection did not take the fleet snapshot"
            registration_future = pool.submit(register_incompatible_worker)
            assert registration_lock_attempted.wait(timeout=5), "registration did not attempt the queue lock"
            assert not registration_finished.wait(timeout=0.25), (
                "worker registration completed while the fleet snapshot transaction held its queue lock"
            )
            allow_selection_commit.set()
            selected = selected_future.result(timeout=10)
            registration_result = registration_future.result(timeout=10)

        assert selected["publication_version"] == version
        assert registration_result == "worker_fleet_incompatible"
        inventory = repository.worker_inventory(task_queue=queue)
        assert [row["id"] for row in inventory] == [compatible_worker]
        assert all(row["source_revision"] == REVISION for row in inventory)
    finally:
        allow_selection_commit.set()
        if listener_added:
            event.remove(engine, "before_cursor_execute", observe_registration_lock)
        repository._require_compatible_worker_fleet = original_fleet_check
        repository.settings = original_settings
        if selection_snapshot_saved:
            restore_selection()



def test_postgres_rejects_worker_insert_without_deployment_revision_context(repository):
    """A legacy binary that bypasses the application lock cannot insert a worker row."""
    engine = repository.sessions.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("The PostgreSQL registration trigger is the production guard")

    worker_id = str(uuid4())
    queue = "cw11-unattested-" + uuid4().hex
    with pytest.raises(IntegrityError, match="worker registration requires matching deployment-attested source revision"):
        with repository.sessions.begin() as db:
            db.add(WorkerInstance(
                id=worker_id,
                task_queue=queue,
                source_revision=REVISION,
                state="starting",
            ))

    with repository.sessions() as db:
        assert db.get(WorkerInstance, worker_id) is None


def test_postgres_claim_commit_serializes_with_drain_and_blocks_false_completion(repository):
    engine = repository.sessions.kw["bind"]
    if engine.dialect.name != "postgresql":
        pytest.skip("Worker claim/drain lock ordering requires PostgreSQL row locks")

    original_settings = repository.settings
    queue = "cw11-claim-drain-" + uuid4().hex
    repository.settings = replace(
        repository.settings,
        task_queue=queue,
        source_revision=REVISION,
    )
    worker_id = None
    claim_resource = "run-" + uuid4().hex
    claim_locked = Event()
    allow_claim_commit = Event()
    drain_started = Event()
    drain_finished = Event()

    def insert_claim_under_worker_lock():
        with repository.sessions.begin() as db:
            now = utcnow()
            worker = lock_running_worker(
                db,
                worker_id=worker_id,
                task_queue=queue,
                now=now,
                heartbeat_ttl_seconds=WORKER_HEARTBEAT_TTL_SECONDS,
            )
            assert worker is not None
            add_worker_claim(
                db,
                worker=worker,
                claim_type="agent_dispatch",
                resource_id=claim_resource,
                now=now,
            )
            claim_locked.set()
            if not allow_claim_commit.wait(timeout=8):
                raise RuntimeError("test did not release the claim transaction")

    def request_drain():
        drain_started.set()
        try:
            return repository.request_worker_drain(
                task_queue=queue,
                source_revision=REVISION,
                actor_reference="cw11-postgres-test",
                reason="Serialize drain against an in-flight Agent dispatch claim",
            )
        finally:
            drain_finished.set()

    try:
        worker_id = repository.register_worker(
            task_queue=queue,
            source_revision=REVISION,
        )
        assert repository.heartbeat_worker(worker_id) == "running"

        with ThreadPoolExecutor(max_workers=2) as pool:
            claim_future = pool.submit(insert_claim_under_worker_lock)
            try:
                assert claim_locked.wait(timeout=5), "claim transaction did not acquire worker lock"
                drain_future = pool.submit(request_drain)
                assert drain_started.wait(timeout=5), "drain transaction did not start"
                assert not drain_finished.wait(timeout=0.25), (
                    "drain crossed the worker lock while a claim transaction was uncommitted"
                )
            finally:
                allow_claim_commit.set()
            claim_future.result(timeout=10)
            assert drain_future.result(timeout=10) == 1

        assert repository.heartbeat_worker(worker_id) == "draining"
        with pytest.raises(CoworkerError) as blocked:
            repository.mark_worker_drained(worker_id)
        assert blocked.value.code == "worker_claims_active"

        assert repository.complete_worker_claim(
            worker_id=worker_id,
            claim_type="agent_dispatch",
            resource_id=claim_resource,
        ) is True
        repository.mark_worker_drained(worker_id)
        evidence = repository.assert_worker_drain_complete(
            task_queue=queue,
            old_source_revision=REVISION,
        )
        assert evidence["verified"] is True
        assert evidence["workers"][0]["active_claim_count"] == 0
    finally:
        allow_claim_commit.set()
        repository.settings = original_settings
        if worker_id is not None:
            try:
                with repository.sessions() as db:
                    active = db.scalar(select(WorkerClaim.id).where(
                        WorkerClaim.worker_id == worker_id,
                        WorkerClaim.state == "active",
                    ))
                if active is not None:
                    repository.complete_worker_claim(
                        worker_id=worker_id,
                        claim_type="agent_dispatch",
                        resource_id=claim_resource,
                    )
                repository.mark_worker_drained(worker_id)
            except Exception:
                # Preserve the primary regression failure; a failed cleanup is
                # visible through the test's primary assertion/transaction.
                pass
