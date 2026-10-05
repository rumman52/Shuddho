from __future__ import annotations

import hashlib
import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse


ACTION_KIND = "shopping_checkout_create"
CONTRACT_VERSION = 1
REQUIRED_RECEIPT_FIELDS = {
    "provider_order_id",
    "merchant_cart_id",
    "currency",
    "total_minor",
    "status",
    "confirmed_at",
}


class ShoppingCheckoutAdapterAdmissionError(RuntimeError):
    pass


def canonical_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _exact_dict(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} has an unexpected schema."
        )
    return value


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} must be a lowercase SHA-256."
        )
    return value


def _revision(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} must be a full lowercase Git SHA-1."
        )
    return value


def _clean_https_origin(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} must be a clean HTTPS origin."
        )
    clean = value.rstrip("/")
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} must be a clean HTTPS origin."
        )
    return clean


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} must be an ISO-8601 timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} must be an ISO-8601 timestamp."
        ) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ShoppingCheckoutAdapterAdmissionError(
            f"{label} must include a timezone."
        )
    return parsed.astimezone(timezone.utc)


@runtime_checkable
class ShoppingCheckoutProviderAdapter(Protocol):
    """Structural contract for a future provider-specific checkout adapter.

    The protocol is deliberately not connected to the action registry. A concrete
    adapter can be admitted for implementation testing only after its static
    metadata matches an exact TX-15 registration proposal.
    """

    provider_name: str
    adapter_revision: str
    checkout_origin: str
    credential_scopes: frozenset[str]
    action_kind: str
    contract_version: int
    supports_idempotency: bool
    supports_lookup_by_idempotency_key: bool
    supports_lookup_by_provider_order_id: bool
    payment_mode: str
    receives_payment_instrument: bool

    async def create_checkout(
        self,
        *,
        preview: dict,
        idempotency_key: str,
    ) -> dict:
        ...

    async def lookup_checkout(
        self,
        *,
        idempotency_key: str | None = None,
        provider_order_id: str | None = None,
    ) -> dict | None:
        ...


def validate_registration_proposal(
    value: dict,
    *,
    now: datetime | None = None,
    max_review_age_days: int = 14,
) -> dict:
    proposal = _exact_dict(
        value,
        {
            "schema_version",
            "status",
            "provider",
            "operation",
            "adapter_revision",
            "checkout_origin",
            "qualification_sha256",
            "action_contract",
            "credential_scopes",
            "idempotency",
            "reconciliation",
            "receipt",
            "privacy",
            "payment_boundary",
            "change_reference",
            "reviewed_at",
            "reviewer_reference",
            "registry_change_required",
            "registration_authority",
            "operation_allowlisted",
            "external_action_registered",
            "runtime_enabled",
            "payment_authority",
            "registration_proposal_sha256",
        },
        "TX-15 registration proposal",
    )
    if proposal["schema_version"] != 1:
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 registration proposal schema version is unsupported."
        )
    if proposal["status"] != "eligible_for_provider_implementation_review":
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 registration proposal is not eligible for implementation review."
        )

    provider = proposal["provider"]
    if (
        not isinstance(provider, str)
        or not re.fullmatch(r"[a-z0-9_]{2,40}", provider)
        or provider in {"internal", "simulated", "example", "test"}
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 provider identifier is not a concrete provider."
        )
    if proposal["operation"] != f"{provider}:{ACTION_KIND}":
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 operation does not match the provider checkout action."
        )

    _revision(proposal["adapter_revision"], "TX-15 adapter_revision")
    proposal["checkout_origin"] = _clean_https_origin(
        proposal["checkout_origin"],
        "TX-15 checkout_origin",
    )
    _sha256(proposal["qualification_sha256"], "TX-15 qualification_sha256")

    action_contract = _exact_dict(
        proposal["action_contract"],
        {"kind", "version", "source"},
        "TX-15 action_contract",
    )
    if action_contract != {
        "kind": ACTION_KIND,
        "version": CONTRACT_VERSION,
        "source": "TX-13",
    }:
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 action contract is not the supported TX-13 checkout contract."
        )

    scopes = proposal["credential_scopes"]
    if (
        not isinstance(scopes, list)
        or not 1 <= len(scopes) <= 20
        or any(
            not isinstance(item, str)
            or not item.strip()
            or len(item) > 120
            for item in scopes
        )
        or len(scopes) != len(set(scopes))
        or scopes != sorted(scopes)
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 credential scopes are invalid or not canonical."
        )

    idempotency = _exact_dict(
        proposal["idempotency"],
        {"supported", "key_scope", "duplicate_result"},
        "TX-15 idempotency",
    )
    if (
        idempotency["supported"] is not True
        or idempotency["key_scope"] != "checkout_binding"
        or idempotency["duplicate_result"] != "same_order_or_lookup"
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 does not bind the required checkout idempotency contract."
        )

    reconciliation = _exact_dict(
        proposal["reconciliation"],
        {"supported", "lookup_keys", "outcome_unknown_policy", "blind_retry"},
        "TX-15 reconciliation",
    )
    lookup_keys = reconciliation["lookup_keys"]
    if (
        reconciliation["supported"] is not True
        or not isinstance(lookup_keys, list)
        or set(lookup_keys) != {"idempotency_key", "provider_order_id"}
        or len(lookup_keys) != 2
        or reconciliation["outcome_unknown_policy"] != "lookup_before_retry"
        or reconciliation["blind_retry"] is not False
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 does not bind the required checkout reconciliation contract."
        )

    receipt = _exact_dict(
        proposal["receipt"],
        {"readback_supported", "exact_fields", "confirmed_status"},
        "TX-15 receipt",
    )
    fields = receipt["exact_fields"]
    if (
        receipt["readback_supported"] is not True
        or not isinstance(fields, list)
        or set(fields) != REQUIRED_RECEIPT_FIELDS
        or len(fields) != len(REQUIRED_RECEIPT_FIELDS)
        or receipt["confirmed_status"] != "confirmed"
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 receipt contract does not match TX-13."
        )

    privacy = _exact_dict(
        proposal["privacy"],
        {
            "sends_only_required_fields",
            "secrets_in_logs",
            "payment_instrument_to_shuddho",
            "identity_model",
        },
        "TX-15 privacy",
    )
    if (
        privacy["sends_only_required_fields"] is not True
        or privacy["secrets_in_logs"] is not False
        or privacy["payment_instrument_to_shuddho"] is not False
        or privacy["identity_model"] not in {
            "merchant_account",
            "merchant_hosted_user_present",
        }
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 privacy boundary is not compatible with checkout admission."
        )

    payment = _exact_dict(
        proposal["payment_boundary"],
        {
            "mode",
            "shuddho_charges",
            "stores_payment_instrument",
            "requires_user_present",
        },
        "TX-15 payment_boundary",
    )
    if (
        payment["mode"] != "merchant_hosted_user_present"
        or payment["shuddho_charges"] is not False
        or payment["stores_payment_instrument"] is not False
        or payment["requires_user_present"] is not True
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 payment boundary is not merchant-hosted and user-present."
        )

    if (
        proposal["registry_change_required"] is not True
        or proposal["registration_authority"] is not False
        or proposal["operation_allowlisted"] is not False
        or proposal["external_action_registered"] is not False
        or proposal["runtime_enabled"] is not False
        or proposal["payment_authority"] is not False
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 proposal unexpectedly grants runtime checkout authority."
        )

    for field in ("change_reference", "reviewer_reference"):
        item = proposal[field]
        if (
            not isinstance(item, str)
            or not item.strip()
            or len(item) > 300
            or any(ord(char) < 32 for char in item)
        ):
            raise ShoppingCheckoutAdapterAdmissionError(
                f"TX-15 {field} is invalid."
            )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reviewed_at = _parse_time(proposal["reviewed_at"], "TX-15 reviewed_at")
    age = current - reviewed_at
    if age < -timedelta(minutes=1):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 registration proposal review is from the future."
        )
    if age > timedelta(days=max(1, max_review_age_days)):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 registration proposal review is stale."
        )

    stored_digest = _sha256(
        proposal["registration_proposal_sha256"],
        "TX-15 registration_proposal_sha256",
    )
    unsigned = dict(proposal)
    unsigned.pop("registration_proposal_sha256")
    if stored_digest != canonical_sha256(unsigned):
        raise ShoppingCheckoutAdapterAdmissionError(
            "TX-15 registration proposal digest does not match its contents."
        )
    return proposal


def admit_checkout_adapter(
    proposal_value: dict,
    adapter: object,
    *,
    now: datetime | None = None,
) -> dict:
    """Admit a concrete adapter for isolated implementation tests only.

    This function performs no provider I/O and grants no runtime registration.
    """

    proposal = validate_registration_proposal(proposal_value, now=now)

    if not isinstance(adapter, ShoppingCheckoutProviderAdapter):
        raise ShoppingCheckoutAdapterAdmissionError(
            "Checkout adapter does not implement the required structural protocol."
        )
    if (
        not inspect.iscoroutinefunction(adapter.create_checkout)
        or not inspect.iscoroutinefunction(adapter.lookup_checkout)
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "Checkout adapter mutation and lookup methods must be asynchronous."
        )

    expected_metadata = {
        "provider_name": proposal["provider"],
        "adapter_revision": proposal["adapter_revision"],
        "checkout_origin": proposal["checkout_origin"],
        "action_kind": ACTION_KIND,
        "contract_version": CONTRACT_VERSION,
        "supports_idempotency": True,
        "supports_lookup_by_idempotency_key": True,
        "supports_lookup_by_provider_order_id": True,
        "payment_mode": "merchant_hosted_user_present",
        "receives_payment_instrument": False,
    }
    for field, expected in expected_metadata.items():
        actual = getattr(adapter, field, None)
        if field == "checkout_origin":
            actual = _clean_https_origin(actual, "adapter checkout_origin")
        if actual != expected:
            raise ShoppingCheckoutAdapterAdmissionError(
                f"Checkout adapter {field} does not match the TX-15 proposal."
            )

    scopes = getattr(adapter, "credential_scopes", None)
    if (
        not isinstance(scopes, frozenset)
        or set(scopes) != set(proposal["credential_scopes"])
    ):
        raise ShoppingCheckoutAdapterAdmissionError(
            "Checkout adapter credential scopes do not exactly match TX-15."
        )

    admission = {
        "schema_version": 1,
        "status": "admitted_for_provider_implementation_tests",
        "provider": proposal["provider"],
        "operation": proposal["operation"],
        "adapter_revision": proposal["adapter_revision"],
        "checkout_origin": proposal["checkout_origin"],
        "qualification_sha256": proposal["qualification_sha256"],
        "registration_proposal_sha256": proposal["registration_proposal_sha256"],
        "action_contract": proposal["action_contract"],
        "credential_scopes": list(proposal["credential_scopes"]),
        "idempotency": proposal["idempotency"],
        "reconciliation": proposal["reconciliation"],
        "receipt": proposal["receipt"],
        "privacy": proposal["privacy"],
        "payment_boundary": proposal["payment_boundary"],
        "provider_called": False,
        "registration_authority": False,
        "operation_allowlisted": False,
        "external_action_registered": False,
        "runtime_enabled": False,
        "payment_authority": False,
    }
    admission["adapter_admission_sha256"] = canonical_sha256(admission)
    return admission
