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
    "drive": "https://www.googleapis.com/auth/drive.file",
}
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"


class GoogleFailure(ConnectorFailure):
    def __init__(self, code="provider_unavailable", *, definitive=False):
        super().__init__(code, definitive=definitive)


def event_id(action_id):
    # UUID hex is a subset of Google's base32hex event ID alphabet.
    return "shuddho" + action_id.replace("-", "")


def event_body(action):
    p = action["preview"]["payload"]
    reminders = {"useDefault": False, "overrides": []}
    if p["kind"] == "calendar_create_with_reminder":
        reminders["overrides"] = [{
            "method": "popup",
            "minutes": p["reminder_minutes_before_start"],
        }]
    return {"id": event_id(action["id"]), "summary": p["title"], "description": html.escape(p["description"]).replace("\n", "<br>"), "location": p["location"],
            "start": {"dateTime": p["start_at"], "timeZone": p["time_zone"]},
            "end": {"dateTime": p["end_at"], "timeZone": p["time_zone"]},
            "attendees": [{"email": email} for email in p["attendees"]],
            "reminders": reminders,
            "guestsCanModify": False, "guestsCanInviteOthers": False, "guestsCanSeeOtherGuests": True,
            "extendedProperties": {"private": {"shuddhoAction": action["id"], "shuddhoApproval": action["preview_hash"]}}}

def drive_metadata(action, artifact):
    return {
        "name": artifact["filename"],
        "mimeType": artifact["content_type"],
        "appProperties": {
            "shuddhoAction": action["id"],
            "shuddhoApproval": action["preview_hash"],
            "shuddhoArtifact": artifact["id"],
            "shuddhoSha256": artifact["sha256"],
        },
    }


def drive_multipart(action, artifact):
    boundary = "shuddho_" + action["id"].replace("-", "")
    metadata = json.dumps(
        drive_metadata(action, artifact),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    body = (
        b"--" + boundary.encode() + b"\r\n"
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + metadata
        + b"\r\n--" + boundary.encode() + b"\r\n"
        + b"Content-Type: " + artifact["content_type"].encode("ascii") + b"\r\n\r\n"
        + artifact["body"]
        + b"\r\n--" + boundary.encode() + b"--\r\n"
    )
    return body, "multipart/related; boundary=" + boundary


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
    if action["kind"] == "email_thread_reply":
        context = preview.get("reply_context")
        if not isinstance(context, dict):
            raise ValueError("Missing reply context")
        message["In-Reply-To"] = context["parent_message_id"]
        message["References"] = " ".join(context["references"])
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

    async def request(self, method, url, *, token=None, data=None, body=None, params=None, content=None, headers=None):
        # Callers provide only constants or code-owned provider-resource paths.
        event_path = re.fullmatch(re.escape(EVENTS_URL) + r"/shuddho[a-f0-9]{32}", url)
        permission_path = re.fullmatch(
            re.escape(DRIVE_FILES_URL) + r"/[A-Za-z0-9_-]{1,256}/permissions",
            url,
        )
        if (
            url not in {
                TOKEN_URL,
                USERINFO_URL,
                SEND_URL,
                EVENTS_URL,
                DRIVE_FILES_URL,
                DRIVE_UPLOAD_URL,
            }
            and not event_path
            and not permission_path
        ):
            raise ValueError("Unknown connector endpoint")
        try:
            async with asyncio.timeout(20):
                async with httpx.AsyncClient(transport=self.transport, timeout=15, follow_redirects=False, trust_env=False) as client:
                    request_headers = dict(headers or {})
                    if token:
                        request_headers["Authorization"] = "Bearer " + token
                    request_params = params
                    if request_params is None and method == "POST" and url == EVENTS_URL:
                        request_params = {"sendUpdates": "all"}
                    async with client.stream(
                        method,
                        url,
                        headers=request_headers,
                        data=data,
                        json=body,
                        content=content,
                        params=request_params,
                    ) as response:
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

    @staticmethod
    def drive_file_valid(action, artifact, value):
        try:
            metadata = drive_metadata(action, artifact)
            props = value["appProperties"]
            return (
                isinstance(value["id"], str)
                and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value["id"]))
                and value.get("trashed") is not True
                and value.get("name") == metadata["name"]
                and value.get("mimeType") == metadata["mimeType"]
                and props == metadata["appProperties"]
            )
        except (KeyError, TypeError):
            return False

    @staticmethod
    def drive_permission_valid(recipient, value):
        return (
            isinstance(value, dict)
            and value.get("type") == "user"
            and value.get("role") == "reader"
            and value.get("deleted") is not True
            and isinstance(value.get("emailAddress"), str)
            and value["emailAddress"].casefold() == recipient.casefold()
        )

    async def execute_document_share(self, action, access_token, artifact):
        if not isinstance(artifact, dict):
            raise GoogleFailure("document_share_unavailable", definitive=True)
        multipart, content_type = drive_multipart(action, artifact)
        result = await self.request(
            "POST",
            DRIVE_UPLOAD_URL,
            token=access_token,
            content=multipart,
            headers={"Content-Type": content_type},
            params={
                "uploadType": "multipart",
                "fields": "id,name,mimeType,appProperties,trashed",
            },
        )
        if not self.drive_file_valid(action, artifact, result):
            raise GoogleFailure("provider_receipt_invalid")
        file_id = result["id"]
        recipient = action["preview"]["payload"]["recipients"][0]
        try:
            permission = await self.request(
                "POST",
                DRIVE_FILES_URL + "/" + file_id + "/permissions",
                token=access_token,
                body={
                    "type": "user",
                    "role": "reader",
                    "emailAddress": recipient,
                },
                params={
                    "sendNotificationEmail": "true",
                    "fields": "id,type,role,emailAddress,deleted",
                },
            )
        except GoogleFailure:
            # The file already exists. Any failure after this point is a
            # partial external mutation and must never be retried blindly.
            raise GoogleFailure("provider_outcome_unknown") from None
        if not self.drive_permission_valid(recipient, permission):
            raise GoogleFailure("provider_receipt_invalid")
        return {
            "provider": "google",
            "provider_id": file_id,
            "status": "document_shared",
            "recipient": recipient,
            "access": "reader",
            "artifact_sha256": artifact["sha256"],
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def execute(self, action, access_token, attachments=None):
        if action["kind"] == "document_share":
            return await self.execute_document_share(
                action,
                access_token,
                attachments,
            )
        if action["kind"] in {"email_send", "email_send_with_attachments", "email_thread_reply"}:
            request_body = {"raw": email_raw(action, attachments)}
            expected_thread_id = None
            if action["kind"] == "email_thread_reply":
                context = action["preview"].get("reply_context")
                if not isinstance(context, dict) or not isinstance(context.get("thread_id"), str):
                    raise GoogleFailure("provider_receipt_invalid", definitive=True)
                expected_thread_id = context["thread_id"]
                request_body["threadId"] = expected_thread_id
            result = await self.request(
                "POST",
                SEND_URL,
                token=access_token,
                body=request_body,
            )
            provider_id = result.get("id")
            thread_id = result.get("threadId")
            if (
                not isinstance(provider_id, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", provider_id)
                or not isinstance(thread_id, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", thread_id)
                or expected_thread_id is not None
                and thread_id != expected_thread_id
            ):
                raise GoogleFailure("provider_receipt_invalid")
            # Gmail acceptance is not a delivery/read receipt.
            return {"provider": "google", "provider_id": provider_id, "thread_id": thread_id, "status": "accepted_by_gmail",
                    "message_id": f'<{action["id"]}@shuddho.invalid>', "confirmed_at": datetime.now(timezone.utc).isoformat()}
        if action["kind"] not in {"calendar_create", "calendar_create_with_reminder"}:
            raise ValueError("Unknown action kind")
        result = await self.request("POST", EVENTS_URL, token=access_token, body=event_body(action))
        return self.calendar_receipt(action, result)

    @staticmethod
    def calendar_receipt(action, result):
        expected = event_body(action)
        try:
            properties = result["extendedProperties"]["private"]
            actual_reminders = result.get("reminders")
            if action["kind"] == "calendar_create_with_reminder":
                reminders_valid = actual_reminders == expected["reminders"]
            else:
                reminders_valid = (
                    isinstance(actual_reminders, dict)
                    and actual_reminders.get("useDefault") is False
                    and not actual_reminders.get("overrides")
                )
            if (result["id"] != expected["id"] or result.get("status") != "confirmed" or
                    properties.get("shuddhoAction") != action["id"] or properties.get("shuddhoApproval") != action["preview_hash"] or
                    result.get("summary") != expected["summary"] or result.get("description", "") != expected["description"] or
                    result.get("location", "") != expected["location"] or
                    not reminders_valid or
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

    async def reconcile_document_share(self, action, access_token):
        artifact = action["preview"].get("shared_artifact")
        if not isinstance(artifact, dict):
            return None
        action_id = action["id"]
        try:
            result = await self.request(
                "GET",
                DRIVE_FILES_URL,
                token=access_token,
                params={
                    "spaces": "drive",
                    "pageSize": "2",
                    "q": (
                        "trashed = false and "
                        "appProperties has { key='shuddhoAction' and value='"
                        + action_id
                        + "' }"
                    ),
                    "fields": "files(id,name,mimeType,appProperties,trashed)",
                },
            )
            files = result.get("files")
            if (
                not isinstance(files, list)
                or len(files) != 1
                or not self.drive_file_valid(action, artifact, files[0])
            ):
                return None
            file_id = files[0]["id"]
            permissions = await self.request(
                "GET",
                DRIVE_FILES_URL + "/" + file_id + "/permissions",
                token=access_token,
                params={
                    "pageSize": "100",
                    "fields": "permissions(id,type,role,emailAddress,deleted)",
                },
            )
            values = permissions.get("permissions")
            recipient = action["preview"]["payload"]["recipients"][0]
            if (
                not isinstance(values, list)
                or sum(
                    self.drive_permission_valid(recipient, item)
                    for item in values
                ) != 1
            ):
                return None
            return {
                "provider": "google",
                "provider_id": file_id,
                "status": "document_shared",
                "recipient": recipient,
                "access": "reader",
                "artifact_sha256": artifact["sha256"],
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            }
        except GoogleFailure:
            return None

    async def reconcile(self, action, access_token):
        if action["kind"] == "document_share":
            return await self.reconcile_document_share(action, access_token)
        if action["kind"] not in {"calendar_create", "calendar_create_with_reminder"}:
            return None  # Send-only scope intentionally cannot read the mailbox.
        try:
            result = await self.request("GET", EVENTS_URL + "/" + event_id(action["id"]), token=access_token)
            return self.calendar_receipt(action, result)
        except GoogleFailure:
            # Missing or changed event is NOT proof that insertion never ran.
            return None
