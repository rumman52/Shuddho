from __future__ import annotations

import ast
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
        "schema_version": 2,
        "source_revision": state["expected_source_revision"],
        "environment": state["expected_environment"],
        "capabilities": {
            **state["declared_capabilities"],
            "grounded_conversation_replies": state["declared_capabilities"]["conversation_replies"],
        },
        "reviewed_skills": {"research": {"state": "unselected"}},
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
    assert len(evidence["reviewed_skills_sha256"]) == 64


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


def test_verify_rejects_legacy_unenforced_prepared_cohort(tmp_path):
    state = prepared(tmp_path)
    # Older prepare commands admitted this state; equality with the runtime
    # must not turn an unenforced, empty cohort into frozen release evidence.
    state["declared_cohort"]["enforced"] = False
    observed = runtime(state)
    observed["cohort"]["configured_members"] = 0
    with pytest.raises(freeze.StagingReleaseFreezeError, match="cohort"):
        freeze.verify_runtime(state, observed)


@pytest.mark.parametrize("limit", [True, 1.0, 0, 26])
def test_verify_rejects_invalid_prepared_cohort_limit(tmp_path, limit):
    state = prepared(tmp_path)
    state["declared_cohort"]["max_users"] = limit
    observed = runtime(state)
    observed["cohort"].update(max_users=int(limit), configured_members=1)
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


@pytest.mark.parametrize("host", [
    "127.1", "127.0.1", "0177.0.0.1", "0x7f.0.0.1", "0x7f.1", "127.0x1",
])
def test_release_verifier_rejects_legacy_ipv4_forms(host):
    with pytest.raises(freeze.StagingReleaseFreezeError, match="HTTPS origin"):
        freeze.clean_origin("https://" + host)


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

    class FakeClient:
        def __init__(self, **kwargs):
            client_calls.append(kwargs)
            assert kwargs.get("trust_env") is False
            assert kwargs["headers"]["Accept-Encoding"] == "identity"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, path):
            from contextlib import nullcontext

            assert method == "GET"
            assert path == "/api/v1/runtime-manifest"
            return nullcontext(freeze.httpx.Response(200, json=runtime(state)))

    monkeypatch.setattr(freeze.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        ["staging_release_freeze", "verify", "--state", str(state_path),
         "--output", str(output_path)],
    )
    freeze.main()
    assert len(client_calls) == 1
    assert json.loads(output_path.read_text())["status"] == "frozen"

def test_runtime_v1_cannot_be_frozen_as_current_api(tmp_path):
    state = prepared(tmp_path)
    observed = runtime(state)
    observed["schema_version"] = 1
    with pytest.raises(freeze.StagingReleaseFreezeError, match="schema_version"):
        freeze.verify_runtime(state, observed)


@pytest.mark.parametrize("capability", [
    "conversations", "projects", "fly_github", "conversation_replies",
    "agent_browser_read", "reviewed_research",
])
def test_new_runtime_flags_are_declared_and_fail_closed(tmp_path, capability):
    candidate = rollout()
    candidate["capabilities"][capability] = True
    with pytest.raises(freeze.StagingReleaseFreezeError, match="unrelated high-authority"):
        freeze.validate_rollout(candidate)
    state = prepared(tmp_path)
    observed = runtime(state)
    observed["capabilities"] = dict(observed["capabilities"], **{capability: True})
    with pytest.raises(freeze.StagingReleaseFreezeError, match="capability set"):
        freeze.verify_runtime(state, observed)


def test_runtime_v2_rejects_missing_reviewed_skills(tmp_path):
    state = prepared(tmp_path)
    observed = runtime(state)
    del observed["reviewed_skills"]
    with pytest.raises(freeze.StagingReleaseFreezeError, match="reviewed_skills"):
        freeze.verify_runtime(state, observed)


def test_api_manifest_source_exact_43_plus_one_derived_ui_field():
    # Parse the actual backend handler, not a separate handwritten mock.
    api_path = Path(__file__).resolve().parents[1] / "services/coworker/api.py"
    module = ast.parse(api_path.read_text(encoding="utf-8"))
    handler = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "runtime_manifest"
    )
    assignment = next(
        node for node in handler.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "capabilities"
                for target in node.targets)
    )
    manifest = assignment.value
    assert isinstance(manifest, ast.Dict)
    assert all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in manifest.keys)
    entries = {key.value: value for key, value in zip(manifest.keys, manifest.values)}
    assert len(entries) == len(manifest.keys)
    assert len(freeze.RUNTIME_CAPABILITY_KEYS) == 43
    assert len(freeze.API_RUNTIME_CAPABILITY_KEYS) == 44
    assert set(entries) == freeze.API_RUNTIME_CAPABILITY_KEYS
    # The derived indicator cannot independently widen the chat capability.
    assert ast.dump(entries["grounded_conversation_replies"]) == ast.dump(
        entries["conversation_replies"]
    )


def test_derived_field_must_equal_canonical_chat_flag_even_when_enabled():
    declared = capabilities()
    declared["conversation_replies"] = True
    actual = {**declared, "grounded_conversation_replies": True}
    assert freeze.api_runtime_capabilities_match_rollout(actual, declared)
    actual["grounded_conversation_replies"] = False
    assert not freeze.api_runtime_capabilities_match_rollout(actual, declared)


@pytest.mark.parametrize("mutate", [
    lambda actual: actual.pop("grounded_conversation_replies"),
    lambda actual: actual.update(grounded_conversation_replies=True),
    lambda actual: actual.update(grounded_conversation_replies=0),
    lambda actual: actual.update(extra_disabled=False),
    lambda actual: actual.pop("memory"),
    lambda actual: actual.update(memory=0),
])
def test_release_freeze_rejects_derived_drift_and_unknown_flags(tmp_path, mutate):
    state = prepared(tmp_path)
    observed = runtime(state)
    mutate(observed["capabilities"])
    with pytest.raises(freeze.StagingReleaseFreezeError, match="capability set"):
        freeze.verify_runtime(state, observed)


def test_rollout_and_worker_do_not_gain_derived_authority():
    declared = capabilities()
    assert set(declared) == freeze.RUNTIME_CAPABILITY_KEYS
    declared["grounded_conversation_replies"] = False
    assert not freeze.api_runtime_capabilities_match_rollout(declared, declared)
    value = rollout()
    value["capabilities"]["grounded_conversation_replies"] = False
    with pytest.raises(freeze.StagingReleaseFreezeError, match="capabilities"):
        freeze.validate_rollout(value)


@pytest.mark.parametrize("raw", [
    b'{"environment":"production","environment":"staging"}',
    b'{"nested":{"max_users":100,"max_users":5}}',
    b'{"number":NaN}',
    b'{"number":Infinity}',
    b'{"number":-Infinity}',
    b'{"number":1e999}',
])
def test_freeze_operator_json_rejects_ambiguous_values(tmp_path, raw):
    path = tmp_path / "receipt.json"
    path.write_bytes(raw)
    with pytest.raises(freeze.StagingReleaseFreezeError):
        freeze.load_json(path, "operator receipt")


def test_freeze_operator_json_rejects_symlink(tmp_path):
    target = write_json(tmp_path / "target.json", {"release_id": "synthetic"})
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(freeze.StagingReleaseFreezeError):
        freeze.load_json(link, "operator receipt")


def test_freeze_operator_json_rejects_oversized_input(tmp_path):
    path = tmp_path / "oversized.json"
    path.write_bytes(b'{"padding":"' + b"x" * (1024 * 1024) + b'"}')
    with pytest.raises(freeze.StagingReleaseFreezeError):
        freeze.load_json(path, "operator receipt")


def test_freeze_binds_validated_bytes_not_reopened_paths(tmp_path, monkeypatch):
    import hashlib

    candidate = rollout()
    rollout_path = write_json(tmp_path / "rollout.json", candidate)
    policy_path = write_json(tmp_path / "policy.json", {"release_id": candidate["release_id"]})
    original_rollout_hash = hashlib.sha256(rollout_path.read_bytes()).hexdigest()
    original_policy_hash = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    real_validate = freeze.validate_provider_policy

    def replace_paths_after_validation(policy, release_id):
        real_validate(policy, release_id)
        replacement = write_json(tmp_path / "new-rollout.json", {"environment": "production"})
        replacement.replace(rollout_path)
        replacement = write_json(tmp_path / "new-policy.json", {"release_id": "other"})
        replacement.replace(policy_path)

    monkeypatch.setattr(freeze, "validate_provider_policy", replace_paths_after_validation)
    state = freeze.prepare_state(
        rollout_path=rollout_path,
        provider_policy_path=policy_path,
        expected_source_revision="a" * 40,
        build_reference="build-1",
        deployment_reference="deploy-1",
        synthetic_account_reference="synthetic-1",
    )
    assert state["rollout_manifest_sha256"] == original_rollout_hash
    assert state["provider_policy_sha256"] == original_policy_hash
    assert state["expected_environment"] == "staging"


def test_freeze_prepare_publishes_private_receipt_without_overwrite(tmp_path, monkeypatch):
    import stat

    candidate = rollout()
    rollout_path = write_json(tmp_path / "rollout.json", candidate)
    policy_path = write_json(tmp_path / "policy.json", {"release_id": candidate["release_id"]})
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_RELEASE_FREEZE", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")
    monkeypatch.setattr("sys.argv", [
        "staging_release_freeze", "prepare",
        "--rollout", str(rollout_path),
        "--provider-policy-plan", str(policy_path),
        "--expected-source-revision", "a" * 40,
        "--build-reference", "build-1",
        "--deployment-reference", "deploy-1",
        "--synthetic-account-reference", "synthetic-1",
        "--state", str(state_path),
    ])
    freeze.main()
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    original = state_path.read_bytes()
    with pytest.raises(SystemExit) as exc:
        freeze.main()
    assert exc.value.code == 1
    assert state_path.read_bytes() == original


@pytest.mark.parametrize("raw", [
    b'{"environment":"production","environment":"staging"}',
    b'{"capabilities":{"actions":true,"actions":false}}',
    b'{"reviewed_skills":{"n":NaN}}',
    b'{"reviewed_skills":{"n":Infinity}}',
    b'{"reviewed_skills":{"n":-Infinity}}',
    b'{"reviewed_skills":{"n":1e999}}',
    b'{"padding":"' + b'x' * 1_048_576 + b'"}',
    '{"environment":"staging"}'.encode('utf-16'),
], ids=["duplicate-root", "duplicate-nested", "nan", "infinity", "negative-infinity",
        "overflow", "oversized", "utf16"])
def test_runtime_http_json_rejects_ambiguous_or_oversized_bytes(raw):
    with pytest.raises(freeze.StagingReleaseFreezeError):
        freeze.json_object(freeze.httpx.Response(200, content=raw), "runtime manifest")


@pytest.mark.parametrize("status,raw", [(403,b'{}'),(200,b'[]'),(200,b'{'),(200,b'\xff')])
def test_runtime_http_json_preserves_existing_negative_controls(status,raw):
    with pytest.raises(freeze.StagingReleaseFreezeError):
        freeze.json_object(freeze.httpx.Response(status, content=raw), "runtime manifest")


def test_runtime_http_json_accepts_valid_utf8_object():
    expected = {"environment": "staging", "reviewed_skills": {"name": "বাংলা", "n": 1.5}}
    assert freeze.json_object(freeze.httpx.Response(200, json=expected), "runtime manifest") == expected


def test_runtime_http_json_rejects_unexpected_content_encoding():
    response = freeze.httpx.Response(200, content=b'{}')
    response.headers['content-encoding'] = 'gzip'
    with pytest.raises(freeze.StagingReleaseFreezeError):
        freeze.json_object(response, "runtime manifest")


def test_runtime_http_stream_stops_at_bound_and_closes_response():
    class OversizedStream(freeze.httpx.SyncByteStream):
        chunks = 0
        closed = False

        def __iter__(self):
            for _ in range(100):
                self.chunks += 1
                yield b'x' * 65536

        def close(self):
            self.closed = True

    stream = OversizedStream()
    transport = freeze.httpx.MockTransport(
        lambda _: freeze.httpx.Response(200, stream=stream)
    )
    with freeze.httpx.Client(transport=transport) as client:
        with pytest.raises(freeze.StagingReleaseFreezeError, match="byte bound"):
            with client.stream("GET", "https://stage.example.test/runtime") as response:
                freeze.json_object(response, "runtime manifest")
    assert stream.chunks == 17
    assert stream.closed
