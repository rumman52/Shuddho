"""Paid-provider, real-Temporal integration qualification. Opt in explicitly."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("temporalio")
pytestmark = [
    pytest.mark.coworker_integration,
    pytest.mark.skipif(
        os.getenv("SHUDDHO_RUNTIME_V3_LIVE_QUALIFICATION") != "true",
        reason="live DeepSeek qualification is opt-in and may incur provider cost",
    ),
]

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from coworker_worker_helpers import dispatch_tick
from scripts.runtime_v3_qualification import (
    RecordingTransport,
    require_live_configuration,
    summarize_model_calls,
    write_evidence,
)
from services.coworker.agent_planning_model import DeepSeekAgentPlanner
from services.coworker.agent_runtime import AgentRuntime
from services.coworker.agent_schemas import AgentRunCreate
from services.coworker.drafting import DeepSeekDraftModel
from services.coworker.runner import DocumentRunner
from services.coworker.worker import ActionActivities, Activities, AgentActivities
from services.coworker.workflow import (
    AgentWorkflow,
    AgentWorkflowV2,
    AgentWorkflowV3,
    ApprovedActionWorkflow,
    ReportEmailWorkflow,
    ResearchWorkflow,
    WorkServicesWorkflow,
)
from test_coworker import account, container


TOOL_SCOPE = ["document.create", "email.draft"]


def _configuration() -> dict[str, Any]:
    return require_live_configuration(dict(os.environ))


def _configure_container(container, config: dict[str, Any]):
    settings = replace(
        container.settings,
        source_revision=config["source_revision"],
        deepseek_api_key=config["api_key"],
        deepseek_model=config["model"],
        agent_runtime_enabled=True,
        agent_runtime_v3_enabled=True,
        intelligent_planner_enabled=True,
        work_services_enabled=True,
        artifact_services_enabled=True,
        agent_handoffs_enabled=True,
        agent_multi_handoffs_enabled=True,
        agent_v3_planner_cost_microusd_per_1k_tokens=(
            config["cost_rate_microusd_per_1k_tokens"]
        ),
        max_agent_v3_planner_calls=4,
        agent_v3_planner_token_budget=24000,
        max_agent_model_calls_per_run=12,
        max_agent_tokens_per_run=250000,
        max_agent_tool_calls_per_run=8,
    )
    settings.validate()
    container.settings = settings
    for service in (
        container.repository,
        container.agent,
        container.memory,
        container.context,
        container.automations,
        container.actions,
        container.notifications,
        container.connector_reads,
        container.browser,
        container.sandbox,
    ):
        if hasattr(service, "settings"):
            service.settings = settings
    return settings


class RecordingPlanner:
    def __init__(self, settings, transport: RecordingTransport):
        self.transport = transport
        self.delegate = DeepSeekAgentPlanner(settings, transport=transport)

    async def decide(self, *args, **kwargs):
        with self.transport.measure_as("planner"):
            return await self.delegate.decide(*args, **kwargs)


class RecordingDocumentRunner(DocumentRunner):
    def __init__(self, container, settings, transport: RecordingTransport):
        self.transport = transport
        super().__init__(
            container,
            DeepSeekDraftModel(settings, transport=transport),
        )

    async def draft(self, task):
        with self.transport.measure_as("draft"):
            return await super().draft(task)


class LostAcknowledgementRunner(RecordingDocumentRunner):
    """Lose the first document-draft activity acknowledgement after its DB checkpoint."""

    def __init__(self, container, settings, transport, checkpoint):
        super().__init__(container, settings, transport)
        self.checkpoint = checkpoint
        self.interrupted = False

    async def draft(self, task):
        result = await super().draft(task)
        if (
            task.get("agent_run_id")
            and task.get("skill_id") == "document"
            and not self.interrupted
        ):
            self.interrupted = True
            self.checkpoint.set()
            raise RuntimeError("simulated worker loss after persisted draft checkpoint")
        return result


def _make_worker(env, runner, runtime):
    activities = Activities(runner)
    actions = ActionActivities(runner.container.actions)
    agent = AgentActivities(runtime)
    return Worker(
        env.client,
        task_queue=runner.container.settings.task_queue,
        workflows=[
            ReportEmailWorkflow,
            WorkServicesWorkflow,
            ResearchWorkflow,
            ApprovedActionWorkflow,
            AgentWorkflow,
            AgentWorkflowV2,
            AgentWorkflowV3,
        ],
        activities=[
            activities.phase,
            activities.work_phase,
            activities.research_phase,
            activities.failed,
            actions.execute,
            actions.interrupted,
            agent.plan,
            agent.replan,
            agent.decide_v3,
            agent.readiness,
            agent.step,
            agent.complete,
            agent.failed,
        ],
        max_cached_workflows=0,
        graceful_shutdown_timeout=timedelta(seconds=2),
    )


def _new_run(container, owner: str, language: str, *, allowlist=None):
    goals = {
        "en": (
            "First use document.create to create a concise document titled "
            "'Project review summary' containing this exact fact: 'The team completed "
            "12 reviews on 9 November 2026.' Then use email.draft to prepare a "
            "follow-up email to team@example.test with subject 'Project review update' "
            "that repeats the same fact from the created document. Do not send the "
            "email or perform any external action."
        ),
        "bn": (
            "প্রথমে document.create ব্যবহার করে 'প্রকল্প পর্যালোচনা সারাংশ' শিরোনামে "
            "একটি সংক্ষিপ্ত নথি তৈরি করো, যেখানে এই তথ্যটি থাকবে: 'দলটি ৯ নভেম্বর "
            "২০২৬ তারিখে ১২টি পর্যালোচনা সম্পন্ন করেছে।' এরপর email.draft ব্যবহার "
            "করে team@example.test ঠিকানায় 'প্রকল্প পর্যালোচনার আপডেট' বিষয়ে একটি "
            "ফলো-আপ ইমেইলের খসড়া তৈরি করো এবং তৈরি করা নথির একই তথ্য ব্যবহার করো। "
            "ইমেইলটি পাঠাবে না বা কোনো বাহ্যিক কাজ করবে না।"
        ),
    }
    run, _created = container.agent.create(
        owner,
        AgentRunCreate(goal=goals[language], output_language=language),
        "runtime-v3-live-" + language + "-" + uuid.uuid4().hex,
        tool_allowlist=allowlist or TOOL_SCOPE,
    )
    assert run["runtime_version"] == 3
    return run


def _draft_text(value: dict[str, Any]) -> str:
    pieces: list[str] = []
    report = value.get("report") or {}
    pieces.extend([str(report.get("title") or ""), str(report.get("summary") or "")])
    for section in report.get("sections") or []:
        pieces.append(str(section.get("heading") or ""))
        pieces.extend(str(item) for item in section.get("paragraphs") or [])
    email = value.get("email") or {}
    pieces.extend([str(email.get("subject") or ""), str(email.get("body") or "")])
    return "\n".join(piece for piece in pieces if piece.strip())


def _evidence_path() -> Path:
    return Path(os.getenv(
        "SHUDDHO_RUNTIME_V3_EVIDENCE_PATH",
        "artifacts/runtime-v3-live-qualification.json",
    ))


def _assert_model_metrics(transport: RecordingTransport, settings) -> dict[str, Any]:
    metrics = summarize_model_calls(
        transport.records,
        settings.agent_v3_planner_cost_microusd_per_1k_tokens,
    )
    assert metrics["model_call_count"] > 0
    assert metrics["successful_model_call_count"] == metrics["model_call_count"]
    assert metrics["failed_model_call_count"] == 0
    assert metrics["token_usage_complete"] is True
    assert metrics["total_tokens"] > 0
    assert metrics["estimated_cost_microusd"] > 0
    assert metrics["p50_latency_ms"] is not None
    assert metrics["p95_latency_ms"] is not None
    return metrics


def _write_run_evidence(
    *,
    case_id: str,
    language: str,
    settings,
    run: dict,
    saved: dict,
    transport: RecordingTransport,
    history: str,
    restart_count: int = 0,
    cancelled_before_decision_commit: bool = False,
    output_preview: str = "",
    workflow_duration_ms: int | None = None,
) -> None:
    rate = settings.agent_v3_planner_cost_microusd_per_1k_tokens
    metrics = summarize_model_calls(transport.records, rate)
    payload = {
        "qualification": "runtime-v3-live-model-temporal",
        "case_id": case_id,
        "language": language,
        "source_revision": settings.source_revision,
        "model": settings.deepseek_model,
        "temporal_environment": "Temporal test server; workflow history persisted across worker replacement",
        "storage_environment": "isolated SQLite and local test object store",
        "run_id": run["id"],
        "runtime_version": saved.get("runtime_version"),
        "final_state": saved.get("state"),
        "workflow_duration_ms": workflow_duration_ms,
        "workflow_duration_scope": (
            "wall-clock elapsed time; Temporal test-server timer skipping may compress retry waits"
        ),
        "planner_calls": saved.get("planner_calls"),
        "planner_actual_tokens": saved.get("planner_actual_tokens"),
        "decisions": [
            {
                "decision": item.get("decision"),
                "tool": (item.get("payload") or {}).get("tool"),
                "ordinal": (item.get("payload") or {}).get("ordinal"),
            }
            for item in saved.get("decisions", [])
        ],
        "tool_receipts": [
            {
                "tool": item.get("tool"),
                "status": (item.get("receipt") or {}).get("status"),
                "resource_type": (item.get("receipt") or {}).get("resource_type"),
                "resource_id": (item.get("receipt") or {}).get("resource_id"),
            }
            for item in saved.get("tool_invocations", [])
        ],
        "model_metrics": metrics,
        "workflow_history_sha256": hashlib.sha256(history.encode("utf-8")).hexdigest(),
        "workflow_history_contains_goal": False,
        "workflow_history_contains_api_key": False,
        "worker_restart_count": restart_count,
        "cancelled_before_decision_commit": cancelled_before_decision_commit,
        "generated_output_preview": output_preview[:1600],
        "human_review": {
            "required": True,
            "status": "pending",
            "dimensions": [
                "task completion and tool ordering",
                "grounding in the verified upstream artifact",
                "Bangla or English fluency and naturalness",
                "factual fidelity and absence of unsupported claims",
                "email remains a draft and is not sent",
            ],
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    assert _configuration()["api_key"] not in encoded
    write_evidence(_evidence_path(), payload)


async def _run_to_completion(container, env, runner, runtime, run_id: str):
    async with _make_worker(env, runner, runtime):
        started = time.perf_counter()
        await dispatch_tick(container, env.client)
        handle = env.client.get_workflow_handle("shuddho-agent-" + run_id)
        async with env.time_skipping_unlocked():
            await asyncio.wait_for(handle.result(), timeout=240)
        history = (await handle.fetch_history()).to_json()
        workflow_duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    return handle, history, workflow_duration_ms


@pytest.mark.parametrize("language", ["en", "bn"])
def test_runtime_v3_live_bilingual_grounded_multistep_temporal_workflow(container, language):
    async def scenario():
        config = _configuration()
        settings = _configure_container(container, config)
        transport = RecordingTransport(model=settings.deepseek_model)
        try:
            owner = account(container)
            run = _new_run(container, owner, language)
            runner = RecordingDocumentRunner(container, settings, transport)
            runtime = AgentRuntime(
                container,
                runner,
                planner=RecordingPlanner(settings, transport),
            )
            async with await WorkflowEnvironment.start_time_skipping() as env:
                _handle, history, workflow_duration_ms = await _run_to_completion(
                    container, env, runner, runtime, run["id"]
                )

            saved = container.agent.get(owner, run["id"])
            assert saved["state"] == "completed"
            assert saved["runtime_version"] == 3
            assert saved["planner_mode"] == "v3"
            assert saved["planner_calls"] == 3
            assert saved["planner_actual_tokens"] > 0
            assert [item["tool"] for item in saved["tool_invocations"]] == TOOL_SCOPE
            assert all(
                (item.get("receipt") or {}).get("status") == "completed"
                for item in saved["tool_invocations"]
            )
            assert len(saved["decisions"]) == 3
            assert [item["decision"] for item in saved["decisions"]] == [
                "next_step", "next_step", "complete"
            ]

            upstream, downstream = saved["tool_invocations"]
            handoff_source_id = "agent-step-" + upstream["id"]
            email_draft = container.repository.step(
                downstream["receipt"]["resource_id"], "draft"
            )
            assert email_draft is not None
            assert any(
                source.get("id") == handoff_source_id
                for source in email_draft["sources"]
            )
            provenance = email_draft["handoff_provenance"]
            assert any(
                item.get("tool") == "document.create"
                and item.get("invocation_id") == upstream["id"]
                for item in provenance
            )
            handoff_source = next(
                source for source in email_draft["sources"]
                if source.get("id") == handoff_source_id
            )
            assert len(handoff_source["sha256"]) == 64
            assert hashlib.sha256(
                handoff_source["text"].encode("utf-8")
            ).hexdigest() == handoff_source["sha256"]
            output = _draft_text(email_draft["draft"])
            assert output.strip()
            assert {source["id"] for source in email_draft["sources"]} == {
                "brief", handoff_source_id
            }
            assert set(email_draft["draft"]["source_ids"]) == {
                "brief", handoff_source_id
            }
            assert any(value in handoff_source["text"] for value in ("12", "১২"))
            assert any(value in output for value in ("12", "১২", "twelve"))
            assert email_draft["draft"]["output_language"].lower() == language
            if language == "bn":
                assert any("\u0980" <= char <= "\u09ff" for char in output)
            assert "shuddho-agent-" + run["id"] in history
            assert run["goal"] not in history
            assert config["api_key"] not in history

            metrics = _assert_model_metrics(transport, settings)
            assert metrics["model_call_count"] == 5
            assert sum(item["kind"] == "planner" for item in transport.records) == 3
            assert sum(item["kind"] == "draft" for item in transport.records) == 2

            _write_run_evidence(
                case_id=f"{language}-grounded-multistep",
                language=language,
                settings=settings,
                run=run,
                saved=saved,
                transport=transport,
                history=history,
                output_preview=output,
                workflow_duration_ms=workflow_duration_ms,
            )
        finally:
            await transport.close()

    asyncio.run(scenario())


def test_runtime_v3_live_temporal_worker_restart_replays_saved_draft_once(container):
    async def scenario():
        config = _configuration()
        settings = _configure_container(container, config)
        transport = RecordingTransport(model=settings.deepseek_model)
        checkpoint = asyncio.Event()
        try:
            owner = account(container)
            run = _new_run(container, owner, "en")
            runner = LostAcknowledgementRunner(
                container, settings, transport, checkpoint
            )
            runtime = AgentRuntime(
                container,
                runner,
                planner=RecordingPlanner(settings, transport),
            )
            async with await WorkflowEnvironment.start_time_skipping() as env:
                workflow_started = time.perf_counter()
                first_worker = _make_worker(env, runner, runtime)
                first_worker_task = asyncio.create_task(first_worker.run())
                await dispatch_tick(container, env.client)
                await asyncio.wait_for(checkpoint.wait(), timeout=240)
                await first_worker.shutdown()
                await asyncio.wait_for(first_worker_task, timeout=30)

                handle = env.client.get_workflow_handle(
                    "shuddho-agent-" + run["id"]
                )
                async with _make_worker(env, runner, runtime):
                    async with env.time_skipping_unlocked():
                        await asyncio.wait_for(handle.result(), timeout=240)
                history = (await handle.fetch_history()).to_json()
                workflow_duration_ms = max(
                    0, int((time.perf_counter() - workflow_started) * 1000)
                )

            saved = container.agent.get(owner, run["id"])
            assert saved["state"] == "completed"
            assert len(saved["tool_invocations"]) == 2
            assert [item["tool"] for item in saved["tool_invocations"]] == TOOL_SCOPE
            assert sum(item["kind"] == "planner" for item in transport.records) == 3
            assert sum(item["kind"] == "draft" for item in transport.records) == 2
            _assert_model_metrics(transport, settings)
            assert len([
                item for item in saved["tool_invocations"]
                if (item.get("receipt") or {}).get("status") == "completed"
            ]) == 2
            assert run["goal"] not in history
            assert config["api_key"] not in history

            first_task_id = saved["tool_invocations"][0]["receipt"]["resource_id"]
            first_task = container.repository.get_task(owner, first_task_id)
            assert first_task["state"] == "completed"
            assert first_task["usage"]["model_attempts"] == 1

            _write_run_evidence(
                case_id="en-worker-restart-after-draft-checkpoint",
                language="en",
                settings=settings,
                run=run,
                saved=saved,
                transport=transport,
                history=history,
                restart_count=1,
                workflow_duration_ms=workflow_duration_ms,
            )
        finally:
            transport.release_response.set()
            await transport.close()

    asyncio.run(scenario())


def test_runtime_v3_live_cancellation_discards_late_provider_response(container):
    async def scenario():
        config = _configuration()
        settings = _configure_container(container, config)
        transport = RecordingTransport(
            model=settings.deepseek_model,
            hold_first_successful_response=True,
        )
        try:
            owner = account(container)
            run = _new_run(
                container, owner, "en", allowlist=["document.create"]
            )
            runner = RecordingDocumentRunner(container, settings, transport)
            runtime = AgentRuntime(
                container,
                runner,
                planner=RecordingPlanner(settings, transport),
            )
            async with await WorkflowEnvironment.start_time_skipping() as env:
                async with _make_worker(env, runner, runtime):
                    workflow_started = time.perf_counter()
                    await dispatch_tick(container, env.client)
                    await asyncio.wait_for(
                        transport.response_ready.wait(), timeout=180
                    )
                    cancelled = container.agent.cancel(owner, run["id"])
                    assert cancelled["cancel_requested"] is True
                    assert cancelled["state"] == "cancelled"
                    transport.release_response.set()
                    handle = env.client.get_workflow_handle(
                        "shuddho-agent-" + run["id"]
                    )
                    async with env.time_skipping_unlocked():
                        try:
                            await asyncio.wait_for(handle.result(), timeout=90)
                        except Exception as error:
                            assert (
                                "agent_cancelled" in str(error)
                                or "cancelled" in str(error).lower()
                            )
                    history = (await handle.fetch_history()).to_json()
                    workflow_duration_ms = max(
                        0, int((time.perf_counter() - workflow_started) * 1000)
                    )

            saved = container.agent.get(owner, run["id"])
            assert saved["state"] == "cancelled"
            assert saved["planner_calls"] == 1
            assert saved["decisions"] == []
            assert saved["tool_invocations"] == []
            assert len(transport.records) == 1
            assert transport.records[0]["kind"] == "planner"
            assert transport.records[0]["status_code"] == 200
            assert transport.records[0]["total_tokens"] is not None
            _assert_model_metrics(transport, settings)
            assert run["goal"] not in history
            assert config["api_key"] not in history

            _write_run_evidence(
                case_id="en-cancel-late-planner-response",
                language="en",
                settings=settings,
                run=run,
                saved=saved,
                transport=transport,
                history=history,
                cancelled_before_decision_commit=True,
                workflow_duration_ms=workflow_duration_ms,
            )
        finally:
            transport.release_response.set()
            await transport.close()

    asyncio.run(scenario())
