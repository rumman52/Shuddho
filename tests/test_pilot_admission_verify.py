"""Source-only regressions for post-admission pilot access verification.

All credentials, API responses, approvals and users here are synthetic. These
tests do not constitute a pilot admission or independently operated evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy", reason="Install the coworker extra for pilot access tests")
pytest.importorskip("jwt", reason="Install the coworker extra for pilot access tests")

from scripts import day10_release_decision as day10
from scripts import pilot_admission_verify as pilot
from scripts.staging_release_freeze import RUNTIME_CAPABILITY_KEYS

REV = "a" * 40


def ready_files(tmp_path: Path, monkeypatch):
    rollout = {
        "release_id": "pilot-synthetic", "environment": "production",
        "cohort": {"reference": "synthetic-private-cohort", "max_users": 5},
        "capabilities": dict.fromkeys(RUNTIME_CAPABILITY_KEYS, False),
        "action_providers": [], "transaction_operations": [],
    }
    scope = {key: value for key, value in rollout.items() if key != "release_id"}
    claim = {
        "scope_sha256": hashlib.sha256(json.dumps(
            scope, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest(),
        "max_spend_microusd": 1_000_000,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
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
        "pilot_authorization_claim": claim,
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
    assert pilot.require_exact_pilot_members(cfg, members, "nonmember", 5) == (members, "nonmember")
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
    member_ids = [f"account-{i}" for i in range(5)]
    client = Client([Response(200, {"account_id": owner}) for owner in member_ids] + [
        Response(403, {"error": {"code": "cohort_not_enabled"}}),
    ])
    pilot.probe_access(client, [f"synthetic-token-{i}" for i in range(5)], "denied", member_ids)
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
    member_ids = [f"account-{i}" for i in range(5)]
    responses = [Response(200, {"account_id": owner}) for owner in member_ids] + [
        Response(403, {"error": {"code": "cohort_not_enabled"}}),
    ]
    responses[index] = Response(status, body)
    with pytest.raises(pilot.PilotVerificationFailure):
        pilot.probe_access(Client(responses), [f"member-{i}" for i in range(5)], "denied", member_ids)


@pytest.mark.parametrize("invalid_body", [
    None,
    {},
    {"account_id": "another-member"},
    {"account_id": 42},
    {"account_id": None},
    ["not-an-account-response"],
])
def test_member_http_200_with_wrong_identity_fails_closed_without_leaking(invalid_body):
    # A cached/cross-owner 200 is never evidence that this token was admitted.
    members = [f"account-{i}" for i in range(5)]
    responses = [Response(200, {"account_id": account}) for account in members] + [
        Response(403, {"error": {"code": "cohort_not_enabled"}}),
    ]
    responses[2] = Response(200, invalid_body)
    client = Client(responses)
    with pytest.raises(pilot.PilotVerificationFailure, match="identity") as exc:
        pilot.probe_access(client, [f"member-token-{i}" for i in range(5)], "denied", members)
    assert "account-" not in str(exc.value)
    assert "member-token" not in str(exc.value)
    # Abort before checking later members or the nonmember after an identity mismatch.
    assert len(client.headers) == 3


def test_duplicate_or_incomplete_expected_member_identity_list_is_denied():
    members = [f"account-{i}" for i in range(5)]
    tokens = [f"member-token-{i}" for i in range(5)]
    for invalid in (members[:4], [members[0]] * 5):
        client = Client([])
        with pytest.raises(pilot.PilotVerificationFailure, match="identity"):
            pilot.probe_access(client, tokens, "denied", invalid)
        assert client.headers == []


def test_member_http_200_with_malformed_json_fails_closed():
    class InvalidJSON(Response):
        def json(self):
            raise ValueError("response has no parseable JSON")

    members = [f"account-{i}" for i in range(5)]
    client = Client([InvalidJSON(200)])
    with pytest.raises(pilot.PilotVerificationFailure, match="identity"):
        pilot.probe_access(client, [f"member-token-{i}" for i in range(5)], "denied", members)


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
        "canonical_only_capabilities": {"suggestion_model_relevance": False},
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
    lambda runtime: runtime.pop("canonical_only_capabilities"),
    lambda runtime: runtime.update(canonical_only_capabilities={}),
    lambda runtime: runtime.update(canonical_only_capabilities={"suggestion_model_relevance": True}),
    lambda runtime: runtime.update(canonical_only_capabilities={"suggestion_model_relevance": 0}),
    lambda runtime: runtime.update(canonical_only_capabilities={"suggestion_model_relevance": False, "unknown": False}),
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


def test_admission_rollout_sha_is_bound_to_original_parsed_bytes(tmp_path, monkeypatch):
    """Replacing the rollout path after parse must not change the verified digest."""
    rollout_path, decision_path, evidence = ready_files(tmp_path, monkeypatch)
    read_original = day10.read_bounded_json_with_sha

    def swap_after_verified_read(path):
        parsed, digest = read_original(path)
        if path == rollout_path:
            rollout_path.write_text(
                '{"release_id":"substituted","cohort":{"max_users":5}}',
                encoding="utf-8",
            )
        return parsed, digest

    monkeypatch.setattr(day10, "read_bounded_json_with_sha", swap_after_verified_read)
    rollout, digest = pilot.require_release_decision(rollout_path, decision_path, REV)
    assert rollout["release_id"] == "pilot-synthetic"
    assert digest == evidence["rollout_manifest_sha256"]
    assert json.loads(rollout_path.read_text(encoding="utf-8"))["release_id"] == "substituted"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes required")
def test_access_receipt_written_private_with_ordinary_umask(tmp_path):
    """Sensitive owner and admission references must not become world readable."""
    output = tmp_path / "first-access-receipt.json"
    previous_umask = os.umask(0o022)
    try:
        pilot.immutable_report(output, {"status": "failed", "private_observation": "synthetic"})
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "failed"


@pytest.mark.parametrize("case", [
    "valid", "zero", "timezone", "missing", "null", "scope", "missing_spend",
    "boolean", "negative", "expired", "naive", "extra", "changed_scope",
])
def test_post_admission_requires_current_exact_pilot_terms(tmp_path, monkeypatch, case):
    rollout_path, decision_path, decision = ready_files(tmp_path, monkeypatch)
    claim = decision["pilot_authorization_claim"]
    expiry = datetime.fromisoformat(claim["expires_at"])
    if case == "zero":
        claim["max_spend_microusd"] = 0
    elif case == "timezone":
        claim["expires_at"] = expiry.astimezone(timezone(timedelta(hours=6))).isoformat()
    elif case == "missing":
        decision.pop("pilot_authorization_claim")
    elif case == "null":
        decision["pilot_authorization_claim"] = None
    elif case == "scope":
        claim["scope_sha256"] = "e" * 64
    elif case == "missing_spend":
        claim.pop("max_spend_microusd")
    elif case == "boolean":
        claim["max_spend_microusd"] = True
    elif case == "negative":
        claim["max_spend_microusd"] = -1
    elif case == "expired":
        claim["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    elif case == "naive":
        claim["expires_at"] = expiry.replace(tzinfo=None).isoformat()
    elif case == "extra":
        claim["extra"] = False
    elif case == "changed_scope":
        value = json.loads(rollout_path.read_text(encoding="utf-8"))
        value["cohort"]["reference"] = "other-private-cohort"
        rollout_path.write_text(json.dumps(value), encoding="utf-8")
        decision["rollout_manifest_sha256"] = hashlib.sha256(rollout_path.read_bytes()).hexdigest()
    decision_path.write_text(json.dumps(decision), encoding="utf-8")

    if case in {"valid", "zero", "timezone"}:
        assert pilot.require_release_decision(rollout_path, decision_path, REV)[0]["release_id"] == "pilot-synthetic"
    else:
        with pytest.raises(pilot.PilotVerificationFailure, match="authorization terms"):
            pilot.require_release_decision(rollout_path, decision_path, REV)


def test_post_admission_expired_decision_rejects_before_reading_tokens(tmp_path, monkeypatch):
    rollout, decision_path, decision = ready_files(tmp_path, monkeypatch)
    decision["pilot_authorization_claim"]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    decision_path.write_text(json.dumps(decision), encoding="utf-8")

    def forbidden(*args):
        pytest.fail("expired authorization reached private token read")

    monkeypatch.setattr(pilot, "load_member_tokens", forbidden)
    output = tmp_path / "rejected.json"
    assert pilot.main([
        "--rollout", str(rollout), "--decision", str(decision_path),
        "--source-revision", REV, "--member-tokens-file", str(tmp_path / "never-read.json"),
        "--output", str(output),
    ]) == 1
    assert json.loads(output.read_text())["status"] == "failed"


def test_post_admission_expiry_during_probe_cannot_publish_pass(tmp_path, monkeypatch):
    rollout, decision_path, decision = ready_files(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=1)
    decision["pilot_authorization_claim"]["expires_at"] = expiry.isoformat()
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    clock = [now]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0] if tz is not None else clock[0].replace(tzinfo=None)

    monkeypatch.setattr(pilot, "datetime", Clock)
    tokens = [f"synthetic-token-{i}" for i in range(5)]
    members = [f"synthetic-member-{i}" for i in range(5)]
    monkeypatch.setattr(pilot, "load_member_tokens", lambda *args: tokens)
    monkeypatch.setattr(pilot.Settings, "from_env", lambda: SimpleNamespace())
    monkeypatch.setattr(pilot, "env_secret", lambda name: "https://example.test" if "BASE_URL" in name else "synthetic-denied")
    monkeypatch.setattr(pilot, "require_exact_pilot_members", lambda *args: (members, "synthetic-outsider"))
    monkeypatch.setattr(pilot, "assert_denied_unprovisioned", lambda *args: None)
    monkeypatch.setattr(pilot, "verify_live_runtime", lambda *args: None)

    class SyntheticClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr(pilot.httpx, "Client", SyntheticClient)
    def probe(*args):
        clock[0] = expiry + timedelta(seconds=1)
    monkeypatch.setattr(pilot, "probe_access", probe)
    output = tmp_path / "expired-during-probe.json"
    assert pilot.main([
        "--rollout", str(rollout), "--decision", str(decision_path),
        "--source-revision", REV, "--member-tokens-file", str(tmp_path / "synthetic.json"),
        "--output", str(output),
    ]) == 1
    assert json.loads(output.read_text())["status"] == "failed"


@pytest.mark.parametrize("mutation", ["same_size", "grow", "truncate", "permissions", "none"])
def test_private_member_token_capture_rejects_in_place_mutation(tmp_path, monkeypatch, mutation):
    from contextlib import contextmanager

    tokens = [f"synthetic-token-{i}" for i in range(5)]
    path = secret_file(tmp_path, tokens)
    raw = path.read_bytes()
    original_fdopen = os.fdopen

    @contextmanager
    def mutate_after_read(fd, mode):
        with original_fdopen(fd, mode) as stream:
            class Reader:
                def fileno(self):
                    return stream.fileno()

                def read(self, count):
                    assert count == pilot.MAX_SECRET_FILE_BYTES + 1
                    content = stream.read(count)
                    if mutation == "same_size":
                        path.write_bytes(raw.replace(b"synthetic", b"replaced!"))
                    elif mutation == "grow":
                        path.write_bytes(raw + b" " * pilot.MAX_SECRET_FILE_BYTES)
                    elif mutation == "truncate":
                        path.write_bytes(b"[]")
                    elif mutation == "permissions":
                        path.chmod(0o644)
                    return content

            yield Reader()

    monkeypatch.setattr(os, "fdopen", mutate_after_read)
    if mutation == "none":
        assert pilot.load_member_tokens(path) == tokens
    else:
        with pytest.raises(pilot.PilotVerificationFailure, match="Cannot read"):
            pilot.load_member_tokens(path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_member_token_fifo_rejected_without_blocking(tmp_path, monkeypatch):
    path = tmp_path / "private-tokens"
    os.mkfifo(path, 0o600)
    original_open = os.open

    def guarded_open(target, flags, *args, **kwargs):
        if Path(target) == path:
            assert flags & os.O_NONBLOCK, "token reader attempted blocking FIFO open"
        return original_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_open)
    with pytest.raises(pilot.PilotVerificationFailure, match="Cannot read"):
        pilot.load_member_tokens(path)


def test_member_token_parser_recursion_fails_without_exposing_payload(tmp_path, monkeypatch):
    path = secret_file(tmp_path, [f"synthetic-token-{i}" for i in range(5)])

    def fail_parser(*args):
        raise RecursionError("synthetic private parser error")

    monkeypatch.setattr(pilot, "strict_json_loads", fail_parser)
    with pytest.raises(pilot.PilotVerificationFailure, match="Cannot read") as exc:
        pilot.load_member_tokens(path)
    assert "synthetic" not in str(exc.value)


def test_member_token_capture_keeps_original_64k_limit(tmp_path):
    tokens = [f"synthetic-token-{i}" for i in range(5)]
    path = secret_file(tmp_path, tokens)
    raw = path.read_bytes()
    padded = raw + b" " * (pilot.MAX_SECRET_FILE_BYTES - len(raw))
    path.write_bytes(padded)
    assert pilot.load_member_tokens(path) == tokens
    path.write_bytes(padded + b" ")
    with pytest.raises(pilot.PilotVerificationFailure):
        pilot.load_member_tokens(path)


@pytest.mark.parametrize("target", ["runtime", "member", "nonmember"])
@pytest.mark.parametrize("variant", ["duplicate", "nested_duplicate", "nonfinite", "oversized", "gzip", "valid"])
def test_pilot_live_evidence_is_strict_bounded_and_streamed(target, variant):
    """Real HTTPX transport/stream; no network, actual users, or provider calls."""
    import gzip
    import httpx
    from scripts.staging_release_evidence import MAX_ROLLOUT_MANIFEST_BYTES

    rollout = {"cohort": {"max_users": 5}}
    runtime = live_runtime(rollout)
    members = [f"synthetic-account-{i}" for i in range(5)]
    tokens = [f"synthetic-token-{i}" for i in range(5)]
    denied_token = "synthetic-denied"
    status, obj = {
        "runtime": (200, runtime),
        "member": (200, {"account_id": members[0]}),
        "nonmember": (403, {"error": {"code": "cohort_not_enabled"}}),
    }[target]
    raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if variant == "duplicate":
        prefix = {
            "runtime": b'"schema_version":1,',
            "member": b'"account_id":"wrong",',
            "nonmember": b'"error":{"code":"wrong"},',
        }[target]
        raw = b"{" + prefix + raw[1:]
    elif variant == "nested_duplicate":
        raw = raw[:-1] + b',"extra":{"v":false,"v":true}}'
    elif variant == "nonfinite":
        raw = raw[:-1] + b',"extra":1e999}'
    elif variant == "oversized":
        raw = raw[:-1] + b',"padding":"' + b"x" * (MAX_ROLLOUT_MANIFEST_BYTES + 131_072) + b'"}'
    elif variant == "gzip":
        raw = gzip.compress(raw)
        headers["Content-Encoding"] = "gzip"

    class ObservedStream(httpx.SyncByteStream):
        def __init__(self, data):
            self.data = data
            self.consumed = 0
            self.closed = False

        def __iter__(self):
            for offset in range(0, len(self.data), 65536):
                chunk = self.data[offset:offset + 65536]
                self.consumed += len(chunk)
                yield chunk

        def close(self):
            self.closed = True

    selected = ObservedStream(raw)
    selected_requests = []

    def handler(request):
        token = request.headers["Authorization"].removeprefix("Bearer ")
        is_selected = (
            (target == "runtime" and request.url.path == "/api/v1/runtime-manifest")
            or (target == "member" and token == tokens[0])
            or (target == "nonmember" and token == denied_token)
        )
        if is_selected:
            selected_requests.append(request)
            return httpx.Response(status, headers=headers, stream=selected)
        return httpx.Response(200, json={"account_id": members[tokens.index(token)]})

    with httpx.Client(base_url="https://synthetic.invalid", transport=httpx.MockTransport(handler)) as client:
        def verify():
            if target == "runtime":
                pilot.verify_live_runtime(client, tokens[0], rollout, REV, len(tokens))
            else:
                pilot.probe_access(client, tokens, denied_token, members)

        if variant == "valid":
            verify()
        else:
            with pytest.raises(pilot.PilotVerificationFailure):
                verify()
    assert len(selected_requests) == 1
    assert selected_requests[0].headers["Accept-Encoding"] == "identity"
    assert selected.closed
    if variant == "gzip":
        assert selected.consumed == 0
    elif variant == "oversized":
        assert selected.consumed <= MAX_ROLLOUT_MANIFEST_BYTES + 65536
        assert selected.consumed < len(raw)
