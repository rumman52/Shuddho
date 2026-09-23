from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from .auth import Principal, require_principal
from .config import enabled as coworker_enabled
from .container import Container
from .errors import CoworkerError
from .schemas import PreferencesRequest, TaskCreate, UploadRequest
from .skills import available_skills
from .action_schemas import ActionApproval, ActionPrepare, OAuthFinish, OAuthStart
from .agent_schemas import ActionProposalPromotion, ActionProposalReview, AgentRunCreate
from .memory_schemas import MemoryFactCreate, MemoryFactUpdate

router = APIRouter(prefix="/api/v1", tags=["coworker"])


def get_container(request: Request) -> Container:
    return request.app.state.coworker


async def account(request: Request, principal: Annotated[Principal, Depends(require_principal)]):
    container = get_container(request)
    if container.settings.cohort_enforced and principal.account_id not in container.settings.cohort_account_ids:
        raise CoworkerError(
            "cohort_not_enabled",
            "Coworker access is not enabled for this account yet.",
            403,
        )
    await run_in_threadpool(container.repository.ensure_account, principal)
    return principal


Identity = Annotated[Principal, Depends(account)]
Services = Annotated[Container, Depends(get_container)]


@router.get("/memory")
def list_memory(identity: Identity, services: Services):
    return {"enabled": services.settings.agent_memory_enabled, "facts": services.memory.list(identity.account_id)}


@router.post("/memory", status_code=201)
def create_memory(payload: MemoryFactCreate, identity: Identity, services: Services):
    return services.memory.create(identity.account_id, payload)


@router.put("/memory/{fact_id}")
def update_memory(fact_id: UUID, payload: MemoryFactUpdate, identity: Identity, services: Services):
    return services.memory.update(identity.account_id, str(fact_id), payload)


@router.delete("/memory/{fact_id}")
def delete_memory(fact_id: UUID, identity: Identity, services: Services):
    return services.memory.delete(identity.account_id, str(fact_id))


@router.get("/runtime-manifest")
def runtime_manifest(identity: Identity, services: Services):
    settings = services.settings
    capabilities = {
        "coworker": coworker_enabled(),
        "work_services": settings.work_services_enabled,
        "artifact_services": settings.artifact_services_enabled,
        "agent_runtime": settings.agent_runtime_enabled,
        "intelligent_planner": settings.intelligent_planner_enabled,
        "memory": settings.agent_memory_enabled,
        "handoffs": settings.agent_handoffs_enabled,
        "multi_handoffs": settings.agent_multi_handoffs_enabled,
        "dependency_graph": settings.agent_dependency_graph_enabled,
        "parallel_execution": settings.agent_parallel_execution_enabled,
        "outcome_replan": settings.agent_outcome_replan_enabled,
        "research": settings.research_services_enabled,
        "actions": settings.actions_enabled,
        "action_selection": settings.agent_action_selection_enabled,
        "action_proposals": settings.agent_action_proposals_enabled,
    }
    providers = []
    if settings.actions_enabled:
        providers.append("google")
        if settings.microsoft_actions_enabled:
            providers.append("microsoft")
    return {
        "schema_version": 1,
        "source_revision": settings.source_revision,
        "environment": settings.environment,
        "capabilities": capabilities,
        "action_providers": providers,
        "cohort": {
            "enforced": settings.cohort_enforced,
            "configured_members": len(settings.cohort_account_ids),
            "max_users": settings.cohort_max_users,
        },
    }


@router.get("/agent-tools")
def agent_tools(identity: Identity, services: Services):
    return {"enabled": services.settings.agent_runtime_enabled, "tools": services.agent.tools()}


@router.post("/agent-runs", status_code=202)
def create_agent_run(payload: AgentRunCreate, identity: Identity, services: Services, response: Response,
                     idempotency_key: Annotated[str, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]):
    run, created = services.agent.create(identity.account_id, payload, idempotency_key)
    response.headers["Location"] = f'/api/v1/agent-runs/{run["id"]}'
    response.headers["Idempotent-Replayed"] = "false" if created else "true"
    return run


@router.get("/agent-runs")
def list_agent_runs(identity: Identity, services: Services):
    return {"runs": services.agent.list(identity.account_id)}


@router.get("/agent-runs/{run_id}")
def get_agent_run(run_id: UUID, identity: Identity, services: Services):
    return services.agent.get(identity.account_id, str(run_id))


@router.get("/agent-runs/{run_id}/events")
async def agent_run_events(run_id: UUID, request: Request, identity: Identity, services: Services,
                           after: int = Query(default=0, ge=0), stream: bool = False,
                           last_event_id: Annotated[str | None, Header()] = None):
    if last_event_id:
        if not last_event_id.isdecimal() or len(last_event_id) > 12:
            raise CoworkerError("invalid_cursor", "Invalid agent event cursor.")
        after = max(after, int(last_event_id))
    initial = await run_in_threadpool(services.agent.events, identity.account_id, str(run_id), after)
    if not stream:
        return initial

    async def generate():
        cursor = after
        current = initial
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and time.time() < identity.expires_at:
            if await request.is_disconnected():
                return
            for event in current["events"]:
                cursor = event["sequence"]
                yield f'id: {cursor}\nevent: progress\ndata: {json.dumps(event, ensure_ascii=False)}\n\n'
            if current["terminal"]:
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(1)
            current = await run_in_threadpool(services.agent.events, identity.account_id, str(run_id), cursor)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })


@router.post("/agent-runs/{run_id}/cancel")
def cancel_agent_run(run_id: UUID, identity: Identity, services: Services):
    return services.agent.cancel(identity.account_id, str(run_id))


@router.post(
    "/agent-runs/{run_id}/action-proposals/{proposal_id}/promote",
    status_code=201,
)
def promote_action_proposal(
    run_id: UUID,
    proposal_id: UUID,
    payload: ActionProposalPromotion,
    identity: Identity,
    services: Services,
):
    return services.actions.repo.promote_proposal(
        identity.account_id,
        str(run_id),
        str(proposal_id),
        payload.proposal_hash,
        str(payload.connection_id),
    )


@router.post("/agent-runs/{run_id}/action-proposals/{proposal_id}/dismiss")
def dismiss_action_proposal(
    run_id: UUID,
    proposal_id: UUID,
    payload: ActionProposalReview,
    identity: Identity,
    services: Services,
):
    return services.agent.dismiss_action_proposal(
        identity.account_id,
        str(run_id),
        str(proposal_id),
        payload.proposal_hash,
    )


@router.get("/connections")
def connections(identity: Identity, services: Services):
    return {"enabled": services.settings.actions_enabled, "connections": services.actions.repo.connections(identity.account_id)}


@router.post("/connections/google/start")
async def connect_google(payload: OAuthStart, identity: Identity, services: Services):
    return await services.actions.connect(identity.account_id, payload, "google")


@router.post("/connections/google/finish")
async def finish_google(payload: OAuthFinish, identity: Identity, services: Services):
    return await services.actions.finish_connect(identity.account_id, payload, "google")


@router.post("/connections/microsoft/start")
async def connect_microsoft(payload: OAuthStart, identity: Identity, services: Services):
    return await services.actions.connect(identity.account_id, payload, "microsoft")


@router.post("/connections/microsoft/finish")
async def finish_microsoft(payload: OAuthFinish, identity: Identity, services: Services):
    return await services.actions.finish_connect(identity.account_id, payload, "microsoft")


@router.delete("/connections/{connection_id}")
def disconnect(connection_id: UUID, identity: Identity, services: Services):
    return services.actions.repo.disconnect(identity.account_id, str(connection_id))


@router.post("/actions", status_code=201)
def prepare_action(payload: ActionPrepare, identity: Identity, services: Services,
                   idempotency_key: Annotated[str, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]):
    return services.actions.repo.prepare(identity.account_id, payload, idempotency_key)


@router.get("/actions")
def list_actions(identity: Identity, services: Services):
    return {"actions": services.actions.repo.list(identity.account_id)}


@router.get("/actions/{action_id}")
def get_action(action_id: UUID, identity: Identity, services: Services):
    return services.actions.repo.get(identity.account_id, str(action_id))


@router.post("/actions/{action_id}/approve", status_code=202)
def approve_action(action_id: UUID, payload: ActionApproval, identity: Identity, services: Services):
    return services.actions.repo.approve(identity.account_id, str(action_id), payload.preview_hash)


@router.post("/actions/{action_id}/cancel")
def cancel_action(action_id: UUID, identity: Identity, services: Services):
    return services.actions.repo.cancel(identity.account_id, str(action_id))


@router.post("/actions/{action_id}/reconcile")
async def reconcile_action(action_id: UUID, identity: Identity, services: Services):
    return await services.actions.reconcile_owned(identity.account_id, str(action_id))


@router.get("/me")
def me(identity: Identity, services: Services):
    return services.repository.ensure_account(identity)


@router.put("/preferences")
def preferences(payload: PreferencesRequest, identity: Identity, services: Services):
    return services.repository.save_preferences(identity.account_id, payload.model_dump())


@router.get("/skills")
def skills(identity: Identity, services: Services):
    artifacts = services.settings.artifact_services_enabled
    return {"skills": available_skills(services.settings.work_services_enabled, artifacts, services.settings.research_services_enabled),
            "upload_formats": ["txt", "docx", "pdf"] + (["csv", "xlsx", "pptx"] if artifacts else [])}


@router.get("/documents")
def documents(identity: Identity, services: Services):
    return {"documents": services.repository.list_documents(identity.account_id)}


@router.post("/documents", status_code=201)
def create_document(payload: UploadRequest, identity: Identity, services: Services):
    return services.repository.create_upload(identity.account_id, payload)


@router.delete("/documents/{document_id}", status_code=202)
def delete_document(document_id: UUID, identity: Identity, services: Services):
    return services.repository.delete_document(identity.account_id, str(document_id))


@router.put("/documents/{document_id}/content")
async def upload_content(document_id: UUID, request: Request, identity: Identity, services: Services):
    item = await run_in_threadpool(services.repository.get_upload, identity.account_id, str(document_id))
    if item["state"] == "uploaded":
        return {key: value for key, value in item.items() if key != "object_key"}
    body = bytearray()
    try:
        async with asyncio.timeout(30):
            async for chunk in request.stream():
                if len(body) + len(chunk) > min(item["byte_size"], services.settings.max_upload_bytes):
                    raise CoworkerError("upload_size_mismatch", "The upload exceeds its declared file size.", 413)
                body.extend(chunk)
    except TimeoutError:
        raise CoworkerError("upload_timeout", "The file upload timed out. Please try again.", 408) from None
    if len(body) != item["byte_size"] or hashlib.sha256(body).hexdigest() != item["sha256"]:
        raise CoworkerError("upload_mismatch", "The file upload was incomplete or changed. Select the file again.", 409)
    if item["kind"] == "pdf" and not body.startswith(b"%PDF-") or item["kind"] in {"docx", "pptx", "xlsx"} and not body.startswith(b"PK\x03\x04"):
        raise CoworkerError("file_type_mismatch", "The file content does not match its extension.", 415)
    await run_in_threadpool(services.storage.put, item["object_key"], bytes(body), "application/octet-stream")
    return await run_in_threadpool(services.repository.finish_upload, identity.account_id, str(document_id))


@router.post("/tasks", status_code=202)
def create_task(payload: TaskCreate, identity: Identity, services: Services, response: Response,
                idempotency_key: Annotated[str, Header(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]):
    task, created = services.repository.create_task(identity.account_id, payload, idempotency_key)
    response.headers["Location"] = f'/api/v1/tasks/{task["id"]}'
    response.headers["Idempotent-Replayed"] = "false" if created else "true"
    return task


@router.get("/tasks")
def tasks(identity: Identity, services: Services):
    return {"tasks": services.repository.list_tasks(identity.account_id)}


@router.get("/tasks/{task_id}")
def task(task_id: UUID, identity: Identity, services: Services):
    return services.repository.get_task(identity.account_id, str(task_id))


@router.post("/tasks/{task_id}/cancel")
def cancel(task_id: UUID, identity: Identity, services: Services):
    return services.repository.cancel(identity.account_id, str(task_id))


@router.get("/tasks/{task_id}/events")
async def events(task_id: UUID, request: Request, identity: Identity, services: Services,
                 after: int = Query(default=0, ge=0), stream: bool = False,
                 last_event_id: Annotated[str | None, Header()] = None):
    if last_event_id:
        if not last_event_id.isdecimal() or len(last_event_id) > 12:
            raise CoworkerError("invalid_cursor", "Invalid task event cursor.")
        after = max(after, int(last_event_id))
    initial = await run_in_threadpool(services.repository.events, identity.account_id, str(task_id), after)
    if not stream:
        return initial

    async def generate():
        cursor = after
        current = initial
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and time.time() < identity.expires_at:
            if await request.is_disconnected():
                return
            for event in current["events"]:
                cursor = event["sequence"]
                yield f'id: {cursor}\nevent: progress\ndata: {json.dumps(event, ensure_ascii=False)}\n\n'
            if current["terminal"]:
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(1)
            current = await run_in_threadpool(services.repository.events, identity.account_id, str(task_id), cursor)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })


@router.get("/artifacts/{artifact_id}/download")
def download(artifact_id: UUID, identity: Identity, services: Services):
    artifact = services.repository.artifact(identity.account_id, str(artifact_id))
    url = services.storage.download_url(artifact["object_key"], artifact["filename"], artifact["content_type"])
    return {"filename": artifact["filename"], "url": url, "content_path": f"/api/v1/artifacts/{artifact_id}/content" if url is None else None}


@router.get("/artifacts/{artifact_id}/content")
def content(artifact_id: UUID, identity: Identity, services: Services):
    artifact = services.repository.artifact(identity.account_id, str(artifact_id))
    body = services.storage.get(artifact["object_key"], min(artifact["byte_size"], 16 * 1024 * 1024))
    if hashlib.sha256(body).hexdigest() != artifact["sha256"]:
        raise CoworkerError("artifact_invalid", "This download could not be verified. Please retry.", 503)
    return Response(body, media_type=artifact["content_type"], headers={
        "Content-Disposition": f'attachment; filename="{artifact["filename"]}"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


def mount(app, container: Container):
    app.state.coworker = container
    app.include_router(router)

    previous_validation_handler = app.exception_handlers.get(RequestValidationError)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if not request.url.path.startswith("/api/v1/") and previous_validation_handler:
            return await previous_validation_handler(request, error)
        # Pydantic errors can include the original document or non-JSON values.
        message = ("Check the full email addresses, required content, start/end times and IANA time zone. A time skipped or repeated by daylight saving needs a different time or an explicit UTC offset."
                   if request.url.path.startswith("/api/v1/actions") else "Check the required fields, language code, and file limits.")
        return JSONResponse({"error": {"code": "invalid_request", "message": message},
                             "fields": [list(item["loc"]) for item in error.errors()]}, status_code=422)

    @app.exception_handler(CoworkerError)
    async def coworker_error(_request, error):
        return JSONResponse({"error": {"code": error.code, "message": error.message}}, status_code=error.status_code,
                            headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def private_responses(request, call_next):
        if request.url.path.startswith("/api/v1/") and request.method in {"POST", "PUT"} and not request.url.path.endswith("/content"):
            body = bytearray()
            try:
                async with asyncio.timeout(15):
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > 256 * 1024:
                            return JSONResponse({"error": {"code": "request_too_large", "message": "This request is too large."}}, status_code=413)
                        body.extend(chunk)
                request._body = bytes(body)
            except TimeoutError:
                return JSONResponse({"error": {"code": "request_timeout", "message": "The request timed out."}}, status_code=408)
        if not request.url.path.startswith("/api/v1/") and request.headers.get("authorization", "").lower().startswith("bearer "):
            return JSONResponse({"error": {"code": "account_route_required", "message": "Account sessions are accepted only by the workspace API."}}, status_code=400)
        try:
            response = await call_next(request)
        except Exception as error:
            if not request.url.path.startswith("/api/v1/"):
                raise
            logging.getLogger("shuddho.coworker").error("Workspace request unavailable error_type=%s", type(error).__name__)
            return JSONResponse({"error": {"code": "workspace_unavailable", "message": "Your workspace is temporarily unavailable. Please try again."}},
                                status_code=503, headers={"Cache-Control": "no-store"})
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        try:
            async with previous_lifespan(application) as state:
                yield state
        finally:
            container.repository.sessions.kw["bind"].dispose()

    app.router.lifespan_context = lifespan
