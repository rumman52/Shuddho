"""Microsoft Graph delegated connector for approved email/calendar actions."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx

from .action_schemas import address
from .connector_actions import ConnectorFailure


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
ME_URL = GRAPH_ROOT + "/me"
SEND_URL = GRAPH_ROOT + "/me/sendMail"
EVENTS_URL = GRAPH_ROOT + "/me/events"
MAIL_DELTA_URL = GRAPH_ROOT + "/me/mailFolders/inbox/messages/delta"
CALENDAR_DELTA_URL = GRAPH_ROOT + "/me/calendarView/delta"
SUBSCRIPTIONS_URL = GRAPH_ROOT + "/subscriptions"
SCOPES = {
    "email": "Mail.Send",
    "calendar": "Calendars.ReadWrite",
    "email_read": "Mail.ReadBasic",
    "calendar_read": "Calendars.Read",
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
    reminder_minutes = (
        payload["reminder_minutes_before_start"]
        if payload["kind"] == "calendar_create_with_reminder"
        else None
    )
    body = {
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
        "isReminderOn": reminder_minutes is not None,
        "transactionId": event_transaction_id(action["id"]),
    }
    if reminder_minutes is not None:
        body["reminderMinutesBeforeStart"] = reminder_minutes
    return body

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

    @staticmethod
    def _graph_delta_url(url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if (
            parsed.scheme != "https"
            or parsed.hostname != "graph.microsoft.com"
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
            or parsed.fragment
            or len(url) > 8192
        ):
            return False
        return parsed.path in {
            "/v1.0/me/mailFolders('inbox')/messages/delta",
            "/v1.0/me/mailFolders/inbox/messages/delta",
            "/v1.0/me/calendarView/delta",
        }

    @staticmethod
    def _safe_excerpt(value, limit=1000):
        if not isinstance(value, str):
            return ""
        value = re.sub(r"https?://\S+", "[link removed]", value, flags=re.IGNORECASE)
        value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
        return re.sub(r"\s+", " ", value).strip()[:limit]

    async def request(
        self,
        method,
        url,
        *,
        token=None,
        data=None,
        body=None,
        params=None,
        headers=None,
        allow_empty=False,
    ):
        token_url = _token_url(self.settings)
        event_pattern = re.escape(EVENTS_URL) + r"/[A-Za-z0-9._~%-]{1,512}"
        subscription_pattern = re.escape(SUBSCRIPTIONS_URL) + r"/[A-Za-z0-9._~%-]{1,512}"
        delta_url = self._graph_delta_url(url)
        if (
            url not in {
                token_url, ME_URL, SEND_URL, EVENTS_URL,
                MAIL_DELTA_URL, CALENDAR_DELTA_URL, SUBSCRIPTIONS_URL,
            }
            and not re.fullmatch(event_pattern, url)
            and not re.fullmatch(subscription_pattern, url)
            and not delta_url
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
                        headers=(
                            {**(headers or {}), "Authorization": "Bearer " + token}
                            if token else dict(headers or {})
                        ),
                        data=data,
                        json=body,
                        params=params,
                    ) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            is_cursor_request = (
                                delta_url
                                and url not in {MAIL_DELTA_URL, CALENDAR_DELTA_URL}
                            )
                            if (
                                is_cursor_request
                                and response.status_code in {400, 404, 410}
                            ):
                                raise ConnectorFailure(
                                    "provider_cursor_invalid",
                                    definitive=True,
                                )
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

    @staticmethod
    def _recipient_addresses(values) -> list[str]:
        result = []
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            email = item.get("emailAddress")
            value = email.get("address") if isinstance(email, dict) else None
            if isinstance(value, str) and len(value) <= 254:
                result.append(value)
            if len(result) >= 20:
                break
        return result

    async def read_email(
        self,
        access_token: str,
        cursor: str | None,
        max_items: int,
    ) -> dict:
        max_items = max(1, min(int(max_items), 30))
        url = cursor or MAIL_DELTA_URL
        params = None if cursor else {
            "$top": str(max_items),
            "$select": (
                "id,conversationId,receivedDateTime,lastModifiedDateTime,"
                "subject,sender,toRecipients,ccRecipients,isRead,hasAttachments"
            ),
        }
        result = await self.request("GET", url, token=access_token, params=params)
        next_cursor = result.get("@odata.nextLink") or result.get("@odata.deltaLink")
        if (
            not isinstance(next_cursor, str)
            or not self._graph_delta_url(next_cursor)
            or len(next_cursor) > 8192
        ):
            raise ConnectorFailure("provider_response_invalid", definitive=True)
        changes = []
        now_version = datetime.now(timezone.utc).isoformat()
        values = result.get("value")
        if not isinstance(values, list) or len(values) > max_items:
            raise ConnectorFailure("provider_snapshot_limit", definitive=True)
        for item in values:
            if not isinstance(item, dict):
                continue
            resource_id = item.get("id")
            if not isinstance(resource_id, str) or not 1 <= len(resource_id) <= 512:
                continue
            removed = isinstance(item.get("@removed"), dict)
            version = item.get("lastModifiedDateTime") or now_version
            if not isinstance(version, str) or not version:
                version = now_version
            sender = item.get("sender")
            sender_address = ""
            if isinstance(sender, dict):
                email = sender.get("emailAddress")
                if isinstance(email, dict) and isinstance(email.get("address"), str):
                    sender_address = email["address"][:254]
            payload = {
                "kind": "email",
                "message_id": resource_id,
            }
            if not removed:
                payload.update({
                    "conversation_id": item.get("conversationId")
                    if isinstance(item.get("conversationId"), str) else None,
                    "from": sender_address,
                    "to": self._recipient_addresses(item.get("toRecipients")),
                    "cc": self._recipient_addresses(item.get("ccRecipients")),
                    "subject": self._safe_excerpt(item.get("subject"), 300),
                    "received_at": item.get("receivedDateTime")
                    if isinstance(item.get("receivedDateTime"), str) else None,
                    "is_read": item.get("isRead")
                    if isinstance(item.get("isRead"), bool) else None,
                    "has_attachments": item.get("hasAttachments")
                    if isinstance(item.get("hasAttachments"), bool) else None,
                    "authority": "provider_content_is_untrusted_data",
                })
            changes.append({
                "resource_id": resource_id,
                "provider_version": version[:128],
                "state": "deleted" if removed else "active",
                "payload": payload,
            })
        return {"cursor": next_cursor, "changes": changes}

    async def read_calendar(
        self,
        access_token: str,
        cursor: str | None,
        max_items: int,
    ) -> dict:
        max_items = max(1, min(int(max_items), 50))
        url = cursor or CALENDAR_DELTA_URL
        if cursor:
            params = None
        else:
            now = datetime.now(timezone.utc)
            params = {
                "startDateTime": (now - timedelta(days=7)).isoformat(),
                "endDateTime": (now + timedelta(days=60)).isoformat(),
            }
        result = await self.request(
            "GET",
            url,
            token=access_token,
            params=params,
            headers={"Prefer": f"odata.maxpagesize={max_items}"},
        )
        next_cursor = result.get("@odata.nextLink") or result.get("@odata.deltaLink")
        if (
            not isinstance(next_cursor, str)
            or not self._graph_delta_url(next_cursor)
            or len(next_cursor) > 8192
        ):
            raise ConnectorFailure("provider_response_invalid", definitive=True)
        changes = []
        now_version = datetime.now(timezone.utc).isoformat()
        values = result.get("value")
        if not isinstance(values, list) or len(values) > max_items:
            raise ConnectorFailure("provider_snapshot_limit", definitive=True)
        for item in values:
            if not isinstance(item, dict):
                continue
            resource_id = item.get("id")
            if not isinstance(resource_id, str) or not 1 <= len(resource_id) <= 512:
                continue
            removed = isinstance(item.get("@removed"), dict) or item.get("isCancelled") is True
            version = item.get("lastModifiedDateTime") or now_version
            if not isinstance(version, str) or not version:
                version = now_version
            attendees = []
            for entry in item.get("attendees", []) if isinstance(item.get("attendees"), list) else []:
                if not isinstance(entry, dict):
                    continue
                email = entry.get("emailAddress")
                address_value = email.get("address") if isinstance(email, dict) else None
                if isinstance(address_value, str):
                    attendees.append(address_value[:254])
                if len(attendees) >= 20:
                    break
            payload = {"kind": "calendar_event", "event_id": resource_id}
            if not removed:
                location = item.get("location")
                display_name = (
                    location.get("displayName")
                    if isinstance(location, dict) else ""
                )
                payload.update({
                    "status": "confirmed",
                    "summary": self._safe_excerpt(item.get("subject"), 300),
                    "description": self._safe_excerpt(item.get("bodyPreview"), 1000),
                    "location": self._safe_excerpt(display_name, 300),
                    "start": item.get("start") if isinstance(item.get("start"), dict) else {},
                    "end": item.get("end") if isinstance(item.get("end"), dict) else {},
                    "attendees": attendees,
                    "authority": "provider_content_is_untrusted_data",
                })
            changes.append({
                "resource_id": resource_id,
                "provider_version": version[:128],
                "state": "deleted" if removed else "active",
                "payload": payload,
            })
        return {"cursor": next_cursor, "changes": changes}

    async def read_connected(
        self,
        capability: str,
        access_token: str,
        cursor: str | None,
        max_items: int,
    ) -> dict:
        if capability == "email_read":
            return await self.read_email(access_token, cursor, max_items)
        if capability == "calendar_read":
            return await self.read_calendar(access_token, cursor, max_items)
        raise ConnectorFailure("connector_read_unregistered", definitive=True)

    async def start_read_watch(
        self,
        capability: str,
        access_token: str,
        *,
        channel_id: str,
        callback_url: str,
        channel_token: str,
        gmail_topic: str,
    ) -> dict:
        if capability == "email_read":
            resource = "/me/mailFolders/inbox/messages"
        elif capability == "calendar_read":
            resource = "/me/events"
        else:
            raise ConnectorFailure("connector_read_unregistered", definitive=True)
        expiration = datetime.now(timezone.utc) + timedelta(days=2)
        result = await self.request(
            "POST",
            SUBSCRIPTIONS_URL,
            token=access_token,
            body={
                "changeType": "created,updated,deleted",
                "notificationUrl": callback_url,
                "resource": resource,
                "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
                "clientState": channel_token,
            },
        )
        provider_id = result.get("id")
        resource_result = result.get("resource")
        expires = result.get("expirationDateTime")
        if (
            not isinstance(provider_id, str)
            or not 1 <= len(provider_id) <= 512
            or resource_result != resource
            or not isinstance(expires, str)
        ):
            raise ConnectorFailure("provider_response_invalid", definitive=True)
        try:
            expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise ConnectorFailure("provider_response_invalid", definitive=True) from None
        return {
            "provider_subscription_id": provider_id,
            "provider_resource_id": resource,
            "provider_cursor_hint": None,
            "expires_at_ms": int(expires_at.timestamp() * 1000),
        }

    async def stop_read_watch(
        self,
        capability: str,
        access_token: str,
        *,
        provider_subscription_id: str | None,
        provider_resource_id: str | None,
    ) -> None:
        if not provider_subscription_id:
            return
        await self.request(
            "DELETE",
            SUBSCRIPTIONS_URL + "/" + provider_subscription_id,
            token=access_token,
            allow_empty=True,
        )

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
        if action["kind"] not in {"calendar_create", "calendar_create_with_reminder"}:
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
            if result.get("isReminderOn") != expected["isReminderOn"]:
                raise ValueError()
            if expected["isReminderOn"] and result.get("reminderMinutesBeforeStart") != expected["reminderMinutesBeforeStart"]:
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
