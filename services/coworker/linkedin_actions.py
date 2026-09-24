"""LinkedIn delegated connector for explicitly approved personal text posts.

The standard confidential web OAuth flow is used here. LinkedIn documents PKCE
separately for native loopback clients and requires provider enablement for that
flow, so the web connector relies on exact redirect matching, state, and the
backend-only client secret.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from .connector_actions import ConnectorFailure


AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
PROFILE_URL = "https://api.linkedin.com/v2/me"
POSTS_URL = "https://api.linkedin.com/rest/posts"
SCOPES = {"social": "w_member_social"}
IDENTITY_SCOPE = "r_liteprofile"
RESTLI_VERSION = "2.0.0"
_RESERVED_LITTLE = frozenset("\\|{}@[]()<>*_~")


def _scope_value() -> str:
    return IDENTITY_SCOPE + " " + SCOPES["social"]


def _person_urn(member_id: str) -> str:
    return "urn:li:person:" + member_id


def _escape_little(value: str) -> str:
    """Encode plain user text without allowing mention/template injection.

    A simple #word is retained as LinkedIn's supported hashtag element. Other
    reserved little-text characters are escaped so the rendered text stays
    equal to the user-approved text.
    """
    out: list[str] = []
    for index, char in enumerate(value):
        if char == "#":
            next_char = value[index + 1] if index + 1 < len(value) else ""
            out.append(char if next_char and (next_char.isalnum() or next_char == "_") else "\\#")
        elif char in _RESERVED_LITTLE:
            out.append("\\" + char)
        else:
            out.append(char)
    return "".join(out)


def post_body(action: dict) -> dict:
    payload = action["preview"]["payload"]
    author = action["preview"]["account"]
    if (
        payload.get("kind") != "social_publish_linkedin"
        or not isinstance(payload.get("text"), str)
        or not isinstance(author, str)
        or not re.fullmatch(r"urn:li:person:[A-Za-z0-9_-]{1,200}", author)
    ):
        raise ConnectorFailure("provider_receipt_invalid", definitive=True)
    return {
        "author": author,
        "commentary": _escape_little(payload["text"]),
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


class LinkedInActions:
    provider_name = "linkedin"
    scopes = SCOPES

    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def authorization_url(self, state, verifier, capability):
        if capability != "social":
            raise ValueError("Unsupported LinkedIn capability")
        # verifier is intentionally not sent: LinkedIn's documented PKCE flow
        # is for enabled native loopback clients, not this confidential web app.
        return AUTH_URL + "?" + urlencode({
            "response_type": "code",
            "client_id": self.settings.linkedin_client_id,
            "redirect_uri": self.settings.linkedin_redirect_uri,
            "state": state,
            "scope": _scope_value(),
        })

    async def _request(
        self,
        method,
        url,
        *,
        token=None,
        data=None,
        body=None,
        allow_empty=False,
        capture_headers=False,
    ):
        if url not in {TOKEN_URL, PROFILE_URL, POSTS_URL}:
            raise ValueError("Unknown connector endpoint")
        headers = {}
        if token:
            headers["Authorization"] = "Bearer " + token
        if url in {PROFILE_URL, POSTS_URL}:
            headers["X-RestLi-Protocol-Version"] = RESTLI_VERSION
        if url == POSTS_URL:
            headers["Linkedin-Version"] = self.settings.linkedin_api_version
            headers["Content-Type"] = "application/json"
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
                        headers=headers,
                        data=data,
                        json=body,
                    ) as response:
                        if response.status_code < 200 or response.status_code >= 300:
                            code = (
                                "connection_authorization"
                                if response.status_code in {401, 403}
                                else "provider_rejected"
                            )
                            raise ConnectorFailure(
                                code,
                                definitive=response.status_code in {
                                    400, 401, 403, 404, 409, 410, 422, 429,
                                },
                            )
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > 256 * 1024:
                                raise ConnectorFailure(
                                    "provider_response_invalid",
                                    definitive=True,
                                )
                            raw.extend(chunk)
                        response_headers = dict(response.headers)
                        status_code = response.status_code
            if not raw:
                if not allow_empty:
                    raise ConnectorFailure(
                        "provider_response_invalid",
                        definitive=True,
                    )
                result = {}
            else:
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ValueError()
            return (result, response_headers, status_code) if capture_headers else result
        except ConnectorFailure:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError):
            raise ConnectorFailure() from None

    @staticmethod
    def _access(result: dict) -> str:
        token = result.get("access_token")
        if (
            not isinstance(token, str)
            or not 1 <= len(token) <= 8192
            or any(char.isspace() for char in token)
        ):
            raise ConnectorFailure("oauth_response_invalid", definitive=True)
        return token

    async def exchange(self, code, verifier):
        result = await self._request(
            "POST",
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.settings.linkedin_client_id,
                "client_secret": self.settings.linkedin_client_secret,
                "redirect_uri": self.settings.linkedin_redirect_uri,
            },
        )
        self._access(result)
        expires_in = result.get("expires_in")
        scope = result.get("scope")
        if (
            not isinstance(expires_in, int)
            or isinstance(expires_in, bool)
            or expires_in < 60
            or expires_in > 366 * 24 * 60 * 60
            or scope is not None and not isinstance(scope, str)
        ):
            raise ConnectorFailure("oauth_response_invalid", definitive=True)
        if isinstance(scope, str):
            scopes = [item for item in re.split(r"[\s,]+", scope) if item]
            if IDENTITY_SCOPE not in scopes or SCOPES["social"] not in scopes:
                raise ConnectorFailure("oauth_scope_missing", definitive=True)
        # OAuth permits omitting scope when it is identical to the requested
        # scope. Persist the exact request set so the executor can enforce it.
        result["scope"] = _scope_value()
        return result

    @staticmethod
    def persisted_credentials(token: dict) -> dict:
        access_token = LinkedInActions._access(token)
        expires_in = token.get("expires_in")
        if not isinstance(expires_in, int) or isinstance(expires_in, bool):
            raise ConnectorFailure("oauth_response_invalid", definitive=True)
        return {
            "access_token": access_token,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ).isoformat(),
        }

    async def access_from_credentials(self, credentials: dict, capability: str) -> dict:
        if capability != "social":
            raise ConnectorFailure("connection_scope_missing", definitive=True)
        token = credentials.get("access_token")
        expires_at = credentials.get("expires_at")
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError:
            raise ConnectorFailure("connection_authorization", definitive=True) from None
        if (
            expiry.tzinfo is None
            or expiry.astimezone(timezone.utc)
            <= datetime.now(timezone.utc) + timedelta(seconds=30)
            or not isinstance(token, str)
            or not 1 <= len(token) <= 8192
            or any(char.isspace() for char in token)
        ):
            raise ConnectorFailure("connection_authorization", definitive=True)
        return {"access_token": token}

    async def profile(self, access_token):
        result = await self._request("GET", PROFILE_URL, token=access_token)
        member_id = result.get("id")
        if (
            not isinstance(member_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", member_id)
        ):
            raise ConnectorFailure("oauth_identity_invalid", definitive=True)
        urn = _person_urn(member_id)
        # Connection.email is a legacy account-label column. For LinkedIn it
        # stores the stable app-scoped Person URN; no unnecessary email scope
        # is requested.
        return {"sub": member_id, "email": urn}

    async def execute(self, action, access_token, attachments=None):
        if action["kind"] != "social_publish_linkedin" or attachments:
            raise ValueError("Unknown LinkedIn action kind")
        _, headers, status = await self._request(
            "POST",
            POSTS_URL,
            token=access_token,
            body=post_body(action),
            allow_empty=True,
            capture_headers=True,
        )
        provider_id = headers.get("x-restli-id")
        if (
            status != 201
            or not isinstance(provider_id, str)
            or not re.fullmatch(
                r"urn:li:(?:share|ugcPost):[A-Za-z0-9_-]{1,200}",
                provider_id,
            )
        ):
            raise ConnectorFailure("provider_receipt_invalid")
        return {
            "provider": "linkedin",
            "provider_id": provider_id,
            "status": "post_published",
            "author": action["preview"]["account"],
            "visibility": "PUBLIC",
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def reconcile(self, action, access_token):
        # w_member_social grants publishing, not a general social-read surface.
        # An uncertain POST is never repeated or reconciled by expanding scope.
        return None
