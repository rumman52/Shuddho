"""Microsoft Graph delegated connector for approved email/calendar actions."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from .action_schemas import address
from .connector_actions import ConnectorFailure


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
ME_URL = GRAPH_ROOT + "/me"
SEND_URL = GRAPH_ROOT + "/me/sendMail"
EVENTS_URL = GRAPH_ROOT + "/me/events"
SCOPES = {
    "email": "Mail.Send",
    "calendar": "Calendars.ReadWrite",
}
PROFILE_SCOPE = "User.Read"


def _tenant(settings) -> str:
    return settings.microsoft_tenant


def _auth_url(settings) -> str:
    return (
        "https://login.microsoftonline.com/"
        + _tenant(settings)
        + "/oauth2/v2.0/authorize"
    )


def _token_url(settings) -> str:
    return (
        "https://login.microsoftonline.com/"
        + _tenant(settings)
        + "/oauth2/v2.0/token"
    )


def _scope(capability: str) -> str:
    if capability not in SCOPES:
        raise ValueError("Unsupported Microsoft capability")
    return "openid offline_access " + PROFILE_SCOPE + " " + SCOPES[capability]


def _graph_datetime(value: str) -> dict:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Calendar timestamps must include an offset.")
    utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return {"dateTime": utc.isoformat(timespec="seconds"), "timeZone": "UTC"}


def _same_graph_time(actual: dict, expected: dict) -> bool:
    try:
        if actual.get("timeZone") != "UTC" or expected.get("timeZone") != "UTC":
            return False
        left = datetime.fromisoformat(str(actual["dateTime"]).replace("Z", "+00:00"))
        right = datetime.fromisoformat(str(expected["dateTime"]).replace("Z", "+00:00"))
        if left.tzinfo is None:
            left = left.replace(tzinfo=timezone.utc)
        if right.tzinfo is None:
            right = right.replace(tzinfo=timezone.utc)
        return left.astimezone(timezone.utc) == right.astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return False


def event_transaction_id(action_id: str) -> str:
    return "shuddho-" + hashlib.sha256(action_id.encode()).hexdigest()[:48]


def event_body(action: dict) -> dict:
    payload = action["preview"]["payload"]
    return {
        "subject": payload["title"],
        "body": {
            "contentType": "text",
            "content": payload["description"],
        },
        "location": {"displayName": payload["location"]},
        "start": _graph_datetime(payload["start_at"]),
        "end": _graph_datetime(payload["end_at"]),
        "attendees": [
            {
                "emailAddress": {"address": email},
                "type": "required",
            }
            for email in payload["attendees"]
        ],
        "isReminderOn": False,
        "transactionId": event_transaction_id(action["id"]),
    }


def email_body(action: dict, attachments=None) -> dict:
    payload = action["preview"]["payload"]
    attachments = attachments or []

    def recipients(values):
        return [
            {"emailAddress": {"address": value}}
            for value in values
        ]

    message = {
        "subject": payload["subject"],
        "body": {
            "contentType": "Text",
            "content": payload["body"],
        },
        "toRecipients": recipients(payload["to"]),
        "ccRecipients": recipients(payload["cc"]),
        "bccRecipients": recipients(payload["bcc"]),
    }
    if attachments:
        message["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": item["filename"],
                "contentType": item["content_type"],
                "contentBytes": base64.b64encode(item["body"]).decode("ascii"),
            }
            for item in attachments
        ]
    return {
        "message": message,
        "saveToSentItems": True,
    }


class MicrosoftActions:
    provider_name = "microsoft"
    scopes = SCOPES

    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def authorization_url(self, state, verifier, capability):
        challenge = (
            __import__("base64")
            .urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return _auth_url(self.settings) + "?" + urlencode({
            "client_id": self.settings.microsoft_client_id,
            "response_type": "code",
            "redirect_uri": self.settings.microsoft_redirect_uri,
            "response_mode": "query",
            "scope": _scope(capability),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })

    async def request(
        self,
        method,
        url,
        *,
        token=None,
        data=None,
        body=None,
        params=None,
        allow_empty=False,
    ):
        token_url = _token_url(self.settings)
        event_pattern = re.escape(EVENTS_URL) + r"/[A-Za-z0-9._~%-]{1,512}"
        if (
            url not in {token_url, ME_URL, SEND_URL, EVENTS_URL}
            and not re.fullmatch(event_pattern, url)
        ):
            raise ValueError("Unknown connector endpoint")
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
                        headers={
                            "Authorization": "Bearer " + token
                        } if token else {},
                        data=data,
                        json=body,
                        params=params,
                    ) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            code = (
                                "connection_authorization"
                                if response.status_code in {401, 403}
                                else "provider_rejected"
                            )
                            raise ConnectorFailure(
                                code,
                                definitive=response.status_code
                                in {400, 401, 403, 404, 410, 422, 429},
                            )
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > 256 * 1024:
                                raise ConnectorFailure(
                                    "provider_response_invalid",
                                    definitive=True,
                                )
                            raw.extend(chunk)
            if not raw:
                if allow_empty:
                    return {}
                raise ConnectorFailure(
                    "provider_response_invalid",
                    definitive=True,
                )
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except ConnectorFailure:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError):
            raise ConnectorFailure() from None

    async def exchange(self, code, verifier):
        result = await self.request(
            "POST",
            _token_url(self.settings),
            data={
                "client_id": self.settings.microsoft_client_id,
                "client_secret": self.settings.microsoft_client_secret,
                "code": code,
                "redirect_uri": self.settings.microsoft_redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
        self._access(result)
        if (
            not isinstance(result.get("refresh_token"), str)
            or not 1 <= len(result["refresh_token"]) <= 8192
            or not isinstance(result.get("scope"), str)
        ):
            raise ConnectorFailure("oauth_refresh_missing", definitive=True)
        return result

    @staticmethod
    def _access(result):
        token = result.get("access_token")
        if (
            str(result.get("token_type", "")).lower() != "bearer"
            or not isinstance(token, str)
            or not 1 <= len(token) <= 8192
            or any(char.isspace() for char in token)
        ):
            raise ConnectorFailure("oauth_response_invalid", definitive=True)
        return token

    async def refresh(self, refresh_token, capability):
        result = await self.request(
            "POST",
            _token_url(self.settings),
            data={
                "client_id": self.settings.microsoft_client_id,
                "client_secret": self.settings.microsoft_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "scope": _scope(capability),
            },
        )
        self._access(result)
        return result

    async def profile(self, access_token):
        result = await self.request(
            "GET",
            ME_URL,
            token=access_token,
            params={"$select": "id,mail,userPrincipalName"},
        )
        try:
            subject = result["id"]
            email = result.get("mail") or result["userPrincipalName"]
            if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
                raise ValueError()
            return {"sub": subject, "email": address(email)}
        except (KeyError, TypeError, ValueError):
            raise ConnectorFailure("oauth_identity_invalid", definitive=True) from None

    async def execute(self, action, access_token, attachments=None):
        if action["kind"] in {"email_send", "email_send_with_attachments"}:
            await self.request(
                "POST",
                SEND_URL,
                token=access_token,
                body=email_body(action, attachments),
                allow_empty=True,
            )
            return {
                "provider": "microsoft",
                "status": "accepted_by_microsoft_graph",
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }
        if action["kind"] != "calendar_create":
            raise ValueError("Unknown action kind")
        result = await self.request(
            "POST",
            EVENTS_URL,
            token=access_token,
            body=event_body(action),
        )
        return self.calendar_receipt(action, result)

    @staticmethod
    def calendar_receipt(action, result):
        expected = event_body(action)
        try:
            provider_id = result["id"]
            if not isinstance(provider_id, str) or not 1 <= len(provider_id) <= 512:
                raise ValueError()
            if result.get("subject") != expected["subject"]:
                raise ValueError()
            if result.get("location", {}).get("displayName", "") != expected["location"]["displayName"]:
                raise ValueError()
            if not _same_graph_time(result.get("start", {}), expected["start"]):
                raise ValueError()
            if not _same_graph_time(result.get("end", {}), expected["end"]):
                raise ValueError()
            actual_attendees = {
                item.get("emailAddress", {}).get("address", "").casefold()
                for item in result.get("attendees", [])
            }
            expected_attendees = {
                item["emailAddress"]["address"].casefold()
                for item in expected["attendees"]
            }
            if actual_attendees != expected_attendees:
                raise ValueError()
            if result.get("transactionId") not in {
                None,
                expected["transactionId"],
            }:
                raise ValueError()
            if result.get("isCancelled") is True:
                raise ValueError()
            return {
                "provider": "microsoft",
                "provider_id": provider_id,
                "status": "event_created",
                "calendar": "primary",
                "transaction_id": expected["transactionId"],
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }
        except (KeyError, TypeError, ValueError):
            raise ConnectorFailure(
                "provider_receipt_invalid",
                definitive=True,
            ) from None

    async def reconcile(self, action, access_token):
        # If a successful event response was persisted, execute() already
        # completed the action. After a lost POST response Microsoft Graph
        # doesn't expose a deterministic event-id lookup by transactionId in
        # this contract, so Shuddho does not issue a second mutation.
        return None
