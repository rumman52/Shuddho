"""Secret encryption with row-bound authenticated data; no token repr/logging."""
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import CoworkerError


class TokenVault:
    def __init__(self, key: str):
        try:
            raw = base64.b64decode(key, altchars=b"-_", validate=True)
            if len(raw) != 32:
                raise ValueError()
            self._cipher = AESGCM(raw)
        except (ValueError, TypeError):
            raise ValueError("Set SHUDDHO_CONNECTOR_ENCRYPTION_KEY to a base64-encoded 32-byte secret") from None

    def seal(self, value: dict, binding: str) -> str:
        nonce = os.urandom(12)
        return base64.urlsafe_b64encode(nonce + self._cipher.encrypt(
            nonce, json.dumps(value, separators=(",", ":")).encode(), binding.encode())).decode()

    def open(self, value: str, binding: str) -> dict:
        try:
            raw = base64.urlsafe_b64decode(value)
            result = json.loads(self._cipher.decrypt(raw[:12], raw[12:], binding.encode()))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except Exception:
            raise CoworkerError("connector_unavailable", "This connection could not be opened. Reconnect your account.", 503) from None
