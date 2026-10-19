from __future__ import annotations

import hashlib
import json

from .browser import normalize_browser_target
from .browser_schemas import BrowserSessionCreate
from .browser_sources import BROWSER_SOURCE_MEDIA_TYPE, browser_source_identity

from .agent_planner import deterministic_plan, intelligent_tool_names, proposal_to_plan
from .agent_tools import tool
from .agent_planning_model import DeepSeekAgentPlanner, PlannerFailure
from .agent_schemas import AgentObservation
from .errors import CoworkerError
from .runner import DocumentRunner
from .tool_execution import execute_tool_contract, normalize_tool_error, validate_tool_result
from .schemas import ResearchOptions, TaskCreate
from .sandbox_schemas import SandboxExecutionCreate, SandboxSessionCreate


REPLAN_REASONS = {"capability_changed", "result_incomplete"}


class AgentRuntime:
    def __init__(self, container, runner: DocumentRunner, planner=None):
        self.container = container
        self.runner = runner
        self.repo = container.agent
        self.planner = planner or DeepSeekAgentPlanner(container.settings)

    def plan(self, run_id: str) -> int:
        run = self.repo.worker_run(run_id)
        if run["cancel_requested"] or run["state"] == "cancelled":
            raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
        current = self.repo.get(run["owner_id"], run_id)
        if current["tool_invocations"]:
            return len(current["tool_invocations"])
        steps = deterministic_plan(
            run["goal"], run["document_ids"], run["output_language"], self.container.settings, run["actions"],
            tool_allowlist=run.get("tool_allowlist"),
        )
        self.repo.set_planner_mode(run_id, "deterministic")
        saved = self.repo.save_plan(run["owner_id"], run_id, steps)
        return len(saved["tool_invocations"])

    def _planner_reservation(self) -> int:
        per_call = max(1, self.container.settings.agent_planner_token_budget // self.container.settings.max_agent_planner_calls)
        return min(per_call, self.container.settings.agent_planner_token_budget)

    async def plan_for_worker(self, run_id: str) -> int:
        if not self.container.settings.intelligent_planner_enabled:
            return self.plan(run_id)
        run = self.repo.worker_run(run_id)
        current = self.repo.get(run["owner_id"], run_id)
        if current["tool_invocations"]:
            return len(current["tool_invocations"])
        tools = intelligent_tool_names(
            self.container.settings, run["actions"], tool_allowlist=run.get("tool_allowlist"),
        )
        if not tools:
            return self.plan(run_id)
        reservation = self.repo.reserve_planner(run_id, self._planner_reservation())
        actual_tokens = None
        try:
            proposal, actual_tokens, _latency = await self.planner.propose(
                run["goal"],
                tools,
                reason="initial",
                allow_action_proposals=self.container.settings.agent_action_proposals_enabled,
                allow_linkedin_action_proposals=self.container.settings.agent_linkedin_proposals_enabled,
            )
            steps = proposal_to_plan(
                proposal, run["goal"], run["document_ids"], run["output_language"],
                self.container.settings, run["actions"],
                tool_allowlist=run.get("tool_allowlist"),
            )
            saved = self.repo.save_plan(
                run["owner_id"],
                run_id,
                steps,
                action_proposals=proposal.action_proposals,
            )
            if self.container.settings.agent_action_selection_enabled:
                self.repo.release_unselected_actions(run_id)
            self.repo.set_planner_mode(run_id, "intelligent")
            return len(saved["tool_invocations"])
        except PlannerFailure as error:
            actual_tokens = error.total_tokens
            self.repo.set_planner_mode(run_id, "fallback")
            steps = deterministic_plan(
                run["goal"], run["document_ids"], run["output_language"], self.container.settings, run["actions"],
                tool_allowlist=run.get("tool_allowlist"),
            )
            saved = self.repo.save_plan(run["owner_id"], run_id, steps)
            return len(saved["tool_invocations"])
        finally:
            self.repo.settle_planner_capacity(
                run_id, reservation["call"], actual_tokens,
            )

    async def replan(self, run_id: str, from_ordinal: int, reason: str = "capability_changed") -> int:
        if reason not in REPLAN_REASONS:
            raise CoworkerError("invalid_replan_reason", "The agent replan reason is not supported.", 422)
        if not self.container.settings.intelligent_planner_enabled:
            raise CoworkerError("replan_unavailable", "Intelligent replanning is not enabled.", 409)
        run = self.repo.worker_run(run_id)
        current = self.repo.get(run["owner_id"], run_id)
        if current["planner_calls"] >= self.container.settings.max_agent_planner_calls:
            raise CoworkerError("planner_call_limit", "This agent run reached its planner call limit.", 429)
        completed_actions = {
            receipt["resource_id"] for receipt in (
                item.get("receipt") for item in current["tool_invocations"] if item.get("receipt")
            ) if receipt and receipt.get("resource_type") == "action"
        }
        remaining_actions = [action for action in run["actions"] if action["id"] not in completed_actions]
        tools = intelligent_tool_names(
            self.container.settings, remaining_actions, tool_allowlist=run.get("tool_allowlist"),
        )
        if not tools:
            raise CoworkerError("no_agent_tool", "No suitable agent tool is currently enabled.", 409)
        reservation = self.repo.reserve_planner(run_id, self._planner_reservation())
        actual_tokens = None
        try:
            proposal, actual_tokens, _latency = await self.planner.propose(
                run["goal"],
                tools,
                reason=reason,
                allow_action_proposals=False,
                allow_linkedin_action_proposals=False,
            )
        except PlannerFailure as error:
            actual_tokens = error.total_tokens
            raise
        finally:
            self.repo.settle_planner_capacity(
                run_id, reservation["call"], actual_tokens,
            )
        steps = proposal_to_plan(
            proposal, run["goal"], run["document_ids"], run["output_language"],
            self.container.settings, remaining_actions,
            tool_allowlist=run.get("tool_allowlist"),
        )
        saved = self.repo.replace_remaining_plan(run["owner_id"], run_id, from_ordinal, steps)
        if self.container.settings.agent_action_selection_enabled:
            self.repo.release_unselected_actions(run_id)
        self.repo.set_planner_mode(run_id, "replanned")
        return len([step for step in saved["steps"] if step["ordinal"] >= from_ordinal])

    def _v3_planner_reservation(self) -> int:
        per_call = max(
            1,
            self.container.settings.agent_v3_planner_token_budget
            // self.container.settings.max_agent_v3_planner_calls,
        )
        return min(per_call, self.container.settings.agent_v3_planner_token_budget)

    async def decide_v3(self, run_id: str, *, activity_key: str | None = None) -> dict:
        run = self.repo.worker_run(run_id)
        if run["runtime_version"] != 3:
            raise CoworkerError("runtime_version", "This run is not assigned to Agent Runtime v3.", 409)
        if run["cancel_requested"] or run["state"] == "cancelled":
            raise CoworkerError("agent_cancelled", "This agent run was cancelled.", 409)
        self.repo.assert_v3_within_deadline(run_id)
        if activity_key:
            replay = self.repo.v3_activity_result(run_id, activity_key)
            if replay is not None:
                return replay

        current = self.repo.get(run["owner_id"], run_id)
        observations = [
            AgentObservation.model_validate(item).model_dump(mode="json")
            for item in self.repo.verified_observations(run["owner_id"], run_id)
        ]
        tools = intelligent_tool_names(
            self.container.settings,
            run["actions"],
            goal=run["goal"],
            runtime_version=run["runtime_version"],
            tool_allowlist=run.get("tool_allowlist") or [],
        )
        remaining = self.repo.v3_remaining_budget(run_id)
        context_payload, context_sources = self.container.context.planner_context(
            run["owner_id"], run_id
        )
        dependencies = {
            "steps": [{
                "ordinal": step["ordinal"],
                "state": step["state"],
                "depends_on": step["depends_on"],
            } for step in current["steps"] if step["ordinal"] > 0],
            "consequential_actions_require_explicit_approval": True,
            "context": context_payload,
        }
        if not tools and not self.repo.v3_can_complete(run_id):
            self.repo.v3_terminal(
                run_id,
                "blocked",
                "No registered tool is currently available for this bounded run.",
            )
            return {"decision": "blocked"}

        reservation = self.repo.reserve_planner(run_id, self._v3_planner_reservation())
        actual_tokens = None
        cost_microusd = None
        try:
            decision, actual_tokens, _latency, evidence = await self.planner.decide(
                run["goal"],
                tools,
                observations,
                remaining_budget=remaining,
                dependencies=dependencies,
            )
            if actual_tokens is not None and self.container.settings.agent_v3_planner_cost_microusd_per_1k_tokens > 0:
                cost_microusd = (
                    actual_tokens * self.container.settings.agent_v3_planner_cost_microusd_per_1k_tokens + 999
                ) // 1000
            return self.repo.commit_v3_decision(
                run_id, decision, activity_key=activity_key,
                planner_call=reservation["call"], model=evidence["model"],
                prompt_sha256=evidence["prompt_sha256"],
                tool_schema_sha256=evidence["tool_schema_sha256"],
                observation_count=len(observations), total_tokens=actual_tokens,
                cost_microusd=cost_microusd, memory_repository=self.container.memory,
                context_sources=context_sources,
            )
        except PlannerFailure as error:
            actual_tokens = error.total_tokens
            raise
        finally:
            self.repo.settle_planner_capacity(
                run_id,
                reservation["call"],
                actual_tokens,
                cost_microusd,
            )

    async def execute_step(self, run_id: str, ordinal: int) -> dict:
        self.repo.assert_within_deadline(run_id)
        run = self.repo.worker_run(run_id)
        invocation = self.repo.invocation_for_step(run_id, ordinal)
        if invocation["state"] == "completed":
            return {"status": "completed"}
        dependency = self.repo.dependency_state(run["owner_id"], run_id, ordinal)
        if not dependency["ready"]:
            raise CoworkerError("dependency_blocked", "This agent step is waiting for its required prior step.", 409)
        spec = tool(invocation["tool"])
        # Recheck the durable run grant before touching task state or providers.
        # This also rejects stale/forged persisted steps after planner admission.
        if run.get("tool_allowlist") and spec.kind != "approved_action" and spec.name not in run["tool_allowlist"]:
            raise CoworkerError(
                "agent_tool_scope",
                "This tool is outside the recorded run scope.",
                409,
            )
        if not spec.enabled(self.container.settings) and spec.kind == "task":
            if self.container.settings.intelligent_planner_enabled and invocation["state"] == "prepared":
                return {"status": "replan_required"}
            raise CoworkerError("tool_not_supported", "A required Agent tool is not enabled in this runtime.", 409)
        args = spec.validate(invocation["arguments"])
        if spec.kind == "approved_action":
            action = self.container.actions.repo.get(run["owner_id"], str(args.action_id))
            state = action["state"]
            if state == "succeeded":
                summary = {"action_state": state, "provider_confirmed": True}
                self.repo.finish_invocation(run_id, ordinal, "action", action["id"], summary)
                validate_tool_result(spec, {
                    "status": "completed",
                    "resource_type": "action",
                    "resource_id": action["id"],
                    "summary": summary,
                })
                return {"status": "completed"}
            if state == "outcome_unknown":
                raise CoworkerError("outcome_unknown", "The provider result is uncertain. Reconcile the connected service before continuing.", 409)
            if state == "failed":
                error_code = str(action.get("error_code") or "provider_unavailable")
                status_code = (
                    429 if error_code == "provider_rate_limited"
                    else 403 if "scope" in error_code or "permission" in error_code
                    else 503
                )
                raise normalize_tool_error(
                    CoworkerError(
                        error_code,
                        "The approved tool did not complete successfully.",
                        status_code,
                    ),
                    consequential=True,
                )
            if state == "cancelled":
                raise CoworkerError("agent_cancelled", "The approved tool was cancelled.", 409)
            if state == "expired":
                raise CoworkerError("approval_required", "The approved action expired and must be reviewed again.", 409)
            if state not in {"awaiting_approval", "queued", "executing"}:
                raise CoworkerError("action_state", "The attached action is not in a resumable state.", 409)
            self.repo.action_waiting(run_id, ordinal, action["id"], state)
            status = "awaiting_approval" if state == "awaiting_approval" else "executing"
            validate_tool_result(spec, {
                "status": status,
                "resource_type": "action",
                "resource_id": action["id"],
                "summary": {"action_state": state, "provider_confirmed": False},
            })
            return {"status": status}
        if spec.consequential or spec.approval_required:
            raise CoworkerError("approval_required", "This consequential tool must use the approved-action path.", 409)

        if spec.kind == "browser_read":
            if (
                run["runtime_version"] != 3
                or not self.container.settings.agent_browser_read_enabled
                or not spec.enabled(self.container.settings)
            ):
                raise CoworkerError("tool_not_supported", "Agent browser reading is not enabled.", 409)
            if args.purpose != "research":
                raise CoworkerError("browser_agent_scope", "Only read-only research is permitted.", 409)
            target_url, _origin = normalize_browser_target(args.url)
            self.repo.begin_invocation(run_id, ordinal)
            resource = self.repo.step_resource(run_id, ordinal)
            if resource is None:
                session, _created = self.container.browser.create(
                    run["owner_id"],
                    BrowserSessionCreate(purpose="research", start_url=target_url),
                    f"agent:{run_id}:{ordinal}",
                    agent_origin=True,
                )
                try:
                    self.repo.link_invocation_resource(
                        run_id, ordinal, "browser_session", session["id"],
                    )
                except Exception:
                    # Cancellation can win between broker create and Agent link.
                    # Clear its orphaned slot; the Agent ledger remains terminal.
                    self.container.browser.cancel(run["owner_id"], session["id"])
                    raise
                resource = {"resource_type": "browser_session", "resource_id": session["id"]}
            if resource.get("resource_type") != "browser_session":
                raise CoworkerError(
                    "browser_agent_scope", "The run is not bound to a browser session.", 409,
                )
            session_id = str(resource["resource_id"])
            session = self.container.browser.get(run["owner_id"], session_id)
            if (
                session["purpose"] != "research"
                or session["start_url"] != target_url
                or session["cancel_requested"]
                or session["takeover_required"]
                or session["state"] in {"takeover", "cancelled", "expired", "failed", "completed"}
            ):
                raise CoworkerError(
                    "browser_agent_scope", "The supervised browser session is unavailable for this run.", 409,
                )
            command = self.container.browser.prepare_agent_read(
                run["owner_id"], session_id, target_url,
            )
            if command["state"] in {"prepared", "running"}:
                validate_tool_result(spec, {
                    "status": "executing",
                    "resource_type": "browser_command",
                    "resource_id": command["id"],
                    "summary": {"browser_state": command["state"], "observation_scope": "metadata_only"},
                })
                return {"status": "executing"}
            if command["state"] != "succeeded":
                raise CoworkerError(
                    command.get("error_code") or "browser_observation_unavailable",
                    "The supervised read-only browser command did not succeed.", 409,
                )
            result = command.get("result") or {}
            final_url, _final_origin = normalize_browser_target(result.get("final_url", ""))
            title = result.get("title")
            if (
                not isinstance(title, str) or len(title) > 300
                or result.get("submission_performed") is not False
                or bool(result.get("interaction_performed"))
                or bool(result.get("prepared_fields"))
                or result.get("takeover_frame_version") is not None
            ):
                raise CoworkerError(
                    "browser_observation_invalid", "The broker did not verify read-only page metadata.", 409,
                )
            # The broker validates DNS/IP, redirects, origin and no submission
            # before marking the command succeeded. This is a hash of exactly
            # the released *metadata*, not a claim to have captured page HTML.
            metadata_bytes = json.dumps(
                {"url": final_url, "title": title},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            summary = {
                "browser_state": "succeeded",
                "observation_scope": "metadata_only",
                "observation_trust": "untrusted",
                "source_url": final_url,
                "capture_time": command["finished_at"],
                "source_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
                "untrusted_page_title": title,
                "submission_performed": False,
            }
            captured = self.container.browser.read_agent_capture(
                run["owner_id"], session_id, command["id"],
            )
            browser_source_bytes = None
            if captured is not None and captured["text"].strip():
                # Blank/whitespace-only pages must not be reported as read content.
                # Release only a short, untrusted excerpt to the bounded planner.
                # The checksum is of exact captured UTF-8 bytes, NOT the URL/title.
                excerpt = captured["text"].encode("utf-8")[:1200].decode("utf-8", "ignore")
                # The retained source is the EXACT bounded worker capture,
                # not upstream HTML. Persist outside the database under a
                # deterministic owner/command key, never a model-chosen path.
                browser_source_bytes = captured["text"].encode("utf-8")
                artifact_id, object_key, _filename = browser_source_identity(
                    run["owner_id"], command["id"],
                )
                try:
                    self.container.storage.put(
                        object_key, browser_source_bytes, BROWSER_SOURCE_MEDIA_TYPE,
                    )
                    stored = self.container.storage.get(object_key, len(browser_source_bytes))
                except Exception as exc:
                    raise CoworkerError(
                        "browser_source_storage_unavailable",
                        "The private source capture could not be stored or verified.", 503,
                    ) from exc
                if stored != browser_source_bytes:
                    raise CoworkerError(
                        "browser_source_storage_invalid",
                        "The private source capture did not verify.", 503,
                    )
                summary.update({
                    "observation_scope": "captured_text_excerpt",
                    "source_sha256": captured["sha256"],
                    "source_byte_size": captured["byte_size"],
                    "source_truncated": captured["truncated"],
                    "untrusted_page_text_excerpt": excerpt,
                    "artifact_id": artifact_id,
                    "artifact_sha256": captured["sha256"],
                })
            self.repo.finish_invocation(
                run_id, ordinal, "browser_command", command["id"], summary,
                browser_source_bytes=browser_source_bytes,
            )
            validate_tool_result(spec, {
                "status": "completed",
                "resource_type": "browser_command",
                "resource_id": command["id"],
                "summary": summary,
            })
            return {"status": "completed"}

        if spec.kind == "sandbox":
            if run["runtime_version"] != 3 or not self.container.settings.agent_sandbox_tool_enabled:
                raise CoworkerError("tool_not_supported", "Planner sandbox execution is not enabled for this run.", 409)
            self.repo.begin_invocation(run_id, ordinal)
            resource = self.repo.step_resource(run_id, ordinal)
            if resource is None:
                session, _created = self.container.sandbox.create(
                    run["owner_id"],
                    SandboxSessionCreate(purpose="code_task", runtime="python311"),
                    f"agent:{run_id}:{ordinal}",
                )
                self.repo.link_invocation_resource(
                    run_id, ordinal, "sandbox_session", session["id"]
                )
                resource = {"resource_type": "sandbox_session", "resource_id": session["id"]}
            if resource.get("resource_type") != "sandbox_session":
                raise CoworkerError(
                    "sandbox_agent_resource",
                    "This agent step is not bound to the expected sandbox session.",
                    409,
                )
            session_id = str(resource["resource_id"])
            executions = self.container.sandbox.list_executions(run["owner_id"], session_id)
            if not executions:
                prepared = self.container.sandbox.prepare_execution(
                    run["owner_id"],
                    session_id,
                    SandboxExecutionCreate(source=args.source),
                )
                validate_tool_result(spec, {
                    "status": "executing",
                    "resource_type": "sandbox_execution",
                    "resource_id": prepared["id"],
                    "summary": {"sandbox_state": "prepared"},
                })
                return {"status": "executing"}
            execution = executions[0]
            # A resume must never claim an earlier sandbox execution or
            # consume its results for a *different* Agent invocation source.
            # A durable session id is not itself authorization to substitute
            # code. Check exact UTF-8 bytes/digest before both execution
            # polling and verified ToolReceipt settlement.
            requested_source = args.source.encode("utf-8")
            if (
                len(executions) != 1
                or execution.get("source_bytes") != len(requested_source)
                or execution.get("source_sha256") != hashlib.sha256(requested_source).hexdigest()
            ):
                raise CoworkerError(
                    "sandbox_source_binding_mismatch",
                    "The existing sandbox execution does not match the exact code for this Agent step.",
                    409,
                )
            if execution["state"] in {"prepared", "running"}:
                validate_tool_result(spec, {
                    "status": "executing",
                    "resource_type": "sandbox_execution",
                    "resource_id": execution["id"],
                    "summary": {"sandbox_state": execution["state"]},
                })
                return {"status": "executing"}
            if execution["state"] != "succeeded":
                raise CoworkerError(
                    execution.get("error_code") or "sandbox_execution_failed",
                    "The isolated sandbox execution did not complete successfully.",
                    409,
                )
            result = execution.get("result") if isinstance(execution.get("result"), dict) else {}
            artifact = result.get("artifact") if isinstance(result.get("artifact"), dict) else {}
            summary = {
                "sandbox_state": "succeeded",
                "exit_code": result.get("exit_code"),
                "stdout_excerpt": str(result.get("stdout") or "")[:1800],
                "stderr_excerpt": str(result.get("stderr") or "")[:800],
                "stdout_sha256": result.get("stdout_sha256"),
                "stderr_sha256": result.get("stderr_sha256"),
                "sandbox_destroyed": result.get("sandbox_destroyed") is True,
                "output_trust": "untrusted",
                "artifact_id": artifact.get("id"),
                "artifact_sha256": artifact.get("sha256"),
            }
            self.repo.finish_invocation(
                run_id,
                ordinal,
                "sandbox_execution",
                execution["id"],
                summary,
            )
            validate_tool_result(spec, {
                "status": "completed",
                "resource_type": "sandbox_execution",
                "resource_id": execution["id"],
                "summary": summary,
            })
            return {"status": "completed"}

        if spec.kind != "task" or not spec.skill_id:
            raise CoworkerError("tool_not_supported", "This Agent tool is not executable in this runtime.", 409)

        self.repo.begin_invocation(run_id, ordinal)

        def cancelled() -> bool:
            snapshot = self.repo.worker_run(run_id)
            return bool(snapshot["cancel_requested"] or snapshot["state"] == "cancelled")

        async def execute_task_tool() -> dict:
            research = None
            if spec.skill_id == "research":
                research = ResearchOptions(query=args.query, time_range=args.time_range)
            request = TaskCreate(
                skill_id=spec.skill_id,
                instruction=args.instruction,
                notes=args.notes,
                document_ids=args.document_ids,
                output_language=args.output_language,
                research=research,
            )
            task, _ = self.container.repository.create_task(
                run["owner_id"], request, f"agent:{run_id}:{ordinal}", enqueue=False,
                agent_run_id=run_id, agent_step_id=invocation["step_id"]
            )
            self.repo.link_invocation_resource(run_id, ordinal, "task", task["id"])
            worker_task = self.container.repository.worker_task(task["id"], False)
            phases = ["extract"] + (["research"] if worker_task["skill_id"] == "research" else []) + ["draft", "export", "complete"]
            for phase in phases:
                if cancelled():
                    raise CoworkerError("agent_cancelled", "This Agent run was cancelled.", 409)
                await self.runner.phase(task["id"], phase)
            result = self.container.repository.get_task(run["owner_id"], task["id"])
            if result["state"] not in {"completed", "needs_input"}:
                raise CoworkerError("provider_unavailable", "The Agent tool did not produce a valid terminal result.", 503)
            draft_step = self.container.repository.step(task["id"], "draft") or {}
            summary = {
                "task_state": result["state"],
                "artifact_count": len(result["artifacts"]),
                "has_missing_information": result["state"] == "needs_input",
                "memory": draft_step.get("memory_provenance", []),
                "handoff": draft_step.get("handoff_provenance", []),
            }
            return {
                "status": "needs_input" if result["state"] == "needs_input" else "completed",
                "resource_type": "task",
                "resource_id": task["id"],
                "summary": summary,
            }

        async def observe_retry(next_attempt: int, error_code: str) -> None:
            await asyncio.to_thread(
                self.repo.record_tool_retry,
                run_id,
                ordinal,
                next_attempt,
                error_code,
            )

        observed = await execute_tool_contract(
            spec,
            execute_task_tool,
            cancellation_check=cancelled,
            retry_observer=observe_retry,
        )
        task_id = str(observed["resource_id"])
        summary = dict(observed["summary"])
        self.repo.finish_invocation(run_id, ordinal, "task", task_id, summary)
        if (observed["status"] == "needs_input"
                and self.container.settings.agent_outcome_replan_enabled
                and self.container.settings.intelligent_planner_enabled):
            current = self.repo.get(run["owner_id"], run_id)
            if current["planner_mode"] in {"intelligent", "replanned"}:
                return {"status": "outcome_replan_required"}
        return {"status": "completed"}

    def complete(self, run_id: str):
        self.repo.complete_run(run_id)
        if self.container.automations is not None:
            self.container.automations.notify_run_completed(run_id)

    def fail(self, run_id: str, code: str, message: str):
        run = self.repo.worker_run(run_id)
        for ordinal in range(1, 9):
            try:
                invocation = self.repo.invocation_for_step(run_id, ordinal)
            except CoworkerError:
                break
            step = self.repo.step_resource(run_id, ordinal)
            if step and step.get("resource_type") == "task":
                self.container.repository.fail(step["resource_id"], code, message)
            if step and step.get("resource_type") == "sandbox_session":
                try:
                    self.container.sandbox.cancel_for_cleanup(run["owner_id"], step["resource_id"])
                except CoworkerError:
                    pass
        self.repo.fail_run(run_id, code, message)
