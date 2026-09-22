from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import httpx
import pytest

from scripts.microsoft_rollout_activation import (
    MicrosoftRolloutActivationError,
    fetch_frontend_manifest,
    require_backend_flags,
    validate_deployment,
    validate_frontend_manifest,
    validate_operator_status,
    validate_staging,
)


NOW = datetime(2026, 9, 22, 17, 0, tzinfo=timezone.utc)


def staging(verified_at=None):
    return {
        "microsoft_actions": {
            "status": "passed",
            "evidence": "live Microsoft actions passed",
            "verified_at": (
                verified_at
                or (NOW - timedelta(minutes=20)).isoformat()
            ),
        }
    }


def test_staging_evidence_must_be_passed_fresh_and_timestamped():
    verified = validate_staging(
        staging(),
        now=NOW,
        max_age_minutes=60,
    )
    assert verified == NOW - timedelta(minutes=20)

    stale = staging(
        (NOW - timedelta(hours=2)).isoformat()
    )
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="stale",
    ):
        validate_staging(
            stale,
            now=NOW,
            max_age_minutes=60,
        )

    missing = staging()
    del missing["microsoft_actions"]["verified_at"]
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="verified_at",
    ):
        validate_staging(
            missing,
            now=NOW,
            max_age_minutes=60,
        )


def test_deployment_binds_exact_staging_evidence(tmp_path):
    path = tmp_path / "staging.json"
    path.write_text(
        json.dumps(staging()),
        encoding="utf-8",
    )
    from scripts.microsoft_rollout_activation import sha256_file

    deployment = {
        "release_id": "coworker-microsoft-rollout-001",
        "change_reference": "change-1",
        "deployed_at": (
            NOW - timedelta(minutes=10)
        ).isoformat(),
        "frontend_base_url": "https://staging.example.com",
        "frontend_source_revision": "abcdef1234567",
        "staging_evidence_sha256": sha256_file(path),
    }
    result = validate_deployment(
        deployment,
        path,
        not_before=NOW - timedelta(minutes=20),
    )
    assert result == NOW - timedelta(minutes=10)

    deployment["staging_evidence_sha256"] = "0" * 64
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="exact Microsoft staging evidence",
    ):
        validate_deployment(
            deployment,
            path,
            not_before=NOW - timedelta(minutes=20),
        )


def test_backend_requires_both_action_flags():
    require_backend_flags(
        SimpleNamespace(
            actions_enabled=True,
            microsoft_actions_enabled=True,
        )
    )
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="SHUDDHO_ACTIONS_ENABLED",
    ):
        require_backend_flags(
            SimpleNamespace(
                actions_enabled=False,
                microsoft_actions_enabled=True,
            )
        )
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="SHUDDHO_MICROSOFT_ACTIONS_ENABLED",
    ):
        require_backend_flags(
            SimpleNamespace(
                actions_enabled=True,
                microsoft_actions_enabled=False,
            )
        )


def test_frontend_manifest_requires_exact_revision_and_enabled_ui():
    value = {
        "schema_version": 1,
        "app": "shuddho-web-editor",
        "source_revision": "abcdef1234567",
        "coworker_enabled": True,
        "microsoft_actions_enabled": True,
    }
    validate_frontend_manifest(
        value,
        expected_revision="abcdef1234567",
    )

    changed = dict(value)
    changed["source_revision"] = "deadbeef12345"
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="revision",
    ):
        validate_frontend_manifest(
            changed,
            expected_revision="abcdef1234567",
        )

    changed = dict(value)
    changed["microsoft_actions_enabled"] = False
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="Microsoft action UI is disabled",
    ):
        validate_frontend_manifest(
            changed,
            expected_revision="abcdef1234567",
        )


def test_frontend_manifest_fetch_is_https_exact_json_and_no_redirect():
    def transport(request):
        assert (
            str(request.url)
            == "https://staging.example.com/shuddho-rollout-manifest.json"
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "schema_version": 1,
                "app": "shuddho-web-editor",
                "source_revision": "abcdef1234567",
                "coworker_enabled": True,
                "microsoft_actions_enabled": True,
            },
        )

    value = fetch_frontend_manifest(
        "https://staging.example.com",
        transport=httpx.MockTransport(transport),
    )
    assert value["microsoft_actions_enabled"] is True


def test_post_deploy_operator_status_is_required():
    deployment_time = NOW - timedelta(minutes=10)
    status = {
        "release_id": "coworker-microsoft-rollout-001",
        "decision": "CONTINUE_COHORT",
        "generated_at": (
            NOW - timedelta(minutes=5)
        ).isoformat(),
        "breaches": [],
    }
    validate_operator_status(
        status,
        "coworker-microsoft-rollout-001",
        not_before=deployment_time,
        now=NOW,
        freshness_minutes=30,
    )
    status["decision"] = "STOP_ROLLOUT"
    with pytest.raises(
        MicrosoftRolloutActivationError,
        match="CONTINUE_COHORT",
    ):
        validate_operator_status(
            status,
            "coworker-microsoft-rollout-001",
            not_before=deployment_time,
            now=NOW,
            freshness_minutes=30,
        )
