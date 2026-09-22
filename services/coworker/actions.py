"""Explicit user commands only; models have no access to this executor."""
import asyncio

from .action_registry import action_spec
from .action_repository import ActionRepository, TERMINAL
from .connector_actions import ConnectorFailure
from .errors import CoworkerError


class ActionService:
    def __init__(self, repository: ActionRepository, providers: dict[str, object]):
        self.repo = repository
        self.providers = dict(providers)
        # Backward-compatible internal surface for existing Google-only
        # workers/tests while multi-provider routing uses provider_for().
        self.provider = self.providers.get("google")

    def provider_for(self, name: str):
        value = self.providers.get(name)
        if value is None:
            raise CoworkerError(
                "connection_provider_disabled",
                "This connected service is not enabled in this deployment.",
                503,
            )
        return value

    async def connect(self, owner, request, provider="google"):
        adapter = self.provider_for(provider)
        state, verifier = await asyncio.to_thread(
            self.repo.start_oauth,
            owner,
            request.capability,
            provider,
        )
        return {
            "authorization_url": adapter.authorization_url(
                state,
                verifier,
                request.capability,
            ),
            "state": state,
        }

    async def finish_connect(self, owner, request, provider="google"):
        attempt = await asyncio.to_thread(
            self.repo.consume_oauth,
            owner,
            request.state,
        )
        if attempt["provider"] != provider:
            raise CoworkerError(
                "connection_failed",
                "This connection callback belongs to a different provider.",
                409,
            )
        adapter = self.provider_for(provider)
        try:
            token = await adapter.exchange(
                request.code,
                attempt["verifier"],
            )
            scopes = token["scope"].split()
            required = adapter.scopes[attempt["capability"]]
            if required not in scopes:
                raise ConnectorFailure(
                    "oauth_scope_missing",
                    definitive=True,
                )
            profile = await adapter.profile(token["access_token"])
            return await asyncio.to_thread(
                self.repo.finish_connection,
                owner,
                attempt,
                profile,
                token["refresh_token"],
                scopes,
            )
        except ConnectorFailure:
            raise CoworkerError(
                "connection_failed",
                "The connected service could not finish connecting. Start again and grant the requested permission.",
                409,
            ) from None

    async def access(self, action):
        provider_name = action["preview"]["provider"]
        adapter = self.provider_for(provider_name)
        credentials = await asyncio.to_thread(
            self.repo.credentials,
            action["connection_id"],
        )
        capability = action_spec(
            action["kind"],
            provider_name,
        ).capability
        required = adapter.scopes[capability]
        if required not in credentials["scopes"]:
            raise ConnectorFailure(
                "connection_scope_missing",
                definitive=True,
            )
        token = await adapter.refresh(
            credentials["refresh_token"],
            capability,
        )
        if "scope" in token and (
            not isinstance(token["scope"], str)
            or required not in token["scope"].split()
        ):
            raise ConnectorFailure(
                "connection_scope_missing",
                definitive=True,
            )
        if (
            isinstance(token.get("refresh_token"), str)
            and 1 <= len(token["refresh_token"]) <= 8192
        ):
            await asyncio.to_thread(
                self.repo.rotate_token,
                action["connection_id"],
                token["refresh_token"],
            )
        profile = await adapter.profile(token["access_token"])
        if (
            profile["sub"] != action["preview"]["subject_id"]
            or profile["email"] != action["preview"]["account"]
        ):
            raise ConnectorFailure(
                "connection_identity_changed",
                definitive=True,
            )
        return adapter, token["access_token"]

    async def execute(self, action_id):
        action = await asyncio.to_thread(
            self.repo.worker_get,
            action_id,
        )
        if (
            action["state"] in TERMINAL
            and action["state"] != "outcome_unknown"
        ):
            return
        if action["state"] in {"executing", "outcome_unknown"}:
            await self.reconcile(action)
            return
        if action["state"] != "queued":
            return
        self.repo.enabled()
        try:
            adapter, token = await self.access(action)
        except (ConnectorFailure, CoworkerError):
            await asyncio.to_thread(
                self.repo.finish,
                action_id,
                "failed",
                error_code="connection_unavailable",
                unstarted=True,
            )
            return
        claimed = await asyncio.to_thread(
            self.repo.claim_execution,
            action_id,
        )
        if not claimed:
            return
        try:
            receipt = await adapter.execute(claimed, token)
        except ConnectorFailure as error:
            if error.definitive:
                await asyncio.to_thread(
                    self.repo.finish,
                    action_id,
                    "failed",
                    error_code=error.code,
                )
            else:
                await self.reconcile(
                    claimed,
                    adapter=adapter,
                    token=token,
                )
            return
        await asyncio.to_thread(
            self.repo.finish,
            action_id,
            "succeeded",
            receipt=receipt,
        )

    async def reconcile(self, action, adapter=None, token=None):
        receipt = None
        spec = action_spec(
            action["kind"],
            action["preview"]["provider"],
        )
        if spec.reconcile_supported and self.repo.settings.actions_enabled:
            try:
                if adapter is None or token is None:
                    adapter, token = await self.access(action)
                receipt = await adapter.reconcile(action, token)
            except (ConnectorFailure, CoworkerError):
                pass
        if receipt:
            await asyncio.to_thread(
                self.repo.finish,
                action["id"],
                "succeeded",
                receipt=receipt,
            )
        else:
            await asyncio.to_thread(
                self.repo.finish,
                action["id"],
                "outcome_unknown",
                error_code="provider_outcome_unknown",
            )

    async def reconcile_owned(self, owner, action_id):
        self.repo.enabled()
        action = await asyncio.to_thread(
            self.repo.reserve_reconciliation,
            owner,
            action_id,
        )
        await self.reconcile(action)
        return await asyncio.to_thread(
            self.repo.get,
            owner,
            action_id,
        )
