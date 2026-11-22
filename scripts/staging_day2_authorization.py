"""Fail-closed, *source-only* reconciliation of a dated Day 2 staging decision.

An operator-supplied JSON file cannot prove that Founder or C actually
approved anything. D must verify the protected original decision references
against independent records, resource identities, billing and host history.
This module checks structure and release/time/restore consistency only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path


class AuthorizationEvidenceFailure(RuntimeError):
    """A required Founder/C staging decision is missing or inconsistent."""


_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_CURRENCY = re.compile(r"[A-Z]{3}\Z")
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_:.@ /-]{0,199}\Z")
_ROOT_FIELDS = {
    "schema_version", "status", "environment", "release_id", "source_revision",
    "rollout_manifest_sha256", "provider_policy_sha256", "build_reference",
    "deployment_reference", "hosting", "budget", "isolated_restore", "rollback",
    "approvals", "valid_from", "valid_until",
}
# A named worker service alone does not authorize its region or paid compute
# tier. These must be recorded on the same dated Founder/C decision that
# covers the deployment, rather than supplied by an unreviewed workflow input.
_HOSTING_FIELDS = {
    "provider", "workspace_reference", "api_service_reference",
    "worker_service_reference", "worker_region", "worker_plan",
}


def _object(value: object, fields: set[str], field: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise AuthorizationEvidenceFailure(
            f"Day 2 authorization {field} has missing or extra fields."
        )
    return value


def _reference(value: object, field: str) -> str:
    if not isinstance(value, str) or _REFERENCE.fullmatch(value) is None:
        raise AuthorizationEvidenceFailure(
            f"Day 2 authorization {field} must be a bounded nonsecret reference."
        )
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise AuthorizationEvidenceFailure(
            f"Day 2 authorization {field} requires a lowercase SHA-256 digest."
        )
    return value


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise AuthorizationEvidenceFailure(
            f"Day 2 authorization {field} needs an ISO-8601 timezone."
        )
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AuthorizationEvidenceFailure(
            f"Day 2 authorization {field} needs a valid ISO-8601 timestamp."
        ) from None
    if when.tzinfo is None:
        raise AuthorizationEvidenceFailure(
            f"Day 2 authorization {field} needs a timezone."
        )
    return when.astimezone(timezone.utc)


def _bounded_int(value: object, field: str, ceiling: int) -> int:
    if type(value) is not int or not 1 <= value <= ceiling:
        raise AuthorizationEvidenceFailure(
            f"Day 2 authorization {field} must be a bounded positive integer."
        )
    return value


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise AuthorizationEvidenceFailure(
                "Day 2 authorization has duplicate JSON fields."
            )
        value[key] = item
    return value


def read_private_authorization(path: Path) -> dict:
    """Open the exact protected inode once; never follow a replacement symlink.

    A path.is_symlink()/stat()/read_text() sequence is vulnerable to a
    path-swap between the initial checks and the credential-bearing read.
    POSIX O_NOFOLLOW and fstat on the already-open fd close that gap.
    """
    try:
        if path.is_symlink():
            raise AuthorizationEvidenceFailure(
                "Day 2 authorization must be a regular private receipt, never a symlink."
            )
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        if os.name == "posix":
            if not hasattr(os, "O_NOFOLLOW"):
                raise AuthorizationEvidenceFailure(
                    "Day 2 authorization requires no-follow private file support."
                )
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            details = os.fstat(handle.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise AuthorizationEvidenceFailure(
                    "Day 2 authorization must be a regular private receipt."
                )
            if details.st_size < 1 or details.st_size > 32_768:
                raise AuthorizationEvidenceFailure(
                    "Day 2 authorization receipt is empty or oversized."
                )
            if os.name == "posix" and stat.S_IMODE(details.st_mode) != 0o600:
                raise AuthorizationEvidenceFailure(
                    "Day 2 authorization receipt must have mode 0600."
                )
            content = handle.read(32_769)
            if len(content) > 32_768:
                raise AuthorizationEvidenceFailure(
                    "Day 2 authorization receipt exceeded the allowed size while reading."
                )
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_fields)
    except (OSError, UnicodeError, ValueError):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization private receipt cannot be read as valid JSON."
        ) from None
    if not isinstance(value, dict):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization receipt must contain a JSON object."
        )
    return value


def reconcile_authorization(
    authorization: object,
    *,
    release: dict,
    freeze_prepared_at: object,
    preseed_attested_at: object,
    integrity: dict,
    model_attempts: object,
    restore_verified_at: datetime,
) -> dict:
    """Bind an operator-recorded decision to actual receipt identities/times.

    This function does *not* verify the asserted approvals or charges. Its
    result cannot be substituted for an independent Founder/C/D readback.
    """
    receipt = _object(authorization, _ROOT_FIELDS, "receipt")
    if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != 1 or receipt.get("status") != "operator_recorded":
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization must be a schema-v1 operator-recorded decision, never an asserted PASS."
        )
    if receipt.get("environment") != "staging":
        raise AuthorizationEvidenceFailure("Day 2 authorization must be staging-only.")
    revision = receipt.get("source_revision")
    if (
        not isinstance(revision, str) or _REVISION.fullmatch(revision) is None
        or revision != release.get("source_revision")
        or _reference(receipt.get("release_id"), "release_id") != release.get("release_id")
    ):
        raise AuthorizationEvidenceFailure("Day 2 authorization source/release identity differs from freeze.")
    for field in ("rollout_manifest_sha256", "provider_policy_sha256"):
        if _digest(receipt.get(field), field) != release.get(field):
            raise AuthorizationEvidenceFailure(
                "Day 2 authorization " + field + " differs from frozen release."
            )
    for field in ("build_reference", "deployment_reference"):
        if _reference(receipt.get(field), field) != _reference(
            release.get(field), "freeze." + field
        ):
            raise AuthorizationEvidenceFailure(
                "Day 2 authorization " + field + " differs from frozen deployment."
            )

    hosting = _object(receipt.get("hosting"), _HOSTING_FIELDS, "hosting")
    for field in hosting:
        _reference(hosting[field], "hosting." + field)
    if (hosting["api_service_reference"] == hosting["worker_service_reference"]
            or "production" in hosting["api_service_reference"].lower()
            or "production" in hosting["worker_service_reference"].lower()):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization requires distinct staging-only API and persistent worker services."
        )

    budget = _object(receipt.get("budget"), {
        "currency", "max_spend_minor_units", "maximum_duration_minutes",
        "max_provider_attempts",
    }, "budget")
    currency = budget["currency"]
    if not isinstance(currency, str) or _CURRENCY.fullmatch(currency) is None:
        raise AuthorizationEvidenceFailure("Day 2 authorization budget currency is invalid.")
    max_spend = _bounded_int(budget["max_spend_minor_units"], "max_spend_minor_units", 1_000_000_000)
    max_duration = _bounded_int(budget["maximum_duration_minutes"], "maximum_duration_minutes", 10_080)
    max_calls = _bounded_int(budget["max_provider_attempts"], "max_provider_attempts", 100_000)
    if type(model_attempts) is not int or not 1 <= model_attempts <= max_calls:
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization provider attempt limit was exceeded or missing."
        )

    targets = _object(receipt.get("isolated_restore"), {
        "database_fingerprint", "storage_fingerprint", "api_origin_sha256",
    }, "isolated_restore")
    expected_target = {
        "database_fingerprint": integrity.get("target_database_fingerprint"),
        "storage_fingerprint": integrity.get("target_storage_fingerprint"),
        "api_origin_sha256": (
            integrity.get("restored_api_access", {}).get("restored_api_origin_sha256")
            if isinstance(integrity.get("restored_api_access"), dict) else None
        ),
    }
    for field in targets:
        if _digest(targets[field], "isolated_restore." + field) != expected_target[field]:
            raise AuthorizationEvidenceFailure(
                "Day 2 authorization isolated restore " + field + " differs from verified target."
            )

    rollback = _object(receipt.get("rollback"), {
        "owner_reference", "procedure_reference",
    }, "rollback")
    for field in rollback:
        _reference(rollback[field], "rollback." + field)

    approvals = _object(receipt.get("approvals"), {"founder", "operator_c"}, "approvals")
    times = []
    references = []
    for role in ("founder", "operator_c"):
        item = _object(approvals[role], {"decision", "approved_at", "reference"},
                       "approvals." + role)
        if item["decision"] != "approved":
            raise AuthorizationEvidenceFailure(
                "Day 2 authorization requires a dated approved decision for Founder and C."
            )
        times.append(_time(item["approved_at"], "approvals." + role + ".approved_at"))
        references.append(_reference(item["reference"], "approvals." + role + ".reference"))
    if references[0] == references[1]:
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization Founder and C must have separate approval references."
        )

    start = _time(receipt.get("valid_from"), "valid_from")
    end = _time(receipt.get("valid_until"), "valid_until")
    baseline = _time(preseed_attested_at, "preseed_baseline.attested_at")
    prepared = _time(freeze_prepared_at, "freeze.prepared_at")
    if (
        not all(t <= start for t in times)
        or not start <= baseline <= prepared <= restore_verified_at <= end
        or (end - start).total_seconds() <= 0
        or (end - start).total_seconds() > max_duration * 60
    ):
        raise AuthorizationEvidenceFailure(
            "Day 2 authorization approval chronology, archive, deployment or time-budget window is inconsistent."
        )
    # Only hashes, limits and the need for independent verification leave the
    # private evidence directory; never include decision references or actors.
    receipt_sha = hashlib.sha256(json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return {
        "status": "operator_recorded_requires_independent_review",
        "receipt_sha256": receipt_sha,
        "currency": currency,
        "max_spend_minor_units": max_spend,
        "maximum_duration_minutes": max_duration,
        "max_provider_attempts": max_calls,
        "required_independent_verification": True,
    }


def preflight_restored_destination(
    authorization: object,
    *,
    source_revision: str,
    release_id: str,
    rollout_manifest_sha256: str,
    source_api_origin: str,
    restored_api_origin: str,
    target_database_fingerprint: str,
    target_storage_fingerprint: str,
    now: datetime | None = None,
) -> str:
    """Check the *recorded* Founder/C destination before any owner bearer is sent.

    Unlike final release reconciliation, this is a pretransmission boundary.
    The protected approval's exact isolated API SHA, database and storage
    fingerprints are checked against the intended operator destination.
    An operator-written JSON is NOT independent proof of actual consent;
    reviewer D must still verify original Founder/C decisions and providers.
    """
    from scripts.staging_api_exercise import ExerciseFailure, require_https_base
    from scripts.staging_day2_execution import EXPECTED_STAGING_API_ORIGIN

    receipt = _object(authorization, _ROOT_FIELDS, "receipt")
    if (
        type(receipt.get("schema_version")) is not int
        or receipt["schema_version"] != 1
        or receipt.get("status") != "operator_recorded"
        or receipt.get("environment") != "staging"
    ):
        raise AuthorizationEvidenceFailure("Restored API requires a protected staging-only operator-recorded decision.")
    if (
        _reference(receipt.get("release_id"), "release_id") != release_id
        or _reference(receipt.get("source_revision"), "source_revision") != source_revision
        or _REVISION.fullmatch(source_revision) is None
        or _digest(receipt.get("rollout_manifest_sha256"), "rollout_manifest_sha256")
        != _digest(rollout_manifest_sha256, "current rollout_manifest_sha256")
    ):
        raise AuthorizationEvidenceFailure("Restored API approval does not match the current frozen release.")
    for key in ("provider_policy_sha256",):
        _digest(receipt.get(key), key)
    for key in ("build_reference", "deployment_reference"):
        _reference(receipt.get(key), key)
    hosting = _object(receipt.get("hosting"), _HOSTING_FIELDS, "hosting")
    for key, value in hosting.items():
        _reference(value, "hosting." + key)
    if (
        hosting["provider"] != "Render"
        or hosting["workspace_reference"] != "tea-d6ok4okhg0os73erkdv0"
        or hosting["api_service_reference"] != "srv-dav98otg1s2s73cod4gg"
        or hosting["worker_service_reference"] == hosting["api_service_reference"]
        or "production" in hosting["worker_service_reference"].lower()
    ):
        raise AuthorizationEvidenceFailure("Restored API authorization is not for the reviewed Render staging services.")
    try:
        source = require_https_base(source_api_origin)
        restored = require_https_base(restored_api_origin)
    except ExerciseFailure:
        raise AuthorizationEvidenceFailure("Restored API requires exact clean public HTTPS origins.") from None
    if source != EXPECTED_STAGING_API_ORIGIN or source == restored:
        raise AuthorizationEvidenceFailure("Source API origin is not the reviewed staging API or restore is not isolated.")

    targets = _object(receipt.get("isolated_restore"), {
        "database_fingerprint", "storage_fingerprint", "api_origin_sha256",
    }, "isolated_restore")
    approved_api_sha = _digest(targets["api_origin_sha256"], "isolated_restore.api_origin_sha256")
    if (
        _digest(targets["database_fingerprint"], "isolated_restore.database_fingerprint")
        != _digest(target_database_fingerprint, "target_database_fingerprint")
        or _digest(targets["storage_fingerprint"], "isolated_restore.storage_fingerprint")
        != _digest(target_storage_fingerprint, "target_storage_fingerprint")
        or approved_api_sha != hashlib.sha256(restored.encode("utf-8")).hexdigest()
    ):
        raise AuthorizationEvidenceFailure("Isolated API, PostgreSQL or object-storage target is not approved.")

    budget = _object(receipt.get("budget"), {
        "currency", "max_spend_minor_units", "maximum_duration_minutes", "max_provider_attempts",
    }, "budget")
    if not isinstance(budget["currency"], str) or _CURRENCY.fullmatch(budget["currency"]) is None:
        raise AuthorizationEvidenceFailure("Restored API approval budget currency is invalid.")
    _bounded_int(budget["max_spend_minor_units"], "max_spend_minor_units", 1_000_000_000)
    max_duration = _bounded_int(budget["maximum_duration_minutes"], "maximum_duration_minutes", 10_080)
    _bounded_int(budget["max_provider_attempts"], "max_provider_attempts", 100_000)

    rollback = _object(receipt.get("rollback"), {
        "owner_reference", "procedure_reference",
    }, "rollback")
    for key, value in rollback.items():
        _reference(value, "rollback." + key)

    approvals = _object(receipt.get("approvals"), {"founder", "operator_c"}, "approvals")
    signatures = []
    approval_times = []
    for key in ("founder", "operator_c"):
        decision = _object(approvals[key], {
            "decision", "approved_at", "reference",
        }, "approvals." + key)
        if decision["decision"] != "approved":
            raise AuthorizationEvidenceFailure("Restored API requires both Founder and C dated decisions.")
        signatures.append(_reference(decision["reference"], "approvals." + key + ".reference"))
        approval_times.append(_time(decision["approved_at"], "approvals." + key + ".approved_at"))
    if signatures[0] == signatures[1]:
        raise AuthorizationEvidenceFailure("Founder and C decisions must have distinct original references.")
    start, end = _time(receipt.get("valid_from"), "valid_from"), _time(receipt.get("valid_until"), "valid_until")
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise AuthorizationEvidenceFailure("Restore approval preflight clock must include a timezone.")
    checked_at = checked_at.astimezone(timezone.utc)
    if (
        not all(t <= start for t in approval_times)
        or not start <= checked_at <= end
        or not 0 < (end - start).total_seconds() <= max_duration * 60
    ):
        raise AuthorizationEvidenceFailure("Restored API is outside the dated Founder/C authorization window.")

    return approved_api_sha
