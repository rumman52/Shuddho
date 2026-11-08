from coworker_worker_helpers import run_dispatcher
"""Local-only browser fixture: real auth verification, DB, Temporal and exports.

The identity and model responses are test fixtures. This file is excluded from
the Docker image and must never be installed as a deployed service.
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from temporalio.testing import WorkflowEnvironment

from sqlalchemy import select

from test_coworker import FakeModel, account, draft
from coworker_samples import work_draft
from research_samples import SimulatedResearch
from action_samples import enable_actions
from test_coworker_temporal import make_worker
from services.coworker.api import mount
from services.coworker.auth import JwtVerifier
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.drafting import DraftResult
from services.coworker.agent_runtime import AgentRuntime
from services.coworker.agent_schemas import AgentPlannerProposal, AgentV3Decision
from services.coworker.migrate import upgrade
from services.coworker.runner import DocumentRunner
from services.coworker.models import AgentRun

if os.getenv("SHUDDHO_BROWSER_TESTS") != "true":
    raise RuntimeError("This fixture requires SHUDDHO_BROWSER_TESTS=true")
folder = Path(os.environ["SHUDDHO_TEST_WORKDIR"])
folder.mkdir(parents=True, exist_ok=True)
issuer = "https://identity.example.test/auth/v1"
settings = Settings(database_url=f"sqlite:///{folder / 'browser.sqlite3'}", auth_issuer=issuer,
                    environment="development", storage_backend="local", local_storage_path=folder / "files", work_services_enabled=True,
                    artifact_services_enabled=True, research_services_enabled=True, search_api_key="fixture-only-search-key",
                    conversations_enabled=True, projects_enabled=True, conversation_replies_enabled=True,
                    deepseek_api_key="browser-fixture-only-chat-key")
upgrade(settings.database_url)
container = Container.create(settings)
google_fixture = enable_actions(container)
settings = replace(
    container.settings,
    agent_runtime_enabled=True,
    intelligent_planner_enabled=True,
    agent_action_proposals_enabled=True,
    action_attachments_enabled=True,
    action_reminders_enabled=True,
    max_active_agent_runs=3,  # Match the three-run acceptance scenario; production default stays bounded at two.
)
settings.validate()
container.settings = settings
container.repository.settings = settings
container.projects.settings = settings
container.conversations.settings = settings
container.conversation_replies.settings = settings
container.actions.repo.settings = settings
container.agent.settings = settings
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": "browser-test", "alg": "RS256"}
container.verifier = JwtVerifier(issuer, "authenticated", httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [jwk]})))
now = int(time.time())
sessions = {}
for subject in ["alice", "bob"]:
    user = {"id": subject, "aud": "authenticated", "role": "authenticated", "email": subject + "@example.test",
            "app_metadata": {"provider": "email"}, "user_metadata": {}, "created_at": "2026-09-13T00:00:00Z"}
    token = jwt.encode({"iss": issuer, "sub": subject, "aud": "authenticated", "role": "authenticated", "iat": now, "exp": now + 3600},
                       key, algorithm="RS256", headers={"kid": "browser-test"})
    sessions[subject] = {"access_token": token, "refresh_token": "test-only-refresh-" + subject, "token_type": "bearer", "expires_in": 3600, "expires_at": now + 3600, "user": user}
(folder / "sessions.json").write_text(json.dumps(sessions))
(folder / "sessions.json").chmod(0o600)


class BrowserChatModel:
    def __init__(self):
        self.messages = []

    async def generate(self, messages):
        self.messages = messages
        return "This reply used the project instructions."


chat_model = BrowserChatModel()
container.conversation_replies.model = chat_model


class BrowserModel(FakeModel):
    def messages(self, task, sources):
        return [{"role": "user", "content": json.dumps({"skill_id": task["skill_id"], "sources": sources})}]

    async def generate(self, _messages, language, source_ids):
        await asyncio.sleep(2)  # Exercise progress, navigation and refresh.
        skill_id = json.loads(_messages[-1]["content"])["skill_id"]
        if skill_id == "report_email":
            value = draft(language)
            value.report.sections[0].source_ids = sorted(source_ids)
        else:
            value = work_draft(skill_id, language, sorted(source_ids))
        return DraftResult(value, 180, 2000)


class BrowserAgentPlanner:
    """Deterministic local planner for real conversation-to-Temporal browser tests."""

    def __init__(self):
        self.calls = []
        self.release = asyncio.Event()

    def reset(self):
        self.calls.clear()
        self.release = asyncio.Event()

    async def decide(self, goal, tools, observations, *, remaining_budget, dependencies):
        steering = dependencies.get("steering") or {}
        call = {
            "goal": goal,
            "steering_revision": int(steering.get("revision", 0)),
            "steering_instructions": list(steering.get("instructions") or []),
            "observation_count": len(observations),
            "available_tools": list(tools),
        }
        self.calls.append(call)
        await self.release.wait()
        if observations:
            decision = AgentV3Decision(decision="complete")
        elif "document.create" in tools:
            steering_text = " ".join(
                str(item.get("instruction", ""))
                for item in call["steering_instructions"]
                if isinstance(item, dict)
            ).lower()
            objective = (
                "Create a concise Bangla summary document that satisfies the user's task."
                if "bangla" in steering_text
                else "Create a concise document that satisfies the user's task."
            )
            decision = AgentV3Decision(
                decision="next_step",
                tool="document.create",
                objective=objective,
            )
        else:
            decision = AgentV3Decision(
                decision="blocked",
                message="The browser fixture has no eligible document tool.",
            )
        call["decision"] = decision.decision
        call["selected_tool"] = decision.tool
        call["objective"] = decision.objective
        return decision, 42, 1, {
            "model": "browser-fixture-v3",
            "prompt_sha256": "a" * 64,
            "tool_schema_sha256": "b" * 64,
        }

    async def propose(self, goal, tools, **kwargs):
        assert kwargs.get("allow_action_proposals") is True
        tool = "email.draft" if "email.draft" in tools else tools[0]
        return AgentPlannerProposal.model_validate({
            "steps": [{"tool": tool, "objective": "Draft the requested project update."}],
            "action_proposals": [{
                "payload": {
                    "kind": "email_send",
                    "to": ["recipient@example.org"],
                    "cc": [],
                    "bcc": [],
                    "subject": "Agent project update",
                    "body": "The project is ready for review.",
                },
                "rationale": "The goal explicitly requested this email.",
            }],
        }), 42, 1


browser_agent_planner = None


@asynccontextmanager
async def lifespan(_app):
    global browser_agent_planner
    async with await WorkflowEnvironment.start_time_skipping() as env:
        stop = asyncio.Event()
        runner = DocumentRunner(container, BrowserModel(), research=SimulatedResearch(settings))
        browser_agent_planner = BrowserAgentPlanner()
        runtime = AgentRuntime(container, runner, planner=browser_agent_planner)
        worker_id = await asyncio.to_thread(
            container.repository.register_worker,
            task_queue=settings.task_queue,
            source_revision=settings.source_revision,
        )
        state = await asyncio.to_thread(container.repository.heartbeat_worker, worker_id)
        if state != "running":
            raise RuntimeError(f"Browser fixture worker failed to enter running state: {state}")
        async with make_worker(env, runner, agent_runtime=runtime):
            dispatcher = asyncio.create_task(run_dispatcher(container, env.client, stop, worker_id))
            try:
                yield
            finally:
                stop.set()
                await dispatcher
        # Match production: certify drain only after the Temporal worker context exits.
        await asyncio.to_thread(container.repository.mark_worker_drained, worker_id)


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
mount(app, container)


@app.get("/health")
def health():
    return {"status": "ok", "fixture": True}


@app.get("/fixture/chat/context")
def chat_context():
    return {"messages": chat_model.messages}


@app.get("/fixture/actions/counts")
def action_counts():
    return {"emails": len(google_fixture.sent), "events": len(google_fixture.events)}


def _set_agent_runtime_v3(enabled: bool):
    updated = replace(container.settings, agent_runtime_v3_enabled=enabled)
    updated.validate()
    container.settings = updated
    services = (
        container.repository, container.projects, container.conversations,
        container.conversation_replies, container.conversation_dispatch,
        container.agent, getattr(container, "context", None),
        getattr(container, "memory", None),
    )
    for service in services:
        if service is not None and hasattr(service, "settings"):
            service.settings = updated
    if getattr(container, "actions", None) is not None and hasattr(container.actions, "repo"):
        container.actions.repo.settings = updated
    return updated


@app.post("/fixture/agent/enable-v3")
async def enable_agent_runtime_v3():
    if browser_agent_planner is None:
        raise RuntimeError("Browser Agent planner is not ready.")
    browser_agent_planner.reset()
    _set_agent_runtime_v3(True)
    return {"enabled": True}


@app.post("/fixture/agent/disable-v3")
async def disable_agent_runtime_v3():
    if browser_agent_planner is not None:
        browser_agent_planner.release.set()
    _set_agent_runtime_v3(False)
    return {"enabled": False}


@app.post("/fixture/agent/release-planner")
async def release_agent_planner():
    if browser_agent_planner is None:
        raise RuntimeError("Browser Agent planner is not ready.")
    browser_agent_planner.release.set()
    return {"released": True}


@app.get("/fixture/agent/planner-calls")
def agent_planner_calls():
    return {"calls": list(browser_agent_planner.calls if browser_agent_planner is not None else [])}


@app.get("/fixture/agent/runs")
def agent_runs():
    owner = account(container, "alice")
    with container.repository.sessions() as db:
        ids = db.scalars(select(AgentRun.id).where(AgentRun.owner_id == owner)).all()
    runs = [container.agent.get(owner, str(run_id)) for run_id in ids]
    return {"runs": [{
        "id": run["id"],
        "goal": run["goal"],
        "state": run["state"],
        "steering_revision": run["steering_revision"],
        "steering_instructions": run.get("steering_instructions", []),
        "decision_count": len(run.get("decisions", [])),
        "tool_invocation_count": len(run.get("tool_invocations", [])),
        "tool_receipts": [
            invocation["receipt"]
            for invocation in run.get("tool_invocations", [])
            if invocation.get("receipt") is not None
        ],
    } for run in runs]}


@app.post("/fixture/actions/lose-reply")
def lose_reply():
    google_fixture.lose_reply = True
    return {"fixture": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
