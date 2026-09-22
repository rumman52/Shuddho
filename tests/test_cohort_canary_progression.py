from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.cohort_canary_progression import evaluate_progression


def rollout():
    return {
        "release_id": "coworker-cohort-001",
        "cohort": {"reference": "ticket", "max_users": 25},
        "rollback": {"global_kill_switch": "SHUDDHO_COWORKER_ENABLED=false"},
    }


def plan():
    return {
        "release_id": "coworker-cohort-001",
        "max_gap_minutes": 10,
        "stale_after_minutes": 10,
        "stages": [
            {
                "name": "canary-5",
                "min_members": 5,
                "max_users": 5,
                "min_healthy_windows": 3,
                "min_observation_minutes": 10,
                "min_task_samples": 6,
                "min_provider_samples": 6,
                "min_agent_samples": 3,
                "min_research_samples": 0,
                "min_action_samples": 0,
            },
            {
                "name": "canary-10",
                "min_members": 10,
                "max_users": 10,
                "min_healthy_windows": 3,
                "min_observation_minutes": 10,
                "min_task_samples": 12,
                "min_provider_samples": 12,
                "min_agent_samples": 6,
                "min_research_samples": 0,
                "min_action_samples": 0,
            },
        ],
    }


def row(at: datetime, *, members=5, decision="CONTINUE_COHORT", task_samples=2, provider_samples=2, agent_samples=1):
    return {
        "decision": decision,
        "release_id": "coworker-cohort-001",
        "snapshot": {
            "generated_at": at.isoformat(),
            "cohort_members_configured": members,
            "tasks": {"samples": task_samples},
            "provider": {"samples": provider_samples},
            "agents": {"samples": agent_samples},
            "research": {"samples": 0},
            "actions": {"samples": 0},
        },
        "breaches": [],
        "rollback": None,
    }


def healthy_history():
    start = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
    return [row(start + timedelta(minutes=5 * index)) for index in range(3)]


def test_sustained_healthy_stage_becomes_eligible_for_expansion():
    history = healthy_history()
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "ELIGIBLE_FOR_EXPANSION"
    assert result["next_stage"] == "canary-10"
    assert result["reasons"] == []


def test_any_stop_window_stops_rollout():
    history = healthy_history()
    history[1]["decision"] = "STOP_ROLLOUT"
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert "health_history_contains_stop" in result["reasons"]


def test_stale_latest_snapshot_stops_rollout():
    result = evaluate_progression(
        healthy_history(),
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 30, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["latest_health_snapshot_stale"]


def test_monitoring_gap_holds_stage():
    history = healthy_history()
    history[2]["snapshot"]["generated_at"] = datetime(2026, 9, 22, 4, 25, tzinfo=timezone.utc).isoformat()
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 27, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert "monitoring_gap" in result["reasons"]


def test_insufficient_real_samples_hold_stage():
    history = healthy_history()
    for item in history:
        item["snapshot"]["tasks"]["samples"] = 0
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert "insufficient_task_samples" in result["reasons"]


def test_stage_member_limit_is_hard_stop():
    history = [row(datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc), members=6)]
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 2, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["configured_members_exceed_current_stage"]


def test_final_stage_never_auto_expands():
    value = plan()
    history = []
    start = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
    for index in range(3):
        history.append(row(start + timedelta(minutes=5 * index), members=10, task_samples=4, provider_samples=4, agent_samples=2))
    result = evaluate_progression(
        history,
        rollout(),
        value,
        current_stage="canary-10",
        now=datetime(2026, 9, 22, 4, 12, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert result["next_stage"] is None
    assert result["reasons"] == ["final_stage_reached"]
