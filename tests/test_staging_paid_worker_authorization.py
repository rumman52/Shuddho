"""Part 02 D02.T05/G05 — fail closed before *paid* Render worker creation."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/provision-pa10-staging-worker.yml"
NOW = datetime(2026, 11, 21, 14, 30, tzinfo=timezone.utc)
SHA = "a" * 40
WORKSPACE = "tea-d6ok4okhg0os73erkdv0"
API_ID = "srv-dav98otg1s2s73cod4gg"
WORKER = "shuddho-worker-staging"


def example_private_decision() -> dict:
    """Untrusted test data, not authorization to operate anything."""
    return {
        "schema_version": 1, "status": "operator_recorded", "environment": "staging",
        "release_id": "approved-day2-release-001", "source_revision": SHA,
        "rollout_manifest_sha256": "a" * 64,
        "provider_policy_sha256": "b" * 64,
        "build_reference": "sha256:immutable-reviewed-worker-build",
        "deployment_reference": "approved-staging-change-123",
        "hosting": {
            "provider": "Render",
            "workspace_reference": WORKSPACE,
            "api_service_reference": API_ID,
            "worker_service_reference": WORKER,
            "worker_region": "oregon",
            "worker_plan": "0.5c-512mb",
        },
        "budget": {
            "currency": "USD", "max_spend_minor_units": 2500,
            "maximum_duration_minutes": 180, "max_provider_attempts": 3,
        },
        "isolated_restore": {
            "database_fingerprint": "c" * 64,
            "storage_fingerprint": "d" * 64,
            "api_origin_sha256": "e" * 64,
        },
        "rollback": {
            "owner_reference": "approved-staging-rollback-operator",
            "procedure_reference": "reviewed-restore-rollback-runbook",
        },
        "approvals": {
            "founder": {
                "decision": "approved",
                "approved_at": "2026-11-21T13:00:00+00:00",
                "reference": "protected-founder-record-100",
            },
            "operator_c": {
                "decision": "approved",
                "approved_at": "2026-11-21T13:10:00+00:00",
                "reference": "protected-c-record-200",
            },
        },
        "valid_from": "2026-11-21T14:00:00+00:00",
        "valid_until": "2026-11-21T16:00:00+00:00",
    }


def verify(decision: object, *, at: datetime = NOW):
    from scripts.staging_paid_worker_authorization import verify_paid_worker_authorization
    return verify_paid_worker_authorization(
        decision,
        source_revision=SHA,
        workspace_id=WORKSPACE,
        api_service_id=API_ID,
        worker_name=WORKER,
        worker_region="oregon",
        worker_plan="0.5c-512mb",
        checked_at=at,
    )


def test_paid_worker_workflow_requires_private_decision_before_render_mutation():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    mutation = workflow.index("      - name: Create or repair shuddho-worker-staging")
    prefix = workflow[:mutation]
    assert "PA10_DAY2_FOUNDER_C_AUTHORIZATION_B64" in prefix
    assert "python3 -m scripts.staging_paid_worker_authorization" in prefix
    assert "umask 077" in prefix
    assert "chmod 600" in prefix
    assert "trap" in prefix
    assert "env:\n          AUTHORIZATION_B64: ${{ secrets.PA10_DAY2_FOUNDER_C_AUTHORIZATION_B64 }}" in prefix
    assert "      - name: Revalidate protected main immediately before paid worker mutation" in prefix
    # The *authorized* region and paid plan must equal the Render CLI flags.
    assert '--worker-region "oregon"' in prefix
    assert '--worker-plan "0.5c-512mb"' in prefix
    assert "--region oregon" in workflow[mutation:]
    assert "--plan 0.5c-512mb" in workflow[mutation:]
    assert workflow.count("--plan 0.5c-512mb") == 2


def test_worker_preprovision_decision_is_scoped_and_not_self_approving():
    proof = verify(example_private_decision())
    assert proof["status"] == "operator_recorded_requires_independent_review"
    assert proof["independent_confirmation_required"] is True
    assert len(proof["receipt_sha256"]) == 64
    for private_text in ("protected-founder-record-100", "protected-c-record-200"):
        assert private_text not in repr(proof)


@pytest.mark.parametrize("field_path,bad", [
    (("status",), "passed"),
    (("schema_version",), True),
    (("environment",), "production"),
    (("source_revision",), "b" * 40),
    (("rollout_manifest_sha256",), "not-a-digest"),
    (("provider_policy_sha256",), None),
    (("build_reference",), ""),
    (("deployment_reference",), ""),
    (("hosting", "provider"), "Unreviewed"),
    (("hosting", "workspace_reference"), "other-team"),
    (("hosting", "api_service_reference"), "srv-wrong-api"),
    (("hosting", "worker_service_reference"), "shuddho-api"),
    (("hosting", "worker_region"), "frankfurt"),
    (("hosting", "worker_region"), ""),
    (("hosting", "worker_plan"), "1c-2gb"),
    (("hosting", "worker_plan"), "free"),
    (("budget", "currency"), "US"),
    (("budget", "max_spend_minor_units"), 0),
    (("budget", "max_spend_minor_units"), True),
    (("budget", "maximum_duration_minutes"), 100),
    (("budget", "max_provider_attempts"), 0),
    (("isolated_restore", "database_fingerprint"), "malformed"),
    (("isolated_restore", "storage_fingerprint"), ""),
    (("isolated_restore", "api_origin_sha256"), "not-a-digest"),
    (("rollback", "owner_reference"), ""),
    (("rollback", "procedure_reference"), ""),
    (("approvals", "founder", "decision"), "pending"),
    (("approvals", "founder", "reference"), "protected-c-record-200"),
    (("approvals", "founder", "approved_at"), "2026-11-21T14:01:00+00:00"),
    (("approvals", "operator_c", "approved_at"), "2026-11-21T16:01:00+00:00"),
    (("valid_from",), "2026-11-21T13:00:00+00:00"),
    (("valid_until",), "2026-11-21T14:29:59+00:00"),
])
def test_invalid_or_self_reported_paid_worker_approval_never_qualifies(field_path, bad):
    from scripts.staging_day2_authorization import AuthorizationEvidenceFailure
    receipt = example_private_decision()
    obj = receipt
    for key in field_path[:-1]:
        obj = obj[key]
    obj[field_path[-1]] = bad
    with pytest.raises(AuthorizationEvidenceFailure, match="authorization"):
        verify(receipt)


def test_missing_paid_worker_approval_rejected():
    from scripts.staging_day2_authorization import AuthorizationEvidenceFailure
    with pytest.raises(AuthorizationEvidenceFailure, match="authorization"):
        verify(None)


def test_approval_window_rejects_live_clock_after_duration():
    from scripts.staging_day2_authorization import AuthorizationEvidenceFailure
    receipt = example_private_decision()
    with pytest.raises(AuthorizationEvidenceFailure, match="authorization"):
        verify(receipt, at=datetime(2026, 11, 21, 16, 0, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize("field", ["worker_region", "worker_plan"])
def test_paid_worker_authorization_rejects_unreviewed_missing_plan_or_region(field):
    from scripts.staging_day2_authorization import AuthorizationEvidenceFailure
    record = example_private_decision()
    record["hosting"].pop(field)
    with pytest.raises(AuthorizationEvidenceFailure, match="authorization"):
        verify(record)


@pytest.mark.parametrize("worker_region,worker_plan", [
    ("frankfurt", "0.5c-512mb"),
    ("oregon", "1c-2gb"),
    ("oregon", "free"),
])
def test_paid_worker_authorization_rejects_actual_provisioning_flags_not_approved(worker_region, worker_plan):
    from scripts.staging_day2_authorization import AuthorizationEvidenceFailure
    from scripts.staging_paid_worker_authorization import verify_paid_worker_authorization

    with pytest.raises(AuthorizationEvidenceFailure, match="authorization"):
        verify_paid_worker_authorization(
            example_private_decision(),
            source_revision=SHA, workspace_id=WORKSPACE,
            api_service_id=API_ID, worker_name=WORKER,
            worker_region=worker_region, worker_plan=worker_plan,
            checked_at=NOW,
        )
