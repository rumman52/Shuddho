"""Explicit user commands only; models have no access to this executor."""
import asyncio

from .action_repository import ActionRepository, TERMINAL
from .errors import CoworkerError
from .google_actions import GoogleActions, GoogleFailure, SCOPES


class ActionService:
    def __init__(self, repository: ActionRepository, provider: GoogleActions):
        self.repo, self.provider = repository, provider

    async def connect(self, owner, request):
        state, verifier = await asyncio.to_thread(self.repo.start_oauth, owner, request.capability)
        return {"authorization_url": self.provider.authorization_url(state, verifier, request.capability), "state": state}

    async def finish_connect(self, owner, request):
        attempt = await asyncio.to_thread(self.repo.consume_oauth, owner, request.state)
        try:
            token = await self.provider.exchange(request.code, attempt["verifier"])
            scopes = token["scope"].split()
            if SCOPES[attempt["capability"]] not in scopes:
                raise GoogleFailure("oauth_scope_missing", definitive=True)
            profile = await self.provider.profile(token["access_token"])
            return await asyncio.to_thread(self.repo.finish_connection, owner, attempt, profile, token["refresh_token"], scopes)
        except GoogleFailure:
            raise CoworkerError("connection_failed", "Google could not finish connecting. Start again and grant the requested permission.", 409) from None

    async def access(self, action):
        credentials = await asyncio.to_thread(self.repo.credentials, action["connection_id"])
        capability = "email" if action["kind"] == "email_send" else "calendar"
        if SCOPES[capability] not in credentials["scopes"]:
            raise GoogleFailure("connection_scope_missing", definitive=True)
        token = await self.provider.refresh(credentials["refresh_token"])
        if "scope" in token and (not isinstance(token["scope"], str) or SCOPES[capability] not in token["scope"].split()):
            raise GoogleFailure("connection_scope_missing", definitive=True)
        if isinstance(token.get("refresh_token"), str) and 1 <= len(token["refresh_token"]) <= 8192:
            await asyncio.to_thread(self.repo.rotate_token, action["connection_id"], token["refresh_token"])
        profile = await self.provider.profile(token["access_token"])
        if profile["sub"] != action["preview"]["subject_id"] or profile["email"] != action["preview"]["account"]:
            raise GoogleFailure("connection_identity_changed", definitive=True)
        return token["access_token"]

    async def execute(self, action_id):
        action = await asyncio.to_thread(self.repo.worker_get, action_id)
        if action["state"] in TERMINAL and action["state"] != "outcome_unknown":
            return
        if action["state"] in {"executing", "outcome_unknown"}:
            await self.reconcile(action)
            return
        if action["state"] != "queued":
            return  # A workflow cannot turn an unapproved preview into a send.
        self.repo.enabled()
        try:
            token = await self.access(action)  # Read-only preflight before claim.
        except (GoogleFailure, CoworkerError):
            await asyncio.to_thread(self.repo.finish, action_id, "failed", error_code="connection_unavailable", unstarted=True)
            return
        claimed = await asyncio.to_thread(self.repo.claim_execution, action_id)
        if not claimed:
            return
        try:
            receipt = await self.provider.execute(claimed, token)
        except GoogleFailure as error:
            if error.definitive:
                await asyncio.to_thread(self.repo.finish, action_id, "failed", error_code=error.code)
            else:
                await self.reconcile(claimed, token)
            return
        # A database failure here causes a retry to reconcile, never to POST
        # again. For Gmail this remains unknown if the receipt was lost.
        await asyncio.to_thread(self.repo.finish, action_id, "succeeded", receipt=receipt)

    async def reconcile(self, action, token=None):
        receipt = None
        if action["kind"] == "calendar_create" and self.repo.settings.actions_enabled:
            try:
                token = token or await self.access(action)
                receipt = await self.provider.reconcile(action, token)
            except (GoogleFailure, CoworkerError):
                pass
        if receipt:
            await asyncio.to_thread(self.repo.finish, action["id"], "succeeded", receipt=receipt)
        else:
            await asyncio.to_thread(self.repo.finish, action["id"], "outcome_unknown", error_code="provider_outcome_unknown")

    async def reconcile_owned(self, owner, action_id):
        self.repo.enabled()
        action = await asyncio.to_thread(self.repo.reserve_reconciliation, owner, action_id)
        await self.reconcile(action)
        return await asyncio.to_thread(self.repo.get, owner, action_id)
