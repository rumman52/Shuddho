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
            agent=FakeAgent(), repository=SimpleNamespace(sessions=FakeSessions()),
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
