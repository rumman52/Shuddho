"""Authenticated, read-only document/task access proof on an isolated restored API.

The source and restored APIs must be distinct approved public HTTPS origins.
This check proves observed API behavior; it does not independently authenticate
cloud deployment-to-database/object-store bindings or authorize spending.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid

import httpx

from scripts.staging_api_exercise import ExerciseFailure, require_https_base
from scripts.staging_day2_execution import (
    Day2Failure, _managed_identity_claims, bearer, require_distinct_owners,
)


_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")


class RestoredAPIReadbackFailure(RuntimeError):
    """Isolated restored API owner access is missing, leaked or inconsistent."""


def _guard() -> None:
    if (
        os.environ.get("SHUDDHO_STAGING_ALLOW_RESTORED_API_READBACK", "").lower() != "true"
        or os.environ.get("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", "").lower() != "true"
    ):
        raise RestoredAPIReadbackFailure(
            "Restored API readback requires explicit staging and synthetic-account guards."
        )


def _origins(client: httpx.Client, source_origin: str, restored_origin: str) -> tuple[str, str]:
    try:
        source = require_https_base(source_origin)
        restored = require_https_base(restored_origin)
    except (ExerciseFailure, ValueError):
        raise RestoredAPIReadbackFailure("Restored and source API origins must be clean public HTTPS.") from None
    if source == restored or str(client.base_url).rstrip("/") != restored:
        raise RestoredAPIReadbackFailure(
            "Restored API origin must differ from source and match the configured HTTP client."
        )
    return source, restored


def _get(client: httpx.Client, route: str, token: str, expected: int, label: str) -> httpx.Response:
    try:
        response = client.get(route, headers=bearer(token))
    except httpx.HTTPError:
        raise RestoredAPIReadbackFailure(f"{label} could not be read from restored HTTPS API.") from None
    if response.status_code != expected:
        raise RestoredAPIReadbackFailure(
            f"{label} expected HTTP {expected} but received HTTP {response.status_code}."
        )
    return response


def _json(response: httpx.Response, label: str) -> dict:
    try:
        value = response.json()
    except (ValueError, UnicodeError):
        raise RestoredAPIReadbackFailure(f"{label} returned invalid JSON.") from None
    if not isinstance(value, dict):
        raise RestoredAPIReadbackFailure(f"{label} did not return a JSON object.")
    return value


def attest_restored_api_access(
    client: httpx.Client,
    token_a: str,
    token_b: str,
    *,
    source_origin: str,
    restored_origin: str,
    approved_restored_origin_sha256: str,
    expected_owner_id: str,
    document_id: str,
    task_id: str,
    document_sha256: str,
    document_size: int,
    source_revision: str,
    expected_issuer: str,
    expected_audience: str,
) -> dict:
    """Confirm owner-A restored probe and owner-B denial without making writes.

    A managed issuer-pinned service verifies the bearer signatures when
    handling authenticated /me and resource requests. Only read-only GETs are
    issued, with no redirects; all outputs are redacted booleans/digests.
    """
    _guard()
    source, restored = _origins(client, source_origin, restored_origin)
    # This is a last-line fail-closed check for standalone probe invocations.
    # The backup/restore operator must first compare this digest to the
    # protected Founder/C approval and the actual DB/object target identities.
    if (
        not isinstance(approved_restored_origin_sha256, str)
        or _SHA.fullmatch(approved_restored_origin_sha256) is None
        or hashlib.sha256(restored.encode("utf-8")).hexdigest()
        != approved_restored_origin_sha256
    ):
        raise RestoredAPIReadbackFailure(
            "Restored API HTTPS origin does not match the approved isolated target before bearer transmission."
        )
    try:
        doc_id, run_id = str(uuid.UUID(document_id)), str(uuid.UUID(task_id))
    except (ValueError, AttributeError, TypeError):
        raise RestoredAPIReadbackFailure("Restored probe document/task identity is invalid.") from None
    if (
        not isinstance(expected_owner_id, str) or _SHA.fullmatch(expected_owner_id) is None
        or not isinstance(document_sha256, str) or _SHA.fullmatch(document_sha256) is None
        or type(document_size) is not int or not 1 <= document_size <= 16 * 1024 * 1024
        or not isinstance(source_revision, str) or _REVISION.fullmatch(source_revision) is None
    ):
        raise RestoredAPIReadbackFailure("Restored probe has invalid owner, digest, size or source revision.")
    if client.follow_redirects:
        raise RestoredAPIReadbackFailure("Restored API client must not follow redirects.")

    # Local JWT header/claim inspection comes BEFORE the first credentialed
    # HTTP request. The restored API subsequently authenticates signatures
    # and binds each subject to a distinct managed /me account/workspace.
    try:
        subject_a, derived_owner_a = _managed_identity_claims(
            token_a, expected_issuer=expected_issuer,
            expected_audience=expected_audience, minimum_validity_seconds=300,
        )
        subject_b, _ = _managed_identity_claims(
            token_b, expected_issuer=expected_issuer,
            expected_audience=expected_audience, minimum_validity_seconds=300,
        )
    except Day2Failure:
        raise RestoredAPIReadbackFailure(
            "Managed restored owner token claims are invalid before credentialed access."
        ) from None
    if token_a == token_b or subject_a == subject_b or derived_owner_a != expected_owner_id:
        raise RestoredAPIReadbackFailure(
            "Managed restored owner token subjects or archived owner identity do not match."
        )

    runtime = _json(
        _get(client, "/api/v1/runtime-manifest", token_a, 200, "isolated runtime-manifest"),
        "isolated runtime-manifest",
    )
    if (
        runtime.get("schema_version") != 2
        or runtime.get("environment") != "staging"
        or runtime.get("source_revision") != source_revision
    ):
        raise RestoredAPIReadbackFailure("Isolated API runtime does not match the reviewed staging source.")

    try:
        require_distinct_owners(
            client, token_a, token_b,
            expected_issuer=expected_issuer,
            expected_audience=expected_audience,
            minimum_validity_seconds=300,
        )
    except Day2Failure:
        raise RestoredAPIReadbackFailure("Restored API did not validate two distinct managed owners.") from None

    me_a = _json(_get(client, "/api/v1/me", token_a, 200, "restored owner A identity"),
                 "restored owner A identity")
    if me_a.get("account_id") != expected_owner_id:
        raise RestoredAPIReadbackFailure(
            "Restored API owner A token does not bind to the archived source owner."
        )

    document_route = f"/api/v1/documents/{doc_id}/content"
    _get(client, document_route, token_b, 404, "restored foreign document content")
    listed = _json(
        _get(client, "/api/v1/documents", token_b, 200, "restored owner B document catalog"),
        "restored owner B document catalog",
    ).get("documents")
    if (not isinstance(listed, list)
            or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in listed)
            or any(item["id"] == doc_id for item in listed)):
        raise RestoredAPIReadbackFailure(
            "Owner B could enumerate owner A's restored document or has an invalid catalog."
        )

    # Stream and hash with an exact byte ceiling. Even a misconfigured API
    # cannot make this privileged operator retain an unbounded private body.
    digest = hashlib.sha256()
    total = 0
    try:
        with client.stream("GET", document_route, headers=bearer(token_a)) as response:
            if response.status_code != 200:
                raise RestoredAPIReadbackFailure(
                    f"restored owner A document content expected HTTP 200 but received HTTP {response.status_code}."
                )
            for block in response.iter_bytes():
                total += len(block)
                if total > document_size:
                    raise RestoredAPIReadbackFailure(
                        "Restored owner A document exceeded the archived private byte size."
                    )
                digest.update(block)
    except httpx.HTTPError:
        raise RestoredAPIReadbackFailure(
            "Restored owner A document could not be streamed over HTTPS."
        ) from None
    if total != document_size or digest.hexdigest() != document_sha256:
        raise RestoredAPIReadbackFailure(
            "Authenticated owner A document bytes differ from the isolated archive manifest."
        )

    task_route = f"/api/v1/tasks/{run_id}"
    _get(client, task_route, token_b, 404, "restored foreign task")
    task = _json(_get(client, task_route, token_a, 200, "restored owner A task"),
                 "restored owner A task")
    if task.get("id") != run_id or task.get("state") != "cancelled":
        raise RestoredAPIReadbackFailure(
            "Authenticated owner A task does not match the restored cancelled probe."
        )

    return {
        "status": "verified",
        "runtime_source_revision": source_revision,
        "source_api_origin_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "restored_api_origin_sha256": hashlib.sha256(restored.encode()).hexdigest(),
        "owner_a_document_sha256": document_sha256,
        "owner_a_document_bytes": document_size,
        "owner_a_document_retrievable": True,
        "owner_b_document_denied": True,
        "owner_b_document_unlisted": True,
        "owner_a_cancelled_task_verified": True,
        "owner_b_task_denied": True,
        "owner_a_identity_verified": True,
        "owner_b_identity_verified": True,
    }
