"""Fixed Google endpoints. OAuth tokens never enter model or workflow history."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from urllib.parse import urlencode

import httpx

from .action_schemas import address
from .connector_actions import ConnectorFailure

SCOPES = {
    "email": "https://www.googleapis.com/auth/gmail.send",
    "calendar": "https://www.googleapis.com/auth/calendar.events.owned",
}
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class GoogleFailure(ConnectorFailure):
    def __init__(self, code="provider_unavailable", *, definitive=False):
        super().__init__(code, definitive=definitive)


def event_id(action_id):
    # UUID hex is a subset of Google's base32hex event ID alphabet.
    return "shuddho" + action_id.replace("-", "")


def event_body(action):
    p = action["preview"]["payload"]
    return {"id": event_id(action["id"]), "summary": p["title"], "description": html.escape(p["description"]).replace("\n", "<br>"), "location": p["location"],
            "start": {"dateTime": p["start_at"], "timeZone": p["time_zone"]},
            "end": {"dateTime": p["end_at"], "timeZone": p["time_zone"]},
            "attendees": [{"email": email} for email in p["attendees"]],
            "reminders": {"useDefault": False, "overrides": []},
            "guestsCanModify": False, "guestsCanInviteOthers": False, "guestsCanSeeOtherGuests": True,
            "extendedProperties": {"private": {"shuddhoAction": action["id"], "shuddhoApproval": action["preview_hash"]}}}


def email_raw(action, attachments=None):
    preview, p = action["preview"], action["preview"]["payload"]
    attachments = attachments or []
    message = EmailMessage(policy=SMTP)
    message["From"], message["To"], message["Subject"] = preview["account"], ", ".join(p["to"]), p["subject"]
    if p["cc"]:
        message["Cc"] = ", ".join(p["cc"])
    if p["bcc"]:
        message["Bcc"] = ", ".join(p["bcc"])
    message["Message-ID"] = f'<{action["id"]}@shuddho.invalid>'
    message["Date"] = format_datetime(datetime.now(timezone.utc))
    message.set_content(p["body"], subtype="plain", charset="utf-8")
    for attachment in attachments:
        maintype, subtype = attachment["content_type"].split("/", 1)
        message.add_attachment(
            attachment["body"],
            maintype=maintype,
            subtype=subtype,
            filename=attachment["filename"],
        )
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


class GoogleActions:
    provider_name = "google"
    scopes = SCOPES
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def authorization_url(self, state, verifier, capability):
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return AUTH_URL + "?" + urlencode({"client_id": self.settings.google_client_id, "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code", "scope": "openid email " + SCOPES[capability], "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline",
            "prompt": "consent select_account", "include_granted_scopes": "false"})

    async def request(self, method, url, *, token=None, data=None, body=None):
        # Callers provide only constants or a code-owned UUID event path.
        if url not in {TOKEN_URL, USERINFO_URL, SEND_URL, EVENTS_URL} and not re.fullmatch(re.escape(EVENTS_URL) + r"/shuddho[a-f0-9]{32}", url):
            raise ValueError("Unknown connector endpoint")
        try:
            async with asyncio.timeout(20):
                async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False, trust_env=False) as client:
                    async with client.stream(method, url, headers={"Authorization": "Bearer " + token} if token else {}, data=data, json=body,
                                             params={"sendUpdates": "all"} if method == "POST" and url == EVENTS_URL else None) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            # 5xx, redirects, conflicts and timeouts may hide a
                            # successful mutation. Do not blindly repeat it.
                            code = "connection_authorization" if response.status_code in {401, 403} else "provider_rejected"
                            raise GoogleFailure(code, definitive=response.status_code in {400, 401, 403, 404, 410, 422, 429})
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > 256 * 1024:
                                raise GoogleFailure("provider_response_invalid")
                            raw.extend(chunk)
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError):
            raise GoogleFailure() from None

    async def exchange(self, code, verifier):
        result = await self.request("POST", TOKEN_URL, data={"code": code, "code_verifier": verifier,
            "client_id": self.settings.google_client_id, "client_secret": self.settings.google_client_secret,
            "redirect_uri": self.settings.google_redirect_uri, "grant_type": "authorization_code"})
        self.access(result)
        if not isinstance(result.get("refresh_token"), str) or not 1 <= len(result["refresh_token"]) <= 8192 or not isinstance(result.get("scope"), str):
            raise GoogleFailure("oauth_refresh_missing", definitive=True)
        return result

    @staticmethod
    def access(result):
        if (str(result.get("token_type", "")).lower() != "bearer" or not isinstance(result.get("access_token"), str) or
                not 1 <= len(result["access_token"]) <= 8192 or any(c.isspace() for c in result["access_token"])):
            raise GoogleFailure("oauth_response_invalid", definitive=True)
        return result["access_token"]

    async def refresh(self, refresh_token, capability=None):
        result = await self.request("POST", TOKEN_URL, data={"refresh_token": refresh_token,
            "client_id": self.settings.google_client_id, "client_secret": self.settings.google_client_secret,
            "grant_type": "refresh_token"})
        self.access(result)
        return result

    async def profile(self, access_token):
        result = await self.request("GET", USERINFO_URL, token=access_token)
        try:
            if not isinstance(result.get("sub"), str) or not 1 <= len(result["sub"]) <= 255 or result.get("email_verified") is not True:
                raise ValueError()
            return {"sub": result["sub"], "email": address(result["email"])}
        except (ValueError, KeyError, TypeError):
            raise GoogleFailure("oauth_identity_invalid", definitive=True) from None

    async def execute(self, action, access_token, attachments=None):
        if action["kind"] in {"email_send", "email_send_with_attachments"}:
            result = await self.request(
                "POST",
                SEND_URL,
                token=access_token,
                body={"raw": email_raw(action, attachments)},
            )
            provider_id = result.get("id")
            if not isinstance(provider_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", provider_id):
                raise GoogleFailure("provider_receipt_invalid")
            # Gmail acceptance is not a delivery/read receipt.
            return {"provider": "google", "provider_id": provider_id, "status": "accepted_by_gmail",
                    "message_id": f'<{action["id"]}@shuddho.invalid>', "confirmed_at": datetime.now(timezone.utc).isoformat()}
        if action["kind"] != "calendar_create":
            raise ValueError("Unknown action kind")
        result = await self.request("POST", EVENTS_URL, token=access_token, body=event_body(action))
        return self.calendar_receipt(action, result)

    @staticmethod
    def calendar_receipt(action, result):
        expected = event_body(action)
        try:
            properties = result["extendedProperties"]["private"]
            if (result["id"] != expected["id"] or result.get("status") != "confirmed" or
                    properties.get("shuddhoAction") != action["id"] or properties.get("shuddhoApproval") != action["preview_hash"] or
                    result.get("summary") != expected["summary"] or result.get("description", "") != expected["description"] or
                    result.get("location", "") != expected["location"] or
                    {a["email"].casefold() for a in result.get("attendees", [])} != {a["email"].casefold() for a in expected["attendees"]}):
                raise ValueError()
            for key in ("start", "end"):
                actual_time = datetime.fromisoformat(result[key]["dateTime"].replace("Z", "+00:00"))
                if actual_time.tzinfo is None or actual_time != datetime.fromisoformat(expected[key]["dateTime"]):
                    raise ValueError()
            return {"provider": "google", "provider_id": result["id"], "status": "event_created", "calendar": "primary",
                    "confirmed_at": datetime.now(timezone.utc).isoformat()}
        except (KeyError, ValueError, TypeError, AttributeError):
            raise GoogleFailure("provider_receipt_invalid") from None

    async def reconcile(self, action, access_token):
        if action["kind"] != "calendar_create":
            return None  # Send-only scope intentionally cannot read the mailbox.
        try:
            result = await self.request("GET", EVENTS_URL + "/" + event_id(action["id"]), token=access_token)
            return self.calendar_receipt(action, result)
        except GoogleFailure:
            # Missing or changed event is NOT proof that insertion never ran.
            return None
