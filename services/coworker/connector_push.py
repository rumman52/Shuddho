from __future__ import annotations

import base64
import hashlib
import json
import re

import jwt

from .errors import CoworkerError

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GooglePushVerifier:
    def __init__(self, settings, jwks_client=None):
        self.settings = settings
        self.jwks = jwks_client or jwt.PyJWKClient(
            GOOGLE_JWKS_URL,
            cache_jwk_set=True,
            lifespan=3600,
        )

    def verify(self, authorization: str | None) -> dict:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise CoworkerError("connector_push_unauthorized", "Invalid push identity.", 401)
        token = authorization[7:]
        if not token or len(token) > 8192 or any(char.isspace() for char in token):
            raise CoworkerError("connector_push_unauthorized", "Invalid push identity.", 401)
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.settings.google_gmail_push_audience,
                options={"require": ["exp", "iat", "aud", "iss", "email"]},
            )
        except Exception:
            raise CoworkerError("connector_push_unauthorized", "Invalid push identity.", 401) from None
        if (
            claims.get("iss") not in GOOGLE_ISSUERS
            or claims.get("email") != self.settings.google_gmail_push_service_account
            or claims.get("email_verified") is not True
        ):
            raise CoworkerError("connector_push_unauthorized", "Invalid push identity.", 401)
        return claims


def decode_gmail_pubsub(payload: dict) -> dict:
    if not isinstance(payload, dict) or set(payload) - {"message", "subscription", "deliveryAttempt"}:
        raise CoworkerError("connector_push_invalid", "Invalid Gmail push payload.", 400)
    message = payload.get("message")
    subscription = payload.get("subscription")
    if (
        not isinstance(message, dict)
        or not isinstance(subscription, str)
        or not re.fullmatch(r"projects/[A-Za-z0-9._:-]+/subscriptions/[A-Za-z0-9._~-]+", subscription)
    ):
        raise CoworkerError("connector_push_invalid", "Invalid Gmail push payload.", 400)
    message_id = message.get("messageId")
    data = message.get("data")
    if (
        not isinstance(message_id, str)
        or not re.fullmatch(r"[A-Za-z0-9._~-]{1,256}", message_id)
        or not isinstance(data, str)
        or len(data) > 16384
    ):
        raise CoworkerError("connector_push_invalid", "Invalid Gmail push payload.", 400)
    try:
        raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        if len(raw) > 8192:
            raise ValueError()
        value = json.loads(raw)
    except (ValueError, json.JSONDecodeError, UnicodeError):
        raise CoworkerError("connector_push_invalid", "Invalid Gmail push payload.", 400) from None
    email = value.get("emailAddress")
    history_id = value.get("historyId")
    if (
        not isinstance(email, str)
        or len(email) > 320
        or "@" not in email
        or not isinstance(history_id, str)
        or not history_id.isdecimal()
    ):
        raise CoworkerError("connector_push_invalid", "Invalid Gmail push payload.", 400)
    return {
        "subscription": subscription,
        "message_id": message_id,
        "email": email.casefold(),
        "history_id": history_id,
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
    }
