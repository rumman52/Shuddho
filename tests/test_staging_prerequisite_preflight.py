from __future__ import annotations

import pytest

from scripts import staging_prerequisite_preflight as preflight


def valid_env() -> dict[str, str]:
    return {
        "RENDER_API_KEY": "render-secret",
        "SHUDDHO_COWORKER_ENV": "staging",
        "SHUDDHO_COWORKER_DATABASE_URL": (
            "postgresql://shuddho_staging_runtime.bsmbvjenpvcyfjzwtuax:fixture-secret"
            "@aws-0-us-west-1.pooler.supabase.com:5432/postgres?sslmode=verify-full&sslrootcert=infra/supabase-root-2021.pem"
        ),
        "SHUDDHO_AUTH_ISSUER": "https://bsmbvjenpvcyfjzwtuax.supabase.co/auth/v1",
        "SHUDDHO_AUTH_AUDIENCE": "authenticated",
        "SHUDDHO_TEMPORAL_ADDRESS": "example.tmprl.cloud:7233",
        "SHUDDHO_TEMPORAL_NAMESPACE": "shuddho-staging",
        "SHUDDHO_TEMPORAL_API_KEY": "temporal-secret",
        "SHUDDHO_STAGING_S3_ACCESS_KEY_ID": "access-key",
        "SHUDDHO_STAGING_S3_SECRET_ACCESS_KEY": "secret-key",
        "SHUDDHO_TEMPORAL_TLS": "true",
        "SHUDDHO_TEMPORAL_TASK_QUEUE": "shuddho-documents-v1",
        "SHUDDHO_COWORKER_STORAGE": "s3",
        "SHUDDHO_COWORKER_BUCKET": "shuddho-coworker-staging",
        "SHUDDHO_COWORKER_S3_ENDPOINT": "https://bsmbvjenpvcyfjzwtuax.storage.supabase.co/storage/v1/s3",
        "AWS_DEFAULT_REGION": "us-west-1",
    }


def test_validate_passes_without_optional_model_secret():
    result = preflight.validate(valid_env())
    assert result["status"] == "passed"
    assert result["checks"]["DEEPSEEK_API_KEY"] == "not_configured_optional"
    assert result["checks"]["temporal_task_queue"] == "shuddho-documents-v1"
    assert result["checks"]["environment"] == "staging"
    assert result["checks"]["database_url"] == "valid_postgresql_url"
    assert result["checks"]["auth_issuer"] == "pinned_supabase_staging_issuer"
    assert result["checks"]["storage_endpoint"] == "pinned_supabase_staging_s3_endpoint"
    assert result["checks"]["auth_audience"] == "authenticated"


@pytest.mark.parametrize(
    "name",
    [
        "RENDER_API_KEY",
        "SHUDDHO_TEMPORAL_ADDRESS",
        "SHUDDHO_TEMPORAL_NAMESPACE",
        "SHUDDHO_TEMPORAL_API_KEY",
        "SHUDDHO_STAGING_S3_ACCESS_KEY_ID",
        "SHUDDHO_STAGING_S3_SECRET_ACCESS_KEY",
    ],
)
def test_validate_reports_exact_missing_required_secret(name):
    env = valid_env()
    env[name] = ""
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight.validate(env)


@pytest.mark.parametrize(
    "name",
    [
        "SHUDDHO_COWORKER_ENV",
        "SHUDDHO_COWORKER_DATABASE_URL",
        "SHUDDHO_AUTH_ISSUER",
        "SHUDDHO_AUTH_AUDIENCE",
    ],
)
def test_validate_requires_staging_database_and_managed_auth_configuration(name):
    env = valid_env()
    env[name] = ""
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight.validate(env)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SHUDDHO_COWORKER_ENV", "production"),
        ("SHUDDHO_COWORKER_DATABASE_URL", "https://db.example.test/shuddho"),
        ("SHUDDHO_COWORKER_DATABASE_URL", "postgresql://db.example.test/"),
        ("SHUDDHO_COWORKER_DATABASE_URL", "postgresql://db.example.test:70000/shuddho_staging"),
        ("SHUDDHO_AUTH_ISSUER", "http://auth.example.test/auth/v1"),
        ("SHUDDHO_AUTH_ISSUER", "https://user:pass@auth.example.test/auth/v1"),
        ("SHUDDHO_AUTH_ISSUER", "https://auth.example.test/auth/v1?token=x"),
        ("SHUDDHO_AUTH_AUDIENCE", "public"),
    ],
)
def test_validate_rejects_invalid_staging_database_and_auth_configuration(name, value):
    env = valid_env()
    env[name] = value
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight.validate(env)


@pytest.mark.parametrize(
    "value",
    [
        "https://example.tmprl.cloud:7233",
        "example.tmprl.cloud",
        "example.tmprl.cloud:not-a-port",
        "example.tmprl.cloud:0",
        "example.tmprl.cloud:70000",
        "user@example.tmprl.cloud:7233",
        "example.tmprl.cloud:7233/path",
    ],
)
def test_validate_rejects_invalid_temporal_address(value):
    env = valid_env()
    env["SHUDDHO_TEMPORAL_ADDRESS"] = value
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_TEMPORAL_ADDRESS"):
        preflight.validate(env)



@pytest.mark.parametrize(
    "address",
    [
        "localhost:7233",
        "127.0.0.1:7233",
        "192.168.1.4:7233",
        "0x7f.0.0.1:7233",
        "[::1]:7233",
        "temporal.internal:7233",
        "temporal.localhost:7233",
        "temporal.home.arpa:7233",
        "bad..tmprl.cloud:7233",
        "-bad.tmprl.cloud:7233",
        "example.tmprl.cloud:7233 ",
        " example.tmprl.cloud:7233",
    ],
)
def test_validate_rejects_temporal_local_or_non_dns_staging_host(address):
    # This preflight accepts a credential-bearing staging connection only to a
    # public DNS-shaped endpoint. It does not resolve DNS or prove TLS identity.
    env = valid_env()
    env["SHUDDHO_TEMPORAL_ADDRESS"] = address
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_TEMPORAL_ADDRESS"):
        preflight.validate(env)


def test_validate_requires_exact_staging_queue_bucket_and_tls():
    env = valid_env()
    env["SHUDDHO_TEMPORAL_TASK_QUEUE"] = "other"
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_TEMPORAL_TASK_QUEUE"):
        preflight.validate(env)

    env = valid_env()
    env["SHUDDHO_COWORKER_BUCKET"] = "production-bucket"
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_COWORKER_BUCKET"):
        preflight.validate(env)

    env = valid_env()
    env["SHUDDHO_TEMPORAL_TLS"] = "false"
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_TEMPORAL_TLS"):
        preflight.validate(env)


def test_validate_accepts_reviewed_s3_endpoint_path_and_rejects_unsafe_parts():
    env = valid_env()
    env["SHUDDHO_COWORKER_S3_ENDPOINT"] = "https://bsmbvjenpvcyfjzwtuax.storage.supabase.co/storage/v1/s3"
    assert preflight.validate(env)["status"] == "passed"

    env = valid_env()
    env["SHUDDHO_COWORKER_S3_ENDPOINT"] = "http://storage.example.test/storage/v1/s3"
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_COWORKER_S3_ENDPOINT"):
        preflight.validate(env)

    env = valid_env()
    env["SHUDDHO_COWORKER_S3_ENDPOINT"] = "https://user:pass@storage.example.test/storage/v1/s3"
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_COWORKER_S3_ENDPOINT"):
        preflight.validate(env)

    env = valid_env()
    env["SHUDDHO_COWORKER_S3_ENDPOINT"] = "https://storage.example.test/storage/v1/s3?token=x"
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_COWORKER_S3_ENDPOINT"):
        preflight.validate(env)


@pytest.mark.parametrize(
    ("name", "endpoint"),
    [
        ("SHUDDHO_AUTH_ISSUER", "https://auth.example.test/auth/v1"),
        ("SHUDDHO_AUTH_ISSUER", "https://bsmbvjenpvcyfjzwtuax.supabase.co/auth/v1/"),
        ("SHUDDHO_AUTH_ISSUER", "https://different.supabase.co/auth/v1"),
        ("SHUDDHO_COWORKER_S3_ENDPOINT", "https://storage.example.test/storage/v1/s3"),
        ("SHUDDHO_COWORKER_S3_ENDPOINT", "https://different.storage.supabase.co/storage/v1/s3"),
        ("SHUDDHO_COWORKER_S3_ENDPOINT", "https://bsmbvjenpvcyfjzwtuax.storage.supabase.co/storage/v1/s3/"),
    ],
)
def test_preflight_rejects_public_https_endpoints_outside_approved_staging_project(name, endpoint):
    """DNS-shaped public HTTPS alone must not authorize credential destinations."""
    env = valid_env()
    env[name] = endpoint
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight.validate(env)


@pytest.mark.parametrize(
    "name",
    [
        "SHUDDHO_COWORKER_ENV",
        "SHUDDHO_AUTH_AUDIENCE",
        "SHUDDHO_TEMPORAL_NAMESPACE",
        "SHUDDHO_TEMPORAL_TLS",
        "SHUDDHO_TEMPORAL_TASK_QUEUE",
        "SHUDDHO_COWORKER_STORAGE",
        "SHUDDHO_COWORKER_BUCKET",
        "AWS_DEFAULT_REGION",
    ],
)
@pytest.mark.parametrize("padding", [" ", "\t"], ids=["space", "tab"])
def test_preflight_rejects_padding_that_runtime_does_not_normalize(name, padding):
    env = valid_env()
    env[name] = padding + env[name] + padding
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight.validate(env)


@pytest.mark.parametrize("name", ["SHUDDHO_TEMPORAL_NAMESPACE", "AWS_DEFAULT_REGION"])
def test_preflight_rejects_non_whitespace_control_characters_in_runtime_fields(name):
    env = valid_env()
    env[name] += "\x7f"
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight.validate(env)


@pytest.mark.parametrize(
    "port",
    ["７２３３", "9" * 5000],
    ids=["unicode-digits", "overlong"],
)
def test_preflight_temporal_port_must_be_bounded_ascii(port):
    env = valid_env()
    env["SHUDDHO_TEMPORAL_ADDRESS"] = "example.tmprl.cloud:" + port
    with pytest.raises(preflight.PreflightFailure, match="SHUDDHO_TEMPORAL_ADDRESS"):
        preflight.validate(env)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("postgresql://", "POSTGRESQL://"),
        ("postgresql://", "\x01postgresql://"),
        ("fixture-secret", "fixture-secret@extra"),
        ("fixture-secret", "fixture\x7fsecret"),
        ("fixture-secret", "fixture%00secret"),
    ],
    ids=["scheme-case", "leading-control", "ambiguous-userinfo", "raw-control", "decoded-nul"],
)
def test_preflight_rejects_database_urls_not_safe_for_runtime_parser(old, new):
    env = valid_env()
    name = "SHUDDHO_COWORKER_DATABASE_URL"
    env[name] = env[name].replace(old, new, 1)
    with pytest.raises(preflight.PreflightFailure, match=name) as error:
        preflight.validate(env)
    assert env[name] not in str(error.value)
    assert "fixture-secret" not in str(error.value)


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
def test_preflight_preserves_valid_runtime_scheme_and_percent_encoded_password(scheme):
    env = valid_env()
    name = "SHUDDHO_COWORKER_DATABASE_URL"
    env[name] = env[name].replace("postgresql://", scheme + "://", 1).replace(
        "fixture-secret", "fixture%40secret%3A%2F"
    )
    env["SHUDDHO_TEMPORAL_TLS"] = "TRUE"
    assert preflight.validate(env)["status"] == "passed"
