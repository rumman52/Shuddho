from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


_ALLOWED_PUSH_HOSTS = frozenset({
    "fcm.googleapis.com",
    "android.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
})
_SUBSCRIPTION_AAD = b"shuddho-browser-push-v1"
_MAX_ENDPOINT_BYTES = 2048
_MAX_PUSH_PLAINTEXT = 3993


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def b64url_decode(value: str, *, expected_bytes: int | None = None) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("Web Push key material is missing.")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError("Web Push key material is not valid base64url.") from exc
    if expected_bytes is not None and len(raw) != expected_bytes:
        raise ValueError("Web Push key material has an unexpected length.")
    return raw


def validate_push_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint or len(endpoint.encode("utf-8")) > _MAX_ENDPOINT_BYTES:
        raise ValueError("The Web Push endpoint is invalid.")
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The Web Push endpoint is not an allowed HTTPS push-service URL.") from exc
    allowed = (
        host in _ALLOWED_PUSH_HOSTS
        or host.endswith(".notify.windows.com")
    )
    if (
        parsed.scheme != "https"
        or not host
        or not allowed
        or parsed.username
        or parsed.password
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise ValueError("The Web Push endpoint is not an allowed HTTPS push-service URL.")
    return endpoint


def validate_subscription_material(p256dh: str, auth: str) -> None:
    public_bytes = b64url_decode(p256dh, expected_bytes=65)
    if public_bytes[0] != 4:
        raise ValueError("The Web Push subscription public key is invalid.")
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_bytes)
    except ValueError as exc:
        raise ValueError("The Web Push subscription public key is invalid.") from exc
    b64url_decode(auth, expected_bytes=16)


def validate_web_push_configuration(
    vapid_private_key: str,
    encryption_key: str,
    subject: str,
) -> None:
    raw_private = b64url_decode(vapid_private_key, expected_bytes=32)
    private_value = int.from_bytes(raw_private, "big")
    try:
        ec.derive_private_key(private_value, ec.SECP256R1())
    except ValueError as exc:
        raise ValueError("SHUDDHO_WEB_PUSH_VAPID_PRIVATE_KEY is invalid.") from exc
    b64url_decode(encryption_key, expected_bytes=32)
    if not (subject.startswith("mailto:") or subject.startswith("https://")):
        raise ValueError("SHUDDHO_WEB_PUSH_VAPID_SUBJECT must be a mailto: or https:// contact URI.")


@dataclass(frozen=True)
class PushSendResult:
    status_code: int


class WebPushSubscriptionVault:
    def __init__(self, settings):
        self._key: bytes | None = None
        if settings.browser_push_enabled:
            self._key = b64url_decode(settings.web_push_encryption_key, expected_bytes=32)

    @property
    def available(self) -> bool:
        return self._key is not None

    def seal(self, endpoint: str, p256dh: str, auth: str) -> str:
        if self._key is None:
            raise ValueError("Browser Push subscription encryption is unavailable.")
        payload = json.dumps(
            {"endpoint": endpoint, "p256dh": p256dh, "auth": auth},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        nonce = os.urandom(12)
        encrypted = AESGCM(self._key).encrypt(nonce, payload, _SUBSCRIPTION_AAD)
        return b64url_encode(nonce + encrypted)

    def open(self, ciphertext: str) -> dict[str, str]:
        if self._key is None:
            raise ValueError("Browser Push subscription encryption is unavailable.")
        raw = b64url_decode(ciphertext)
        if len(raw) < 13:
            raise ValueError("Browser Push subscription ciphertext is invalid.")
        payload = AESGCM(self._key).decrypt(raw[:12], raw[12:], _SUBSCRIPTION_AAD)
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Browser Push subscription ciphertext is invalid.")
        endpoint = validate_push_endpoint(value.get("endpoint"))
        p256dh = value.get("p256dh")
        auth = value.get("auth")
        validate_subscription_material(p256dh, auth)
        return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}


class WebPushSender:
    def __init__(self, settings, requester=None):
        self.settings = settings
        self.requester = requester or httpx.post
        self._private_key = None
        self._public_key = ""
        if settings.browser_push_enabled:
            validate_web_push_configuration(
                settings.web_push_vapid_private_key,
                settings.web_push_encryption_key,
                settings.web_push_vapid_subject,
            )
            private_value = int.from_bytes(
                b64url_decode(settings.web_push_vapid_private_key, expected_bytes=32),
                "big",
            )
            self._private_key = ec.derive_private_key(private_value, ec.SECP256R1())
            encoded_public = self._private_key.public_key().public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
            self._public_key = b64url_encode(encoded_public)

    @property
    def available(self) -> bool:
        return self._private_key is not None

    @property
    def application_server_key(self) -> str:
        return self._public_key

    @staticmethod
    def _encrypt_payload(p256dh: str, auth: str, payload: bytes) -> bytes:
        if len(payload) > _MAX_PUSH_PLAINTEXT:
            raise ValueError("Browser Push payload exceeds the bounded plaintext limit.")
        ua_public_bytes = b64url_decode(p256dh, expected_bytes=65)
        auth_secret = b64url_decode(auth, expected_bytes=16)
        ua_public = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), ua_public_bytes
        )
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        as_public_bytes = ephemeral.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        shared = ephemeral.exchange(ec.ECDH(), ua_public)
        ikm = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=auth_secret,
            info=b"WebPush: info\x00" + ua_public_bytes + as_public_bytes,
        ).derive(shared)
        salt = os.urandom(16)
        cek = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=salt,
            info=b"Content-Encoding: aes128gcm\x00",
        ).derive(ikm)
        nonce = HKDF(
            algorithm=hashes.SHA256(),
            length=12,
            salt=salt,
            info=b"Content-Encoding: nonce\x00",
        ).derive(ikm)
        encrypted = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
        body = (
            salt
            + (4096).to_bytes(4, "big")
            + bytes([len(as_public_bytes)])
            + as_public_bytes
            + encrypted
        )
        if len(body) > 4096:
            raise ValueError("Browser Push encrypted payload exceeds the bounded record size.")
        return body

    def send(self, subscription: dict[str, str], payload: dict, *, ttl: int) -> PushSendResult:
        if self._private_key is None:
            raise ValueError("Browser Push is unavailable.")
        endpoint = validate_push_endpoint(subscription["endpoint"])
        validate_subscription_material(subscription["p256dh"], subscription["auth"])
        parsed = urlparse(endpoint)
        origin = "https://" + (parsed.hostname or "")
        if parsed.port not in {None, 443}:
            origin += ":" + str(parsed.port)
        claims = {
            "aud": origin,
            "exp": int(time.time()) + 12 * 60 * 60,
            "sub": self.settings.web_push_vapid_subject,
        }
        token = jwt.encode(claims, self._private_key, algorithm="ES256")
        cleartext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        body = self._encrypt_payload(subscription["p256dh"], subscription["auth"], cleartext)
        response = self.requester(
            endpoint,
            content=body,
            headers={
                "Authorization": "vapid t=" + token + ", k=" + self._public_key,
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "TTL": str(max(0, min(int(ttl), 3600))),
            },
            timeout=8.0,
            follow_redirects=False,
        )
        return PushSendResult(status_code=int(response.status_code))


def endpoint_fingerprint(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()
