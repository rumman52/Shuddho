"""Require an operator-recorded Founder+C decision before a *paid* staging worker.

This checks a protected record's format, scope, cost and active time window.
It does NOT authenticate human consent or attest provider billing; C/D must
verify the original independent decision records out of band. The source
gate rejects missing evidence before any Render service create/update.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.staging_day2_authorization import (
    AuthorizationEvidenceFailure,
    _ROOT_FIELDS,
    _bounded_int,
    _digest,
    _object,
    _reference,
    _time,
    read_private_authorization,
)


_REVISION = re.compile(r"[a-f0-9]{40}\Z")


def verify_paid_worker_authorization(
    authorization: object,
    *,
    source_revision: str,
    workspace_id: str,
    api_service_id: str,
    worker_name: str,
    checked_at: datetime,
) -> dict:
    """Reconcile proposed *paid* worker mutation with a dated private decision.

    Bind to the exact immutable dispatch commit and the intended Rumman
    workspace, live staging API service and dedicated worker *name*. Because
    a new Render worker has no ID yet, reviewer C/D must inspect the actual
    ID, service, plan, billing and account bindings after provisioning.
    """
    receipt = _object(authorization, _ROOT_FIELDS, "paid-worker receipt")
    if (
        type(receipt.get("schema_version")) is not int
        or receipt["schema_version"] != 1
        or receipt.get("status") != "operator_recorded"
        or receipt.get("environment") != "staging"
    ):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization needs a schema-v1, staging-only operator record, not an asserted PASS."
        )
    if (
        not isinstance(source_revision, str)
        or _REVISION.fullmatch(source_revision) is None
        or receipt.get("source_revision") != source_revision
    ):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization source revision differs from the exact staging workflow commit."
        )
    _reference(receipt.get("release_id"), "release_id")
    for field in ("rollout_manifest_sha256", "provider_policy_sha256"):
        _digest(receipt.get(field), field)
    for field in ("build_reference", "deployment_reference"):
        _reference(receipt.get(field), field)

    hosting = _object(receipt.get("hosting"), {
        "provider", "workspace_reference", "api_service_reference",
        "worker_service_reference",
    }, "hosting")
    for field in hosting:
        _reference(hosting[field], "hosting." + field)
    if (
        hosting["provider"] != "Render"
        or hosting["workspace_reference"] != workspace_id
        or hosting["api_service_reference"] != api_service_id
        or hosting["worker_service_reference"] != worker_name
        or worker_name == api_service_id
        or "production" in worker_name.lower()
    ):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization is not scoped to the reviewed Rumman staging API and paid worker."
        )

    budget = _object(receipt.get("budget"), {
        "currency", "max_spend_minor_units", "maximum_duration_minutes",
        "max_provider_attempts",
    }, "budget")
    if budget["currency"] != "USD":
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization paid Render worker budget must be explicitly denominated in USD."
        )
    max_spend = _bounded_int(
        budget["max_spend_minor_units"], "budget.max_spend_minor_units", 1_000_000_000,
    )
    max_minutes = _bounded_int(
        budget["maximum_duration_minutes"], "budget.maximum_duration_minutes", 10_080,
    )
    max_calls = _bounded_int(
        budget["max_provider_attempts"], "budget.max_provider_attempts", 100_000,
    )

    restore = _object(receipt.get("isolated_restore"), {
        "database_fingerprint", "storage_fingerprint", "api_origin_sha256",
    }, "isolated_restore")
    for field in restore:
        _digest(restore[field], "isolated_restore." + field)
    if len(set(restore.values())) != len(restore):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization isolated restore target fingerprints must be distinct."
        )

    rollback = _object(receipt.get("rollback"), {
        "owner_reference", "procedure_reference",
    }, "rollback")
    for field in rollback:
        _reference(rollback[field], "rollback." + field)

    approvals = _object(
        receipt.get("approvals"), {"founder", "operator_c"}, "approvals",
    )
    decision_times: list[datetime] = []
    decision_refs: list[str] = []
    for role in ("founder", "operator_c"):
        proof = _object(
            approvals.get(role), {"decision", "approved_at", "reference"},
            "approvals." + role,
        )
        if proof["decision"] != "approved":
            raise AuthorizationEvidenceFailure(
                "Day 2 authorization requires separate affirmative Founder and C decisions."
            )
        decision_times.append(
            _time(proof["approved_at"], "approvals." + role + ".approved_at"),
        )
        decision_refs.append(
            _reference(proof["reference"], "approvals." + role + ".reference"),
        )
    if decision_refs[0] == decision_refs[1]:
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization needs distinct original Founder/C decision references."
        )

    start = _time(receipt.get("valid_from"), "valid_from")
    end = _time(receipt.get("valid_until"), "valid_until")
    if (
        not isinstance(checked_at, datetime)
        or checked_at.tzinfo is None
        or checked_at.utcoffset() is None
    ):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization requires the operator's current timezone-aware time."
        )
    instant = checked_at.astimezone(timezone.utc)
    if (
        not all(decided <= start for decided in decision_times)
        or not start <= instant <= end
        or not 0 < (end - start).total_seconds() <= max_minutes * 60
    ):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization decision chronology, spending duration or live validity window is invalid."
        )

    # Hashed, nonsecret structural receipt only; never echo the source refs,
    # decision contents, protected path, credentials, or human identities.
    canonical = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return {
        "status": "operator_recorded_requires_independent_review",
        "receipt_sha256": hashlib.sha256(canonical).hexdigest(),
        "source_revision": source_revision,
        "independent_confirmation_required": True,
        "paid_worker_scope_checked": True,
        "approved_cost_ceiling_minor_units": max_spend,
        "approved_duration_ceiling_minutes": max_minutes,
        "approved_provider_attempt_ceiling": max_calls,
        "currency": "USD",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Block paid staging worker creation without a private scoped Founder+C decision.",
    )
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--api-service-id", required=True)
    parser.add_argument("--worker-name", required=True)
    args = parser.parse_args(argv)
    try:
        record = read_private_authorization(args.authorization_file)
        value = verify_paid_worker_authorization(
            record,
            source_revision=args.source_revision,
            workspace_id=args.workspace_id,
            api_service_id=args.api_service_id,
            worker_name=args.worker_name,
            checked_at=datetime.now(timezone.utc),
        )
    except AuthorizationEvidenceFailure as error:
        # This is a local *shape* check, not evidence of a real approval.
        # Errors contain field names only, never values from the private file.
        print(json.dumps({"status": "blocked_external", "error": str(error)}))
        return 1
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
