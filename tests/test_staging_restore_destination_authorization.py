"""Source-only Day 2 regression: never send owner bearers to an unapproved restored API.

These synthetic authorization records and tokens are NOT live Founder/C consent.
All HTTPS calls here use MockTransport; none contact the hosted service.
"""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone

import httpx
import pytest

from scripts import staging_day2_authorization as authorization
from scripts import staging_restored_api_access as restored

SOURCE = "https://shuddho-api-staging.onrender.com"
TARGET = "https://isolated-restore.example.test"
SHA = "a" * 40
ROLLOUT_SHA = "b" * 64
DB = "c" * 64
STORAGE = "d" * 64
NOW = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _decision() -> dict:
    return {
        "schema_version": 1, "status": "operator_recorded",
        "environment": "staging", "release_id": "day2-synthetic",
        "source_revision": SHA, "rollout_manifest_sha256": ROLLOUT_SHA,
        "provider_policy_sha256": "e" * 64,
        "build_reference": "sha256:staging-build",
        "deployment_reference": "approved-staging-deploy",
        "hosting": {
            "provider": "Render",
            "workspace_reference": "tea-d6ok4okhg0os73erkdv0",
            "api_service_reference": "srv-dav98otg1s2s73cod4gg",
            "worker_service_reference": "shuddho-worker-staging",
            "worker_region": "oregon",
            "worker_plan": "0.5c-512mb",
        },
        "budget": {
            "currency": "USD", "max_spend_minor_units": 2500,
            "maximum_duration_minutes": 180, "max_provider_attempts": 3,
        },
        "isolated_restore": {
            "database_fingerprint": DB,
            "storage_fingerprint": STORAGE,
            "api_origin_sha256": _digest(TARGET),
        },
        "rollback": {
            "owner_reference": "rollback-owner", "procedure_reference": "safe-restore-rollback",
        },
        "approvals": {
            "founder": {
                "decision": "approved", "approved_at": "2026-11-22T10:00:00+00:00",
                "reference": "synthetic-founder-protected-record",
            },
            "operator_c": {
                "decision": "approved", "approved_at": "2026-11-22T10:15:00+00:00",
                "reference": "synthetic-C-protected-record",
            },
        },
        "valid_from": "2026-11-22T11:00:00+00:00",
        "valid_until": "2026-11-22T13:00:00+00:00",
    }


def _attest(decision=None, **kwargs):
    return authorization.preflight_restored_destination(
        _decision() if decision is None else decision,
        source_revision=kwargs.get("source_revision", SHA),
        release_id=kwargs.get("release_id", "day2-synthetic"),
        rollout_manifest_sha256=kwargs.get("rollout_manifest_sha256", ROLLOUT_SHA),
        source_api_origin=kwargs.get("source_api_origin", SOURCE),
        restored_api_origin=kwargs.get("restored_api_origin", TARGET),
        target_database_fingerprint=kwargs.get("target_database_fingerprint", DB),
        target_storage_fingerprint=kwargs.get("target_storage_fingerprint", STORAGE),
        now=kwargs.get("now", NOW),
    )


def test_only_the_exact_recorded_isolated_api_and_two_target_resources_pass_preflight():
    assert _attest() == _digest(TARGET)


@pytest.mark.parametrize(("field", "value"), [
    ("source_revision", "f" * 40),
    ("release_id", "wrong-release"),
    ("rollout_manifest_sha256", "9" * 64),
    ("source_api_origin", "https://wrong-staging.example.test"),
    ("restored_api_origin", "https://unapproved-restore.example.test"),
    ("restored_api_origin", "https://isolated-restore.example.test:444"),
    ("target_database_fingerprint", "4" * 64),
    ("target_storage_fingerprint", "5" * 64),
    ("now", datetime(2026, 11, 22, 13, 0, 1, tzinfo=timezone.utc)),
])
def test_restore_rejects_unapproved_origin_db_bucket_release_or_expired_window(field, value):
    with pytest.raises(authorization.AuthorizationEvidenceFailure):
        _attest(**{field: value})


@pytest.mark.parametrize(("path", "value"), [
    (("schema_version",), True),
    (("status",), "passed"),
    (("environment",), "production"),
    (("source_revision",), "f" * 40),
    (("isolated_restore", "api_origin_sha256"), "0" * 64),
    (("isolated_restore", "database_fingerprint"), "0" * 64),
    (("isolated_restore", "storage_fingerprint"), "0" * 64),
    (("hosting", "worker_plan"), ""),
    (("hosting", "worker_region"), ""),
    (("approvals", "founder", "decision"), "pending"),
    (("approvals", "operator_c", "reference"), "synthetic-founder-protected-record"),
    (("approvals", "founder", "approved_at"), "2026-11-22T11:01:00+00:00"),
    (("valid_until",), "2026-11-22T11:01:00+00:00"),
])
def test_unsafe_or_self_declared_authorization_cannot_unlock_restored_api(path, value):
    decision = copy.deepcopy(_decision())
    leaf = decision
    for key in path[:-1]:
        leaf = leaf[key]
    leaf[path[-1]] = value
    with pytest.raises(authorization.AuthorizationEvidenceFailure):
        _attest(decision)


def test_restored_api_refuses_mismatched_approval_before_sending_either_bearer(monkeypatch):
    monkeypatch.setenv("SHUDDHO_STAGING_ALLOW_RESTORED_API_READBACK", "true")
    monkeypatch.setenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "true")

    def forbid(_request):
        pytest.fail("Owner A or B bearer was sent to an unapproved isolated API")

    with httpx.Client(
        base_url=TARGET, follow_redirects=False, transport=httpx.MockTransport(forbid),
    ) as client:
        with pytest.raises(restored.RestoredAPIReadbackFailure, match="approved"):
            restored.attest_restored_api_access(
                client, "synthetic-A", "synthetic-B",
                source_origin=SOURCE, restored_origin=TARGET,
                approved_restored_origin_sha256="0" * 64,
                expected_owner_id="a" * 64,
                document_id="11111111-1111-4111-8111-111111111111",
                task_id="22222222-2222-4222-8222-222222222222",
                document_sha256="b" * 64,
                document_size=12, source_revision=SHA,
                expected_issuer="https://bsmbvjenpvcyfjzwtuax.supabase.co/auth/v1",
                expected_audience="authenticated",
            )
