"""Regression tests for release-ledger snapshot and concurrent append integrity."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import multiprocessing
import threading

import pytest

from scripts import cohort_release_ledger as ledger_module

KEY = b"k" * 32
RELEASE = "synthetic-release"


def _inputs(tmp_path):
    values = {
        "rollout": {"release_id": RELEASE},
        "canary_plan": {"release_id": RELEASE, "stages": [{"name": "canary"}]},
        "progression_decision": {
            "release_id": RELEASE, "decision": "HOLD",
            "current_stage": "canary", "next_stage": None,
        },
        "operator_status": {"release_id": RELEASE},
    }
    paths = {}
    for name, value in values.items():
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    return paths


def _append(path, inputs, reference):
    return ledger_module.append_event(
        ledger=path, key=KEY, release_id=RELEASE, event_type="hold",
        actor_reference="synthetic-operator", change_reference=reference,
        current_stage="canary", next_stage=None, **inputs,
    )


def test_signed_hash_describes_validated_bytes_not_replacement(tmp_path, monkeypatch):
    inputs = _inputs(tmp_path)
    path = tmp_path / "ledger.jsonl"
    decision = inputs["progression_decision"]
    expected = hashlib.sha256(decision.read_bytes()).hexdigest()
    real_read = ledger_module.read_entries

    def swap_after_validation(ledger):
        replacement = decision.with_suffix(".replacement")
        replacement.write_text('{"decision":"STOP_ROLLOUT"}', encoding="utf-8")
        replacement.replace(decision)
        return real_read(ledger)

    monkeypatch.setattr(ledger_module, "read_entries", swap_after_validation)
    # An implementation may either sign exactly the validated snapshot or
    # refuse to sign when an input changes; it must never attest replacement bytes.
    try:
        entry = _append(path, inputs, "one")
    except ledger_module.ReleaseLedgerError:
        assert not path.exists()
    else:
        assert entry["artifact_sha256"]["progression_decision"] == expected
        assert ledger_module.verify_entries(real_read(path), KEY)["entries"] == 1


def test_concurrent_successes_cannot_lose_a_signed_event(tmp_path, monkeypatch):
    inputs = _inputs(tmp_path)
    path = tmp_path / "ledger.jsonl"
    real_read = ledger_module.read_entries
    barrier = threading.Barrier(2)
    thread_state = threading.local()

    def simultaneous_read(ledger):
        entries = real_read(ledger)
        if not getattr(thread_state, "read", False):
            thread_state.read = True
            barrier.wait(timeout=10)
        return entries

    monkeypatch.setattr(ledger_module, "read_entries", simultaneous_read)

    def attempt(reference):
        try:
            return _append(path, inputs, reference)
        except ledger_module.ReleaseLedgerError as exc:
            assert "changed" in str(exc).lower()
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["one", "two"]))
    successes = [entry for entry in results if entry is not None]
    entries = real_read(path)
    assert successes
    assert {entry["entry_hash"] for entry in entries} == {
        entry["entry_hash"] for entry in successes
    }
    assert len(entries) == len(successes)
    assert ledger_module.verify_entries(entries, KEY)["entries"] == len(successes)


def test_process_contention_rejects_stale_append_and_allows_fresh_retry(tmp_path, monkeypatch):
    inputs = _inputs(tmp_path)
    path = tmp_path / "ledger.jsonl"
    real_read = ledger_module.read_entries
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    results = context.Queue()
    first_read = True

    def simultaneous_read(ledger):
        nonlocal first_read
        entries = real_read(ledger)
        if first_read:
            first_read = False
            barrier.wait(timeout=10)
        return entries

    monkeypatch.setattr(ledger_module, "read_entries", simultaneous_read)

    def attempt(reference):
        try:
            entry = _append(path, inputs, reference)
        except ledger_module.ReleaseLedgerError as exc:
            results.put(("conflict", reference, str(exc)))
        else:
            results.put(("success", reference, entry["entry_hash"]))

    processes = [context.Process(target=attempt, args=(ref,)) for ref in ("one", "two")]
    try:
        for process in processes:
            process.start()
        records = [results.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()
        results.join_thread()

    assert sorted(record[0] for record in records) == ["conflict", "success"]
    conflict = next(record for record in records if record[0] == "conflict")
    winner = next(record for record in records if record[0] == "success")
    assert "Ledger changed" in conflict[2]
    assert real_read(path)[0]["entry_hash"] == winner[2]

    monkeypatch.setattr(ledger_module, "read_entries", real_read)
    retry = _append(path, inputs, conflict[1])
    assert retry["previous_entry_hash"] == winner[2]
    assert ledger_module.verify_entries(real_read(path), KEY)["entries"] == 2
    sidecar = path.with_name("." + path.name + ".lock")
    assert sidecar.is_file()
    assert sidecar.stat().st_mode & 0o077 == 0


def test_append_refuses_linked_lock_without_touching_target(tmp_path):
    inputs = _inputs(tmp_path)
    path = tmp_path / "ledger.jsonl"
    target = tmp_path / "unrelated"
    target.write_text("unchanged", encoding="utf-8")
    path.with_name("." + path.name + ".lock").symlink_to(target)
    with pytest.raises(ledger_module.ReleaseLedgerError, match="Could not commit ledger append"):
        _append(path, inputs, "one")
    assert not path.exists()
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_append_write_failure_does_not_hold_lock_or_modify_history(tmp_path, monkeypatch):
    inputs = _inputs(tmp_path)
    path = tmp_path / "ledger.jsonl"
    first = _append(path, inputs, "one")
    real_write = ledger_module.atomic_write

    def fail_before_replace(path, content):
        raise OSError("synthetic write failure")

    monkeypatch.setattr(ledger_module, "atomic_write", fail_before_replace)
    with pytest.raises(ledger_module.ReleaseLedgerError, match="Could not commit ledger append"):
        _append(path, inputs, "two")
    assert ledger_module.read_entries(path) == [first]

    monkeypatch.setattr(ledger_module, "atomic_write", real_write)
    second = _append(path, inputs, "two")
    assert second["previous_entry_hash"] == first["entry_hash"]
    assert ledger_module.verify_entries(ledger_module.read_entries(path), KEY)["entries"] == 2


def test_rollback_signs_the_validated_completion_receipt(tmp_path, monkeypatch):
    inputs = _inputs(tmp_path)
    path = tmp_path / "ledger.jsonl"
    inputs["progression_decision"].write_text(json.dumps({
        "release_id": RELEASE, "decision": "STOP_ROLLOUT",
        "current_stage": "canary", "next_stage": None,
    }), encoding="utf-8")
    ledger_module.append_event(
        ledger=path, key=KEY, release_id=RELEASE, event_type="stop_rollout",
        actor_reference="synthetic-operator", change_reference="stop",
        current_stage="canary", next_stage=None, **inputs,
    )
    inputs["operator_status"].write_text(json.dumps({
        "release_id": RELEASE, "decision": "CONTINUE_COHORT", "breaches": [],
    }), encoding="utf-8")
    receipt = tmp_path / "rollback.json"
    receipt.write_text(json.dumps({
        "release_id": RELEASE, "status": "rollback_completed",
        "artifact_sha256": {
            "rollout_manifest": hashlib.sha256(inputs["rollout"].read_bytes()).hexdigest(),
            "operator_status": hashlib.sha256(inputs["operator_status"].read_bytes()).hexdigest(),
        },
    }), encoding="utf-8")
    expected = hashlib.sha256(receipt.read_bytes()).hexdigest()
    real_read = ledger_module.read_entries

    def replace_receipt(ledger):
        receipt.write_text('{"status":"failed"}', encoding="utf-8")
        return real_read(ledger)

    monkeypatch.setattr(ledger_module, "read_entries", replace_receipt)
    entry = ledger_module.append_rollback_event(
        ledger=path, key=KEY, release_id=RELEASE,
        actor_reference="synthetic-operator", change_reference="rollback",
        current_stage="canary", rollback_completion=receipt, **inputs,
    )
    assert entry["artifact_sha256"]["rollback_completion"] == expected
    assert ledger_module.verify_entries(real_read(path), KEY)["entries"] == 2
