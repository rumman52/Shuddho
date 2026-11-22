"""Day 2 source-only checks for protecting managed owner credentials before HTTP.

Mocked JWT payloads are NOT cryptographic authentication; the real API
must verify the actual JWT signatures. These tests make no hosted requests.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time

import httpx
import pytest

from scripts import staging_api_exercise as exercise
from scripts.staging_prerequisite_preflight import (
    EXPECTED_AUTH_AUDIENCE,
    EXPECTED_AUTH_ISSUER,
)

STAGING_API = "https://shuddho-api-staging.onrender.com"
SUBJECT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _segment(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()


def _token(*, subject=SUBJECT, issuer=EXPECTED_AUTH_ISSUER,
           audience=EXPECTED_AUTH_AUDIENCE, expiry=None,
           anonymous=False, algorithm="RS256") -> str:
    now = int(time.time())
    claims = {
        "iss": issuer, "aud": audience, "exp": expiry if expiry is not None else now + 3600,
        "iat": now, "sub": subject, "role": "authenticated", "is_anonymous": anonymous,
    }
    return _segment({"alg": algorithm, "kid": "test-key"}) + "." + _segment(claims) + ".c2ln"


def _account(subject=SUBJECT) -> str:
    return hashlib.sha256(json.dumps([EXPECTED_AUTH_ISSUER, subject]).encode()).hexdigest()


def test_managed_owner_is_bound_to_approved_origin_and_api_subject(monkeypatch):
    calls = []

    def signed_api_request(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={"account_id": _account(), "workspace_id": "synthetic-workspace"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(exercise.httpx, "get", signed_api_request)
    assert exercise.verified_staging_owner(_token(), origin=STAGING_API) == _account()
    assert len(calls) == 1
    assert calls[0][0] == STAGING_API + "/api/v1/me"
    assert calls[0][1]["follow_redirects"] is False
    assert calls[0][1]["timeout"] == 20
    assert calls[0][1]["headers"]["Authorization"].startswith("Bearer ")


@pytest.mark.parametrize(("token", "origin"), [
    (_token(), "https://other.example.test"),
    (_token(), "https://shuddho-api-staging.onrender.com:444"),
    (_token(), "https://shuddho-api-staging.onrender.com@evil.example.test"),
    (_token(), "http://shuddho-api-staging.onrender.com"),
    (_token(issuer="https://wrong.supabase.co/auth/v1"), STAGING_API),
    (_token(audience="service_role"), STAGING_API),
    (_token(expiry=int(time.time()) + 5), STAGING_API),
    (_token(subject=""), STAGING_API),
    (_token(anonymous=True), STAGING_API),
    (_token(algorithm="none"), STAGING_API),
    ("not-a-jwt", STAGING_API),
])
def test_invalid_owner_or_destination_is_rejected_without_any_network(monkeypatch, token, origin):
    monkeypatch.setattr(
        exercise.httpx, "get",
        lambda *a, **k: pytest.fail("Unverified private bearer reached the network."),
    )
    with pytest.raises(exercise.ExerciseFailure):
        exercise.verified_staging_owner(token, origin=origin)


@pytest.mark.parametrize(("status", "body"), [
    (200, {"account_id": "0" * 64, "workspace_id": "synthetic-workspace"}),
    (200, {"account_id": _account(), "workspace_id": None}),
    (200, {"account_id": _account()}),
    (401, {"error": "not authorized"}),
    (302, {"error": "redirect must never be followed"}),
])
def test_managed_owner_rejects_unbound_or_unauthorized_server_response(
    monkeypatch, status, body,
):
    def signed_api_request(url, **kwargs):
        return httpx.Response(status, json=body, request=httpx.Request("GET", url))
    monkeypatch.setattr(exercise.httpx, "get", signed_api_request)
    with pytest.raises(exercise.ExerciseFailure):
        exercise.verified_staging_owner(_token(), origin=STAGING_API)


def test_managed_owner_sanitizes_transport_errors(monkeypatch):
    def broken_get(url, **kwargs):
        raise httpx.ConnectError("internal-private-token-leak", request=httpx.Request("GET", url))

    monkeypatch.setattr(exercise.httpx, "get", broken_get)
    with pytest.raises(exercise.ExerciseFailure) as error:
        exercise.verified_staging_owner(_token(), origin=STAGING_API)
    assert "internal-private-token-leak" not in str(error.value)


def test_backup_and_temporal_recovery_use_the_same_pinned_owner_lookup(monkeypatch):
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("temporalio")
    from scripts import staging_backup_restore as backup
    from scripts import staging_temporal_recovery as temporal

    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", STAGING_API)
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", _token())
    calls = []

    def verified(token, *, origin):
        calls.append((token, origin))
        return _account()

    monkeypatch.setattr(backup, "verified_staging_owner", verified)
    monkeypatch.setattr(temporal, "verified_staging_owner", verified)
    assert backup.resolve_owner() == _account()
    assert temporal.staging_owner() == _account()
    assert calls == [(_token(), STAGING_API), (_token(), STAGING_API)]


def test_backup_and_recovery_refuse_unverified_owner_before_data_mutation(monkeypatch):
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("temporalio")
    from scripts import staging_backup_restore as backup
    from scripts import staging_temporal_recovery as temporal

    monkeypatch.setenv("SHUDDHO_STAGING_API_BASE_URL", "https://other.example.test")
    monkeypatch.setenv("SHUDDHO_STAGING_TOKEN_A", _token())
    monkeypatch.setattr(
        exercise.httpx, "get",
        lambda *a, **k: pytest.fail("Incorrectly configured recovery sent bearer over HTTP"),
    )
    with pytest.raises(backup.BackupRestoreFailure, match="owner"):
        backup.resolve_owner()
    with pytest.raises(temporal.RecoveryFailure, match="owner"):
        temporal.staging_owner()
