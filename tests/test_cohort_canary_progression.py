from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import stat
import sys

import pytest

from scripts import cohort_canary_progression as canary
from scripts.cohort_canary_progression import evaluate_progression, load_recovery_epoch
from scripts.cohort_release_ledger import (
    append_event,
    append_recovery_event,
    append_rollback_event,
    file_sha256,
)


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


def test_latest_membership_drop_holds_even_after_earlier_healthy_windows():
    history = healthy_history()
    history.append(row(datetime(2026, 9, 22, 4, 15, tzinfo=timezone.utc), members=4))
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "HOLD"
    assert result["reasons"] == ["stage_not_fully_enrolled"]


def test_stop_before_full_enrollment_still_stops_release():
    start = datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc)
    history = [
        row(start, members=4, decision="STOP_ROLLOUT"),
        row(start + timedelta(minutes=5), members=5),
        row(start + timedelta(minutes=10), members=5),
        row(start + timedelta(minutes=15), members=5),
    ]
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 4, 17, tzinfo=timezone.utc),
    )
    assert result["decision"] == "STOP_ROLLOUT"
    assert result["reasons"] == ["health_history_contains_stop"]


KEY = b"k" * 32


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def recovery_epoch_files(tmp_path):
    rollout_path = write_json(tmp_path / "rollout.json", {
        "release_id": "coworker-cohort-001",
        "cohort": {"max_users": 25},
    })
    plan_path = write_json(tmp_path / "plan.json", {
        "release_id": "coworker-cohort-001",
        "stages": [{"name": "canary-5"}, {"name": "canary-10"}],
    })
    progression = write_json(tmp_path / "stop.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
        "current_stage": "canary-5",
        "next_stage": None,
    })
    stop_status = write_json(tmp_path / "stop-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "STOP_ROLLOUT",
    })
    rollback_status = write_json(tmp_path / "rollback-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    rollback_completion = write_json(tmp_path / "rollback-completion.json", {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "rollback_completed",
        "mode": "global",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout_path),
            "operator_status": file_sha256(rollback_status),
        },
    })
    recovery_status = write_json(tmp_path / "recovery-status.json", {
        "release_id": "coworker-cohort-001",
        "decision": "CONTINUE_COHORT",
        "breaches": [],
    })
    recovery_verification = write_json(tmp_path / "recovery.json", {
        "schema_version": 1,
        "release_id": "coworker-cohort-001",
        "status": "recovery_verified",
        "current_stage": "canary-5",
        "verified_at": "2026-09-22T05:00:00+00:00",
        "artifact_sha256": {
            "rollout_manifest": file_sha256(rollout_path),
            "canary_plan": file_sha256(plan_path),
            "rollback_completion": file_sha256(rollback_completion),
            "operator_status": file_sha256(recovery_status),
        },
    })
    return (
        rollout_path,
        plan_path,
        progression,
        stop_status,
        rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    )


def build_recovery_ledger(tmp_path, monkeypatch, *, mutate_recovery=None):
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", KEY.decode())
    (
        rollout_path,
        plan_path,
        progression,
        stop_status,
        rollback_status,
        rollback_completion,
        recovery_status,
        recovery_verification,
    ) = recovery_epoch_files(tmp_path)
    ledger = tmp_path / "ledger.jsonl"
    append_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        event_type="stop_rollout",
        actor_reference="oncall-primary",
        change_reference="incident-1",
        current_stage="canary-5",
        next_stage=None,
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression,
        operator_status=stop_status,
        created_at="2026-09-22T04:50:00+00:00",
    )
    append_rollback_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-1",
        current_stage="canary-5",
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression,
        operator_status=rollback_status,
        rollback_completion=rollback_completion,
        created_at="2026-09-22T04:58:00+00:00",
    )
    append_recovery_event(
        ledger=ledger,
        key=KEY,
        release_id="coworker-cohort-001",
        actor_reference="oncall-primary",
        change_reference="incident-1",
        current_stage="canary-5",
        rollout=rollout_path,
        canary_plan=plan_path,
        progression_decision=progression,
        operator_status=recovery_status,
        rollback_completion=rollback_completion,
        recovery_verification=recovery_verification,
        created_at="2026-09-22T05:00:00+00:00",
    )
    # Sign an authentic receipt before mutating the fixture. The strict release
    # signer must refuse malformed input; the canary verifier separately
    # refuses evidence corrupted after the ledger has authenticated its bytes.
    if mutate_recovery is not None:
        mutate_recovery(recovery_verification)
    return ledger, recovery_verification


def test_post_recovery_epoch_excludes_historical_stop(monkeypatch, tmp_path):
    ledger, recovery_verification = build_recovery_ledger(tmp_path, monkeypatch)
    epoch = load_recovery_epoch(
        recovery_verification,
        ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
    )
    history = [
        row(datetime(2026, 9, 22, 4, 55, tzinfo=timezone.utc), decision="STOP_ROLLOUT"),
        row(datetime(2026, 9, 22, 5, 5, tzinfo=timezone.utc)),
        row(datetime(2026, 9, 22, 5, 10, tzinfo=timezone.utc)),
        row(datetime(2026, 9, 22, 5, 15, tzinfo=timezone.utc)),
    ]
    result = evaluate_progression(
        history,
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 5, 17, tzinfo=timezone.utc),
        epoch_start=epoch,
    )
    assert result["decision"] == "ELIGIBLE_FOR_EXPANSION"
    assert result["reasons"] == []


def test_recovery_epoch_requires_fresh_post_recovery_health(monkeypatch, tmp_path):
    ledger, recovery_verification = build_recovery_ledger(tmp_path, monkeypatch)
    epoch = load_recovery_epoch(
        recovery_verification,
        ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
    )
    result = evaluate_progression(
        [row(datetime(2026, 9, 22, 4, 55, tzinfo=timezone.utc), decision="STOP_ROLLOUT")],
        rollout(),
        plan(),
        current_stage="canary-5",
        now=datetime(2026, 9, 22, 5, 2, tzinfo=timezone.utc),
        epoch_start=epoch,
    )
    assert result["decision"] == "HOLD"
    assert result["reasons"] == ["no_post_recovery_health"]


def test_unledgered_recovery_cannot_create_progression_epoch(monkeypatch, tmp_path):
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", KEY.decode())
    *_files, recovery_verification = recovery_epoch_files(tmp_path)
    ledger = tmp_path / "empty-ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    with pytest.raises(Exception, match="ledger"):
        load_recovery_epoch(
            recovery_verification,
            ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
        )


def test_recovery_epoch_starts_after_ledger_entry_not_only_artifact(monkeypatch, tmp_path):
    ledger, recovery_verification = build_recovery_ledger(tmp_path, monkeypatch)
    entries = ledger.read_text(encoding="utf-8").splitlines()
    last = json.loads(entries[-1])
    last["created_at"] = "2026-09-22T05:02:00+00:00"
    from scripts.cohort_release_ledger import entry_core, sign_entry
    last["entry_hash"], last["hmac_sha256"] = sign_entry(entry_core(last), KEY)
    entries[-1] = json.dumps(last, sort_keys=True, separators=(",", ":"))
    ledger.write_text("\n".join(entries) + "\n", encoding="utf-8")

    epoch = load_recovery_epoch(
        recovery_verification,
        ledger,
        release_id="coworker-cohort-001",
        current_stage="canary-5",
    )
    assert epoch == datetime(2026, 9, 22, 5, 2, tzinfo=timezone.utc)


def test_schema_v12_recovery_epoch_rejects_different_rollout(monkeypatch, tmp_path):
    monkeypatch.setenv("SHUDDHO_RELEASE_LEDGER_HMAC_KEY", KEY.decode())
    (
        rollout_path,
        _plan_path,
        _progression,
        _stop_status,
        _rollback_status,
        _rollback_completion,
        _recovery_status,
        recovery_verification,
    ) = recovery_epoch_files(tmp_path)
    value = json.loads(recovery_verification.read_text(encoding="utf-8"))
    value["schema_version"] = 12
    value["artifact_sha256"]["rollout_manifest"] = "0" * 64
    recovery_verification.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(
        Exception,
        match="does not bind the current rollout manifest",
    ):
        load_recovery_epoch(
            recovery_verification,
            tmp_path / "unused-ledger.jsonl",
            release_id="coworker-cohort-001",
            current_stage="canary-5",
            rollout_path=rollout_path,
        )


# Part 05 / Day 10: source-only evidence-boundary regressions. All rows are synthetic.
def _history_receipt():
    return row(datetime(2026, 9, 22, 4, 0, tzinfo=timezone.utc))


def test_canary_plan_rejects_duplicate_expansion_control(tmp_path):
    """A duplicate threshold must not be silently resolved to its last value."""
    path = tmp_path / "canary-plan.json"
    payload = json.dumps(plan())
    assert '"max_gap_minutes": 10' in payload
    path.write_text(
        payload.replace(
            '"max_gap_minutes": 10',
            '"max_gap_minutes": 999, "max_gap_minutes": 10',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(canary.CanaryProgressionError, match="plan"):
        canary.load_plan(path)


def test_canary_history_rejects_duplicate_health_decision(tmp_path):
    """An earlier STOP may not be hidden behind a later CONTINUE JSON key."""
    directory = tmp_path / "history"
    directory.mkdir()
    payload = json.dumps(_history_receipt())
    assert '"decision": "CONTINUE_COHORT"' in payload
    (directory / "one.json").write_text(
        payload.replace(
            '"decision": "CONTINUE_COHORT"',
            '"decision": "STOP_ROLLOUT", "decision": "CONTINUE_COHORT"',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(canary.CanaryProgressionError, match="history"):
        canary.load_history(directory)


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink checks")
def test_canary_history_rejects_symlinked_receipt(tmp_path):
    """An external linked report must not count as a trusted health window."""
    directory = tmp_path / "history"
    directory.mkdir()
    target = tmp_path / "outside.json"
    target.write_text(json.dumps(_history_receipt()), encoding="utf-8")
    (directory / "one.json").symlink_to(target)
    with pytest.raises(canary.CanaryProgressionError, match="history"):
        canary.load_history(directory)


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink checks")
def test_canary_history_rejects_symlinked_directory(tmp_path):
    """The history-directory boundary must not redirect to another location."""
    actual = tmp_path / "outside"
    actual.mkdir()
    (actual / "one.json").write_text(json.dumps(_history_receipt()), encoding="utf-8")
    linked = tmp_path / "linked-history"
    linked.symlink_to(actual, target_is_directory=True)
    with pytest.raises(canary.CanaryProgressionError, match="directory"):
        canary.load_history(linked)


def test_canary_history_rejects_oversized_health_receipt(tmp_path):
    """An evidence report with unbounded padding must fail before parsing."""
    directory = tmp_path / "history"
    directory.mkdir()
    (directory / "one.json").write_bytes(
        json.dumps(_history_receipt()).encode("utf-8") + b" " * 4_000_100,
    )
    with pytest.raises(canary.CanaryProgressionError, match="history"):
        canary.load_history(directory)


def _set_canary_cli_inputs(tmp_path, monkeypatch, output):
    directory = tmp_path / "health"
    directory.mkdir()
    now = datetime.now(timezone.utc)
    for index, age_minutes in enumerate((12, 6, 1)):
        receipt = row(now - timedelta(minutes=age_minutes))
        (directory / f"{index}.json").write_text(json.dumps(receipt), encoding="utf-8")
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps(rollout()), encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "cohort_canary_progression",
        "--history-dir", str(directory),
        "--rollout", str(rollout_path),
        "--plan", str(plan_path),
        "--current-stage", "canary-5",
        "--output", str(output),
    ])


@pytest.mark.skipif(os.name != "posix", reason="POSIX private receipt mode")
def test_canary_first_decision_report_is_private_at_default_umask(tmp_path, monkeypatch):
    """A release-specific canary result must not be readable by other users."""
    output = tmp_path / "result.json"
    _set_canary_cli_inputs(tmp_path, monkeypatch, output)
    previous_umask = os.umask(0o022)
    try:
        canary.main()
    finally:
        os.umask(previous_umask)
    assert json.loads(output.read_text(encoding="utf-8"))["decision"] == "ELIGIBLE_FOR_EXPANSION"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_canary_first_decision_report_cannot_be_overwritten(tmp_path, monkeypatch):
    """An earlier result path must remain unchanged, even if it has old content."""
    output = tmp_path / "decision.json"
    _set_canary_cli_inputs(tmp_path, monkeypatch, output)
    output.write_bytes(b"ORIGINAL_CANARY_DECISION\n")
    with pytest.raises(SystemExit, match="already exists"):
        canary.main()
    assert output.read_bytes() == b"ORIGINAL_CANARY_DECISION\n"


# Part 05 / Day 10: synthetic canary recovery trust boundary regressions.
# Successful HMAC validation does not authorize ambiguous or mutable input bytes.
def _corrupt_verified_at(path):
    original = path.read_text(encoding="utf-8")
    assert '"verified_at": "2026-09-22T05:00:00+00:00"' in original
    path.write_text(
        original.replace(
            '"verified_at": "2026-09-22T05:00:00+00:00"',
            '"verified_at": "2026-09-22T04:00:00+00:00", '
            '"verified_at": "2026-09-22T05:00:00+00:00"',
            1,
        ),
        encoding="utf-8",
    )


def test_signed_recovery_epoch_rejects_ambiguous_verified_at(monkeypatch, tmp_path):
    """Last-key-wins JSON must never create an approved recovery epoch."""
    ledger, receipt = build_recovery_ledger(
        tmp_path, monkeypatch, mutate_recovery=_corrupt_verified_at,
    )
    with pytest.raises(canary.CanaryProgressionError, match="recovery verification"):
        load_recovery_epoch(
            receipt, ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow receipt boundary")
def test_signed_recovery_epoch_rejects_symlinked_verification(monkeypatch, tmp_path):
    ledger, receipt = build_recovery_ledger(tmp_path, monkeypatch)
    target = tmp_path / "elsewhere.json"
    receipt.rename(target)
    receipt.symlink_to(target)
    with pytest.raises(canary.CanaryProgressionError, match="recovery verification"):
        load_recovery_epoch(
            receipt, ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
        )


def test_signed_recovery_epoch_rejects_oversized_verification(monkeypatch, tmp_path):
    """Signing a too-large file must not make it an acceptable control receipt."""
    def pad_receipt(path):
        with path.open("ab") as stream:
            stream.write(b" " * 4_000_100)

    ledger, receipt = build_recovery_ledger(
        tmp_path, monkeypatch, mutate_recovery=pad_receipt,
    )
    with pytest.raises(canary.CanaryProgressionError, match="recovery verification"):
        load_recovery_epoch(
            receipt, ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
        )


def test_recovery_epoch_digest_is_bound_to_the_same_parsed_bytes(monkeypatch, tmp_path):
    """A pathname swap after parsing cannot validate different signed bytes."""
    ledger, receipt = build_recovery_ledger(tmp_path, monkeypatch)
    signed_bytes = receipt.read_bytes()
    assert b"2026-09-22T05:00:00+00:00" in signed_bytes
    tampered_bytes = signed_bytes.replace(
        b"2026-09-22T05:00:00+00:00",
        b"2026-09-22T05:30:00+00:00",
        1,
    )
    receipt.write_bytes(tampered_bytes)
    real_sha = canary.file_sha256

    def swap_on_second_read(path):
        if path == receipt:
            # The release ledger still attests the originally signed bytes.
            receipt.write_bytes(signed_bytes)
        return real_sha(path)

    monkeypatch.setattr(canary, "file_sha256", swap_on_second_read)
    with pytest.raises(canary.CanaryProgressionError, match="does not bind"):
        load_recovery_epoch(
            receipt, ledger,
            release_id="coworker-cohort-001",
            current_stage="canary-5",
        )
    # A safe single-read rejection never invokes the deprecated later SHA hook
    # and therefore leaves the untrusted, post-signing bytes unchanged.
    assert receipt.read_bytes() == tampered_bytes
