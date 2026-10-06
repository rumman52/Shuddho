from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


class RestaurantReservationProbeError(RuntimeError):
    pass


OPERATION = "opentable:restaurant_reservation_create"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RestaurantReservationProbeError(f"{name} is required.")
    return value


def require_guard() -> None:
    if os.environ.get(
        "SHUDDHO_STAGING_ALLOW_LIVE_RESTAURANT_RESERVATIONS", ""
    ).lower() != "true":
        raise RestaurantReservationProbeError(
            "Set SHUDDHO_STAGING_ALLOW_LIVE_RESTAURANT_RESERVATIONS=true only "
            "for the dedicated OpenTable sandbox qualification."
        )
    if os.environ.get("SHUDDHO_COWORKER_ENV", "").lower() != "staging":
        raise RestaurantReservationProbeError(
            "Restaurant reservation live qualification may run only in staging."
        )
    if os.environ.get("SHUDDHO_OPENTABLE_ENVIRONMENT", "").lower() != "sandbox":
        raise RestaurantReservationProbeError(
            "Restaurant reservation live qualification refuses non-sandbox OpenTable."
        )


def auth(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def request_json(
    response: httpx.Response,
    label: str,
    expected: int = 200,
) -> dict:
    if response.status_code != expected:
        raise RestaurantReservationProbeError(
            f"{label} returned HTTP {response.status_code}; expected {expected}."
        )
    try:
        value = response.json()
    except ValueError:
        raise RestaurantReservationProbeError(
            f"{label} did not return JSON."
        ) from None
    if not isinstance(value, dict):
        raise RestaurantReservationProbeError(
            f"{label} returned an unexpected shape."
        )
    return value


def wrong_hash(value: str) -> str:
    if (
        len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise RestaurantReservationProbeError("Preview hash is invalid.")
    return ("0" if value[0] != "0" else "1") + value[1:]


def reservation_payload() -> dict:
    try:
        restaurant_id = int(env("SHUDDHO_STAGING_RESTAURANT_ID"))
        party_size = int(os.environ.get("SHUDDHO_STAGING_RESTAURANT_PARTY_SIZE", "2"))
    except ValueError:
        raise RestaurantReservationProbeError(
            "Restaurant ID and party size must be integers."
        ) from None
    if restaurant_id < 1 or not 1 <= party_size <= 20:
        raise RestaurantReservationProbeError(
            "Restaurant ID/party size are outside allowed bounds."
        )
    return {
        "restaurant_id": restaurant_id,
        "restaurant_name": env("SHUDDHO_STAGING_RESTAURANT_NAME"),
        "date_time": env("SHUDDHO_STAGING_RESTAURANT_DATE_TIME"),
        "time_zone": env("SHUDDHO_STAGING_RESTAURANT_TIME_ZONE"),
        "party_size": party_size,
        "reservation_attribute": os.environ.get(
            "SHUDDHO_STAGING_RESTAURANT_ATTRIBUTE", "default"
        ),
        "dining_area_id": None,
        "environment": None,
        "guest_first_name": env("SHUDDHO_STAGING_RESTAURANT_GUEST_FIRST_NAME"),
        "guest_last_name": env("SHUDDHO_STAGING_RESTAURANT_GUEST_LAST_NAME"),
        "guest_email": env("SHUDDHO_STAGING_RESTAURANT_GUEST_EMAIL"),
        "guest_phone_number": env("SHUDDHO_STAGING_RESTAURANT_GUEST_PHONE"),
        "guest_phone_country_code": env(
            "SHUDDHO_STAGING_RESTAURANT_GUEST_COUNTRY"
        ).upper(),
        "special_request": os.environ.get(
            "SHUDDHO_STAGING_RESTAURANT_SPECIAL_REQUEST", ""
        ),
        "opentable_terms_accepted": True,
        "opentable_terms_version": "2026-07-22",
        "guest_contact_sharing_approved": True,
    }


def validate_authority(value: dict) -> None:
    if (
        value.get("schema_version") != 2
        or value.get("personal_transactions_enabled") is not True
        or value.get("restaurant_reservations_enabled") is not True
        or value.get("shopping_checkout_enabled") is not False
        or value.get("travel_booking_enabled") is not False
        or not isinstance(value.get("operations"), list)
        or OPERATION not in value["operations"]
    ):
        raise RestaurantReservationProbeError(
            "Deployed transaction authority is not the reviewed bounded restaurant scope."
        )


def validate_review_surface(value: dict) -> None:
    transaction = value.get("transaction")
    terms = value.get("terms")
    reservation = value.get("reservation")
    if (
        not isinstance(transaction, dict)
        or transaction.get("transaction_kind") != "restaurant_reservation"
        or transaction.get("provider") != "opentable"
        or transaction.get("state") != "terms_ready"
        or transaction.get("currency") != "XXX"
        or not isinstance(terms, dict)
        or terms.get("currency") != "XXX"
        or terms.get("total_minor") != 0
        or not isinstance(reservation, dict)
        or not isinstance(reservation.get("availability_sha256"), str)
        or len(reservation["availability_sha256"]) != 64
        or reservation.get("availability", {}).get("payment_required") is not False
    ):
        raise RestaurantReservationProbeError(
            "Reservation review did not preserve the exact no-payment boundary."
        )


def wait_action(
    client: httpx.Client,
    token: str,
    action_id: str,
    timeout: int,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = request_json(
            client.get(f"/api/v1/actions/{action_id}", headers=auth(token)),
            "read reservation action",
        )
        if value.get("state") in {
            "succeeded",
            "failed",
            "cancelled",
            "outcome_unknown",
        }:
            return value
        time.sleep(1)
    raise RestaurantReservationProbeError(
        "Timed out waiting for the OpenTable reservation action."
    )


def receipt_evidence(value: dict) -> str:
    receipt = value.get("receipt")
    if (
        value.get("state") != "succeeded"
        or not isinstance(receipt, dict)
        or receipt.get("provider") != "opentable"
        or receipt.get("status") != "reservation_confirmed"
        or receipt.get("payment_required") is not False
        or not receipt.get("confirmation_number")
    ):
        raise RestaurantReservationProbeError(
            "OpenTable did not return the exact no-payment confirmation receipt."
        )
    return hashlib.sha256(
        json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the guarded TX-06 OpenTable sandbox reservation qualification."
        )
    )
    parser.add_argument("--base-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    try:
        require_guard()
        if args.timeout < 1:
            raise RestaurantReservationProbeError("Timeout must be positive.")
        base_url = env("SHUDDHO_STAGING_API_BASE_URL").rstrip("/")
        if not base_url.startswith("https://"):
            raise RestaurantReservationProbeError(
                "SHUDDHO_STAGING_API_BASE_URL must use HTTPS."
            )
        token = env("SHUDDHO_STAGING_TOKEN_A")
        payload = reservation_payload()
        marker = uuid.uuid4().hex

        with httpx.Client(
            base_url=base_url,
            timeout=30,
            follow_redirects=False,
        ) as client:
            authority = request_json(
                client.get(
                    "/api/v1/transaction-authority-manifest",
                    headers=auth(token),
                ),
                "read transaction authority",
            )
            validate_authority(authority)

            review = request_json(
                client.post(
                    "/api/v1/restaurant-reservations",
                    headers=auth(token)
                    | {"Idempotency-Key": "tx28-restaurant-" + marker},
                    json=payload,
                ),
                "create restaurant reservation review",
                expected=201,
            )
            validate_review_surface(review)
            transaction = review["transaction"]
            terms = review["terms"]

            started = request_json(
                client.post(
                    f"/api/v1/transactions/{transaction['id']}/review",
                    headers=auth(token),
                    json={"expected_revision": transaction["revision"]},
                ),
                "start exact reservation review",
            )
            confirmed = request_json(
                client.post(
                    f"/api/v1/transactions/{transaction['id']}/review/confirm",
                    headers=auth(token),
                    json={
                        "expected_revision": started["revision"],
                        "terms_sha256": terms["terms_sha256"],
                    },
                ),
                "confirm exact reservation review",
            )
            prepared = request_json(
                client.post(
                    f"/api/v1/restaurant-reservations/{transaction['id']}/prepare-action",
                    headers=auth(token),
                    json={
                        "expected_revision": confirmed["transaction"]["revision"],
                        "terms_sha256": terms["terms_sha256"],
                    },
                ),
                "prepare bound reservation action",
                expected=201,
            )
            action = prepared.get("action")
            if (
                not isinstance(action, dict)
                or action.get("state") != "awaiting_approval"
                or action.get("receipt") is not None
                or action.get("preview", {}).get("payload", {}).get(
                    "no_payment_required"
                ) is not True
            ):
                raise RestaurantReservationProbeError(
                    "Reservation action did not stop at explicit approval."
                )

            rejected = client.post(
                f"/api/v1/actions/{action['id']}/approve",
                headers=auth(token),
                json={"preview_hash": wrong_hash(action["preview_hash"])},
            )
            if rejected.status_code != 409:
                raise RestaurantReservationProbeError(
                    "Wrong-hash reservation approval was not rejected."
                )

            request_json(
                client.post(
                    f"/api/v1/actions/{action['id']}/approve",
                    headers=auth(token),
                    json={"preview_hash": action["preview_hash"]},
                ),
                "approve reservation action",
                expected=202,
            )
            terminal = wait_action(client, token, action["id"], args.timeout)
            provider_hash = receipt_evidence(terminal)

        evidence = {}
        if args.base_evidence:
            evidence = json.loads(args.base_evidence.read_text(encoding="utf-8"))
            if not isinstance(evidence, dict):
                raise RestaurantReservationProbeError(
                    "Base evidence must contain a JSON object."
                )
        evidence["restaurant_reservations"] = {
            "status": "passed",
            "evidence": (
                "OpenTable sandbox no-payment reservation passed availability "
                "binding, separate review/approval, wrong-hash denial, one "
                "provider confirmation receipt, and zero payment escalation."
            ),
            "verified_at": utcnow_iso(),
            "operation": OPERATION,
            "provider_evidence_sha256": provider_hash,
        }
        args.output.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "passed",
            "operation": OPERATION,
            "provider_evidence_sha256": provider_hash,
            "output": str(args.output),
        }, indent=2))
    except (
        RestaurantReservationProbeError,
        OSError,
        ValueError,
        httpx.HTTPError,
    ) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
