from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
from temporalio.client import Client

from scripts.staging_api_exercise import env_secret, require_https_base
from services.coworker.agent_schemas import AgentPlanStep, AgentRunCreate
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.worker import Dispatcher


class RollbackFailure(RuntimeError):
    pass


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def require_guard() -> None:
    if os.environ.get("SHUDDHO_STAGING_ALLOW_ROLLBACK_EXERCISE", "").lower() != "true":
        raise RollbackFailure(
            "Set SHUDDHO_STAGING_ALLOW_ROLLBACK_EXERCISE=true only in controlled staging."
        )


def resolve_owner() -> str:
    base_url = require_https_base(env_secret("SHUDDHO_STAGING_API_BASE_URL"))
    token = env_secret("SHUDDHO_STAGING_TOKEN_A")
    try:
        response = httpx.get(
            base_url + "/api/v1/me",
            headers={"Authorization": "Bearer " + token},
            timeout=20,
            follow_redirects=False,
        )
    except httpx.HTTPError as error:
        raise RollbackFailure(f"Staging /me request failed: {type(error).__name__}") from None
    if response.status_code != 200:
        raise RollbackFailure(f"Staging /me returned HTTP {response.status_code}.")
    try:
        value = response.json()
    except ValueError:
        raise RollbackFailure("Staging /me did not return JSON.") from None
    owner = value.get("account_id") if isinstance(value, dict) else None
    if not isinstance(owner, str) or not owner:
        raise RollbackFailure("Staging /me did not return an account id.")
    return owner


async def temporal_client(settings: Settings) -> Client:
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        api_key=settings.temporal_api_key or None,
        tls=settings.temporal_tls,
    )


async def workflow_type(client: Client, workflow_id: str) -> str:
    query = f'WorkflowId = "{workflow_id}"'
    async for item in client.list_workflows(query):
        value = getattr(item, "workflow_type", None)
        if isinstance(value, str) and value:
            return value
        name = getattr(value, "name", None)
        if isinstance(name, str) and name:
            return name
        break
    raise RollbackFailure(f"Temporal visibility did not return a workflow type for {workflow_id}.")


def simple_plan() -> list[AgentPlanStep]:
    return [
        AgentPlanStep(tool="document.create", arguments={
            "instruction": "Create a short synthetic rollback validation document.",
            "notes": "Synthetic staging probe only. No customer data.",
            "document_ids": [],
            "output_language": "en",
        })
    ]


def require_prepare_flags(settings: Settings) -> None:
    if not settings.agent_runtime_enabled:
        raise RollbackFailure("SHUDDHO_AGENT_RUNTIME_ENABLED must be true.")
    if not settings.agent_dependency_graph_enabled or not settings.agent_parallel_execution_enabled:
        raise RollbackFailure(
            "Prepare requires both dependency graph and parallel execution enabled so the dispatcher selects v2."
        )
    if not settings.work_services_enabled:
        raise RollbackFailure("SHUDDHO_WORK_SERVICES_ENABLED must be true for the synthetic document task.")


def require_verify_flags(settings: Settings) -> None:
    if not settings.agent_runtime_enabled:
        raise RollbackFailure("SHUDDHO_AGENT_RUNTIME_ENABLED must remain true during rollback verification.")
    if settings.agent_parallel_execution_enabled:
        raise RollbackFailure(
            "Verify requires SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED=false after the rollback deployment."
        )
    if not settings.work_services_enabled:
        raise RollbackFailure("SHUDDHO_WORK_SERVICES_ENABLED must remain true for the synthetic document task.")


async def create_and_dispatch(container: Container, client: Client, owner: str, key_prefix: str) -> dict:
    run, _created = container.agent.create(
        owner,
        AgentRunCreate(
            goal="Create a synthetic rollback validation document.",
            output_language="en",
        ),
        key_prefix + "-" + uuid.uuid4().hex,
    )
    container.agent.save_plan(owner, run["id"], simple_plan())
    await Dispatcher(container, client).dispatch_agent_run(run["id"])
    workflow_id = "shuddho-agent-" + run["id"]
    return {"run_id": run["id"], "workflow_id": workflow_id}


async def wait_for_completion(client: Client, workflow_id: str) -> None:
    try:
        await asyncio.wait_for(client.get_workflow_handle(workflow_id).result(), timeout=180)
    except TimeoutError:
        raise RollbackFailure(f"Workflow {workflow_id} did not complete within the staging timeout.") from None


async def prepare(settings: Settings, state_path: Path) -> dict:
    require_guard()
    require_prepare_flags(settings)
    owner = resolve_owner()
    container = Container.create(settings)
    client = await temporal_client(settings)
    try:
        value = await create_and_dispatch(container, client, owner, "staging-v2-before-rollback")
        observed = await workflow_type(client, value["workflow_id"])
        if observed != "shuddho_agent_run_v2":
            raise RollbackFailure(f"Expected pre-rollback v2 workflow; Temporal recorded {observed!r}.")
        await wait_for_completion(client, value["workflow_id"])
        saved = container.agent.get(owner, value["run_id"])
        if saved["state"] != "completed":
            raise RollbackFailure(f"Pre-rollback v2 Agent run ended in state {saved['state']!r}.")
        state = {
            "owner_id": owner,
            "v2_run_id": value["run_id"],
            "v2_workflow_id": value["workflow_id"],
            "v2_workflow_type": observed,
        }
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return {
            "workflow_id": value["workflow_id"],
            "workflow_type": observed,
            "next": "Disable only SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED, redeploy API/workers with both workflow classes still registered, then run verify.",
        }
    finally:
        container.repository.sessions.kw["bind"].dispose()


async def verify(
    settings: Settings,
    state_path: Path,
    rollout_reference: str,
    evidence_path: Path,
    base_evidence: Path | None,
) -> dict:
    require_guard()
    require_verify_flags(settings)
    if not rollout_reference.strip():
        raise RollbackFailure("A non-empty rollback deployment reference is required.")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise RollbackFailure("Rollback state file must be a JSON object.")
    required = {"owner_id", "v2_run_id", "v2_workflow_id", "v2_workflow_type"}
    if not required.issubset(state):
        raise RollbackFailure("Rollback state file is incomplete.")

    owner = resolve_owner()
    if owner != state["owner_id"]:
        raise RollbackFailure("Rollback verification must use the same disposable staging account.")

    container = Container.create(settings)
    client = await temporal_client(settings)
    try:
        old_type = await workflow_type(client, str(state["v2_workflow_id"]))
        if old_type != "shuddho_agent_run_v2":
            raise RollbackFailure(f"Existing workflow type changed unexpectedly: {old_type!r}.")
        old_run = container.agent.get(owner, str(state["v2_run_id"]))
        if old_run["state"] != "completed":
            raise RollbackFailure(f"Existing v2 run is no longer completed: {old_run['state']!r}.")

        new_value = await create_and_dispatch(container, client, owner, "staging-v1-after-rollback")
        new_type = await workflow_type(client, new_value["workflow_id"])
        if new_type != "shuddho_agent_run_v1":
            raise RollbackFailure(f"Expected post-rollback v1 workflow; Temporal recorded {new_type!r}.")
        await wait_for_completion(client, new_value["workflow_id"])
        new_run = container.agent.get(owner, new_value["run_id"])
        if new_run["state"] != "completed":
            raise RollbackFailure(f"Post-rollback v1 Agent run ended in state {new_run['state']!r}.")

        base = {}
        if base_evidence:
            value = json.loads(base_evidence.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise RollbackFailure("Base staging evidence must be a JSON object.")
            base.update(value)
        ref = rollout_reference.strip()[:240]
        base["flag_rollback"] = passed(
            f"existing v2 workflow remained valid and a newly dispatched Agent run used shuddho_agent_run_v1 after parallel flag disable; rollout_ref={ref}"
        )
        evidence_path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        return {
            "checks": {"flag_rollback": "passed"},
            "pre_rollback_workflow": str(state["v2_workflow_id"]),
            "post_rollback_workflow": new_value["workflow_id"],
        }
    finally:
        container.repository.sessions.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate controlled AgentWorkflow v2-to-v1 feature-flag rollback."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--state", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--state", type=Path, required=True)
    verify_parser.add_argument("--rollout-reference", required=True)
    verify_parser.add_argument("--base-evidence", type=Path)
    verify_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "prepare":
            result = asyncio.run(prepare(settings, args.state))
            print(json.dumps({"status": "prepared", **result}, indent=2))
        else:
            result = asyncio.run(verify(
                settings,
                args.state,
                args.rollout_reference,
                args.output,
                args.base_evidence,
            ))
            print(json.dumps({"written": str(args.output), **result}, indent=2))
    except (RollbackFailure, httpx.HTTPError, OSError, ValueError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
