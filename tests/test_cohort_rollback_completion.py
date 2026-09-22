from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for rollback completion tests")

from scripts import cohort_rollback_completion as rollback
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.migrate import upgrade
from services.coworker.models import Outbox, Task
from services.coworker.schemas import TaskCreate


ISSUER = "https://identity.example.test/auth/v1"


def rollout():
    return {
        "release_id": "coworker-cohort-001",
        "rollback": {
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
        },
    }


def test_global_switch_must_actually_be_disabled(monkeypatch):
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "false")
    assert rollback.require_switch_state("global", rollout()) == "SHUDDHO_COWORKER_ENABLED=false"
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "true")
    with pytest.raises(rollback.RollbackCompletionError, match="still enabled"):
        rollback.require_switch_state("global", rollout())


def test_post_status_must_be_fresh_and_healthy():
    deployed = datetime(2026, 9, 22, 7, 0, tzinfo=timezone.utc)
    status = {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T07:05:00+00:00",
        "cohort_members_configured": 5,
        "breaches": [],
    }
    result = rollback.validate_post_status(
        status,
        release_id="coworker-cohort-001",
        deployed_at=deployed,
    )
    assert result["cohort_members_configured"] == 5

    status["generated_at"] = "2026-09-22T06:59:00+00:00"
    with pytest.raises(rollback.RollbackCompletionError, match="predates"):
        rollback.validate_post_status(
            status,
            release_id="coworker-cohort-001",
            deployed_at=deployed,
        )


def test_cohort_counts_require_drain_and_delivered_outbox(tmp_path):
    invited = Principal(ISSUER, "rollback-user", 0)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'rollback.sqlite3'}",
        auth_issuer=ISSUER,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        cohort_enforced=True,
        cohort_account_ids=frozenset({invited.account_id}),
        cohort_max_users=5,
    )
    upgrade(settings.database_url)
    container = Container.create(settings)
    try:
        container.repository.ensure_account(invited)
        task, _ = container.repository.create_task(
            invited.account_id,
            TaskCreate(
                instruction="Synthetic rollback drain task.",
                notes="Synthetic rollback verification.",
                output_language="en",
            ),
            "rollback-task",
        )
        with pytest.raises(rollback.RollbackCompletionError, match="active_tasks=1"):
            rollback.cohort_counts(settings, "global")

        with container.repository.sessions.begin() as db:
            row = db.get(Task, task["id"])
            row.state = "cancelled"
            row.cancel_requested = True
            outbox = db.get(Outbox, task["id"])
            outbox.delivered = True

        result = rollback.cohort_counts(settings, "global")
        assert all(value == 0 for value in result.values())
    finally:
        container.repository.sessions.kw["bind"].dispose()


def test_build_evidence_binds_rollout_and_post_status(monkeypatch, tmp_path):
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    status_path = tmp_path / "status.json"
    status_path.write_text(json.dumps({
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": "2026-09-22T07:05:00+00:00",
        "window_minutes": 15,
        "cohort_members_configured": 5,
        "breaches": [],
        "rollback": None,
    }), encoding="utf-8")
    monkeypatch.setenv("SHUDDHO_COWORKER_ENABLED", "false")
    monkeypatch.setattr(
        rollback,
        "cohort_counts",
        lambda _settings, _mode: {
            "active_tasks": 0,
            "active_agent_runs": 0,
            "active_provider_actions": 0,
            "outcome_unknown_actions": 0,
            "undelivered_task_outbox": 0,
            "undelivered_agent_outbox": 0,
        },
    )
    value = rollback.build_evidence(
        settings=SimpleNamespace(),
        rollout=rollout(),
        rollout_path=rollout_path,
        post_status_path=status_path,
        mode="global",
        deployment_reference="deploy-rollback-123",
        deployed_at="2026-09-22T07:00:00+00:00",
    )
    assert value["status"] == "rollback_completed"
    assert value["applied_switch"] == "SHUDDHO_COWORKER_ENABLED=false"
    assert value["artifact_sha256"]["rollout_manifest"] == rollback.sha256_file(rollout_path)
    assert value["artifact_sha256"]["operator_status"] == rollback.sha256_file(status_path)
