from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass

import httpx
import jwt
from fastapi import Request

from .errors import CoworkerError


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str
    expires_at: int

    @property
    def account_id(self) -> str:
        return hashlib.sha256(json.dumps([self.issuer, self.subject]).encode()).hexdigest()


class JwtVerifier:
    """Verify asymmetric managed-auth tokens; never trust token-provided URLs."""

    def __init__(self, issuer: str, audience: str, transport=None):
        self.issuer = issuer
        self.audience = audience
        self.transport = transport
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _refresh(self) -> None:
        try:
            async with asyncio.timeout(5):
                async with httpx.AsyncClient(timeout=5, transport=self.transport, follow_redirects=False) as client:
                    async with client.stream("GET", self.issuer + "/.well-known/jwks.json") as response:
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 65536:
                                raise ValueError("JWKS too large")
                raw = json.loads(body)
                keys = {}
                for item in raw["keys"][:20]:
                    if item.get("alg") in {"RS256", "ES256"} and item.get("use", "sig") == "sig":
                        keys[str(item["kid"])] = jwt.PyJWK.from_dict(item)
                self._keys = keys
                self._fetched_at = time.monotonic()
        except (httpx.HTTPError, TimeoutError, ValueError, KeyError, TypeError, AttributeError, jwt.PyJWTError):
            raise CoworkerError("auth_unavailable", "Sign-in verification is temporarily unavailable. Please retry.", 503) from None

    async def verify(self, token: str) -> Principal:
        try:
            if len(token) > 16384:
                raise ValueError()
            header = jwt.get_unverified_header(token)
            if header.get("alg") not in {"RS256", "ES256"}:
                raise ValueError()
            kid = header.get("kid")
            if not isinstance(kid, str) or not 1 <= len(kid) <= 200:
                raise ValueError()
            async with self._lock:
                age = time.monotonic() - self._fetched_at
                if not self._fetched_at or age > 300 or (kid not in self._keys and age > 30):
                    await self._refresh()
                key = self._keys.get(kid)
            if key is None or key.algorithm_name != header["alg"]:
                raise ValueError()
            claims = jwt.decode(
                token, key.key, algorithms=[key.algorithm_name], audience=self.audience,
                issuer=self.issuer, leeway=15,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
            if claims.get("role") != "authenticated" or claims.get("is_anonymous") is True:
                raise ValueError()
            subject = claims["sub"]
            if not isinstance(subject, str) or not 1 <= len(subject) <= 128:
                raise ValueError()
            return Principal(self.issuer, subject, int(claims["exp"]))
        except (jwt.PyJWTError, ValueError, KeyError, TypeError):
            raise CoworkerError("sign_in_required", "Please sign in again to continue.", 401) from None


async def require_principal(request: Request) -> Principal:
    container = getattr(request.app.state, "coworker", None)
    if container is None:
        raise CoworkerError("coworker_unavailable", "The coworker workspace is not available yet.", 503)
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise CoworkerError("sign_in_required", "Sign in to use your coworker workspace.", 401)
    return await container.verifier.verify(token)
