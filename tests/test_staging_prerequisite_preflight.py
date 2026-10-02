from __future__ import annotations

import pytest

from scripts import staging_prerequisite_preflight as preflight


def valid_env() -> dict[str, str]:
    return {
        "RENDER_API_KEY": "render-secret",
        "SHUDDHO_TEMPORAL_ADDRESS": "example.tmprl.cloud:7233",
        "SHUDDHO_TEMPORAL_NAMESPACE": "shuddho-staging",
        "SHUDDHO_TEMPORAL_API_KEY": "temporal-secret",
        "SHUDDHO_STAGING_S3_ACCESS_KEY_ID": "access-key",
        "SHUDDHO_STAGING_S3_SECRET_ACCESS_KEY": "secret-key",
        "SHUDDHO_TEMPORAL_TLS": "true",
        "SHUDDHO_TEMPORAL_TASK_QUEUE": "shuddho-documents-v1",
        "SHUDDHO_COWORKER_STORAGE": "s3",
        "SHUDDHO_COWORKER_BUCKET": "shuddho-coworker-staging",
        "SHUDDHO_COWORKER_S3_ENDPOINT": "https://storage.example.test",
        "AWS_DEFAULT_REGION": "us-west-1",
    }


def test_validate_passes_without_optional_model_secret():
    result = preflight.validate(valid_env())
    assert result["status"] == "passed"
    assert result["checks"]["DEEPSEEK_API_KEY"] == "not_configured_optional"
    assert result["checks"]["temporal_task_queue"] == "shuddho-documents-v1"


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
    env["SHUDDHO_COWORKER_S3_ENDPOINT"] = "https://storage.example.test/storage/v1/s3"
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
