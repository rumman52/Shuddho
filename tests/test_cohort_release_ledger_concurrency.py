"""Regression tests for release-ledger snapshot and concurrent append integrity."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
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
