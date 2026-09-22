from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

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
