from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for staging Temporal recovery tests")
pytest.importorskip("temporalio", reason="Install the coworker extra for staging Temporal recovery tests")

from scripts import staging_temporal_recovery as recovery


def step(ordinal: int, *, depends=None, started=None, finished=None, state="completed"):
    return SimpleNamespace(
        id=f"step-{ordinal}",
        ordinal=ordinal,
        depends_on_ordinals=list(depends or []),
        state=state,
        started_at=started,
        finished_at=finished,
    )


def task(run_id: str, ordinal: int):
    return SimpleNamespace(
        id=f"task-{ordinal}",
        state="completed",
        agent_step_id=f"step-{ordinal}",
        idempotency_key=f"agent:{run_id}:{ordinal}",
    )


def completed_fixture():
    base = datetime(2026, 9, 22, 2, 0, tzinfo=timezone.utc)
    run = SimpleNamespace(
        id="run-1",
        state="completed",
        created_at=base,
        updated_at=base + timedelta(seconds=30),
    )
    steps = [
        step(1, started=base + timedelta(seconds=2), finished=base + timedelta(seconds=12)),
        step(2, started=base + timedelta(seconds=3), finished=base + timedelta(seconds=14)),
        step(3, depends=[1, 2], started=base + timedelta(seconds=15), finished=base + timedelta(seconds=25)),
    ]
    tasks = [task(run.id, 1), task(run.id, 2), task(run.id, 3)]
    return base, run, steps, tasks


def test_validate_persisted_recovery_accepts_real_fan_in_and_restart_window():
    base, run, steps, tasks = completed_fixture()
    result = recovery.validate_persisted_recovery(
        run, steps, tasks, base + timedelta(seconds=8)
    )
    assert result["child_tasks"] == 3
    assert [child["task_id"] for child in result["completed_children"]] == [
        "task-1", "task-2", "task-3",
    ]
    assert all(child["state"] == "completed" for child in result["completed_children"])
    assert result["fan_in_started_at"].endswith("+00:00")


def test_validate_persisted_recovery_rejects_early_fan_in():
    base, run, steps, tasks = completed_fixture()
    steps[2].started_at = base + timedelta(seconds=10)
    with pytest.raises(recovery.RecoveryFailure, match="before both dependencies"):
        recovery.validate_persisted_recovery(
            run, steps, tasks, base + timedelta(seconds=8)
        )


def test_validate_persisted_recovery_rejects_duplicate_or_wrong_child_linkage():
    base, run, steps, tasks = completed_fixture()
    tasks[2].agent_step_id = "step-2"
    with pytest.raises(recovery.RecoveryFailure, match="duplicated"):
        recovery.validate_persisted_recovery(
            run, steps, tasks, base + timedelta(seconds=8)
        )


def test_validate_persisted_recovery_rejects_wrong_idempotency_contract():
    base, run, steps, tasks = completed_fixture()
    tasks[1].idempotency_key = "unexpected-key"
    with pytest.raises(recovery.RecoveryFailure, match="idempotency"):
        recovery.validate_persisted_recovery(
            run, steps, tasks, base + timedelta(seconds=8)
        )


def test_validate_persisted_recovery_requires_restart_after_execution_started():
    base, run, steps, tasks = completed_fixture()
    with pytest.raises(recovery.RecoveryFailure, match="after agent execution started"):
        recovery.validate_persisted_recovery(
            run, steps, tasks, base + timedelta(seconds=1)
        )


def test_parse_utc_requires_timezone():
    assert recovery.parse_utc("2026-09-22T08:10:00+06:00").tzinfo == timezone.utc
    with pytest.raises(recovery.RecoveryFailure, match="timezone"):
        recovery.parse_utc("2026-09-22T08:10:00")


def test_require_runtime_needs_parallel_recovery_flags():
    settings = SimpleNamespace(
        agent_runtime_enabled=True,
        agent_dependency_graph_enabled=True,
        agent_parallel_execution_enabled=True,
        research_services_enabled=True,
        work_services_enabled=True,
        max_agent_parallel_steps=2,
    )
    recovery.require_runtime(settings)
    settings.agent_parallel_execution_enabled = False
    with pytest.raises(recovery.RecoveryFailure, match="agent_parallel_execution_enabled"):
        recovery.require_runtime(settings)


def test_synthetic_plan_is_two_research_branches_then_document():
    plan = recovery.synthetic_plan()
    assert [item.tool for item in plan] == [
        "research.search",
        "research.search",
        "document.create",
    ]


def _private_recovery_settings():
    return SimpleNamespace(
        source_revision="a" * 40,
        agent_runtime_enabled=True,
        agent_dependency_graph_enabled=True,
        agent_parallel_execution_enabled=True,
        research_services_enabled=True,
        work_services_enabled=True,
        max_agent_parallel_steps=2,
        agent_run_timeout_seconds=60,
        task_queue="test-staging-queue",
    )


@pytest.mark.parametrize("destination", ["existing", "symlink", "missing_directory"])
def test_recovery_prepare_rejects_unsafe_state_before_remote_mutation(
    monkeypatch, tmp_path, destination,
):
    import asyncio
    import json

    from scripts.staging_release_evidence import StagingReleaseEvidenceError

    rollout = tmp_path / "rollout.json"
    rollout.write_text(json.dumps({"release_id": "synthetic-release"}), encoding="utf-8")
    state = tmp_path / "state.json"
    if destination == "existing":
        state.write_text('{"original":true}', encoding="utf-8")
    elif destination == "symlink":
        original = tmp_path / "original.json"
        original.write_text('{"original":true}', encoding="utf-8")
        state.symlink_to(original)
    else:
        state = tmp_path / "missing" / "state.json"

    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_RECOVERY_EXERCISE", "true")
    monkeypatch.setattr(
        recovery, "staging_owner",
        lambda: pytest.fail("remote owner lookup occurred before private state preflight"),
    )
    with pytest.raises(StagingReleaseEvidenceError):
        asyncio.run(recovery.prepare(_private_recovery_settings(), state, rollout))

    if destination == "existing":
        assert state.read_text(encoding="utf-8") == '{"original":true}'
    elif destination == "symlink":
        assert original.read_text(encoding="utf-8") == '{"original":true}'


def test_recovery_prepare_publishes_private_atomic_state(monkeypatch, tmp_path):
    import asyncio
    import json
    import stat

    rollout = tmp_path / "rollout.json"
    rollout.write_text(json.dumps({"release_id": "synthetic-release"}), encoding="utf-8")
    state = tmp_path / "state.json"
    calls = []

    class FakeAgent:
        def create(self, owner, request, key):
            calls.append("create")
            return {"id": "synthetic-run", "created_at": "2026-11-13T00:00:00+00:00"}, True

        def save_plan(self, owner, run_id, plan):
            calls.append("save_plan")
            return {"steps": [
                {"depends_on": []}, {"depends_on": []},
                {"depends_on": [1, 2]},
            ]}

        def delivered(self, run_id):
            calls.append("delivered")

    class FakeSessions:
        kw = {"bind": SimpleNamespace(dispose=lambda: calls.append("dispose"))}

    async def fake_start(*args, **kwargs):
        calls.append("start_workflow")

    async def fake_temporal_client(_settings):
        return SimpleNamespace(start_workflow=fake_start)

    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_RECOVERY_EXERCISE", "true")
    monkeypatch.setattr(recovery, "staging_owner", lambda: "synthetic-owner")
    monkeypatch.setattr(
        recovery.Container, "create",
        lambda _settings: SimpleNamespace(
            agent=FakeAgent(), repository=SimpleNamespace(
                sessions=FakeSessions(),
                worker_inventory=lambda **kwargs: [{
                    "id": "worker-original", "task_queue": "test-staging-queue",
                    "source_revision": "a" * 40, "state": "running",
                    "heartbeat_fresh": True,
                    "started_at": "2026-11-12T23:00:00+00:00",
                    "heartbeat_at": "2026-11-13T00:00:00+00:00",
                }],
            ),
        ),
    )
    monkeypatch.setattr(recovery, "temporal_client", fake_temporal_client)

    result = asyncio.run(recovery.prepare(_private_recovery_settings(), state, rollout))

    assert result["owner_id"] == "synthetic-owner"
    assert calls == ["create", "save_plan", "start_workflow", "delivered", "dispose"]
    assert stat.S_IMODE(state.stat().st_mode) == 0o600
    assert json.loads(state.read_text(encoding="utf-8"))["run_id"] == "synthetic-run"
    assert not list(tmp_path.glob(".state.json.*"))


@pytest.mark.parametrize("offset_seconds", [26, 35, 59])
def test_validate_persisted_recovery_rejects_restart_after_final_step_finished(offset_seconds):
    """A post-completion restart must not qualify as an active-worker recovery."""
    base, run, steps, tasks = completed_fixture()
    # The final persisted step ended at base + 25 seconds. The agent row
    # updated at base + 30 seconds, and the old validator allowed + 30 more.
    with pytest.raises(recovery.RecoveryFailure, match="before the recovery run finished"):
        recovery.validate_persisted_recovery(
            run, steps, tasks, base + timedelta(seconds=offset_seconds)
        )


def _outbox_fixture():
    _, run, _, tasks = completed_fixture()
    parent = [SimpleNamespace(run_id=run.id, delivered=True, attempts=0)]
    # AgentRuntime creates each child with enqueue=False; no cw_outbox rows.
    children = []
    return run, tasks, parent, children


def test_recovery_requires_one_logical_agent_outbox_and_no_child_task_outboxes():
    run, tasks, parent, children = _outbox_fixture()
    assert recovery.validate_outbox_effects(run, tasks, parent, children) == {
        "agent_outbox_effect_count": 1,
        "agent_outbox_delivered": True,
        "child_task_outbox_count": 0,
        "child_task_outbox_expected_absent": True,
    }


@pytest.mark.parametrize("failure", [
    "no_parent", "duplicate_parent", "foreign_parent", "parent_undelivered",
    "unexpected_child_outbox", "duplicate_task_identity",
])
def test_recovery_refuses_missing_or_duplicate_logical_outbox_effects(failure):
    run, tasks, parent, children = _outbox_fixture()
    if failure == "no_parent":
        parent.clear()
    elif failure == "duplicate_parent":
        parent.append(parent[0])
    elif failure == "foreign_parent":
        parent[0].run_id = "foreign"
    elif failure == "parent_undelivered":
        parent[0].delivered = False
    elif failure == "unexpected_child_outbox":
        children.append(SimpleNamespace(task_id=tasks[0].id, delivered=True, attempts=1))
    elif failure == "duplicate_task_identity":
        tasks[2].id = tasks[1].id
    with pytest.raises(recovery.RecoveryFailure, match="outbox|identities"):
        recovery.validate_outbox_effects(run, tasks, parent, children)


def _worker_evidence():
    base = datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc)
    before = {
        "id": "old-worker", "task_queue": "test-staging-queue",
        "source_revision": "a" * 40,
        "started_at": (base - timedelta(minutes=2)).isoformat(),
        "heartbeat_at": (base + timedelta(seconds=1)).isoformat(),
    }
    after = {
        "id": "new-worker", "task_queue": "test-staging-queue",
        "source_revision": "a" * 40, "state": "running", "heartbeat_fresh": True,
        "started_at": (base + timedelta(seconds=10)).isoformat(),
        "heartbeat_at": (base + timedelta(seconds=12)).isoformat(),
    }
    return base, before, after


def _replace(before, after, base):
    return recovery.validate_worker_replacement(
        before, [after], revision="a" * 40, task_queue="test-staging-queue",
        restart_at=base + timedelta(seconds=8),
        active_start=base + timedelta(seconds=2),
        active_finish=base + timedelta(seconds=25),
    )


def test_worker_replacement_proves_new_identity_and_heartbeat_during_run():
    base, before, after = _worker_evidence()
    got = _replace(before, after, base)
    assert got["worker_before_id"] == "old-worker"
    assert got["worker_after_id"] == "new-worker"
    assert got["worker_after_started_at"] == after["started_at"]
    assert got["worker_before_heartbeat_at"] == before["heartbeat_at"]
    assert got["worker_after_heartbeat_at"] == after["heartbeat_at"]


@pytest.mark.parametrize("broken", [
    "same_instance", "wrong_revision", "stale", "registered_before_work",
    "registered_before_restart",
    "registered_after_completion", "no_heartbeat_advance", "late_platform_event",
    "wrong_previous_identity", "pre_restart_heartbeat_stale",
    "pre_restart_heartbeat_after_restart", "old_worker_registered_after_run_started",
])
def test_worker_replacement_rejects_forged_or_nonactive_restart(broken):
    base, before, after = _worker_evidence()
    if broken == "same_instance":
        after["id"] = before["id"]
    elif broken == "wrong_revision":
        after["source_revision"] = "b" * 40
    elif broken == "stale":
        after["heartbeat_fresh"] = False
    elif broken == "registered_before_work":
        after["started_at"] = (base + timedelta(seconds=1)).isoformat()
    elif broken == "registered_before_restart":
        after["started_at"] = (base + timedelta(seconds=6)).isoformat()
    elif broken == "registered_after_completion":
        after["started_at"] = (base + timedelta(seconds=26)).isoformat()
    elif broken == "no_heartbeat_advance":
        after["heartbeat_at"] = after["started_at"]
    elif broken == "late_platform_event":
        after["started_at"] = (base + timedelta(minutes=8)).isoformat()
    elif broken == "wrong_previous_identity":
        before["source_revision"] = "b" * 40
    elif broken == "pre_restart_heartbeat_stale":
        # The old poller could have died BEFORE the active child task began.
        before["heartbeat_at"] = (base - timedelta(seconds=30)).isoformat()
    elif broken == "pre_restart_heartbeat_after_restart":
        before["heartbeat_at"] = (base + timedelta(seconds=9)).isoformat()
    elif broken == "old_worker_registered_after_run_started":
        before["started_at"] = (base + timedelta(seconds=3)).isoformat()
        before["heartbeat_at"] = (base + timedelta(seconds=4)).isoformat()
    with pytest.raises(recovery.RecoveryFailure, match="worker|restart|Worker"):
        _replace(before, after, base)


def test_worker_registry_never_accepts_concurrent_fresh_pollers():
    base, before, after = _worker_evidence()
    duplicate = dict(after, id="unexpected-worker")
    with pytest.raises(recovery.RecoveryFailure, match="exactly one"):
        recovery.validate_worker_replacement(
            before, [after, duplicate], revision="a" * 40,
            task_queue="test-staging-queue",
            restart_at=base + timedelta(seconds=8),
            active_start=base + timedelta(seconds=2),
            active_finish=base + timedelta(seconds=25),
        )


def test_restart_between_child_steps_cannot_pass_active_task_recovery():
    base, run, steps, tasks = completed_fixture()
    # Distinct phase gap: branches end at +12/+14 and fan-in starts +15.
    with pytest.raises(recovery.RecoveryFailure, match="actively executing child task"):
        recovery.validate_persisted_recovery(
            run, steps, tasks, base + timedelta(seconds=14, milliseconds=500)
        )


def test_parse_utc_rejects_missing_or_wrong_type_without_unhandled_exception():
    for malformed in (None, 1, False, [], {}):
        with pytest.raises(recovery.RecoveryFailure, match="timezone"):
            recovery.parse_utc(malformed)


def test_old_worker_heartbeat_at_exact_registry_freshness_boundary_is_accepted():
    from services.coworker.reviewed_skill_registry import WORKER_HEARTBEAT_TTL_SECONDS

    base, before, after = _worker_evidence()
    before["heartbeat_at"] = (
        base + timedelta(seconds=8 - WORKER_HEARTBEAT_TTL_SECONDS)
    ).isoformat()
    # A strict greater-than check rejects stale, while a TTL-equal heartbeat
    # remains fresh exactly as in repository.worker_inventory.
    assert _replace(before, after, base)["worker_before_id"] == "old-worker"


def _active_checkpoint_fixture():
    # The original prepare heartbeat is intentionally old: a genuine
    # long-running child must not have to complete inside 15 seconds.
    base, original, after = _worker_evidence()
    original["heartbeat_at"] = (base - timedelta(minutes=1)).isoformat()
    state = {
        "run_id": "run-checkpoint", "owner_id": "synthetic-owner",
        "workflow_id": "shuddho-agent-run-checkpoint",
        "release_context": {"release_id": "frozen-run", "source_revision": "a" * 40},
        "worker_before": original,
    }
    run = SimpleNamespace(
        id="run-checkpoint", owner_id="synthetic-owner", state="running",
    )
    step = SimpleNamespace(
        id="step-1", ordinal=1, run_id=run.id, owner_id=run.owner_id,
        state="running", started_at=base + timedelta(seconds=2), finished_at=None,
    )
    child = SimpleNamespace(
        id="task-1", agent_run_id=run.id, agent_step_id=step.id,
        owner_id=run.owner_id, state="running",
    )
    current = dict(
        original, state="running", heartbeat_fresh=True,
        heartbeat_at=(base + timedelta(seconds=5)).isoformat(),
    )
    facts = {
        "completed_children": [{
            "ordinal": 1, "task_id": child.id,
            "started_at": step.started_at.isoformat(),
            "finished_at": (base + timedelta(seconds=25)).isoformat(),
        }],
    }
    return base, state, run, step, child, current, facts, after


def test_just_in_time_checkpoint_allows_real_long_running_child_with_fresh_worker():
    base, state, run, step, child, current, facts, after = _active_checkpoint_fixture()
    captured_at = base + timedelta(seconds=7)
    receipt = recovery.attest_active_worker_checkpoint(
        state, run, [step], [child], [current],
        revision="a" * 40, task_queue="test-staging-queue",
        captured_at=captured_at,
    )
    assert receipt["status"] == "active_child_observed"
    assert receipt["worker_before"]["id"] == state["worker_before"]["id"]
    assert receipt["active_child_task_id"] == child.id

    # The stale prepare snapshot CANNOT be promoted to a PASS.
    with pytest.raises(recovery.RecoveryFailure, match="stale"):
        _replace(state["worker_before"], after, base)
    refreshed = recovery.worker_from_active_checkpoint(
        state, receipt, facts,
        restart_at=base + timedelta(seconds=8),
        revision="a" * 40, task_queue="test-staging-queue",
    )
    assert _replace(refreshed, after, base)["worker_before_heartbeat_at"] == current["heartbeat_at"]


@pytest.mark.parametrize("broken", [
    "not_active_run", "no_running_step", "no_started_step", "completed_step",
    "queued_child", "wrong_child_link", "wrong_worker", "stale_worker",
    "future_heartbeat", "late_old_registration", "duplicate_worker",
])
def test_live_checkpoint_rejects_missing_active_child_or_old_polling_evidence(broken):
    base, state, run, step, child, current, facts, after = _active_checkpoint_fixture()
    captured_at = base + timedelta(seconds=7)
    inventories = [current]
    if broken == "not_active_run":
        run.state = "completed"
    elif broken == "no_running_step":
        step.state = "completed"
    elif broken == "no_started_step":
        step.started_at = None
    elif broken == "completed_step":
        step.finished_at = base + timedelta(seconds=6)
    elif broken == "queued_child":
        child.state = "queued"
    elif broken == "wrong_child_link":
        child.agent_step_id = "not-the-original-step"
    elif broken == "wrong_worker":
        current["id"] = "an-unrelated-worker"
    elif broken == "stale_worker":
        current["heartbeat_at"] = (base - timedelta(seconds=20)).isoformat()
    elif broken == "future_heartbeat":
        current["heartbeat_at"] = (base + timedelta(seconds=9)).isoformat()
    elif broken == "late_old_registration":
        current["started_at"] = (base + timedelta(seconds=4)).isoformat()
    elif broken == "duplicate_worker":
        inventories.append(dict(current, id="unexpected-concurrent-poller"))
    with pytest.raises(recovery.RecoveryFailure):
        recovery.attest_active_worker_checkpoint(
            state, run, [step], [child], inventories,
            revision="a" * 40, task_queue="test-staging-queue",
            captured_at=captured_at,
        )


@pytest.mark.parametrize("broken", [
    "other_run", "wrong_release", "wrong_worker", "stale_checkpoint",
    "stale_heartbeat", "checkpoint_after_restart", "wrong_child",
    "wrong_ordinal", "after_child_finished", "non_timezone_checkpoint",
])
def test_recovery_checkpoint_cannot_be_reused_or_backdated(broken):
    base, state, run, step, child, current, facts, after = _active_checkpoint_fixture()
    receipt = recovery.attest_active_worker_checkpoint(
        state, run, [step], [child], [current],
        revision="a" * 40, task_queue="test-staging-queue",
        captured_at=base + timedelta(seconds=7),
    )
    if broken == "other_run":
        receipt["run_id"] = "another-run"
    elif broken == "wrong_release":
        receipt["release_context"] = {"release_id": "another-release"}
    elif broken == "wrong_worker":
        receipt["worker_before"]["id"] = "different-worker"
    elif broken == "stale_checkpoint":
        receipt["captured_at"] = (base - timedelta(minutes=1)).isoformat()
        receipt["worker_before"]["heartbeat_at"] = (base - timedelta(minutes=1)).isoformat()
    elif broken == "stale_heartbeat":
        receipt["worker_before"]["heartbeat_at"] = (base - timedelta(minutes=1)).isoformat()
    elif broken == "checkpoint_after_restart":
        receipt["captured_at"] = (base + timedelta(seconds=9)).isoformat()
    elif broken == "wrong_child":
        receipt["active_child_task_id"] = "unrelated-child"
    elif broken == "wrong_ordinal":
        receipt["active_ordinal"] = True
    elif broken == "after_child_finished":
        facts["completed_children"][0]["finished_at"] = (base + timedelta(seconds=6)).isoformat()
    elif broken == "non_timezone_checkpoint":
        receipt["captured_at"] = "2026-11-13T00:00:07"
    with pytest.raises(recovery.RecoveryFailure):
        recovery.worker_from_active_checkpoint(
            state, receipt, facts,
            restart_at=base + timedelta(seconds=8),
            revision="a" * 40, task_queue="test-staging-queue",
        )
