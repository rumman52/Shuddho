"""Explicit user commands only; models have no access to this executor."""
import asyncio
import hashlib

from .action_registry import action_spec
from .action_repository import ActionRepository, TERMINAL
from .connector_actions import ConnectorFailure
from .connector_registry import CONNECTOR_ACTION_AUDIENCE
from .errors import CoworkerError


class ActionService:
    def __init__(
        self,
        repository: ActionRepository,
        providers: dict[str, object],
        storage=None,
        *,
        permission_gateway=None,
        credential_broker=None,
    ):
        self.repo = repository
        self.providers = dict(providers)
        self.storage = storage
        self.permission_gateway = permission_gateway
        self.credential_broker = credential_broker
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
        if request.capability not in adapter.scopes:
            raise CoworkerError(
                "connection_provider_disabled",
                "This connected service does not support that capability.",
                409,
            )
        if (
            request.capability == "drive"
            and not self.repo.settings.action_document_sharing_enabled
        ):
            raise CoworkerError(
                "action_document_sharing_disabled",
                "Document sharing is not enabled in this deployment.",
                503,
            )
        if (
            request.capability == "social"
            and not self.repo.settings.action_social_publishing_enabled
        ):
            raise CoworkerError(
                "action_social_publishing_disabled",
                "Social publishing is not enabled in this deployment.",
                503,
            )
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
            credentials = (
                adapter.persisted_credentials(token)
                if hasattr(adapter, "persisted_credentials")
                else {"refresh_token": token["refresh_token"]}
            )
            return await asyncio.to_thread(
                self.repo.finish_connection,
                owner,
                attempt,
                profile,
                credentials,
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
        if hasattr(adapter, "access_from_credentials"):
            token = await adapter.access_from_credentials(credentials, capability)
        else:
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

    async def authorized_access(self, action, *, purpose: str):
        if not self.repo.settings.connector_trust_boundary_enabled:
            return await self.access(action)
        if self.permission_gateway is None or self.credential_broker is None:
            raise CoworkerError(
                "connector_trust_boundary_unavailable",
                "The connector trust boundary is not available to this worker.",
                503,
            )
        grant = await asyncio.to_thread(
            self.permission_gateway.authorize_action,
            action["owner_id"],
            action["id"],
            purpose=purpose,
            audience=CONNECTOR_ACTION_AUDIENCE,
        )
        return grant

    async def grant_access(self, grant, action, *, purpose: str):
        if not self.repo.settings.connector_trust_boundary_enabled:
            return await self.access(action)
        if self.credential_broker is None:
            raise CoworkerError(
                "connector_trust_boundary_unavailable",
                "The connector credential boundary is not available to this worker.",
                503,
            )
        return await self.credential_broker.issue_access(
            grant,
            action,
            purpose=purpose,
            audience=CONNECTOR_ACTION_AUDIENCE,
        )

    async def load_attachments(self, action):
        if action["kind"] != "email_send_with_attachments":
            return []
        if self.storage is None:
            raise CoworkerError(
                "attachment_unavailable",
                "Approved attachments are unavailable for this worker.",
                503,
            )
        metadata = await asyncio.to_thread(
            self.repo.execution_attachments,
            action,
        )
        result = []
        for item in metadata:
            try:
                body = await asyncio.to_thread(
                    self.storage.get,
                    item["object_key"],
                    item["byte_size"],
                )
            except (FileNotFoundError, CoworkerError):
                raise CoworkerError(
                    "attachment_unavailable",
                    "An approved attachment is no longer available.",
                    409,
                ) from None
            if (
                len(body) != item["byte_size"]
                or hashlib.sha256(body).hexdigest() != item["sha256"]
            ):
                raise CoworkerError(
                    "attachment_changed",
                    "An approved attachment changed after review.",
                    409,
                )
            result.append({
                key: value
                for key, value in item.items()
                if key != "object_key"
            } | {"body": body})
        return result

    async def load_shared_artifact(self, action):
        if action["kind"] != "document_share":
            return None
        if self.storage is None:
            raise CoworkerError(
                "document_share_unavailable",
                "The approved document is unavailable for this worker.",
                503,
            )
        metadata = await asyncio.to_thread(
            self.repo.execution_shared_artifact,
            action,
        )
        try:
            body = await asyncio.to_thread(
                self.storage.get,
                metadata["object_key"],
                metadata["byte_size"],
            )
        except (FileNotFoundError, CoworkerError):
            raise CoworkerError(
                "document_share_unavailable",
                "The approved document is no longer available.",
                409,
            ) from None
        if (
            len(body) != metadata["byte_size"]
            or hashlib.sha256(body).hexdigest() != metadata["sha256"]
        ):
            raise CoworkerError(
                "document_share_changed",
                "The approved document changed after review.",
                409,
            )
        return {
            key: value
            for key, value in metadata.items()
            if key != "object_key"
        } | {"body": body}

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
            attachments = await self.load_attachments(action)
        except CoworkerError:
            # Preserve the existing external attachment error contract.
            await asyncio.to_thread(
                self.repo.finish,
                action_id,
                "failed",
                error_code="attachment_unavailable",
                unstarted=True,
            )
            return
        try:
            shared_artifact = await self.load_shared_artifact(action)
        except CoworkerError as error:
            await asyncio.to_thread(
                self.repo.finish,
                action_id,
                "failed",
                error_code=error.code,
                unstarted=True,
            )
            return
        boundary_enabled = self.repo.settings.connector_trust_boundary_enabled
        grant = None
        if boundary_enabled:
            try:
                grant = await self.authorized_access(action, purpose="execute")
            except (ConnectorFailure, CoworkerError):
                await asyncio.to_thread(
                    self.repo.finish,
                    action_id,
                    "failed",
                    error_code="connection_unavailable",
                    unstarted=True,
                )
                return
        else:
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
        claimed = dict(claimed) | {"owner_id": action["owner_id"]}
        if boundary_enabled:
            try:
                adapter, token = await self.grant_access(
                    grant,
                    claimed,
                    purpose="execute",
                )
            except (ConnectorFailure, CoworkerError):
                await asyncio.to_thread(
                    self.repo.finish,
                    action_id,
                    "failed",
                    error_code="connection_unavailable",
                )
                return
        try:
            if claimed["kind"] == "email_send_with_attachments":
                receipt = await adapter.execute(claimed, token, attachments)
            elif claimed["kind"] == "document_share":
                receipt = await adapter.execute(claimed, token, shared_artifact)
            else:
                # Preserve the v1 connector call shape for existing actions and
                # persisted Temporal workflows; attachments are a new contract.
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
                    if self.repo.settings.connector_trust_boundary_enabled:
                        grant = await self.authorized_access(
                            action,
                            purpose="reconcile",
                        )
                        adapter, token = await self.grant_access(
                            grant,
                            action,
                            purpose="reconcile",
                        )
                    else:
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
