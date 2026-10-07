from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select

from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.models import (
    AgentCheckpoint,
    AgentDecision,
    AgentOutbox,
    AgentRun,
    AgentStep,
    ExternalAction,
    ModelAttempt,
    Task,
    ToolInvocation,
    Transaction,
    utcnow,
)

ACTIVE_RUN_STATES = {"queued", "planning", "running", "awaiting_approval"}
MEASURED_TERMINAL_STATES = {"completed", "failed", "needs_input", "blocked"}
MODEL_FAILURE_STATES = {"failed", "unknown"}
PROVIDER_STEP_ERRORS = {
    "provider_unavailable",
    "provider_rate_limited",
    "tool_timeout",
    "outcome_unknown",
    "planner_timeout",
    "planner_connection",
    "planner_unavailable",
}
TRANSACTION_TERMINAL_STATES = {
    "confirmed", "cancelled", "expired", "failed", "outcome_unknown"
}


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def duration_ms(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int((aware(end) - aware(start)).total_seconds() * 1000))


def percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def estimated_cost_microusd(tokens: int, settings: Settings) -> int:
    rate = max(0, int(settings.agent_v3_planner_cost_microusd_per_1k_tokens))
    return (max(0, int(tokens)) * rate + 999) // 1000 if rate else 0


def _run_record(db, run: AgentRun, settings: Settings, now: datetime) -> dict:
    decisions = list(db.scalars(select(AgentDecision).where(
        AgentDecision.run_id == run.id,
    ).order_by(AgentDecision.sequence)).all())
    invocations = list(db.scalars(select(ToolInvocation).where(
        ToolInvocation.run_id == run.id,
    ).order_by(ToolInvocation.created_at, ToolInvocation.id)).all())
    steps = list(db.scalars(select(AgentStep).where(
        AgentStep.run_id == run.id,
    )).all())
    child_tasks = list(db.scalars(select(Task).where(
        Task.agent_run_id == run.id,
    )).all())
    child_ids = [item.id for item in child_tasks]
    model_attempts = list(db.scalars(select(ModelAttempt).where(
        ModelAttempt.task_id.in_(child_ids)
    )).all()) if child_ids else []
    actions = list(db.scalars(select(ExternalAction).where(
        ExternalAction.agent_run_id == run.id,
    )).all())
    checkpoints = list(db.scalars(select(AgentCheckpoint).where(
        AgentCheckpoint.run_id == run.id,
        AgentCheckpoint.kind == "wait_for_approval",
    ).order_by(AgentCheckpoint.created_at)).all())
    tool_retries = list(db.scalars(select(AgentCheckpoint).where(
        AgentCheckpoint.run_id == run.id,
        AgentCheckpoint.kind == "tool_retry",
    )).all())
    outbox = db.get(AgentOutbox, run.id)

    planner_failures = max(0, int(run.planner_calls or 0) - len(decisions))
    child_model_failures = sum(item.state in MODEL_FAILURE_STATES for item in model_attempts)
    provider_step_failures = sum(
        item.state == "failed" and item.error_code in PROVIDER_STEP_ERRORS
        for item in steps
    )
    action_failures = sum(item.state in {"failed", "outcome_unknown"} for item in actions)
    provider_failures = (
        planner_failures
        + child_model_failures
        + provider_step_failures
        + action_failures
        + len(tool_retries)
    )

    charged_child_tokens = sum(max(0, int(item.charged_tokens or 0)) for item in model_attempts)
    planner_tokens = max(int(run.planner_tokens or 0), int(run.planner_actual_tokens or 0))
    accounted_tokens = planner_tokens + charged_child_tokens
    planner_cost = max(
        int(run.planner_cost_microusd or 0),
        estimated_cost_microusd(planner_tokens, settings),
    )
    cost_microusd = planner_cost + estimated_cost_microusd(charged_child_tokens, settings)

    tool_latencies = [
        value for value in (
            duration_ms(item.started_at, item.finished_at or (now if item.state == "running" else None))
            for item in invocations
        ) if value is not None
    ]
    signatures: set[str] = set()
    duplicate_attempts = 0
    for item in invocations:
        signature = item.tool_name + ":" + json.dumps(
            item.arguments or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if signature in signatures:
            duplicate_attempts += 1
        signatures.add(signature)

    attempts_by_task: dict[str, int] = {}
    for item in model_attempts:
        attempts_by_task[item.task_id] = attempts_by_task.get(item.task_id, 0) + 1
    model_retries = sum(max(0, count - 1) for count in attempts_by_task.values())
    dispatch_retries = max(0, int(outbox.attempts or 0) - 1) if outbox is not None else 0
    retries = planner_failures + model_retries + dispatch_retries + len(tool_retries)

    action_by_id = {item.id: item for item in actions}
    approval_wait_ms = 0
    for checkpoint in checkpoints:
        action = action_by_id.get(checkpoint.resource_id or "")
        wait_end = action.approved_at if action is not None and action.approved_at else now
        approval_wait_ms += duration_ms(checkpoint.created_at, wait_end) or 0

    models = sorted({
        *(item.model for item in decisions if item.model),
        *(item.model for item in model_attempts if item.model),
    })
    terminal = run.state not in ACTIVE_RUN_STATES
    latency_end = run.updated_at if terminal else now
    abandoned = (
        run.error_code == "agent_deadline"
        or (run.state in ACTIVE_RUN_STATES and aware(run.deadline_at) <= now)
    )
    return {
        "run_id": run.id,
        "model": models[0] if len(models) == 1 else ("multiple" if models else None),
        "models": models,
        "tokens": accounted_tokens,
        "latency_ms": duration_ms(run.created_at, latency_end) or 0,
        "tool_calls": len(invocations),
        "tool_latency_ms_total": sum(tool_latencies),
        "tool_latency_ms_p95": percentile(tool_latencies, 0.95),
        "retries": retries,
        "routing_decision": "agent_run",
        "routing_mode": run.planner_mode,
        "approval_waits": len(checkpoints),
        "approval_wait_ms": approval_wait_ms,
        "provider_failures": provider_failures,
        "cost_microusd": cost_microusd,
        "completion_state": run.state,
        "duplicate_attempts": duplicate_attempts,
        "outcome_unknown": sum(item.state == "outcome_unknown" for item in actions),
        "abandoned": abandoned,
        "model_calls": int(run.planner_calls or 0) + len(model_attempts),
        "model_failures": planner_failures + child_model_failures,
        "tool_failures": sum(item.state == "failed" for item in invocations),
        "planner_calls": int(run.planner_calls or 0),
        "planner_decisions": len(decisions),
    }


def aggregate(records: list[dict], transactions: list[Transaction], settings: Settings) -> dict:
    measured = [item for item in records if item["completion_state"] in MEASURED_TERMINAL_STATES]
    completed = sum(item["completion_state"] == "completed" for item in measured)
    tool_calls = sum(item["tool_calls"] for item in records)
    tool_failures = sum(item["tool_failures"] for item in records)
    model_calls = sum(item["model_calls"] for item in records)
    model_failures = sum(item["model_failures"] for item in records)
    latencies = [item["latency_ms"] for item in measured]
    tx_terminal = [item for item in transactions if item.state in TRANSACTION_TERMINAL_STATES]
    tx_unknown = sum(item.state == "outcome_unknown" for item in tx_terminal)
    return {
        "runs": {
            "samples": len(records),
            "measured_terminal": len(measured),
            "completed": completed,
            "success_rate": ratio(completed, len(measured)),
            "p50_latency_ms": percentile(latencies, 0.50),
            "p95_latency_ms": percentile(latencies, 0.95),
            "p99_latency_ms": percentile(latencies, 0.99),
            "average_steps": round(tool_calls / len(records), 4) if records else None,
            "token_consumption": sum(item["tokens"] for item in records),
            "average_cost_microusd": (
                round(sum(item["cost_microusd"] for item in records) / len(records), 2)
                if records else None
            ),
            "duplicate_attempts": sum(item["duplicate_attempts"] for item in records),
            "outcome_unknown": sum(item["outcome_unknown"] for item in records),
            "abandoned": sum(bool(item["abandoned"]) for item in records),
            "provider_failures": sum(item["provider_failures"] for item in records),
        },
        "tools": {
            "calls": tool_calls,
            "failures": tool_failures,
            "failure_rate": ratio(tool_failures, tool_calls),
        },
        "models": {
            "calls": model_calls,
            "failures": model_failures,
            "failure_rate": ratio(model_failures, model_calls),
        },
        "transactions": {
            "samples": len(tx_terminal),
            "confirmed": sum(item.state == "confirmed" for item in tx_terminal),
            "failed": sum(item.state == "failed" for item in tx_terminal),
            "outcome_unknown": tx_unknown,
            "outcome_unknown_rate": ratio(tx_unknown, len(tx_terminal)),
        },
        "budgets": {
            "max_model_calls_per_run": settings.max_agent_model_calls_per_run,
            "max_tokens_per_run": settings.max_agent_tokens_per_run,
            "max_tool_calls_per_run": settings.max_agent_tool_calls_per_run,
            "max_runtime_seconds": settings.agent_run_timeout_seconds,
            "max_cost_microusd_per_run": settings.max_agent_cost_microusd_per_run,
        },
    }


def collect_snapshot(settings: Settings, *, window_minutes: int = 60, now: datetime | None = None) -> dict:
    if window_minutes < 1:
        raise ValueError("window_minutes must be positive")
    now = aware(now or utcnow())
    cutoff = now - timedelta(minutes=window_minutes)
    sessions = session_factory(settings.database_url)
    engine = sessions.kw["bind"]
    try:
        with sessions() as db:
            runs = list(db.scalars(select(AgentRun).where(or_(
                AgentRun.updated_at >= cutoff,
                AgentRun.state.in_(ACTIVE_RUN_STATES),
            )).order_by(AgentRun.created_at)).all())
            records = [_run_record(db, run, settings, now) for run in runs]
            transactions = list(db.scalars(select(Transaction).where(
                Transaction.updated_at >= cutoff,
            )).all())
            dashboard = aggregate(records, transactions, settings)
        return {
            "schema_version": 1,
            "generated_at": now.isoformat(),
            "window_minutes": window_minutes,
            "records": records,
            "dashboard": dashboard,
        }
    finally:
        engine.dispose()


def metric_value(value) -> str:
    if value is None:
        return "NaN"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return format(value, ".12g")
    raise TypeError(type(value).__name__)


def render_openmetrics(snapshot: dict) -> str:
    d = snapshot["dashboard"]
    metrics = {
        "shuddho_core_agent_run_success_ratio": d["runs"]["success_rate"],
        "shuddho_core_agent_tool_failure_ratio": d["tools"]["failure_rate"],
        "shuddho_core_agent_model_failure_ratio": d["models"]["failure_rate"],
        "shuddho_core_agent_run_latency_p50_ms": d["runs"]["p50_latency_ms"],
        "shuddho_core_agent_run_latency_p95_ms": d["runs"]["p95_latency_ms"],
        "shuddho_core_agent_run_latency_p99_ms": d["runs"]["p99_latency_ms"],
        "shuddho_core_agent_average_steps": d["runs"]["average_steps"],
        "shuddho_core_agent_token_consumption": d["runs"]["token_consumption"],
        "shuddho_core_agent_average_cost_microusd": d["runs"]["average_cost_microusd"],
        "shuddho_core_agent_duplicate_attempts": d["runs"]["duplicate_attempts"],
        "shuddho_core_agent_outcome_unknown": d["runs"]["outcome_unknown"],
        "shuddho_core_agent_abandoned_runs": d["runs"]["abandoned"],
        "shuddho_core_agent_provider_failures": d["runs"]["provider_failures"],
        "shuddho_transactions_outcome_unknown": d["transactions"]["outcome_unknown"],
        "shuddho_transactions_outcome_unknown_ratio": d["transactions"]["outcome_unknown_rate"],
    }
    lines: list[str] = []
    for name, value in metrics.items():
        lines.extend([
            f"# HELP {name} Phase 10 Core Agent production observability metric.",
            f"# TYPE {name} gauge",
            f"{name} {metric_value(value)}",
        ])
    lines.append("# EOF")
    return "\n".join(lines) + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Phase 10 Core Agent observability and economics.")
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--prom-output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings.from_env()
    snapshot = collect_snapshot(settings, window_minutes=args.window_minutes)
    atomic_write(args.json_output, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    atomic_write(args.prom_output, render_openmetrics(snapshot))
    print(json.dumps({
        "runs": snapshot["dashboard"]["runs"]["samples"],
        "transactions": snapshot["dashboard"]["transactions"]["samples"],
        "json_output": str(args.json_output),
        "prom_output": str(args.prom_output),
    }, indent=2))


if __name__ == "__main__":
    main()
