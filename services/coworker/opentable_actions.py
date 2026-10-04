"""Bounded OpenTable Consumer API v2 restaurant reservation adapter.

TX-06 supports standard no-payment reservations only. Provider hosts and paths
are code-owned; caller content cannot select arbitrary egress.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from .action_registry import stable_digest
from .connector_actions import ConnectorFailure

SCOPES = {"restaurant_reservation": "DEFAULT"}
SERVICE_SUBJECT = "opentable-partner"
SERVICE_ACCOUNT = "opentable-service@shuddho.invalid"

OAUTH_HOSTS = {
    "sandbox": "https://oauth-pp.opentable.com",
    "production": "https://oauth.opentable.com",
}
API_HOSTS = {
    "sandbox": "https://platform.otqa.com",
    "production": "https://platform.opentable.com",
}


class OpenTableFailure(ConnectorFailure):
    def __init__(self, code="provider_unavailable", *, definitive=False):
        super().__init__(code, definitive=definitive)


def local_provider_time(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OpenTableFailure("reservation_time_invalid", definitive=True)
    return parsed.replace(tzinfo=None).isoformat(timespec="minutes")


def _standard_slot(value: dict, payload: dict) -> dict | None:
    try:
        if local_provider_time(str(value.get("time"))) != local_provider_time(payload["date_time"]):
            return None
    except (OpenTableFailure, ValueError, TypeError):
        return None
    types = value.get("availability_types")
    if not isinstance(types, list):
        return None
    for item in types:
        if not isinstance(item, dict) or str(item.get("type", "")).casefold() != "standard":
            continue
        policy = item.get("cancellationPolicy", item.get("cancellation_policy"))
        # TX-06 deliberately excludes deposit/hold/fee-bearing inventory.
        if policy is not None and policy != {}:
            return None
        dining = item.get("diningArea", item.get("dining_area"))
        requested_area = payload.get("dining_area_id")
        requested_environment = payload.get("environment")
        selected_area = None
        if requested_area is not None:
            if not isinstance(dining, list):
                continue
            selected_area = next(
                (
                    entry
                    for entry in dining
                    if isinstance(entry, dict) and entry.get("id") == requested_area
                ),
                None,
            )
            if selected_area is None:
                continue
            attributes = selected_area.get("attributes")
            if (
                isinstance(attributes, list)
                and payload["reservation_attribute"] not in attributes
            ):
                continue
            if (
                requested_environment is not None
                and selected_area.get("environment") != requested_environment
            ):
                continue
        return {
            "restaurant_id": payload["restaurant_id"],
            "party_size": payload["party_size"],
            "date_time": local_provider_time(payload["date_time"]),
            "reservation_attribute": payload["reservation_attribute"],
            "dining_area_id": requested_area,
            "environment": (
                selected_area.get("environment")
                if selected_area is not None
                else requested_environment
            ),
            "availability_type": "Standard",
            "cancellation_policy": None,
            "payment_required": False,
            "experience": None,
        }
    return None


class OpenTableActions:
    provider_name = "opentable"
    scopes = SCOPES

    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport
        self.oauth_host = OAUTH_HOSTS[settings.opentable_environment]
        self.api_host = API_HOSTS[settings.opentable_environment]

    def authorization_url(self, state, verifier, capability):
        raise OpenTableFailure("service_connection_only", definitive=True)

    async def exchange(self, code, verifier):
        raise OpenTableFailure("service_connection_only", definitive=True)

    async def refresh(self, refresh_token, capability):
        return await self._access_token()

    async def access_from_credentials(self, credentials, capability):
        if capability != "restaurant_reservation" or credentials != {"service": "opentable"}:
            raise OpenTableFailure("connection_authorization", definitive=True)
        return await self._access_token()

    async def profile(self, access_token):
        if not isinstance(access_token, str) or not access_token:
            raise OpenTableFailure("oauth_response_invalid", definitive=True)
        return {"sub": SERVICE_SUBJECT, "email": SERVICE_ACCOUNT}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        params: dict | None = None,
        body: dict | None = None,
        headers: dict | None = None,
        basic_auth: tuple[str, str] | None = None,
    ) -> tuple[int, dict, httpx.Headers]:
        token_url = self.oauth_host + "/api/v2/oauth/token"
        availability_path = re.fullmatch(
            re.escape(self.api_host) + r"/v2/availability/[1-9][0-9]{0,11}",
            url,
        )
        booking_path = re.fullmatch(
            re.escape(self.api_host) + r"/v2/booking/[1-9][0-9]{0,11}/reservations",
            url,
        )
        if url != token_url and not availability_path and not booking_path:
            raise ValueError("Unknown OpenTable endpoint")
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **dict(headers or {}),
        }
        if token is not None:
            request_headers["Authorization"] = "Bearer " + token
        if basic_auth is not None:
            encoded = base64.b64encode(
                (basic_auth[0] + ":" + basic_auth[1]).encode("utf-8")
            ).decode("ascii")
            request_headers["Authorization"] = "Basic " + encoded
            request_headers["Content-Length"] = "0"
        try:
            async with asyncio.timeout(20):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=15,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        method,
                        url,
                        params=params,
                        json=body,
                        headers=request_headers,
                    ) as response:
                        raw_value = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw_value) + len(chunk) > 256 * 1024:
                                raise OpenTableFailure(
                                    "provider_response_invalid",
                                    definitive=True,
                                )
                            raw_value.extend(chunk)
                        raw = bytes(raw_value)
        except (TimeoutError, httpx.TimeoutException, httpx.TransportError):
            raise OpenTableFailure("provider_outcome_unknown") from None
        try:
            value = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            raise OpenTableFailure("provider_response_invalid", definitive=True) from None
        if not isinstance(value, dict):
            raise OpenTableFailure("provider_response_invalid", definitive=True)
        return response.status_code, value, response.headers

    async def _access_token(self) -> dict:
        status, value, _headers = await self._request(
            "POST",
            self.oauth_host + "/api/v2/oauth/token",
            params={"grant_type": "client_credentials"},
            basic_auth=(
                self.settings.opentable_client_id,
                self.settings.opentable_client_secret,
            ),
        )
        token = value.get("access_token")
        if status != 200 or not isinstance(token, str) or not token:
            raise OpenTableFailure("connection_authorization", definitive=True)
        scope = value.get("scope", "DEFAULT")
        if not isinstance(scope, str) or "DEFAULT" not in scope.split():
            raise OpenTableFailure("connection_scope_missing", definitive=True)
        return {
            "access_token": token,
            "scope": scope,
            "token_type": "Bearer",
        }

    async def service_availability(self, payload: dict) -> dict:
        token = await self._access_token()
        return await self.availability(payload, token["access_token"])

    async def availability(self, payload: dict, access_token: str) -> dict:
        rid = payload["restaurant_id"]
        status, value, headers = await self._request(
            "GET",
            f"{self.api_host}/v2/availability/{rid}",
            token=access_token,
            params={
                "start_date_time": local_provider_time(payload["date_time"]),
                "forward_minutes": 0,
                "backward_minutes": 0,
                "party_size": payload["party_size"],
                "require_attributes": payload["reservation_attribute"],
                "include_credit_card_results": "false",
                "include_experiences": "false",
            },
        )
        if status != 200:
            raise OpenTableFailure(
                "reservation_availability_unavailable",
                definitive=status in {400, 401, 403, 404},
            )
        if value.get("rid") != rid or value.get("party_size") != payload["party_size"]:
            raise OpenTableFailure("provider_response_invalid", definitive=True)
        available = value.get("times_available")
        if not isinstance(available, list):
            raise OpenTableFailure("provider_response_invalid", definitive=True)
        selected = next(
            (
                slot
                for item in available
                if isinstance(item, dict)
                and (slot := _standard_slot(item, payload)) is not None
            ),
            None,
        )
        if selected is None:
            raise OpenTableFailure("reservation_not_available", definitive=True)
        return {
            "selection": selected,
            "availability_sha256": stable_digest(selected),
            "provider_request_id": headers.get("OT-RequestId"),
        }

    async def execute(self, action: dict, access_token: str, attachments=None) -> dict:
        payload = action["preview"]["payload"]
        fresh = await self.availability(payload, access_token)
        if fresh["availability_sha256"] != payload["availability_sha256"]:
            raise OpenTableFailure("reservation_availability_changed", definitive=True)
        body = {
            "date_time": local_provider_time(payload["date_time"]),
            "party_size": payload["party_size"],
            "first_name": payload["guest_first_name"],
            "last_name": payload["guest_last_name"],
            "email_address": payload["guest_email"],
            "phone": {
                "number": payload["guest_phone_number"].lstrip("+"),
                "country_code": payload["guest_phone_country_code"],
                "phone_type": "mobile",
            },
            "reservation_attribute": payload["reservation_attribute"],
            "special_request": payload["special_request"],
            "restaurant_email_marketing_opt_in": "false",
        }
        if payload.get("dining_area_id") is not None:
            body["dining_area_id"] = payload["dining_area_id"]
        if payload.get("environment") is not None:
            body["environment"] = payload["environment"]
        status, value, headers = await self._request(
            "POST",
            f"{self.api_host}/v2/booking/{payload['restaurant_id']}/reservations",
            token=access_token,
            body=body,
            headers={"X-Request-Id": action["id"]},
        )
        if status in {200, 201}:
            confirmation = value.get("confirmation_number")
            try:
                confirmed_time = local_provider_time(str(value.get("date_time")))
            except (OpenTableFailure, ValueError, TypeError):
                confirmed_time = None
            if (
                not isinstance(confirmation, int)
                or value.get("party_size") != payload["party_size"]
                or confirmed_time != local_provider_time(payload["date_time"])
                or value.get("post_booking_required_action") not in {None, "None"}
                or value.get("payment") is not None
            ):
                # The provider may have created a reservation, so never invite
                # a second booking attempt from an ambiguous success response.
                raise OpenTableFailure("provider_receipt_invalid")
            return {
                "provider": "opentable",
                "status": "reservation_confirmed",
                "confirmation_number": confirmation,
                "restaurant_id": payload["restaurant_id"],
                "restaurant_name": payload["restaurant_name"],
                "date_time": value["date_time"],
                "time_zone": payload["time_zone"],
                "party_size": value["party_size"],
                "reservation_attribute": payload["reservation_attribute"],
                "dining_area_id": payload.get("dining_area_id"),
                "environment": payload.get("environment"),
                "manage_reservation_url": value.get("manage_reservation_url"),
                "booking_policy_message": value.get("message"),
                "provider_request_id": headers.get("OT-RequestId"),
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "payment_required": False,
            }
        # Provider-documented validation/business-rule failures indicate that
        # this request did not produce a confirmed reservation.
        if status in {400, 404, 409, 422}:
            code = "reservation_not_available"
            text = json.dumps(value, ensure_ascii=False).casefold()
            if "creditcardrequired" in text or "credit card required" in text:
                code = "reservation_payment_required"
            elif "overlapping" in text:
                code = "reservation_overlap"
            raise OpenTableFailure(code, definitive=True)
        # 401/403 cannot safely be treated as a completed booking.
        if status in {401, 403}:
            raise OpenTableFailure("connection_authorization", definitive=True)
        raise OpenTableFailure("provider_outcome_unknown")

    async def reconcile(self, action: dict, access_token: str):
        # Consumer Booking v2 does not provide a TX-06-qualified read-only
        # confirmation lookup. Never turn reconciliation into a second POST.
        return None
