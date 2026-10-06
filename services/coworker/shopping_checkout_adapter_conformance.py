from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .action_registry import (
    ACTION_SPECS,
    registered_transaction_operations,
    stable_digest,
)
from .shopping_checkout_adapter import admit_checkout_adapter
from .shopping_checkout_contract import (
    ShoppingCheckoutPreview,
    validate_checkout_receipt,
)


ACTION_KIND = "shopping_checkout_create"
TX14_QUALIFICATION_KEYS = {
    "schema_version",
    "provider",
    "operation",
    "adapter_revision",
    "checkout_origin",
    "credential_boundary",
    "idempotency",
    "reconciliation",
    "receipt",
    "privacy",
    "payment_boundary",
    "live_probe",
    "registration_authority",
    "operation_allowlisted",
    "external_action_registered",
    "payment_authority",
    "qualification_sha256",
}
TX14_PROBE_KEYS = {
    "status",
    "environment",
    "verified_at",
    "source_revision",
    "checkout_origin",
    "idempotency_passed",
    "reconciliation_passed",
    "receipt_match_passed",
    "privacy_passed",
    "payment_boundary_passed",
    "evidence_sha256",
}


class ShoppingCheckoutAdapterConformanceError(RuntimeError):
    pass


def _aware(value: datetime, *, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ShoppingCheckoutAdapterConformanceError(
            f"{label} must include a timezone offset."
        )
    return value.astimezone(timezone.utc)


def _parse_time(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise ShoppingCheckoutAdapterConformanceError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ShoppingCheckoutAdapterConformanceError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    return _aware(parsed, label=label)


def _sha256(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutAdapterConformanceError(
            f"{label} must be a lowercase SHA-256."
        )
    return value


def _require_runtime_closed() -> None:
    if ACTION_KIND in ACTION_SPECS:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 refuses provider implementation tests while checkout is runtime registered."
        )
    if any(
        operation.endswith(f":{ACTION_KIND}")
        for operation in registered_transaction_operations()
    ):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 refuses provider implementation tests while a checkout operation is allowlisted."
        )


def _require_tx14_qualification(
    value: dict,
    *,
    admission: dict,
    current: datetime,
    max_probe_age_hours: int,
) -> dict:
    if not isinstance(value, dict) or set(value) != TX14_QUALIFICATION_KEYS:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 requires the exact normalized TX-14 qualification object."
        )

    stored_digest = _sha256(
        value["qualification_sha256"],
        label="TX-14 qualification_sha256",
    )
    unsigned = dict(value)
    unsigned.pop("qualification_sha256")
    if stored_digest != stable_digest(unsigned):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 qualification digest does not match its contents."
        )
    if stored_digest != admission["qualification_sha256"]:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 qualification does not match the admitted TX-15 proposal."
        )

    if (
        value["schema_version"] != 1
        or value["provider"] != admission["provider"]
        or value["operation"] != admission["operation"]
        or value["adapter_revision"] != admission["adapter_revision"]
        or value["checkout_origin"] != admission["checkout_origin"]
    ):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 qualification identity does not match TX-16 admission."
        )

    credentials = value.get("credential_boundary")
    if (
        not isinstance(credentials, dict)
        or credentials.get("storage") != "credential_broker"
        or credentials.get("server_side_only") is not True
        or credentials.get("least_privilege") is not True
        or credentials.get("raw_payment_credentials") is not False
        or credentials.get("scopes") != admission["credential_scopes"]
    ):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 credential boundary does not match the admitted adapter."
        )

    for key in ("idempotency", "reconciliation", "receipt", "privacy", "payment_boundary"):
        if stable_digest(value[key]) != stable_digest(admission[key]):
            raise ShoppingCheckoutAdapterConformanceError(
                f"TX-14 {key} evidence does not match TX-16 admission."
            )

    if (
        value["registration_authority"] is not False
        or value["operation_allowlisted"] is not False
        or value["external_action_registered"] is not False
        or value["payment_authority"] is not False
    ):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 qualification unexpectedly grants checkout authority."
        )

    probe = value["live_probe"]
    if not isinstance(probe, dict) or set(probe) != TX14_PROBE_KEYS:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 live probe has an unexpected schema."
        )
    if (
        probe["status"] != "passed"
        or probe["environment"] != "staging"
        or probe["source_revision"] != admission["adapter_revision"]
        or probe["checkout_origin"] != admission["checkout_origin"]
    ):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 live probe is not bound to this exact staging adapter and origin."
        )
    for key in (
        "idempotency_passed",
        "reconciliation_passed",
        "receipt_match_passed",
        "privacy_passed",
        "payment_boundary_passed",
    ):
        if probe[key] is not True:
            raise ShoppingCheckoutAdapterConformanceError(
                f"TX-14 live probe did not pass {key}."
            )

    _sha256(probe["evidence_sha256"], label="TX-14 live probe evidence_sha256")
    verified_at = _parse_time(
        probe["verified_at"],
        label="TX-14 live probe verified_at",
    )
    age = current - verified_at
    if age < -timedelta(minutes=1):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 live probe timestamp is from the future."
        )
    if age > timedelta(hours=max(1, max_probe_age_hours)):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-14 live probe evidence is stale."
        )
    return probe


def _require_staging_boundary(adapter: object, *, reviewed_origin: str) -> None:
    if getattr(adapter, "implementation_test_only", None) is not True:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 requires an adapter explicitly marked implementation_test_only."
        )
    if getattr(adapter, "implementation_test_environment", None) != "staging":
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 provider I/O is allowed only from the controlled staging test path."
        )
    if getattr(adapter, "implementation_test_origin", None) != reviewed_origin:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 implementation-test origin must match the reviewed TX-14/TX-15 origin."
        )


def _idempotency_key(admission: dict, preview: ShoppingCheckoutPreview) -> str:
    preview_value = preview.model_dump(mode="json")
    return stable_digest(
        {
            "schema_version": 1,
            "adapter_admission_sha256": admission["adapter_admission_sha256"],
            "checkout_binding_id": str(preview.checkout_binding_id),
            "checkout_binding_scope_sha256": preview.checkout_binding_scope_sha256,
            "preview_sha256": stable_digest(preview_value),
        }
    )


async def _lookup(
    adapter: object,
    *,
    idempotency_key: str | None = None,
    provider_order_id: str | None = None,
) -> dict | None:
    try:
        value = await adapter.lookup_checkout(
            idempotency_key=idempotency_key,
            provider_order_id=provider_order_id,
        )
    except Exception as exc:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 staging checkout lookup failed."
        ) from exc
    if value is not None and not isinstance(value, dict):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 checkout lookup must return a receipt dictionary or None."
        )
    return value


async def _create(
    adapter: object,
    *,
    preview: dict,
    idempotency_key: str,
) -> dict:
    try:
        value = await adapter.create_checkout(
            preview=preview,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 staging checkout creation failed."
        ) from exc
    if not isinstance(value, dict):
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 checkout creation must return a receipt dictionary."
        )
    return value


def _validated_receipt(
    preview: ShoppingCheckoutPreview,
    receipt: dict,
    *,
    now: datetime,
    label: str,
) -> dict:
    try:
        result = validate_checkout_receipt(
            preview.model_dump(mode="json"),
            receipt,
            now=now,
        )
    except Exception as exc:
        raise ShoppingCheckoutAdapterConformanceError(
            f"TX-23 {label} receipt failed the TX-13 receipt contract."
        ) from exc

    confirmed_at = _parse_time(
        result["receipt"]["confirmed_at"],
        label=f"TX-23 {label} confirmed_at",
    )
    if confirmed_at > preview.expires_at:
        raise ShoppingCheckoutAdapterConformanceError(
            f"TX-23 {label} receipt was confirmed after the reviewed checkout expired."
        )
    return result


async def exercise_shopping_checkout_adapter(
    proposal_value: dict,
    qualification_value: dict,
    adapter: object,
    *,
    preview_value: dict,
    allow_provider_test_io: bool = False,
    now: datetime | None = None,
    max_probe_age_hours: int = 24,
) -> dict[str, Any]:
    """Exercise a TX-16-admitted checkout adapter in controlled staging only."""

    current = _aware(
        now or datetime.now(timezone.utc),
        label="TX-23 current time",
    )
    _require_runtime_closed()

    admission = admit_checkout_adapter(
        proposal_value,
        adapter,
        now=current,
    )
    probe = _require_tx14_qualification(
        qualification_value,
        admission=admission,
        current=current,
        max_probe_age_hours=max_probe_age_hours,
    )

    if allow_provider_test_io is not True:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 provider implementation tests require explicit allow_provider_test_io=True."
        )
    _require_staging_boundary(
        adapter,
        reviewed_origin=probe["checkout_origin"],
    )

    try:
        preview = ShoppingCheckoutPreview.model_validate(preview_value)
    except Exception as exc:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 preview does not satisfy the TX-13 checkout contract."
        ) from exc

    if preview.expires_at <= current:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 refuses to call a provider with an expired checkout preview."
        )
    if preview.provider != admission["provider"]:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 preview provider does not match the admitted provider."
        )

    normalized_preview = preview.model_dump(mode="json")
    idempotency_key = _idempotency_key(admission, preview)

    existing = await _lookup(
        adapter,
        idempotency_key=idempotency_key,
    )
    existing_validated = (
        _validated_receipt(
            preview,
            existing,
            now=current,
            label="pre-create lookup",
        )
        if existing is not None
        else None
    )

    first = await _create(
        adapter,
        preview=normalized_preview,
        idempotency_key=idempotency_key,
    )
    first_validated = _validated_receipt(
        preview,
        first,
        now=current,
        label="first create",
    )

    second = await _create(
        adapter,
        preview=normalized_preview,
        idempotency_key=idempotency_key,
    )
    second_validated = _validated_receipt(
        preview,
        second,
        now=current,
        label="idempotent create",
    )

    provider_order_id = first_validated["receipt"]["provider_order_id"]
    by_key = await _lookup(
        adapter,
        idempotency_key=idempotency_key,
    )
    by_provider_id = await _lookup(
        adapter,
        provider_order_id=provider_order_id,
    )
    if by_key is None or by_provider_id is None:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 requires checkout readback by both idempotency key and provider order ID."
        )

    by_key_validated = _validated_receipt(
        preview,
        by_key,
        now=current,
        label="idempotency lookup",
    )
    by_provider_id_validated = _validated_receipt(
        preview,
        by_provider_id,
        now=current,
        label="provider order lookup",
    )

    receipt_hashes = {
        first_validated["receipt_sha256"],
        second_validated["receipt_sha256"],
        by_key_validated["receipt_sha256"],
        by_provider_id_validated["receipt_sha256"],
    }
    if existing_validated is not None:
        receipt_hashes.add(existing_validated["receipt_sha256"])
    if len(receipt_hashes) != 1:
        raise ShoppingCheckoutAdapterConformanceError(
            "TX-23 provider implementation is not idempotent or readback-stable."
        )

    _require_runtime_closed()

    result = {
        "schema_version": 1,
        "status": "provider_implementation_conformance_passed",
        "provider": admission["provider"],
        "operation": admission["operation"],
        "adapter_revision": admission["adapter_revision"],
        "checkout_origin": admission["checkout_origin"],
        "qualification_sha256": admission["qualification_sha256"],
        "live_probe_evidence_sha256": probe["evidence_sha256"],
        "adapter_admission_sha256": admission["adapter_admission_sha256"],
        "preview_sha256": stable_digest(normalized_preview),
        "receipt_sha256": first_validated["receipt_sha256"],
        "idempotency_key_sha256": stable_digest(
            {"idempotency_key": idempotency_key}
        ),
        "provider_test_environment": "staging",
        "staging_provider_io": True,
        "provider_called": True,
        "create_attempts": 2,
        "lookup_attempts": 3,
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "identity_authority": False,
        "payment_authority": False,
    }
    result["conformance_sha256"] = stable_digest(result)
    return result
