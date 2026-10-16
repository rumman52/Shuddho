from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for cohort health tests")

from scripts.cohort_health_gate import collect_snapshot, evaluate, percentile95, rate
from services.coworker.auth import Principal
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.migrate import upgrade
from services.coworker.models import ModelAttempt, Task, utcnow
from services.coworker.schemas import TaskCreate


def snapshot():
    return {
        "generated_at": "2026-09-22T04:00:00+00:00",
        "window_minutes": 15,
        "cohort_members_configured": 10,
        "active": {"tasks": 1, "agent_runs": 1, "provider_actions": 0, "oldest_work_age_seconds": 30},
        "tasks": {"samples": 10, "completed": 9, "failed": 1, "needs_input": 0, "success_rate": 0.9, "failure_rate": 0.1},
        "provider": {"samples": 10, "failed_or_unknown": 0, "failure_rate": 0.0, "p95_latency_ms": 1200, "window_tokens": 50000},
        "agents": {"samples": 5, "failed": 0, "failure_rate": 0.0},
        "research": {"samples": 0, "failed": 0, "failure_rate": None},
        "actions": {"samples": 0, "failed_or_unknown": 0, "outcome_unknown": 0, "failure_rate": None},
        "storage": {"total_bytes": 1000000},
    }


def rollout(*, research=False, actions=False):
    return {
        "release_id": "coworker-cohort-001",
        "cohort": {"reference": "ticket", "max_users": 25},
        "capabilities": {
            "agent_runtime": True,
            "research": research,
            "actions": actions,
        },
        "rollback": {
            "global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false",
            "agent_kill_switch": "SHUDDHO_AGENT_RUNTIME_ENABLED=false",
            "parallel_kill_switch": "SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false",
            "research_kill_switch": "SHUDDHO_RESEARCH_SERVICES_ENABLED=false",
            "actions_kill_switch": "SHUDDHO_ACTIONS_ENABLED=false",
        },
    }


def thresholds():
    return {
        "window_minutes": 15,
        "max_active_work_age_seconds": 300,
        "min_task_samples": 5,
        "max_task_failure_rate": 0.20,
        "min_provider_samples": 5,
        "max_provider_failure_rate": 0.10,
        "max_model_p95_latency_ms": 90000,
        "max_window_tokens": 250000,
        "max_total_storage_bytes": 2147483648,
        "min_agent_samples": 3,
        "max_agent_failure_rate": 0.20,
        "min_research_samples": 3,
        "max_research_failure_rate": 0.20,
        "min_action_samples": 1,
        "max_action_failure_rate": 0.10,
        "max_action_outcome_unknown": 0,
    }


def test_healthy_snapshot_continues_cohort():
    result = evaluate(snapshot(), rollout(), thresholds())
    assert result["decision"] == "CONTINUE_COHORT"
    assert result["breaches"] == []
    assert result["rollback"] is None


def test_task_provider_and_queue_breaches_stop_rollout():
    value = snapshot()
    value["active"]["oldest_work_age_seconds"] = 600
    value["tasks"]["failure_rate"] = 0.4
    value["provider"]["failure_rate"] = 0.3
    result = evaluate(value, rollout(), thresholds())
    assert result["decision"] == "STOP_ROLLOUT"
    names = {item["metric"] for item in result["breaches"]}
    assert {"active.oldest_work_age_seconds", "tasks.failure_rate", "provider.failure_rate"}.issubset(names)
    assert result["rollback"]["global_kill_switch"] == "SHUDDHO_COWORKER_ENABLED=false"


def test_rate_thresholds_respect_minimum_samples():
    value = snapshot()
    value["tasks"]["samples"] = 1
    value["tasks"]["failure_rate"] = 1.0
    value["provider"]["samples"] = 1
    value["provider"]["failure_rate"] = 1.0
    result = evaluate(value, rollout(), thresholds())
    assert result["decision"] == "CONTINUE_COHORT"


def test_enabled_actions_stop_on_any_uncertain_outcome():
    value = snapshot()
    value["actions"] = {
        "samples": 1,
        "failed_or_unknown": 1,
        "outcome_unknown": 1,
        "failure_rate": 1.0,
    }
    result = evaluate(value, rollout(actions=True), thresholds())
    assert result["decision"] == "STOP_ROLLOUT"
    names = {item["metric"] for item in result["breaches"]}
    assert "actions.outcome_unknown" in names


def test_disabled_optional_capabilities_do_not_trigger_their_rate_gates():
    value = snapshot()
    value["research"] = {"samples": 10, "failed": 10, "failure_rate": 1.0}
    value["actions"] = {"samples": 10, "failed_or_unknown": 10, "outcome_unknown": 10, "failure_rate": 1.0}
    result = evaluate(value, rollout(research=False, actions=False), thresholds())
    assert result["decision"] == "CONTINUE_COHORT"


def test_configured_members_cannot_exceed_rollout_manifest():
    value = snapshot()
    value["cohort_members_configured"] = 26
    result = evaluate(value, rollout(), thresholds())
    assert result["decision"] == "STOP_ROLLOUT"
    assert any(item["metric"] == "cohort_members_configured" for item in result["breaches"])


def test_percentile_and_rate_helpers_are_deterministic():
    assert rate(1, 4) == 0.25
    assert rate(0, 0) is None
    assert percentile95([]) is None
    assert percentile95([10, 20, 30, 40, 50]) == 50


def test_collect_snapshot_scopes_metrics_to_configured_cohort(tmp_path):
    issuer = "https://identity.example.test/auth/v1"
    invited = Principal(issuer, "cohort-health-invited", 0)
    outsider = Principal(issuer, "cohort-health-outsider", 0)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'health.sqlite3'}",
        auth_issuer=issuer,
        environment="development",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        cohort_enforced=True,
        cohort_account_ids=frozenset({invited.account_id}),
        cohort_max_users=25,
    )
    upgrade(settings.database_url)
    container = Container.create(settings)
    try:
        container.repository.ensure_account(invited)
        container.repository.ensure_account(outsider)
        invited_task, _ = container.repository.create_task(
            invited.account_id,
            TaskCreate(instruction="Synthetic cohort health task.", notes="Synthetic staging evidence.", output_language="en"),
            "health-invited",
        )
        outsider_task, _ = container.repository.create_task(
            outsider.account_id,
            TaskCreate(instruction="Synthetic outsider task.", notes="Synthetic staging evidence.", output_language="en"),
            "health-outsider",
        )
        now = utcnow()
        with container.repository.sessions.begin() as db:
            invited_row = db.get(Task, invited_task["id"])
            invited_row.state = "completed"
            invited_row.updated_at = now
            outsider_row = db.get(Task, outsider_task["id"])
            outsider_row.state = "failed"
            outsider_row.updated_at = now
            db.add(ModelAttempt(
                task_id=invited_task["id"],
                attempt=1,
                owner_id=invited.account_id,
                day=now.date().isoformat(),
                reserved_tokens=100,
                charged_tokens=80,
                state="completed",
                model="deepseek-flash",
                latency_ms=500,
                created_at=now,
            ))
            db.add(ModelAttempt(
                task_id=outsider_task["id"],
                attempt=1,
                owner_id=outsider.account_id,
                day=now.date().isoformat(),
                reserved_tokens=100,
                charged_tokens=100,
                state="failed",
                model="deepseek-flash",
                latency_ms=99999,
                created_at=now,
            ))
        value = collect_snapshot(settings, window_minutes=15, now=now + timedelta(seconds=1))
        assert value["cohort_members_configured"] == 1
        assert value["tasks"]["samples"] == 1
        assert value["tasks"]["completed"] == 1
        assert value["tasks"]["failed"] == 0
        assert value["provider"]["samples"] == 1
        assert value["provider"]["failure_rate"] == 0.0
        assert value["provider"]["p95_latency_ms"] == 500
        assert value["provider"]["window_tokens"] == 80
    finally:
        container.repository.sessions.kw["bind"].dispose()


def test_reviewed_research_version_is_measured_by_cohort_stop_gate(tmp_path):
    """A failed reviewed task must not disappear from the research denominator."""
    from services.coworker.schemas import ResearchOptions

    issuer = "https://identity.example.test/auth/v1"
    member = Principal(issuer, "reviewed-research-cohort-member", 0)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'reviewed-health.sqlite3'}",
        auth_issuer=issuer, environment="development",
        storage_backend="local", local_storage_path=tmp_path / "objects",
        research_services_enabled=True,
        search_provider="tavily", search_api_key="fixture-only-search-key",
        cohort_enforced=True,
        cohort_account_ids=frozenset({member.account_id}),
        cohort_max_users=25,
    )
    upgrade(settings.database_url)
    container = Container.create(settings)
    try:
        container.repository.ensure_account(member)
        request = TaskCreate(
            skill_id="research", instruction="Synthetic researched comparison.",
            research=ResearchOptions(query="synthetic cited comparison"),
        )
        legacy, _ = container.repository.create_task(
            member.account_id, request, "legacy-research-health", enqueue=False,
        )
        reviewed, _ = container.repository.create_task(
            member.account_id, request, "reviewed-research-health", enqueue=False,
        )
        now = utcnow()
        with container.repository.sessions.begin() as db:
            older = db.get(Task, legacy["id"])
            older.state = "completed"
            older.updated_at = now
            newer = db.get(Task, reviewed["id"])
            newer.workflow_version = "work_research_reviewed_v1"
            newer.state = "failed"
            newer.updated_at = now

        value = collect_snapshot(settings, window_minutes=15, now=now + timedelta(seconds=1))
        assert value["research"] == {
            "samples": 2, "failed": 1, "failure_rate": 0.5,
        }
        result = evaluate(value, rollout(research=True), {
            **thresholds(), "min_research_samples": 2,
        })
        assert result["decision"] == "STOP_ROLLOUT"
        assert any(item["metric"] == "research.failure_rate" for item in result["breaches"])
    finally:
        container.repository.sessions.kw["bind"].dispose()

def test_reviewed_skill_rollback_preflight_rejects_unfenced_or_unpinned_live_tasks(tmp_path):
    """Classify both pre-fence reviewed tasks and fenced tasks with missing identity."""
    from scripts.reviewed_skill_rollback_preflight import inspect_reviewed_rollback
    from services.coworker.models import Step

    issuer = "https://identity.example.test/auth/v1"
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'reviewed-rollback.sqlite3'}",
        auth_issuer=issuer, environment="development",
        storage_backend="local", local_storage_path=tmp_path / "objects",
    )
    upgrade(settings.database_url)
    container = Container.create(settings)
    try:
        admitted = []
        for label in ("legacy", "fenced", "missing", "completed", "agent-missing"):
            member = Principal(issuer, f"rollback-preflight-{label}", 0)
            container.repository.ensure_account(member)
            task, _ = container.repository.create_task(
                member.account_id,
                TaskCreate(
                    instruction=f"Synthetic {label} rollback inventory.",
                    notes="Fixture-only rollback inventory record.",
                ),
                f"preflight-{label}",
                enqueue=False,
            )
            admitted.append(task["id"])
        legacy_id, fenced_id, missing_id, completed_id, agent_missing_id = admitted
        with container.repository.sessions.begin() as db:
            legacy = db.get(Task, legacy_id)
            legacy.workflow_version = "work_research_v1"
            db.add(Step(
                task_id=legacy_id, phase="reviewed_skill_identity",
                output={"review_sha256": "a" * 64},
            ))
            fenced = db.get(Task, fenced_id)
            fenced.workflow_version = "work_research_reviewed_v2"
            db.add(Step(
                task_id=fenced_id, phase="reviewed_skill_identity",
                output={"review_sha256": "b" * 64},
            ))
            missing = db.get(Task, missing_id)
            missing.workflow_version = "work_research_reviewed_v1"
            agent_missing = db.get(Task, agent_missing_id)
            agent_missing.workflow_version = "work_research_v1"
            agent_missing.agent_run_id = "synthetic-owned-legacy-run"
            completed = db.get(Task, completed_id)
            completed.workflow_version = "work_research_v1"
            completed.state = "completed"
            db.add(Step(
                task_id=completed_id, phase="reviewed_skill_identity",
                output={"review_sha256": "c" * 64},
            ))

        result = inspect_reviewed_rollback(container.repository.sessions)
        assert result["decision"] == "BLOCKED_TASK_LEDGER"
        assert result["active_unfenced_reviewed_tasks"] == 1
        assert result["active_fenced_tasks_missing_review_identity"] == 1
        assert result["active_fenced_reviewed_tasks"] == 1
        assert result["terminal_legacy_reviewed_tasks"] == 1
        assert result["active_legacy_agent_research_without_review_identity"] == 1
        assert set(result["blockers"]) == {
            "active_reviewed_tasks_without_worker_version_fence",
            "active_fenced_tasks_missing_review_identity",
            "active_legacy_agent_research_without_review_identity",
        }
        assert result["fleet_drained_verified"] is False
        assert result["rollout_authorized"] is False

        with container.repository.sessions.begin() as db:
            db.get(Task, legacy_id).state = "failed"
            db.get(Task, missing_id).state = "cancelled"
            db.get(Task, agent_missing_id).state = "cancelled"

        checked = inspect_reviewed_rollback(container.repository.sessions)
        assert checked["decision"] == "TASK_LEDGER_CHECK_ONLY"
        assert checked["blockers"] == []
        assert checked["active_fenced_reviewed_tasks"] == 1
        assert checked["terminal_legacy_reviewed_tasks"] == 2
        assert checked["active_legacy_agent_research_without_review_identity"] == 0
        assert checked["fleet_drained_verified"] is False
        assert checked["staging_verified"] is False
        assert checked["rollout_authorized"] is False
    finally:
        container.repository.sessions.kw["bind"].dispose()


def test_reviewed_skill_rollback_cli_requires_backend_database_env(monkeypatch):
    from scripts.reviewed_skill_rollback_preflight import main

    monkeypatch.delenv("SHUDDHO_COWORKER_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="SHUDDHO_COWORKER_DATABASE_URL"):
        main()
