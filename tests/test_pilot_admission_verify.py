"""Source-only regressions for post-admission pilot access verification.

All credentials, API responses, approvals and users here are synthetic. These
tests do not constitute a pilot admission or independently operated evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for pilot access tests")
pytest.importorskip("jwt", reason="Install the coworker extra for pilot access tests")

from scripts import pilot_admission_verify as pilot
from scripts.staging_release_freeze import RUNTIME_CAPABILITY_KEYS

REV = "a" * 40


def ready_files(tmp_path: Path, monkeypatch):
    rollout = {"release_id": "pilot-synthetic", "cohort": {"max_users": 5}}
    rollout_path = tmp_path / "rollout.json"
    rollout_path.write_text(json.dumps(rollout), encoding="utf-8")
    digest = hashlib.sha256(rollout_path.read_bytes()).hexdigest()
    decision = {
        "decision": "READY_FOR_OWNER_CONTROLLED_PILOT",
        "canonical_decision": "GO_CONTROLLED_COHORT",
        "pilot_activated": False,
        "blockers": [],
        "release_id": rollout["release_id"],
        "source_revision": REV,
        "rollout_manifest_sha256": digest,
    }
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    # Isolate the decision-binding contract; canonical rollout shape is
    # already covered by tests/test_cohort_release_gate.py.
    monkeypatch.setattr(pilot, "validate_rollout", lambda *a, **kw: [])
    return rollout_path, decision_path, decision


def test_ready_decision_requires_exact_manifest_bytes_and_source(tmp_path, monkeypatch):
    rollout, decision, evidence = ready_files(tmp_path, monkeypatch)
    manifest, digest = pilot.require_release_decision(rollout, decision, REV)
    assert manifest["release_id"] == "pilot-synthetic"
    assert digest == evidence["rollout_manifest_sha256"]
    with pytest.raises(pilot.PilotVerificationFailure, match="revision"):
        pilot.require_release_decision(rollout, decision, "short")
    rollout.write_text('{"release_id": "pilot-synthetic", "cohort": {"max_users": 5}, "altered": true}',
                       encoding="utf-8")
    with pytest.raises(pilot.PilotVerificationFailure, match="mismatched"):
        pilot.require_release_decision(rollout, decision, REV)


@pytest.mark.parametrize("change", [
    {"decision": "SOURCE_ONLY"},
    {"decision": "STAGING_ONLY"},
    {"canonical_decision": "NO-GO"},
    {"pilot_activated": True},
    {"blockers": ["missing_approvals"]},
    {"release_id": "other-release"},
    {"source_revision": "b" * 40},
    {"rollout_manifest_sha256": "0" * 64},
])
def test_unqualified_decision_never_opens_pilot_check(tmp_path, monkeypatch, change):
    rollout, decision_path, decision = ready_files(tmp_path, monkeypatch)
    decision.update(change)
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(pilot.PilotVerificationFailure, match="absent or mismatched"):
        pilot.require_release_decision(rollout, decision_path, REV)


@pytest.mark.parametrize("maximum", [4, 11, True, "5"])
def test_pilot_limit_only_five_to_ten(tmp_path, monkeypatch, maximum):
    rollout, decision_path, _ = ready_files(tmp_path, monkeypatch)
    rollout.write_text(json.dumps({"release_id": "pilot-synthetic", "cohort": {"max_users": maximum}}),
                       encoding="utf-8")
    with pytest.raises(pilot.PilotVerificationFailure, match="maximum"):
        pilot.require_release_decision(rollout, decision_path, REV)


def secret_file(tmp_path, tokens):
    path = tmp_path / "private-tokens.json"
    path.write_text(json.dumps(tokens), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_private_member_tokens_require_five_to_ten_unique_values(tmp_path):
    path = secret_file(tmp_path, [f"synthetic-token-{i}" for i in range(5)])
    assert len(pilot.load_member_tokens(path)) == 5
    path.write_text(json.dumps(["same"] * 5), encoding="utf-8")
    with pytest.raises(pilot.PilotVerificationFailure, match="distinct"):
        pilot.load_member_tokens(path)
    path.write_text(json.dumps(["synthetic"] * 4), encoding="utf-8")
    with pytest.raises(pilot.PilotVerificationFailure, match="five to ten"):
        pilot.load_member_tokens(path)
    path.write_text(json.dumps(["synthetic"] * 11), encoding="utf-8")
    with pytest.raises(pilot.PilotVerificationFailure, match="five to ten"):
        pilot.load_member_tokens(path)


def test_private_member_token_file_rejects_unsafe_storage(tmp_path):
    path = secret_file(tmp_path, [str(i) for i in range(5)])
    path.chmod(0o644)
    with pytest.raises(pilot.PilotVerificationFailure, match="0600"):
        pilot.load_member_tokens(path)
    path.chmod(0o600)
    link = tmp_path / "tokens-link.json"
    link.symlink_to(path)
    with pytest.raises(pilot.PilotVerificationFailure, match="Cannot read"):
        pilot.load_member_tokens(link)
    path.write_text('["a","b","c","d",NaN]', encoding="utf-8")
    with pytest.raises(pilot.PilotVerificationFailure, match="Cannot read"):
        pilot.load_member_tokens(path)


def test_member_tokens_must_cover_exact_backend_cohort(monkeypatch):
    monkeypatch.setattr(pilot, "token_account_id", lambda token, settings: token)
    members = [f"member-{i}" for i in range(5)]
    cfg = SimpleNamespace(cohort_enforced=True, cohort_max_users=5,
                          cohort_account_ids=frozenset(members))
    assert pilot.require_exact_pilot_members(cfg, members, "nonmember", 5) == "nonmember"
    with pytest.raises(pilot.PilotVerificationFailure, match="exactly match"):
        pilot.require_exact_pilot_members(cfg, members[:-1] + ["outsider"], "nonmember", 5)
    with pytest.raises(pilot.PilotVerificationFailure, match="overlap"):
        pilot.require_exact_pilot_members(cfg, members, members[0], 5)
    with pytest.raises(pilot.PilotVerificationFailure, match="allowlist"):
        pilot.require_exact_pilot_members(
            SimpleNamespace(cohort_enforced=True, cohort_max_users=10,
                            cohort_account_ids=frozenset(members)), members, "nonmember", 5,
        )
    with pytest.raises(pilot.PilotVerificationFailure, match="disabled"):
        pilot.require_exact_pilot_members(
            SimpleNamespace(cohort_enforced=False, cohort_max_users=5,
                            cohort_account_ids=frozenset(members)), members, "nonmember", 5,
        )


class Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.body = body

    def json(self):
        return self.body


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = []

    def get(self, path, headers):
        assert path in {"/api/v1/me", "/api/v1/runtime-manifest"}
        self.headers.append(headers["Authorization"])
        return next(self.responses)


def test_all_five_members_probed_then_nonmember_denied():
    client = Client([Response(200) for _ in range(5)] + [
        Response(403, {"error": {"code": "cohort_not_enabled"}}),
    ])
    pilot.probe_access(client, [f"synthetic-token-{i}" for i in range(5)], "denied")
    assert len(client.headers) == 6
    assert client.headers[-1] == "Bearer denied"


@pytest.mark.parametrize("index,status,body", [
    (0, 403, None),
    (4, 401, None),
    (5, 200, None),
    (5, 403, {"error": {"code": "unrelated"}}),
    (5, 403, {"error": "unexpected"}),
])
def test_any_missing_member_or_nonmember_denial_fails_closed(index, status, body):
    responses = [Response(200) for _ in range(5)] + [
        Response(403, {"error": {"code": "cohort_not_enabled"}}),
    ]
    responses[index] = Response(status, body)
    with pytest.raises(pilot.PilotVerificationFailure):
        pilot.probe_access(Client(responses), [f"member-{i}" for i in range(5)], "denied")


def test_first_access_report_is_immutable_and_contains_no_credentials(tmp_path):
    report = tmp_path / "pilot-observation.json"
    payload = {
        "status": "passed", "members_checked": 5,
        "admission_performed_by_cli": False,
        "human_approvals_authenticated_by_cli": False,
    }
    pilot.immutable_report(report, payload)
    assert json.loads(report.read_text(encoding="utf-8")) == payload
    with pytest.raises(pilot.PilotVerificationFailure, match="already exists"):
        pilot.immutable_report(report, {"status": "failed"})
    assert json.loads(report.read_text(encoding="utf-8")) == payload


def live_runtime(rollout, revision=REV, members=5):
    capabilities = {key: False for key in RUNTIME_CAPABILITY_KEYS}
    rollout.update(environment="production", capabilities=capabilities, action_providers=[])
    return {
        "schema_version": 2,
        "source_revision": revision,
        "environment": "production",
        "capabilities": {**capabilities, "grounded_conversation_replies": capabilities["conversation_replies"]},
        "reviewed_skills": {},
        "action_providers": [],
        "cohort": {
            "enforced": True,
            "configured_members": members,
            "max_users": rollout["cohort"]["max_users"],
        },
    }


def test_live_runtime_matches_exact_source_flags_and_cohort():
    rollout = {"cohort": {"max_users": 5}}
    runtime = live_runtime(rollout)
    client = Client([Response(200, runtime)])
    pilot.verify_live_runtime(client, "synthetic-token", rollout, REV, 5)
    assert client.headers == ["Bearer synthetic-token"]


@pytest.mark.parametrize("mutation", [
    lambda runtime: runtime.update(source_revision="b" * 40),
    lambda runtime: runtime.update(environment="staging"),
    lambda runtime: runtime.update(schema_version=True),
    lambda runtime: runtime["capabilities"].pop("coworker"),
    lambda runtime: runtime["capabilities"].update(unknown_disabled=False),
    lambda runtime: runtime["capabilities"].update(coworker=0),
    lambda runtime: runtime["capabilities"].update(coworker=True),
    lambda runtime: runtime["capabilities"].pop("grounded_conversation_replies"),
    lambda runtime: runtime["capabilities"].update(grounded_conversation_replies=True),
    lambda runtime: runtime["capabilities"].update(grounded_conversation_replies=0),
    lambda runtime: runtime.update(reviewed_skills=None),
    lambda runtime: runtime.update(action_providers=["google"]),
    lambda runtime: runtime["cohort"].update(enforced=False),
    lambda runtime: runtime["cohort"].update(max_users=10),
    lambda runtime: runtime["cohort"].update(configured_members=4),
    lambda runtime: runtime["cohort"].update(configured_members=True),
])
def test_live_runtime_wrong_identity_or_flags_fails_closed(mutation):
    rollout = {"cohort": {"max_users": 5}}
    runtime = live_runtime(rollout)
    mutation(runtime)
    with pytest.raises(pilot.PilotVerificationFailure, match="Live API identity"):
        pilot.verify_live_runtime(Client([Response(200, runtime)]), "synthetic", rollout, REV, 5)


@pytest.mark.parametrize("response", [
    Response(401),
    Response(200, []),
    Response(200, "not a runtime"),
    Response(200, {"source_revision": REV}),
])
def test_live_runtime_unreadable_or_incomplete_fails_closed(response):
    rollout = {"cohort": {"max_users": 5}}
    live_runtime(rollout)
    with pytest.raises(pilot.PilotVerificationFailure):
        pilot.verify_live_runtime(Client([response]), "synthetic", rollout, REV, 5)



def test_first_failed_access_attempt_is_preserved_without_secret_leak(tmp_path, capsys):
    report = tmp_path / "first-failure.json"
    args = [
        "--rollout", str(tmp_path / "missing-rollout.json"),
        "--decision", str(tmp_path / "missing-decision.json"),
        "--source-revision", REV,
        "--member-tokens-file", str(tmp_path / "missing-member-tokens.json"),
        "--output", str(report),
    ]
    assert pilot.main(args) == 1
    first = report.read_bytes()
    receipt = json.loads(first)
    assert receipt["status"] == "failed"
    assert receipt["admission_performed_by_cli"] is False
    assert receipt["human_approvals_authenticated_by_cli"] is False
    assert receipt["failure_type"] in {"ValueError", "EvidenceError"}
    assert "missing-rollout.json" not in first.decode("utf-8")
    assert pilot.main(args) == 1
    assert report.read_bytes() == first
    assert "missing-member-tokens.json" not in capsys.readouterr().out


def test_post_admission_readback_retains_exact_authority_and_derived_ui_split():
    rollout = {"cohort": {"max_users": 5}}
    observed = live_runtime(rollout)
    assert len(rollout["capabilities"]) == 43
    assert len(observed["capabilities"]) == 44
    assert pilot.api_runtime_capabilities_match_rollout(
        observed["capabilities"], rollout["capabilities"],
    )
