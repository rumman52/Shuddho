from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.pa10_staging_evidence import Pa10EvidenceError, REQUIRED_SCENARIOS, compile_bundle


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path):
    rollout = write_json(
        tmp_path / "rollout.json",
        {"release_id": "pa10-stage-001", "capabilities": {"automations": True}},
    )
    policy = write_json(
        tmp_path / "policy.json",
        {"schema_version": 1, "release_id": "pa10-stage-001"},
    )
    release = {
        "release_id": "pa10-stage-001",
        "source_revision": "a" * 40,
        "environment": "staging",
        "deployment_reference": "render-staging-123",
        "rollout_manifest_sha256": file_hash(rollout),
        "provider_policy_sha256": file_hash(policy),
    }
    scenarios = []
    for index, scenario_id in enumerate(REQUIRED_SCENARIOS):
        evidence = write_json(
            tmp_path / f"{scenario_id}.json",
            {
                "status": "passed",
                "release": release,
                "result": {"synthetic": False, "index": index},
            },
        )
        item = {
            "id": scenario_id,
            "status": "passed",
            "release": release,
            "verified_at": f"2026-10-01T12:{index:02d}:00+00:00",
            "evidence": [{"path": str(evidence), "sha256": file_hash(evidence)}],
            "references": [f"staging-run-{index}"],
        }
        if scenario_id in {"meeting_coworker", "email_coworker"}:
            item["providers"] = ["google", "microsoft"]
        if scenario_id == "browser_push":
            item["device_confirmation_reference"] = "browser-device-capture-123"
        if scenario_id == "multilingual_human_review":
            item["languages"] = ["en", "bn"]
            item["human_reviewers"] = 2
        if scenario_id == "task_economics":
            item["completed_useful_task_samples"] = 6
        scenarios.append(item)
    manifest = write_json(
        tmp_path / "manifest.json",
        {"schema_version": 1, "release": release, "scenarios": scenarios},
    )
    return manifest, rollout, policy


def compile_ok(files):
    manifest, rollout, policy = files
    return compile_bundle(
        manifest_path=manifest,
        rollout_path=rollout,
        provider_policy_path=policy,
    )


def test_compile_requires_all_release_bound_scenarios(tmp_path):
    bundle = compile_ok(fixture(tmp_path))
    assert bundle["status"] == "passed"
    assert bundle["scenario_count"] == len(REQUIRED_SCENARIOS)
    assert bundle["staging_records"]["automations"]["status"] == "passed"
    assert bundle["staging_records"]["browser_push"]["status"] == "passed"


def test_missing_scenario_is_rejected(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    value["scenarios"] = value["scenarios"][:-1]
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="scenario set is incomplete"):
        compile_ok(files)


def test_mixed_release_evidence_is_rejected(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    value["scenarios"][0]["release"]["source_revision"] = "b" * 40
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="source_revision"):
        compile_ok(files)


def test_evidence_hash_mismatch_is_rejected(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    value["scenarios"][0]["evidence"][0]["sha256"] = "0" * 64
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="evidence hash does not match"):
        compile_ok(files)


def test_provider_scenarios_require_google_and_microsoft(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    email = next(item for item in value["scenarios"] if item["id"] == "email_coworker")
    email["providers"] = ["google"]
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="both Google and Microsoft"):
        compile_ok(files)


def test_human_review_cannot_be_replaced_with_machine_only_record(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    review = next(
        item
        for item in value["scenarios"]
        if item["id"] == "multilingual_human_review"
    )
    review["human_reviewers"] = 0
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="human reviewer"):
        compile_ok(files)


def test_browser_push_requires_real_device_confirmation_reference(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    push = next(item for item in value["scenarios"] if item["id"] == "browser_push")
    push["device_confirmation_reference"] = ""
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="device-display confirmation"):
        compile_ok(files)


def test_task_economics_requires_measured_completed_useful_task_sample(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    economics = next(item for item in value["scenarios"] if item["id"] == "task_economics")
    economics["completed_useful_task_samples"] = 0
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="measured completed useful proactive-task sample"):
        compile_ok(files)


def test_production_environment_is_rejected(tmp_path):
    files = fixture(tmp_path)
    value = json.loads(files[0].read_text(encoding="utf-8"))
    value["release"]["environment"] = "production"
    write_json(files[0], value)
    with pytest.raises(Pa10EvidenceError, match="non-production environment"):
        compile_ok(files)
