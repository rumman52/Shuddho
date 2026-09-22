from __future__ import annotations

from typing import Protocol


class ConnectorFailure(Exception):
    def __init__(self, code="provider_unavailable", *, definitive=False):
        self.code = code
        self.definitive = definitive
        super().__init__("The connected service did not confirm the request.")


class ConnectorAdapter(Protocol):
    provider_name: str
    scopes: dict[str, str]

    def authorization_url(self, state: str, verifier: str, capability: str) -> str: ...
    async def exchange(self, code: str, verifier: str) -> dict: ...
    async def refresh(self, refresh_token: str, capability: str) -> dict: ...
    async def profile(self, access_token: str) -> dict: ...
    async def execute(self, action: dict, access_token: str) -> dict: ...
    async def reconcile(self, action: dict, access_token: str) -> dict | None: ...
