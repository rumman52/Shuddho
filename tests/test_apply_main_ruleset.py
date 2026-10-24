"""V-01 operator helper tests: safe, explicit, read-back-verified ruleset apply.

These tests exercise a local fake API. They never change real repository settings.
"""
from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json

import pytest

from scripts.apply_main_ruleset import ApplyMainRulesetError, apply_main_ruleset, _request_json


REPO = "rumman52/Shuddho"
POLICY_PATH = Path("infra/github/main-ruleset.json")


def candidate() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def detail() -> dict:
    value = candidate()
    value["id"] = 321
    return value


def test_dry_run_describes_create_without_posting(monkeypatch):
    calls = []

    def fake(method, url, token, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/branches/main"):
            return {"name": "main", "protected": False}
        if "/rulesets?" in url:
            return []
        raise AssertionError(f"unexpected API request: {method} {url}")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", fake)
    result = apply_main_ruleset(REPO, "fake-token", candidate(), apply=False)

    assert result["status"] == "dry_run"
    assert result["would_create"] is True
    assert result["merge_enforcement_verified"] is False
    assert all(method != "POST" for method, _, _ in calls)


def test_apply_requires_exact_repository_confirmation_before_network(monkeypatch):
    def never_call(*_args, **_kwargs):
        raise AssertionError("confirmation must be validated before API access")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", never_call)
    with pytest.raises(ApplyMainRulesetError, match="explicit --confirm-repository"):
        apply_main_ruleset(REPO, "fake-token", candidate(), apply=True, confirm_repository="rumman52/other")


def test_rejects_existing_unverified_main_ruleset_without_overwriting(monkeypatch):
    existing = {
        "id": 55, "name": "organization-wide main policy", "target": "branch",
        "enforcement": "active", "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
    }
    calls = []

    def fake(method, url, token, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/branches/main"):
            return {"name": "main", "protected": False}
        if "/rulesets?" in url:
            return [existing]
        if url.endswith("/rulesets/55"):
            return {**existing, "bypass_actors": [], "rules": []}
        raise AssertionError(f"unexpected API request: {method} {url}")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", fake)
    with pytest.raises(ApplyMainRulesetError, match="refusing to create or replace"):
        apply_main_ruleset(REPO, "fake-token", candidate(), apply=True, confirm_repository=REPO)
    assert all(method != "POST" for method, _, _ in calls)


def test_protected_main_without_verified_ruleset_requires_manual_reconciliation(monkeypatch):
    calls = []

    def fake(method, url, token, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/branches/main"):
            return {"name": "main", "protected": True}
        if "/rulesets?" in url:
            return []
        raise AssertionError(f"unexpected API request: {method} {url}")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", fake)
    with pytest.raises(ApplyMainRulesetError, match="already reports protection"):
        apply_main_ruleset(REPO, "fake-token", candidate(), apply=True, confirm_repository=REPO)
    assert all(method != "POST" for method, _, _ in calls)


def test_existing_verified_ruleset_is_idempotent_and_never_posts(monkeypatch):
    current = detail()
    calls = []

    def fake(method, url, token, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/branches/main"):
            return {"name": "main", "protected": True}
        if "/rulesets?" in url:
            return [current]
        if url.endswith("/rulesets/321"):
            return current
        raise AssertionError(f"unexpected API request: {method} {url}")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", fake)
    result = apply_main_ruleset(REPO, "fake-token", candidate(), apply=True, confirm_repository=REPO)

    assert result["status"] == "already_configured"
    assert result["ruleset_id"] == 321
    assert result["merge_enforcement_verified"] is False
    assert all(method != "POST" for method, _, _ in calls)


def test_apply_posts_once_then_verifies_detail_and_branch(monkeypatch):
    calls = []
    created = detail()

    def fake(method, url, token, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/branches/main"):
            return {"name": "main", "protected": len([x for x in calls if x[0] == "POST"]) == 1}
        if method == "GET" and "/rulesets?" in url:
            return []
        if method == "POST" and url.endswith("/rulesets"):
            assert payload == candidate()
            return {"id": 321, "name": candidate()["name"]}
        if method == "GET" and url.endswith("/rulesets/321"):
            return created
        raise AssertionError(f"unexpected API request: {method} {url}")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", fake)
    result = apply_main_ruleset(REPO, "admin-token", candidate(), apply=True, confirm_repository=REPO)

    assert result["status"] == "configuration_applied_readback_verified"
    assert result["ruleset_id"] == 321
    assert result["configuration_readback_verified"] is True
    assert result["merge_enforcement_verified"] is False
    assert [method for method, _, _ in calls].count("POST") == 1
    assert calls[-1][0] == "GET" and calls[-1][1].endswith("/branches/main")


def test_failed_readback_does_not_report_success_or_attempt_rollback(monkeypatch):
    calls = []
    bad = detail()
    bad["bypass_actors"] = [{"actor_id": 1, "actor_type": "RepositoryRole", "bypass_mode": "always"}]

    def fake(method, url, token, payload=None):
        calls.append((method, url, payload))
        if method == "GET" and url.endswith("/branches/main"):
            return {"name": "main", "protected": len([x for x in calls if x[0] == "POST"]) == 1}
        if method == "GET" and "/rulesets?" in url:
            return []
        if method == "POST":
            return {"id": 321}
        if method == "GET" and url.endswith("/rulesets/321"):
            return bad
        raise AssertionError(f"unexpected API request: {method} {url}")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", fake)
    with pytest.raises(ApplyMainRulesetError, match="321.*read-back verification failed"):
        apply_main_ruleset(REPO, "admin-token", candidate(), apply=True, confirm_repository=REPO)
    assert [method for method, _, _ in calls].count("POST") == 1
    assert not any(method == "DELETE" for method, _, _ in calls)


def test_invalid_candidate_policy_is_rejected_before_network(monkeypatch):
    broken = candidate()
    broken["rules"] = [r for r in broken["rules"] if r.get("type") != "required_status_checks"]

    def never_call(*_args, **_kwargs):
        raise AssertionError("invalid policy must fail before API access")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", never_call)
    with pytest.raises(ApplyMainRulesetError, match="does not satisfy V-01"):
        apply_main_ruleset(REPO, "fake-token", broken, apply=False)


def test_rejects_non_target_repository_and_missing_token(monkeypatch):
    def never_call(*_args, **_kwargs):
        raise AssertionError("invalid input must fail before API access")

    monkeypatch.setattr("scripts.apply_main_ruleset._request_json", never_call)
    with pytest.raises(ApplyMainRulesetError, match="only supports"):
        apply_main_ruleset("owner/another-repo", "fake-token", candidate(), apply=False)
    with pytest.raises(ApplyMainRulesetError, match="missing GitHub token"):
        apply_main_ruleset(REPO, "", candidate(), apply=False)


@contextmanager
def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _Quiet(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def test_ruleset_writer_never_replays_bearer_on_cross_origin_redirect():
    recipient_auth = []

    class Recipient(_Quiet):
        def do_GET(self):
            recipient_auth.append(self.headers.get("Authorization"))
            body = b'{"accepted":true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _serve(Recipient) as recipient:
        class Origin(_Quiet):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", recipient + "/collect")
                self.end_headers()

        with _serve(Origin) as origin:
            with pytest.raises(ApplyMainRulesetError, match="unavailable"):
                _request_json("GET", origin + "/repos/owner/repo", "fake-token")

    assert recipient_auth == []
