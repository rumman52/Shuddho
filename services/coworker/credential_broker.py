from __future__ import annotations

import asyncio

from .connector_actions import ConnectorFailure
from .connector_registry import CONNECTOR_ACTION_AUDIENCE, CONNECTOR_READ_AUDIENCE
from .errors import CoworkerError


class CredentialBroker:
    """Trusted connector-only credential exchange.

    Callers receive only a short-lived provider access token after presenting a
    persisted execution grant bound to one owner/action/connection/purpose.
    Refresh/access credentials remain encrypted in the existing connection
    store and are never exposed through public API/model surfaces.
    """

    def __init__(self, repository, permission_gateway, providers: dict[str, object]):
        self.repository = repository
        self.permission_gateway = permission_gateway
        self.providers = dict(providers)

    def provider_for(self, name: str):
        value = self.providers.get(name)
        if value is None:
            raise CoworkerError(
                "connection_provider_disabled",
                "This connected service is not enabled in this deployment.",
                503,
            )
        return value

    async def issue_read_access(
        self,
        owner_id: str,
        grant_id: str,
        *,
        audience: str = CONNECTOR_READ_AUDIENCE,
    ):
        verified = await asyncio.to_thread(
            self.permission_gateway.validate_read_grant,
            owner_id,
            grant_id,
            audience=audience,
        )
        adapter = self.provider_for(verified["provider"])
        credentials = await asyncio.to_thread(
            self.repository.credentials,
            verified["connection_id"],
            owner_id=owner_id,
            required_scopes=verified["required_scopes"],
            read_grant_id=verified["id"],
        )
        try:
            if hasattr(adapter, "access_from_credentials"):
                token = await adapter.access_from_credentials(
                    credentials,
                    verified["capability"],
                )
            else:
                token = await adapter.refresh(
                    credentials["refresh_token"],
                    verified["capability"],
                )
        except (KeyError, ConnectorFailure):
            raise ConnectorFailure(
                "connection_authorization",
                definitive=True,
            ) from None
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ConnectorFailure("oauth_response_invalid", definitive=True)
        returned_scopes = token.get("scope")
        if returned_scopes is not None:
            if not isinstance(returned_scopes, str):
                raise ConnectorFailure("connection_scope_missing", definitive=True)
            granted = set(returned_scopes.split())
            if any(scope not in granted for scope in verified["required_scopes"]):
                raise ConnectorFailure("connection_scope_missing", definitive=True)
        if (
            isinstance(token.get("refresh_token"), str)
            and 1 <= len(token["refresh_token"]) <= 8192
        ):
            await asyncio.to_thread(
                self.repository.rotate_token,
                verified["connection_id"],
                token["refresh_token"],
                owner_id=owner_id,
                read_grant_id=verified["id"],
            )
        profile = await adapter.profile(access_token)
        if (
            profile["sub"] != verified["subject_id"]
            or profile["email"] != verified["account"]
        ):
            raise ConnectorFailure(
                "connection_identity_changed",
                definitive=True,
            )
        return verified, adapter, access_token

    async def issue_access(
        self,
        grant: dict,
        action: dict,
        *,
        purpose: str,
        audience: str = CONNECTOR_ACTION_AUDIENCE,
    ):
        verified = await asyncio.to_thread(
            self.permission_gateway.validate_grant,
            grant["id"],
            action["id"],
            purpose=purpose,
            audience=audience,
        )
        if (
            verified["owner_id"] != action["owner_id"]
            or verified["connection_id"] != action["connection_id"]
            or verified["provider"] != action["preview"]["provider"]
        ):
            raise CoworkerError(
                "connector_grant_invalid",
                "The connector execution grant does not match this action.",
                409,
            )

        adapter = self.provider_for(verified["provider"])
        credentials = await asyncio.to_thread(
            self.repository.credentials,
            verified["connection_id"],
            owner_id=verified["owner_id"],
            required_scopes=verified["required_scopes"],
            execution_grant_id=verified["id"],
        )
        capability = verified["capability"]
        try:
            if hasattr(adapter, "access_from_credentials"):
                token = await adapter.access_from_credentials(credentials, capability)
            else:
                token = await adapter.refresh(
                    credentials["refresh_token"],
                    capability,
                )
        except (KeyError, ConnectorFailure):
            raise ConnectorFailure(
                "connection_authorization",
                definitive=True,
            ) from None

        access_token = token.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ConnectorFailure(
                "oauth_response_invalid",
                definitive=True,
            )

        returned_scopes = token.get("scope")
        if returned_scopes is not None:
            if not isinstance(returned_scopes, str):
                raise ConnectorFailure(
                    "connection_scope_missing",
                    definitive=True,
                )
            granted = set(returned_scopes.split())
            if any(scope not in granted for scope in verified["required_scopes"]):
                raise ConnectorFailure(
                    "connection_scope_missing",
                    definitive=True,
                )

        if (
            isinstance(token.get("refresh_token"), str)
            and 1 <= len(token["refresh_token"]) <= 8192
        ):
            await asyncio.to_thread(
                self.repository.rotate_token,
                verified["connection_id"],
                token["refresh_token"],
                owner_id=verified["owner_id"],
                execution_grant_id=verified["id"],
            )

        profile = await adapter.profile(access_token)
        if (
            profile["sub"] != action["preview"]["subject_id"]
            or profile["email"] != action["preview"]["account"]
        ):
            raise ConnectorFailure(
                "connection_identity_changed",
                definitive=True,
            )
        return adapter, access_token
