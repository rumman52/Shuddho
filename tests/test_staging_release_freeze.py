from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import staging_release_freeze as freeze


def capabilities():
    value = {key: False for key in freeze.RUNTIME_CAPABILITY_KEYS}
    for key in freeze.PA10_REQUIRED_TRUE:
        value[key] = True
    return value


def rollout():
    return {
        "schema_version": 1,
        "release_id": "pa10-stage-20261001-001",
        "environment": "staging",
        "cohort": {
            "reference": "synthetic-accounts-ticket",
            "enforced": True,
            "max_users": 5,
        },
        "action_providers": ["google", "microsoft"],
        "capabilities": capabilities(),
        "rollback": dict(freeze.EXPECTED_ROLLBACK),
        "monitoring": {
            "queue_age": "queue-dashboard",
            "task_success": "task-dashboard",
            "provider_errors": "provider-alert",
            "latency": "latency-dashboard",
            "token_cost": "cost-dashboard",
            "agent_failures": "agent-alert",
        },
        "incident": {
            "oncall_reference": "staging-oncall",
            "change_reference": "change-001",
        },
    }


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


def prepared(tmp_path: Path):
    rollout_path = write_json(tmp_path / "rollout.json", rollout())
    policy_path = write_json(
        tmp_path / "policy.json",
        {"release_id": "pa10-stage-20261001-001", "schema_version": 1},
    )
    return freeze.prepare_state(
        rollout_path=rollout_path,
        provider_policy_path=policy_path,
        expected_source_revision="a" * 40,
        build_reference="registry.example/shuddho@sha256:abc",
        deployment_reference="render:staging-deploy-123",
        synthetic_account_reference="synthetic-cohort-1",
    )


def runtime(state):
    return {
        "schema_version": 1,
        "source_revision": state["expected_source_revision"],
        "environment": state["expected_environment"],
        "capabilities": state["declared_capabilities"],
        "action_providers": state["declared_action_providers"],
        "cohort": {
            "enforced": state["declared_cohort"]["enforced"],
            "configured_members": 2,
            "max_users": state["declared_cohort"]["max_users"],
        },
    }


def test_guard_fails_closed(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_RELEASE_FREEZE", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", raising=False)
    with pytest.raises(freeze.StagingReleaseFreezeError, match="ALLOW_RELEASE_FREEZE"):
        freeze.require_guard()


def test_clean_origin_rejects_non_https_credentials_and_paths():
    assert freeze.clean_origin("https://stage.example.test") == "https://stage.example.test"
    for value in (
        "http://stage.example.test",
        "https://stage.example.test/api",
        "https://user:pass@stage.example.test",
        "https://stage.example.test?x=1",
    ):
        with pytest.raises(freeze.StagingReleaseFreezeError):
            freeze.clean_origin(value)


def test_rollout_requires_full_pa10_scope_and_rejects_production():
    value = rollout()
    freeze.validate_rollout(value)

    value["environment"] = "production"
    with pytest.raises(freeze.StagingReleaseFreezeError, match="rejects production"):
        freeze.validate_rollout(value)

    value = rollout()
    value["capabilities"]["automations"] = False
    with pytest.raises(freeze.StagingReleaseFreezeError, match="missing required enabled"):
        freeze.validate_rollout(value)

    value = rollout()
    value["capabilities"]["code_execution"] = True
    with pytest.raises(freeze.StagingReleaseFreezeError, match="unrelated high-authority"):
        freeze.validate_rollout(value)


def test_rollout_requires_google_and_microsoft_for_full_provider_qualification():
    value = rollout()
    value["action_providers"] = ["google"]
    with pytest.raises(freeze.StagingReleaseFreezeError, match="Google and Microsoft"):
        freeze.validate_rollout(value)


def test_prepare_binds_exact_files_and_release(tmp_path):
    state = prepared(tmp_path)
    assert state["status"] == "prepared"
    assert state["release_id"] == "pa10-stage-20261001-001"
    assert state["expected_source_revision"] == "a" * 40
    assert len(state["rollout_manifest_sha256"]) == 64
    assert len(state["provider_policy_sha256"]) == 64
    assert state["declared_capabilities"]["automations"] is True
    assert state["declared_capabilities"]["code_execution"] is False


def test_prepare_rejects_provider_policy_from_another_release(tmp_path):
    rollout_path = write_json(tmp_path / "rollout.json", rollout())
    policy_path = write_json(
        tmp_path / "policy.json",
        {"release_id": "different-release"},
    )
    with pytest.raises(freeze.StagingReleaseFreezeError, match="does not match"):
        freeze.prepare_state(
            rollout_path=rollout_path,
            provider_policy_path=policy_path,
            expected_source_revision="a" * 40,
            build_reference="build-1",
            deployment_reference="deploy-1",
            synthetic_account_reference="synthetic-1",
        )


def test_verify_freezes_exact_runtime_identity(tmp_path):
    state = prepared(tmp_path)
    evidence = freeze.verify_runtime(state, runtime(state))
    assert evidence["status"] == "frozen"
    assert evidence["release"]["source_revision"] == "a" * 40
    assert evidence["release"]["environment"] == "staging"
    assert evidence["action_providers"] == ["google", "microsoft"]
    assert evidence["cohort"]["configured_members"] == 2
    assert len(evidence["runtime_manifest_sha256"]) == 64


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_revision", "b" * 40, "source revision"),
        ("environment", "other-stage", "environment"),
        ("action_providers", ["google"], "provider set"),
    ],
)
def test_verify_rejects_deployed_identity_drift(tmp_path, field, value, message):
    state = prepared(tmp_path)
    observed = runtime(state)
    observed[field] = value
    with pytest.raises(freeze.StagingReleaseFreezeError, match=message):
        freeze.verify_runtime(state, observed)


def test_verify_rejects_capability_and_cohort_drift(tmp_path):
    state = prepared(tmp_path)
    observed = runtime(state)
    observed["capabilities"] = dict(observed["capabilities"], browser_push=False)
    with pytest.raises(freeze.StagingReleaseFreezeError, match="capability set"):
        freeze.verify_runtime(state, observed)

    observed = runtime(state)
    observed["cohort"]["max_users"] = 25
    with pytest.raises(freeze.StagingReleaseFreezeError, match="cohort controls"):
        freeze.verify_runtime(state, observed)

    observed = runtime(state)
    observed["cohort"]["configured_members"] = 0
    with pytest.raises(freeze.StagingReleaseFreezeError, match="synthetic member"):
        freeze.verify_runtime(state, observed)


@pytest.mark.parametrize("schema", [True, False, 1.0, "1"])
def test_rollout_rejects_non_integer_schema_version(schema):
    candidate = rollout()
    candidate["schema_version"] = schema
    with pytest.raises(freeze.StagingReleaseFreezeError, match="schema_version"):
        freeze.validate_rollout(candidate)


@pytest.mark.parametrize("schema", [True, False, 1.0, "1"])
def test_runtime_rejects_non_integer_schema_version(tmp_path, schema):
    state = prepared(tmp_path)
    observed = runtime(state)
    observed["schema_version"] = schema
    with pytest.raises(freeze.StagingReleaseFreezeError, match="schema_version"):
        freeze.verify_runtime(state, observed)


@pytest.mark.parametrize("environment", ["preview", "development", "production-preview", "test"])
def test_pa10_freeze_rejects_non_staging_environment(environment):
    candidate = rollout()
    candidate["environment"] = environment
    with pytest.raises(freeze.StagingReleaseFreezeError, match="staging environment"):
        freeze.validate_rollout(candidate)


@pytest.mark.parametrize("invalid", [{}, ["google"], 42, None, True])
def test_pa10_freeze_rejects_malformed_provider_entries_without_crashing(invalid):
    candidate = rollout()
    candidate["action_providers"] = ["google", "microsoft", invalid]
    with pytest.raises(freeze.StagingReleaseFreezeError, match="action_providers"):
        freeze.validate_rollout(candidate)


# PA-10 synthetic-cohort and exact runtime type negative controls.
def test_rollout_rejects_unenforced_staging_cohort():
    candidate = rollout()
    candidate["cohort"]["enforced"] = False
    with pytest.raises(freeze.StagingReleaseFreezeError, match="cohort"):
        freeze.validate_rollout(candidate)


@pytest.mark.parametrize(("capability", "spoofed"), [("coworker", 1), ("research", 0)])
def test_runtime_rejects_numeric_capability_spoofing(tmp_path, capability, spoofed):
    state = prepared(tmp_path)
    observed = runtime(state)
    observed["capabilities"] = dict(observed["capabilities"])
    observed["capabilities"][capability] = spoofed
    with pytest.raises(freeze.StagingReleaseFreezeError, match="capability"):
        freeze.verify_runtime(state, observed)


def test_runtime_rejects_boolean_cohort_user_limit(tmp_path):
    candidate = rollout()
    candidate["cohort"]["max_users"] = 1
    path = write_json(tmp_path / "rollout.json", candidate)
    policy_path = write_json(tmp_path / "policy.json", {"release_id": candidate["release_id"]})
    state = freeze.prepare_state(
        rollout_path=path,
        provider_policy_path=policy_path,
        expected_source_revision="a" * 40,
        build_reference="build-1",
        deployment_reference="deploy-1",
        synthetic_account_reference="synthetic-1",
    )
    observed = runtime(state)
    observed["cohort"] = dict(observed["cohort"], max_users=True, configured_members=1)
    with pytest.raises(freeze.StagingReleaseFreezeError, match="cohort"):
        freeze.verify_runtime(state, observed)


@pytest.mark.parametrize("unsafe_origin", [
    "https://localhost",
    "https://localhost:443",
    "https://api.local",
    "https://worker.internal",
    "https://preview.localhost",
    "https://metadata.google.internal",
    "https://api.home.arpa",
    "https://127.0.0.1",
    "https://10.12.0.5",
    "https://169.254.169.254",
    "https://[::1]",
    "https://api",
    "https://stage.example.test:bad",
    "https://stage.example.test:65536",
])
def test_release_verifier_rejects_private_or_malformed_token_destinations(unsafe_origin):
    """An accidental local origin must not receive the staging bearer token."""
    with pytest.raises(freeze.StagingReleaseFreezeError, match="HTTPS origin"):
        freeze.clean_origin(unsafe_origin)


def test_release_verifier_accepts_public_tls_dns_origin():
    assert freeze.clean_origin("https://api-staging.onrender.com") == "https://api-staging.onrender.com"


@pytest.mark.parametrize("unsafe_origin", [
    "https://stage.example.test\n",
    "https://sta\tge.example.test",
    "https://stage.example.test\r",
])
def test_release_verifier_rejects_control_characters_in_origin(unsafe_origin):
    # urlparse strips CR, LF, and TAB, otherwise normalizing attacker-controlled input.
    with pytest.raises(freeze.StagingReleaseFreezeError, match="HTTPS origin"):
        freeze.clean_origin(unsafe_origin)


def test_release_verification_blocks_proxy_and_ca_env(tmp_path, monkeypatch):
    # No external request: exercise the real verify command with a fake transport.
    state = prepared(tmp_path)
    state_path = write_json(tmp_path / "freeze-state.json", state)
    output_path = tmp_path / "evidence.json"
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_RELEASE_FREEZE", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://api-staging.onrender.com")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", "synthetic-test-token")
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted-proxy.invalid:8080")
    monkeypatch.setenv("SSL_CERT_FILE", "/untrusted/ca.pem")
    client_calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return runtime(state)

    class FakeClient:
        def __init__(self, **kwargs):
            client_calls.append(kwargs)
            assert kwargs.get("trust_env") is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, path):
            assert path == "/api/v1/runtime-manifest"
            return FakeResponse()

    monkeypatch.setattr(freeze.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        ["staging_release_freeze", "verify", "--state", str(state_path),
         "--output", str(output_path)],
    )
    freeze.main()
    assert len(client_calls) == 1
    assert json.loads(output_path.read_text())["status"] == "frozen"
