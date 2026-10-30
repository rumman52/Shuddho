"""Fail-closed HTTPS destination shape for controlled staging prerequisites."""

import pytest

from scripts import staging_prerequisite_preflight as preflight


@pytest.mark.parametrize("name", ["SHUDDHO_AUTH_ISSUER", "SHUDDHO_COWORKER_S3_ENDPOINT"])
@pytest.mark.parametrize("value", [
    "https://trusted.example.test\n.evil.test/auth/v1",
    "https://trusted.example.test\t.evil.test/storage/v1/s3",
    "https://trusted.example.test\r.evil.test/auth/v1",
    " https://storage.example.test/storage/v1/s3",
    "https://storage.example.test/storage/v1/s3 ",
    "https://localhost/auth/v1",
    "https://127.0.0.1/storage/v1/s3",
    "https://10.0.0.2/auth/v1",
    "https://169.254.169.254/latest/meta-data",
    "https://[::1]/storage/v1/s3",
    "https://auth.internal/auth/v1",
    "https://storage.local/storage/v1/s3",
    "https://singlelabel/auth/v1",
    "https://storage.example.test./storage/v1/s3",
])
def test_controlled_staging_endpoint_rejects_unsafe_destination(name, value):
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight._validate_https_endpoint(value, name)


@pytest.mark.parametrize("name", ["SHUDDHO_AUTH_ISSUER", "SHUDDHO_COWORKER_S3_ENDPOINT"])
@pytest.mark.parametrize("value", [
    "https://bsmbvjenpvcyfjzwtuax.supabase.co/auth/v1",
    "https://bsmbvjenpvcyfjzwtuax.storage.supabase.co/storage/v1/s3",
    "https://storage.example.test/storage/v1/s3",
    "https://api.example.test:443/auth/v1",
])
def test_controlled_staging_endpoint_preserves_public_https_provider_urls(name, value):
    preflight._validate_https_endpoint(value, name)


@pytest.mark.parametrize("name", ["SHUDDHO_AUTH_ISSUER", "SHUDDHO_COWORKER_S3_ENDPOINT"])
@pytest.mark.parametrize("host", [
    "127.1", "127.0.1", "0177.0.0.1", "0x7f.0.0.1", "0x7f.1", "127.0x1",
])
def test_controlled_staging_endpoint_rejects_legacy_ipv4_forms(name, host):
    with pytest.raises(preflight.PreflightFailure, match=name):
        preflight._validate_https_endpoint("https://" + host + "/auth/v1", name)
