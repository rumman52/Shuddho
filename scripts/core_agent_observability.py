from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from fractions import Fraction
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


def estimated_cost_microusd(tokens: int, settings: Settings) -> int | None:
    accounted_tokens = max(0, int(tokens))
    rate = max(0, int(settings.agent_v3_planner_cost_microusd_per_1k_tokens))
    if accounted_tokens == 0:
        return 0
    if rate <= 0:
        return None
    return (accounted_tokens * rate + 999) // 1000


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
    planner_settlements = list(db.scalars(select(AgentCheckpoint).where(
        AgentCheckpoint.run_id == run.id,
        AgentCheckpoint.kind == "planner_capacity_settled",
    )).all())

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
    planner_estimate = estimated_cost_microusd(planner_tokens, settings)
    persisted_planner_cost = max(0, int(run.planner_cost_microusd or 0))
    planner_cost = (
        max(persisted_planner_cost, planner_estimate)
        if planner_estimate is not None
        else (persisted_planner_cost if persisted_planner_cost > 0 else None)
    )
    child_cost = estimated_cost_microusd(charged_child_tokens, settings)
    cost_microusd = (
        planner_cost + child_cost
        if planner_cost is not None and child_cost is not None
        else None
    )

    planner_latencies = [
        int(item.latency_ms)
        for item in decisions
        if isinstance(item.latency_ms, int) and not isinstance(item.latency_ms, bool) and item.latency_ms >= 0
    ]
    child_model_latencies = [
        int(item.latency_ms)
        for item in model_attempts
        if isinstance(item.latency_ms, int) and not isinstance(item.latency_ms, bool) and item.latency_ms >= 0
    ]
    model_latencies = planner_latencies + child_model_latencies
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
    # Execution retries and Temporal outbox delivery retries have different
    # denominators; keep dispatch attempts visible without inflating execution rate.
    retries = planner_failures + model_retries + len(tool_retries)

    planner_call_count = int(run.planner_calls or 0)
    planner_direction_complete = (
        planner_call_count == 0
        or (
            len(planner_settlements) == planner_call_count
            and type(run.planner_input_tokens) is int
            and run.planner_input_tokens >= 0
            and type(run.planner_output_tokens) is int
            and run.planner_output_tokens >= 0
        )
    )
    child_direction_complete = all(
        type(item.input_tokens) is int and item.input_tokens >= 0
        and type(item.output_tokens) is int and item.output_tokens >= 0
        for item in model_attempts
    )
    model_call_count = planner_call_count + len(model_attempts)
    planner_input = (
        int(run.planner_input_tokens)
        if planner_call_count and planner_direction_complete else 0
    )
    planner_output = (
        int(run.planner_output_tokens)
        if planner_call_count and planner_direction_complete else 0
    )
    child_input = sum(int(item.input_tokens) for item in model_attempts) if child_direction_complete else 0
    child_output = sum(int(item.output_tokens) for item in model_attempts) if child_direction_complete else 0
    token_directions_available = (
        model_call_count > 0 and planner_direction_complete and child_direction_complete
    )
    input_tokens = planner_input + child_input if token_directions_available else None
    output_tokens = planner_output + child_output if token_directions_available else None
    token_direction_missing_components = []
    if model_call_count == 0:
        token_direction_missing_components.append("no_model_calls")
    else:
        if not planner_direction_complete:
            token_direction_missing_components.append("planner")
        if not child_direction_complete:
            token_direction_missing_components.append("child_model_attempts")

    action_by_id = {item.id: item for item in actions}
    approval_wait_ms = 0
    for checkpoint in checkpoints:
        action = action_by_id.get(checkpoint.resource_id or "")
        wait_end = action.approved_at if action is not None and action.approved_at else now
        approval_wait_ms += duration_ms(checkpoint.created_at, wait_end) or 0

    models = sorted({
        *(item.model for item in decisions if item.model),
        *(item.model for item in model_attempts if item.model),
        *([settings.deepseek_model] if int(run.planner_calls or 0) > 0 else []),
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
        # Direction totals are emitted only when every planner reservation is
        # settled with both provider counts and every child attempt has both.
        # Historical or incomplete calls remain unknown, never zero-filled.
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "token_direction_breakdown_available": token_directions_available,
        "token_direction_missing_components": token_direction_missing_components,
        "token_accounting_basis": "planner max(reserved, actual) plus charged child attempts",
        "prompt_sha256s": sorted({item.prompt_sha256 for item in decisions if item.prompt_sha256}),
        "tool_schema_sha256s": sorted({item.tool_schema_sha256 for item in decisions if item.tool_schema_sha256}),
        # Step outputs and run completion do not independently certify an artifact
        # or a human-approved outcome. External verification stays mandatory.
        "verified_artifact_references": [],
        "accepted_outcome_references": [],
        "artifact_outcome_verification_available": False,
        "latency_ms": duration_ms(run.created_at, latency_end) or 0,
        "tool_calls": len(invocations),
        "tool_latency_ms": tool_latencies,
        "tool_latency_ms_total": sum(tool_latencies),
        "tool_latency_ms_p50": percentile(tool_latencies, 0.50),
        "tool_latency_ms_p95": percentile(tool_latencies, 0.95),
        "tool_latency_ms_p99": percentile(tool_latencies, 0.99),
        "model_latency_ms": model_latencies,
        "model_latency_ms_total": sum(model_latencies),
        "model_latency_ms_p50": percentile(model_latencies, 0.50),
        "model_latency_ms_p95": percentile(model_latencies, 0.95),
        "model_latency_ms_p99": percentile(model_latencies, 0.99),
        "model_latency_samples": len(model_latencies),
        "model_latency_coverage": ratio(len(model_latencies), int(run.planner_calls or 0) + len(model_attempts)),
        "model_latency_scope": "successful planner decisions and child model attempts with recorded latency; failed planner attempts without timing are excluded",
        "cost_estimate_available": cost_microusd is not None,
        "cost_rate_microusd_per_1k_tokens": max(0, int(settings.agent_v3_planner_cost_microusd_per_1k_tokens)),
        "retries": retries,
        "dispatch_retries": dispatch_retries,
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
        "model_calls": model_call_count,
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
    model_latencies = [
        value for item in records for value in item.get("model_latency_ms", [])
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    tool_latencies = [
        value for item in records for value in item.get("tool_latency_ms", [])
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    retry_count = sum(max(0, int(item.get("retries", 0))) for item in records)
    dispatch_retry_count = sum(max(0, int(item.get("dispatch_retries", 0))) for item in records)
    execution_attempts = model_calls + tool_calls
    direction_complete = bool(records) and all(
        item.get("token_direction_breakdown_available") is True
        and type(item.get("input_tokens")) is int
        and item["input_tokens"] >= 0
        and type(item.get("output_tokens")) is int
        and item["output_tokens"] >= 0
        for item in records
    )
    input_token_total = (
        sum(int(item["input_tokens"]) for item in records)
        if direction_complete else None
    )
    output_token_total = (
        sum(int(item["output_tokens"]) for item in records)
        if direction_complete else None
    )
    direction_coverage = ratio(
        sum(item.get("token_direction_breakdown_available") is True for item in records),
        len(records),
    )
    cost_complete = bool(records) and all(item.get("cost_microusd") is not None for item in records)
    total_cost = (
        sum(int(item["cost_microusd"]) for item in records)
        if cost_complete else None
    )
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
            "total_cost_microusd": total_cost,
            "average_cost_microusd": (
                round(total_cost / len(records), 2)
                if total_cost is not None else None
            ),
            "cost_estimate_complete": cost_complete,
            "duplicate_attempts": sum(item["duplicate_attempts"] for item in records),
            "outcome_unknown": sum(item["outcome_unknown"] for item in records),
            "abandoned": sum(bool(item["abandoned"]) for item in records),
            "provider_failures": sum(item["provider_failures"] for item in records),
            "retry_attempts": retry_count,
            "retry_rate": ratio(retry_count, execution_attempts),
            "dispatch_retry_attempts": dispatch_retry_count,
            "input_token_consumption": input_token_total,
            "output_token_consumption": output_token_total,
            "token_direction_coverage": direction_coverage,
        },
        "tools": {
            "calls": tool_calls,
            "failures": tool_failures,
            "failure_rate": ratio(tool_failures, tool_calls),
            "latency_samples": len(tool_latencies),
            "p50_latency_ms": percentile(tool_latencies, 0.50),
            "p95_latency_ms": percentile(tool_latencies, 0.95),
            "p99_latency_ms": percentile(tool_latencies, 0.99),
            "latency_coverage": ratio(len(tool_latencies), tool_calls),
        },
        "models": {
            "calls": model_calls,
            "failures": model_failures,
            "failure_rate": ratio(model_failures, model_calls),
            "latency_samples": len(model_latencies),
            "p50_latency_ms": percentile(model_latencies, 0.50),
            "p95_latency_ms": percentile(model_latencies, 0.95),
            "p99_latency_ms": percentile(model_latencies, 0.99),
            "latency_coverage": ratio(len(model_latencies), model_calls),
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
            "cost_rate_microusd_per_1k_tokens": max(0, int(settings.agent_v3_planner_cost_microusd_per_1k_tokens)),
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
        "shuddho_core_agent_model_latency_p50_ms": d["models"]["p50_latency_ms"],
        "shuddho_core_agent_model_latency_p95_ms": d["models"]["p95_latency_ms"],
        "shuddho_core_agent_model_latency_p99_ms": d["models"]["p99_latency_ms"],
        "shuddho_core_agent_model_latency_coverage": d["models"]["latency_coverage"],
        "shuddho_core_agent_model_latency_samples": d["models"]["latency_samples"],
        "shuddho_core_agent_tool_latency_p50_ms": d["tools"]["p50_latency_ms"],
        "shuddho_core_agent_tool_latency_p95_ms": d["tools"]["p95_latency_ms"],
        "shuddho_core_agent_tool_latency_p99_ms": d["tools"]["p99_latency_ms"],
        "shuddho_core_agent_tool_latency_coverage": d["tools"]["latency_coverage"],
        "shuddho_core_agent_tool_latency_samples": d["tools"]["latency_samples"],
        "shuddho_core_agent_retry_attempts": d["runs"]["retry_attempts"],
        "shuddho_core_agent_retry_rate": d["runs"]["retry_rate"],
        "shuddho_core_agent_dispatch_retry_attempts": d["runs"]["dispatch_retry_attempts"],
        "shuddho_core_agent_input_token_consumption": d["runs"]["input_token_consumption"],
        "shuddho_core_agent_output_token_consumption": d["runs"]["output_token_consumption"],
        "shuddho_core_agent_token_direction_coverage": d["runs"]["token_direction_coverage"],
        "shuddho_core_agent_cost_estimate_complete": d["runs"]["cost_estimate_complete"],
        "shuddho_core_agent_run_latency_p50_ms": d["runs"]["p50_latency_ms"],
        "shuddho_core_agent_run_latency_p95_ms": d["runs"]["p95_latency_ms"],
        "shuddho_core_agent_run_latency_p99_ms": d["runs"]["p99_latency_ms"],
        "shuddho_core_agent_average_steps": d["runs"]["average_steps"],
        "shuddho_core_agent_token_consumption": d["runs"]["token_consumption"],
        "shuddho_core_agent_average_cost_microusd": d["runs"]["average_cost_microusd"],
        "shuddho_core_agent_total_cost_microusd": d["runs"]["total_cost_microusd"],
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



# Day 8 comparison is restricted to the existing 40 development tasks. These
# records are operator-controlled evidence, never telemetry or provider receipts
# inferred from the model's output.
DAY8_PROFILES = {"baseline", "bounded_context_compact_observations"}
DAY8_SHA_FIELDS = (
    "model_settings_sha256", "behavior_sha256", "prompt_sha256", "tool_sha256",
)
DAY8_FREEZE_MATCH_FIELDS = (
    "schema_sha256", "flags_sha256", "budgets_sha256", "prompt_template_sha256",
)
DAY8_CONFIGURATION_FIELDS = (
    "profile", "provider", "model", "time_limit_seconds", *DAY8_SHA_FIELDS, *DAY8_FREEZE_MATCH_FIELDS,
)
DAY8_CASE_FIELDS = (
    "input_tokens", "output_tokens", "model_time_ms", "tool_time_ms",
    "retry_count", "cost_microusd", "end_to_end_latency_ms",
)
DAY8_RETRY_TYPES = ("model", "tool", "dispatch")
DAY8_FAILURE_TYPES = ("provider", "model", "tool")
DAY8_COST_COMPONENTS = ("provider", "tools", "compute", "storage", "other")
DAY8_POLICY_HASH_FIELDS = (
    "quality_rubric_sha256", "pricing_assumptions_sha256",
    "owner_approval_receipt_sha256",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _day8_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _day8_uint(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _day8_counts(value: object, fields: tuple[str, ...]) -> bool:
    return isinstance(value, dict) and set(value) == set(fields) and all(
        _day8_uint(value[field]) for field in fields
    )


def _day8_policy_valid(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {
            "approved_p95_end_to_end_latency_ms",
            "approved_max_cost_microusd_per_accepted_output",
            *DAY8_POLICY_HASH_FIELDS,
        }
        and type(value["approved_p95_end_to_end_latency_ms"]) is int
        and value["approved_p95_end_to_end_latency_ms"] > 0
        and type(value["approved_max_cost_microusd_per_accepted_output"]) is int
        and value["approved_max_cost_microusd_per_accepted_output"] > 0
        and all(_day8_digest(value.get(field)) for field in DAY8_POLICY_HASH_FIELDS)
    )


def _day8_cases(
    report: dict, expected: dict, expected_lineage: dict, label: str,
) -> tuple[dict, dict, bool, bool]:
    schema_version = report.get("schema_version") if isinstance(report, dict) else None
    if not isinstance(report, dict) or schema_version not in {1, 2} or report.get("split") != "development":
        raise ValueError(f"{label}: require development-only schema v1 or v2")
    config = report.get("configuration")
    if not isinstance(config, dict) or config.get("profile") not in DAY8_PROFILES:
        raise ValueError(f"{label}: missing bounded configuration identity")
    if config["profile"] != label:
        raise ValueError(f"{label}: mismatched profile")
    # The selected configuration is copied into the freeze report. Fail closed
    # on arbitrary properties rather than copying a prompt, token or raw ID.
    if set(config) - set(DAY8_CONFIGURATION_FIELDS):
        raise ValueError(f"{label}: unexpected configuration property")
    if config.get("provider") != "deepseek" or not isinstance(config.get("model"), str) or not config["model"].strip():
        raise ValueError(f"{label}: only the currently approved DeepSeek provider is supported")
    if any(not _day8_digest(config.get(key)) for key in DAY8_SHA_FIELDS):
        raise ValueError(f"{label}: missing model/behavior/prompt/tool SHA-256")
    if not _day8_digest(report.get("provider_usage_receipt_sha256")):
        raise ValueError(f"{label}: provider usage receipt hash required")
    if not _day8_digest(report.get("review_ledger_sha256")):
        raise ValueError(f"{label}: human-review ledger hash required")
    results = report.get("results")
    if not isinstance(results, list) or len(results) != 40:
        raise ValueError(f"{label}: exactly 40 first-run development task results required")
    def binding_complete(row: dict, case_id: str) -> bool:
        # Compare operator-supplied attempt metadata to the *actual immutable
        # development suite* loaded and hash-verified by pilot_workflow_eval.
        # This only checks consistency. An independent operator must also
        # attest that the provider request used these exact input/source bytes.
        complete = True
        for field, name in (
            ("case_input_sha256", "case input"),
            ("source_snapshot_sha256", "source snapshot"),
        ):
            value = row.get(field)
            if value is None:
                complete = False  # Old reports remain parseable, never eligible.
            elif not _day8_digest(value) or value != expected_lineage[case_id][field]:
                raise ValueError(f"{label}: frozen {name} digest mismatch")
        return complete

    by_id = {}
    case_source_bindings_complete = True
    seen_accepted_artifact_refs = set()
    seen_accepted_review_refs = set()
    seen_run_ids = set()
    seen_usage_receipts = set()
    for row in results:
        if not isinstance(row, dict):
            raise ValueError(f"{label}: invalid task evidence")
        case_id = row.get("id")
        if not isinstance(case_id, str) or case_id not in expected or case_id in by_id:
            raise ValueError(f"{label}: unknown or duplicated development task ID")
        if (row.get("workflow"), row.get("language")) != expected[case_id]:
            raise ValueError(f"{label}: task workflow/language differs from frozen corpus")
        if not binding_complete(row, case_id):
            case_source_bindings_complete = False
        if schema_version == 2 and (
            row.get("execution_kind") != "first_run"
            or type(row.get("attempt_number")) is not int
            or row["attempt_number"] != 1
        ):
            raise ValueError(f"{label}: results must contain explicitly identified first-run attempts only")
        run_id = row.get("run_id")
        if run_id is not None:
            if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 128:
                raise ValueError(f"{label}: malformed run identity")
            if run_id in seen_run_ids:
                raise ValueError(f"{label}: reused run identity across attempts")
            seen_run_ids.add(run_id)
        usage_receipt = row.get("provider_usage_case_receipt_sha256")
        if usage_receipt is not None:
            if not _day8_digest(usage_receipt):
                raise ValueError(f"{label}: malformed provider usage receipt digest")
            if usage_receipt in seen_usage_receipts:
                raise ValueError(f"{label}: reused provider usage receipt across attempts")
            seen_usage_receipts.add(usage_receipt)
        if row.get("output_sha256") is not None and not _day8_digest(row["output_sha256"]):
            raise ValueError(f"{label}: malformed output digest")
        for field in ("passed", "human_accepted", "safety_passed"):
            if type(row.get(field)) is not bool:
                raise ValueError(f"{label}: {field} must be an explicit reviewed boolean")
        for field in DAY8_CASE_FIELDS:
            if row.get(field) is not None and not _day8_uint(row[field]):
                raise ValueError(f"{label}: {field} must be a measured nonnegative integer or null")
        retries = row.get("retry_breakdown")
        if retries is not None:
            if not _day8_counts(retries, DAY8_RETRY_TYPES):
                raise ValueError(f"{label}: invalid retry breakdown")
            if row.get("retry_count") is not None and (
                retries["model"] + retries["tool"] != row["retry_count"]
            ):
                raise ValueError(f"{label}: retry breakdown must match execution retries; dispatch is separate")
        failures = row.get("failure_breakdown")
        if failures is not None and not _day8_counts(failures, DAY8_FAILURE_TYPES):
            raise ValueError(f"{label}: invalid failure breakdown")
        costs = row.get("cost_components_microusd")
        if costs is not None:
            if not _day8_counts(costs, DAY8_COST_COMPONENTS):
                raise ValueError(f"{label}: invalid all-in cost components")
            if row.get("cost_microusd") is not None and (
                sum(costs.values()) != row["cost_microusd"]
            ):
                raise ValueError(f"{label}: cost components must sum to all-in cost")
        for field in ("verified_artifact_refs",):
            if not isinstance(row.get(field), list) or any(
                not isinstance(ref, str) or not ref.strip() for ref in row[field]
            ):
                raise ValueError(f"{label}: invalid verified artifact references")
        if row["human_accepted"] and (
            not row["passed"] or not row["safety_passed"]
            or not row["verified_artifact_refs"]
            or not isinstance(row.get("accepted_outcome_ref"), str)
            or not row["accepted_outcome_ref"].strip()
        ):
            raise ValueError(f"{label}: accepted outcome lacks valid artifact/review reference")
        if row["human_accepted"]:
            # Distinct accepted tasks require distinct human-review evidence:
            # a single receipt must not silently stand in for 40 reviews.
            outcome_ref = row["accepted_outcome_ref"].strip()
            if outcome_ref in seen_accepted_review_refs:
                raise ValueError(f"{label}: reused accepted outcome reference across tasks")
            seen_accepted_review_refs.add(outcome_ref)
            # A completed paid-model artifact needs nonzero provider usage;
            # zero cannot be substituted for an unavailable measurement.
            for field in ("input_tokens", "output_tokens", "model_time_ms"):
                if row.get(field) == 0:
                    raise ValueError(f"{label}: accepted outcome has zero {field}")
            # One artifact cannot independently prove two different tasks.
            for ref in row["verified_artifact_refs"]:
                artifact_ref = ref.strip()
                if artifact_ref in seen_accepted_artifact_refs:
                    raise ValueError(f"{label}: reused artifact reference across accepted tasks")
                seen_accepted_artifact_refs.add(artifact_ref)
        by_id[case_id] = row
    if set(by_id) != set(expected):
        raise ValueError(f"{label}: incomplete frozen development task coverage")

    # Schema v2 makes the 40 primary executions explicit and retains any later
    # execution as a separate, linked rerun. Legacy v1 remains parseable, but
    # cannot prove that its 40 rows are first runs or that rerun costs are present.
    reruns_by_id: dict[str, list[dict]] = {}
    attempt_provenance_complete = schema_version == 2
    if schema_version == 2:
        reruns = report.get("reruns")
        if not isinstance(reruns, list):
            attempt_provenance_complete = False
            reruns = []
        attempts_by_case: dict[str, set[int]] = {}
        for row in reruns:
            if not isinstance(row, dict):
                raise ValueError(f"{label}: invalid rerun evidence")
            case_id = row.get("id")
            if not isinstance(case_id, str) or case_id not in by_id:
                raise ValueError(f"{label}: rerun references an unknown development task")
            if (row.get("workflow"), row.get("language")) != expected[case_id]:
                raise ValueError(f"{label}: rerun workflow/language differs from frozen corpus")
            if not binding_complete(row, case_id):
                case_source_bindings_complete = False
            attempt_number = row.get("attempt_number")
            if row.get("execution_kind") != "rerun" or type(attempt_number) is not int or attempt_number < 2:
                raise ValueError(f"{label}: reruns must have an explicit attempt number of at least two")
            if row.get("rerun_of_run_id") != by_id[case_id].get("run_id"):
                raise ValueError(f"{label}: rerun must reference its case's first-run identity")
            attempts = attempts_by_case.setdefault(case_id, set())
            if attempt_number in attempts:
                raise ValueError(f"{label}: duplicated rerun attempt number for a development task")
            attempts.add(attempt_number)
            run_id = row.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 128:
                raise ValueError(f"{label}: malformed rerun identity")
            if run_id in seen_run_ids:
                raise ValueError(f"{label}: reused run identity across attempts")
            seen_run_ids.add(run_id)
            usage_receipt = row.get("provider_usage_case_receipt_sha256")
            if usage_receipt is not None:
                if not _day8_digest(usage_receipt):
                    raise ValueError(f"{label}: malformed rerun provider usage receipt digest")
                if usage_receipt in seen_usage_receipts:
                    raise ValueError(f"{label}: reused provider usage receipt across attempts")
                seen_usage_receipts.add(usage_receipt)
            for field in ("passed", "human_accepted", "safety_passed"):
                if type(row.get(field)) is not bool:
                    attempt_provenance_complete = False
            for field in DAY8_CASE_FIELDS:
                if row.get(field) is not None and not _day8_uint(row[field]):
                    raise ValueError(f"{label}: rerun {field} must be a measured nonnegative integer or null")
            retries = row.get("retry_breakdown")
            if retries is not None:
                if not _day8_counts(retries, DAY8_RETRY_TYPES):
                    raise ValueError(f"{label}: invalid rerun retry breakdown")
                if row.get("retry_count") is not None and (
                    retries["model"] + retries["tool"] != row["retry_count"]
                ):
                    raise ValueError(f"{label}: rerun retry breakdown must match execution retries")
            failures = row.get("failure_breakdown")
            if failures is not None and not _day8_counts(failures, DAY8_FAILURE_TYPES):
                raise ValueError(f"{label}: invalid rerun failure breakdown")
            costs = row.get("cost_components_microusd")
            if costs is not None:
                if not _day8_counts(costs, DAY8_COST_COMPONENTS):
                    raise ValueError(f"{label}: invalid rerun all-in cost components")
                if row.get("cost_microusd") is not None and sum(costs.values()) != row["cost_microusd"]:
                    raise ValueError(f"{label}: rerun cost components must sum to all-in cost")
            artifacts = row.get("verified_artifact_refs")
            if not isinstance(artifacts, list) or any(
                not isinstance(ref, str) or not ref.strip() for ref in artifacts
            ):
                attempt_provenance_complete = False
                artifacts = []
            if row.get("output_sha256") is not None and not _day8_digest(row["output_sha256"]):
                raise ValueError(f"{label}: malformed rerun output digest")
            if row.get("human_accepted") is True:
                if (
                    not row.get("passed") or not row.get("safety_passed")
                    or not _day8_digest(row.get("output_sha256"))
                    or not artifacts
                    or not isinstance(row.get("accepted_outcome_ref"), str)
                    or not row["accepted_outcome_ref"].strip()
                ):
                    attempt_provenance_complete = False
                else:
                    outcome_ref = row["accepted_outcome_ref"].strip()
                    if outcome_ref in seen_accepted_review_refs:
                        raise ValueError(f"{label}: reused accepted outcome reference across attempts")
                    seen_accepted_review_refs.add(outcome_ref)
                    for ref in artifacts:
                        artifact_ref = ref.strip()
                        if artifact_ref in seen_accepted_artifact_refs:
                            raise ValueError(f"{label}: reused accepted artifact across attempts")
                        seen_accepted_artifact_refs.add(artifact_ref)
            reruns_by_id.setdefault(case_id, []).append(row)
        for case_id, attempts in attempts_by_case.items():
            if sorted(attempts) != list(range(2, max(attempts) + 1)):
                raise ValueError(f"{label}: rerun attempt numbers must be consecutive from two")
    return by_id, reruns_by_id, attempt_provenance_complete, case_source_bindings_complete

def compare_day8_development(baseline: dict, candidate: dict, suite: dict) -> dict:
    """Compare two externally evidenced, matched 40-task development results.

    Evidence references and approval are furnished by an authorized evaluator;
    this function checks their completeness and consistency but cannot attest
    to remote receipt authenticity or replace independent human review.
    """
    development = [item for item in suite["cases"] if item["split"] == "development"]
    # Do not collapse duplicated IDs in a dict before checking the 40-case
    # denominator. Repeated corpus rows are not independent test cases.
    if len(development) != 40 or len({item["id"] for item in development}) != 40:
        raise ValueError("expected exactly 40 distinct frozen development cases")
    expected = {
        item["id"]: (item["workflow"], item["language"])
        for item in development
    }
    expected_lineage = {}
    for item in development:
        source = item.get("_source")
        if not isinstance(source, dict) or not _day8_digest(source.get("sha256")):
            raise ValueError("frozen development suite lacks a verified source snapshot digest")
        expected_lineage[item["id"]] = {
            "case_input_sha256": _sha256_json({
                key: value for key, value in item.items() if key != "_source"
            }),
            "source_snapshot_sha256": source["sha256"],
        }
    identity = {
        "suite_id": suite["manifest"]["suite_id"],
        "source_revision": suite["manifest"]["source_revision"],
        "case_file_sha256": suite["manifest"]["files"]["development"]["sha256"],
    }
    for label, report in (("baseline", baseline), ("bounded_context_compact_observations", candidate)):
        if any(report.get(key) != value for key, value in identity.items()):
            raise ValueError(f"{label}: development corpus identity mismatch")
    base_cases, base_reruns, base_attempt_provenance, base_lineage_complete = _day8_cases(
        baseline, expected, expected_lineage, "baseline",
    )
    candidate_cases, candidate_reruns, candidate_attempt_provenance, candidate_lineage_complete = _day8_cases(
        candidate, expected, expected_lineage, "bounded_context_compact_observations",
    )

    # First-run results are the fixed 40-case quality denominator. Reruns are
    # separate attempts, but their cost and receipt identities must still be
    # accounted for before any Day 9 freeze can be selected.
    def attempts(cases: dict, reruns: dict) -> list[dict]:
        return [*cases.values(), *(row for rows in reruns.values() for row in rows)]

    base_attempts = attempts(base_cases, base_reruns)
    candidate_attempts = attempts(candidate_cases, candidate_reruns)
    base_config = baseline["configuration"]
    candidate_config = candidate["configuration"]
    # Both arms must have the same explicitly bounded execution budget.
    # A missing legacy value remains readable, but cannot qualify a freeze.
    time_limits_complete = all(
        type(config.get("time_limit_seconds")) is int
        and 1 <= config["time_limit_seconds"] <= 3600
        for config in (base_config, candidate_config)
    )
    if time_limits_complete and base_config["time_limit_seconds"] != candidate_config["time_limit_seconds"]:
        raise ValueError("paired context experiment must preserve the same time limit")
    if any(base_config[key] != candidate_config[key] for key in (
        "provider", "model", "model_settings_sha256", "tool_sha256",
    )):
        raise ValueError("paired context experiment must preserve provider, model, parameters and tool surface")
    freeze_hashes_complete = all(
        _day8_digest(config.get(field))
        for config in (base_config, candidate_config)
        for field in DAY8_FREEZE_MATCH_FIELDS
    )
    if freeze_hashes_complete and any(
        base_config[field] != candidate_config[field]
        for field in DAY8_FREEZE_MATCH_FIELDS
    ):
        raise ValueError("paired context experiment must preserve shared prompt template, schema, flags and budgets")
    base_run_ids = {row["run_id"] for row in base_attempts
                    if isinstance(row.get("run_id"), str)}
    candidate_run_ids = {row["run_id"] for row in candidate_attempts
                         if isinstance(row.get("run_id"), str)}
    if base_run_ids & candidate_run_ids:
        raise ValueError("reused run identity across profiles is not an independent generation")
    base_usage_receipts = {
        row["provider_usage_case_receipt_sha256"] for row in base_attempts
        if _day8_digest(row.get("provider_usage_case_receipt_sha256"))
    }
    candidate_usage_receipts = {
        row["provider_usage_case_receipt_sha256"] for row in candidate_attempts
        if _day8_digest(row.get("provider_usage_case_receipt_sha256"))
    }
    if base_usage_receipts & candidate_usage_receipts:
        raise ValueError("reused provider usage receipt across profiles")
    policy = baseline.get("evaluation_policy")
    candidate_policy = candidate.get("evaluation_policy")
    policy_complete = _day8_policy_valid(policy) and _day8_policy_valid(candidate_policy)
    if policy_complete and policy != candidate_policy:
        raise ValueError("paired context experiment must preserve the approved decision policy")

    def complete_metrics(rows: list[dict]) -> bool:
        return all(
            all(_day8_uint(row.get(field)) for field in DAY8_CASE_FIELDS)
            and _day8_uint(row.get("end_to_end_latency_ms"))
            and all(type(row.get(field)) is bool for field in ("passed", "human_accepted", "safety_passed"))
            and _day8_counts(row.get("retry_breakdown"), DAY8_RETRY_TYPES)
            and _day8_counts(row.get("failure_breakdown"), DAY8_FAILURE_TYPES)
            and _day8_counts(row.get("cost_components_microusd"), DAY8_COST_COMPONENTS)
            and isinstance(row.get("run_id"), str) and bool(row["run_id"].strip())
            and _day8_digest(row.get("provider_usage_case_receipt_sha256"))
            and (row.get("human_accepted") is not True or _day8_digest(row.get("output_sha256")))
            for row in rows
        )

    def cell_summary(rows: list[dict], all_cell_attempts: list[dict],
                     provenance_complete: bool) -> dict:
        count = len(rows)
        accepted_count = sum(
            r["human_accepted"] and r["passed"] and r["safety_passed"] for r in rows
        )
        complete = provenance_complete and complete_metrics(all_cell_attempts)
        times = [r["end_to_end_latency_ms"] for r in rows
                 if _day8_uint(r.get("end_to_end_latency_ms"))]
        # Never calculate a cohort percentile from a censored subset.
        latency_complete = len(times) == count
        cost = sum(r["cost_microusd"] for r in all_cell_attempts) if complete else None
        return {
            "cases": count,
            "rerun_attempts": len(all_cell_attempts) - count,
            "accepted": accepted_count,
            "acceptance_rate": ratio(accepted_count, count),
            "metrics_complete": complete,
            "latency_samples": len(times),
            "p50_end_to_end_latency_ms": percentile(times, 0.50) if latency_complete else None,
            "p95_end_to_end_latency_ms": percentile(times, 0.95) if latency_complete else None,
            "total_input_tokens": sum(r["input_tokens"] for r in all_cell_attempts) if complete else None,
            "total_output_tokens": sum(r["output_tokens"] for r in all_cell_attempts) if complete else None,
            "total_model_time_ms": sum(r["model_time_ms"] for r in all_cell_attempts) if complete else None,
            "total_tool_time_ms": sum(r["tool_time_ms"] for r in all_cell_attempts) if complete else None,
            "total_cost_microusd": cost,
            "cost_microusd_per_accepted_output": (
                round(cost / accepted_count, 2)
                if cost is not None and accepted_count else None
            ),
            "retries_by_type": {
                name: sum(r["retry_breakdown"][name] for r in all_cell_attempts)
                for name in DAY8_RETRY_TYPES
            } if complete else None,
            "failures_by_type": {
                name: sum(r["failure_breakdown"][name] for r in all_cell_attempts)
                for name in DAY8_FAILURE_TYPES
            } if complete else None,
        }

    summaries = {}
    for label, report, items, reruns, provenance_complete, lineage_complete in (
        ("baseline", baseline, base_cases, base_reruns, base_attempt_provenance, base_lineage_complete),
        ("bounded_context_compact_observations", candidate, candidate_cases,
         candidate_reruns, candidate_attempt_provenance, candidate_lineage_complete),
    ):
        records = list(items.values())
        rerun_rows = [row for rows in reruns.values() for row in rows]
        all_rows = [*records, *rerun_rows]
        accepted = [r for r in records if r["human_accepted"] and r["passed"] and r["safety_passed"]]
        by_cell = {}
        cell_metrics = {}
        for workflow in ("research_brief", "project_report_email"):
            for language in ("bn", "en"):
                cell = [r for r in records if (r["workflow"], r["language"]) == (workflow, language)]
                if len(cell) != 10:
                    raise ValueError("frozen corpus requires ten cases in each workflow/language cell")
                name = f"{workflow}/{language}"
                by_cell[name] = sum(
                    r["human_accepted"] and r["passed"] and r["safety_passed"] for r in cell
                )
                cell_attempts = [*cell, *(row for row in rerun_rows
                                           if (row["workflow"], row["language"]) == (workflow, language))]
                cell_metrics[name] = cell_summary(cell, cell_attempts, provenance_complete)
        metrics_complete = provenance_complete and complete_metrics(all_rows)
        # Safety applies to every observed execution, including explicit
        # failed/retried reruns whose costs are already in the denominator.
        # A missing rerun review is unknown, never implicitly safe; a false
        # review excludes that profile even if all first runs were accepted.
        safety_assessed_attempts = sum(
            type(r.get("safety_passed")) is bool for r in all_rows
        )
        unsafe_attempts = sum(r.get("safety_passed") is False for r in all_rows)
        safety_ok = safety_assessed_attempts == len(all_rows) and unsafe_attempts == 0
        artifact_coverage = all(r["verified_artifact_refs"] for r in accepted)
        quality_ok = len(accepted) >= 36 and all(n >= 9 for n in by_cell.values()) and safety_ok and artifact_coverage
        latencies = [r["end_to_end_latency_ms"] for r in records
                     if _day8_uint(r.get("end_to_end_latency_ms"))]
        latency_complete = len(latencies) == 40
        p95 = percentile(latencies, 0.95) if latency_complete else None
        latency_ok = (
            policy_complete and p95 is not None
            and p95 <= policy["approved_p95_end_to_end_latency_ms"]
        )
        totals = {
            field: sum(int(r[field]) for r in all_rows) if metrics_complete else None
            for field in DAY8_CASE_FIELDS
        }
        # Enforce the owner's all-in cost ceiling on the *accepted first-run*
        # denominator. All priced reruns, including failed attempts, remain in
        # totals["cost_microusd"]. Compare integers; rounding the displayed
        # unit cost can otherwise qualify a just-over-budget profile.
        cost_ceiling = (
            policy["approved_max_cost_microusd_per_accepted_output"]
            if policy_complete else None
        )
        cost_ok = (
            cost_ceiling is not None and metrics_complete and bool(accepted)
            and totals["cost_microusd"] is not None
            and totals["cost_microusd"] <= cost_ceiling * len(accepted)
        )
        summaries[label] = {
            "cases": 40,
            "rerun_attempts": len(rerun_rows),
            "safety_assessed_attempts": safety_assessed_attempts,
            "unsafe_attempts": unsafe_attempts,
            "attempt_provenance_complete": provenance_complete,
            "case_source_bindings_complete": lineage_complete,
            "human_accepted": len(accepted),
            "by_cell": by_cell,
            "cell_metrics": cell_metrics,
            "quality_gate_passed": quality_ok,
            "safety_gate_passed": safety_ok,
            "metrics_complete": metrics_complete,
            "end_to_end_latency_samples": len(latencies),
            "p50_end_to_end_latency_ms": percentile(latencies, 0.50) if latency_complete else None,
            "p95_end_to_end_latency_ms": p95,
            "approved_p95_latency_ceiling_ms": (
                policy["approved_p95_end_to_end_latency_ms"] if policy_complete else None
            ),
            "latency_gate_passed": latency_ok,
            "approved_cost_ceiling_microusd_per_accepted_output": cost_ceiling,
            "cost_gate_passed": cost_ok,
            "metric_available_cases": {
                field: sum(_day8_uint(r.get(field)) for r in records)
                for field in DAY8_CASE_FIELDS
            },
            "run_identity_coverage": sum(
                isinstance(r.get("run_id"), str) and bool(r["run_id"].strip())
                for r in records
            ),
            "provider_usage_receipt_coverage": sum(
                _day8_digest(r.get("provider_usage_case_receipt_sha256"))
                for r in records
            ),
            "accepted_output_digest_coverage": sum(
                r["human_accepted"] and _day8_digest(r.get("output_sha256"))
                for r in records
            ),
            "retries_by_type": {
                name: sum(r["retry_breakdown"][name] for r in all_rows)
                for name in DAY8_RETRY_TYPES
            } if metrics_complete else None,
            "failures_by_type": {
                name: sum(r["failure_breakdown"][name] for r in all_rows)
                for name in DAY8_FAILURE_TYPES
            } if metrics_complete else None,
            "all_in_cost_components_microusd": {
                name: sum(r["cost_components_microusd"][name] for r in all_rows)
                for name in DAY8_COST_COMPONENTS
            } if metrics_complete else None,
            "total_input_tokens": totals["input_tokens"],
            "total_output_tokens": totals["output_tokens"],
            "total_model_time_ms": totals["model_time_ms"],
            "total_tool_time_ms": totals["tool_time_ms"],
            "total_retries": totals["retry_count"],
            "total_cost_microusd": totals["cost_microusd"],
            "mean_cost_microusd_per_task": (
                round(totals["cost_microusd"] / 40, 2) if totals["cost_microusd"] is not None else None
            ),
            "cost_microusd_per_accepted_output": (
                round(totals["cost_microusd"] / len(accepted), 2)
                if totals["cost_microusd"] is not None and accepted else None
            ),
            "configuration_sha256": _sha256_json(report["configuration"]),
            "evidence_sha256": _sha256_json(report),
        }
    a, b = summaries["baseline"], summaries["bounded_context_compact_observations"]
    retained_quality = (
        b["human_accepted"] >= a["human_accepted"]
        and all(b["by_cell"][key] >= a["by_cell"][key] for key in a["by_cell"])
        # Aggregate and per-cell totals can conceal a loss on a matched task
        # when a different task newly succeeds. Do not trade accepted results.
        and all(
            not base_cases[case_id]["human_accepted"]
            or candidate_cases[case_id]["human_accepted"]
            for case_id in expected
        )
    )
    blockers = []
    if not freeze_hashes_complete:
        blockers.append("missing shared prompt-template/schema/flags/budgets configuration fingerprints")
    if not time_limits_complete:
        blockers.append("missing or invalid fixed per-task time limit in both profiles")
    if not policy_complete:
        blockers.append("missing or invalid owner-approved latency, cost ceiling, rubric and pricing decision policy")
    if not base_attempt_provenance or not candidate_attempt_provenance:
        blockers.append("missing explicit first-run and rerun attempt provenance in both profiles")
    if not base_lineage_complete or not candidate_lineage_complete:
        blockers.append("missing frozen case input/source snapshot binding for first runs or reruns")
    if not a["metrics_complete"] or not b["metrics_complete"]:
        blockers.append(
            "missing run/output/usage receipts, measured input/output tokens, end-to-end latency, "
            "model/tool time, failure/retry breakdown or verified all-in cost components"
        )
    if policy_complete and a["metrics_complete"] and b["metrics_complete"] and not (
        a["cost_gate_passed"] or b["cost_gate_passed"]
    ):
        blockers.append("neither profile meets the owner-approved cost ceiling per accepted output")
    # Regressed candidate is excluded; a qualified baseline may still be frozen.
    if not (a["quality_gate_passed"] or b["quality_gate_passed"]):
        blockers.append("neither profile meets 36/40, 9/10-per-cell, safety and artifact gates")
    if not (baseline.get("generation_identity_verified") is True
            and candidate.get("generation_identity_verified") is True):
        blockers.append("generation identity not externally verified")
    if not (baseline.get("receipts_independently_verified") is True
            and candidate.get("receipts_independently_verified") is True):
        blockers.append("provider, artifact and human-review receipts not independently verified")
    selected = None
    eligible = [
        (label, summary)
        for label, summary in summaries.items()
        if summary["quality_gate_passed"] and summary["latency_gate_passed"]
        and summary["cost_gate_passed"]
        and (label == "baseline" or retained_quality)
    ]
    if not blockers and len(eligible) > 0:
        # Optimize cost per independently accepted output, not raw spend
        # for a cohort with differing acceptance yields. Baseline wins a tie.
        selected = min(eligible, key=lambda pair: (
            Fraction(pair[1]["total_cost_microusd"], pair[1]["human_accepted"]),
            pair[0] != "baseline",
        ))[0]
    if selected is None and not blockers:
        blockers.append("no eligible candidate with retained quality")
    # Real token/cost differences from an unsafe or otherwise ineligible
    # candidate are not *qualified savings*. Do not surface them as such.
    # A cost delta is only *qualified savings* after the entire matched
    # comparison contract is complete. Without the shared freeze fingerprints
    # or fixed execution-time budgets, costs can be arithmetically measured but
    # cannot substantiate a decision against a controlled experiment.
    qualified_savings = (
        freeze_hashes_complete and time_limits_complete and policy_complete
        and a["quality_gate_passed"] and b["quality_gate_passed"]
        and a["latency_gate_passed"] and b["latency_gate_passed"]
        and a["cost_gate_passed"] and b["cost_gate_passed"]
        and a["metrics_complete"] and b["metrics_complete"]
        and base_lineage_complete and candidate_lineage_complete
        and retained_quality
    )
    cost_delta = (
        a["total_cost_microusd"] - b["total_cost_microusd"]
        if qualified_savings
        and a["total_cost_microusd"] is not None
        and b["total_cost_microusd"] is not None
        and retained_quality
        and baseline.get("receipts_independently_verified") is True
        and candidate.get("receipts_independently_verified") is True
        and baseline.get("generation_identity_verified") is True
        and candidate.get("generation_identity_verified") is True
        else None
    )
    frozen = None
    if selected is not None:
        root = Path(__file__).resolve().parents[1]
        files = (
            "services/coworker/agent_planning_model.py",
            "services/coworker/config.py",
            "services/coworker/models.py",
            "scripts/core_agent_observability.py",
        )
        frozen = {
            "profile": selected,
            "configuration": (baseline if selected == "baseline" else candidate)["configuration"],
            "evaluation_policy": policy,
            "source_file_sha256": {path: _sha256_file(root / path) for path in files},
            "baseline_evidence_sha256": a["evidence_sha256"],
            "candidate_evidence_sha256": b["evidence_sha256"],
            "development_case_source_lineage_sha256": _sha256_json(expected_lineage),
            **identity,
            "promotion_authorized": False,
            "qualification_note": "Operator evidence must be independently checked; this freeze does not activate a deployment.",
        }
        frozen["freeze_sha256"] = _sha256_json(frozen)
    # Keep matched, numeric per-task economics in the access-controlled local
    # JSON report. This data is intentionally never rendered to OpenMetrics.
    per_task = []
    task_fields = (
        *DAY8_CASE_FIELDS, "run_id", "provider_usage_case_receipt_sha256",
        "case_input_sha256", "source_snapshot_sha256",
        "output_sha256", "retry_breakdown", "failure_breakdown",
        "cost_components_microusd", "passed", "human_accepted",
        "safety_passed", "verified_artifact_refs", "accepted_outcome_ref",
    )
    for case_id in sorted(expected):
        record = {"id": case_id, "workflow": expected[case_id][0],
                  "language": expected[case_id][1]}
        for label, cases, reruns, provenance in (
            ("baseline", base_cases, base_reruns, base_attempt_provenance),
            ("bounded_context_compact_observations", candidate_cases,
             candidate_reruns, candidate_attempt_provenance),
        ):
            item = cases[case_id]
            case_reruns = reruns.get(case_id, [])
            economics = {field: item.get(field) for field in task_fields}
            economics["rerun_attempts"] = len(case_reruns)
            economics["unsafe_rerun_attempts"] = sum(
                attempt.get("safety_passed") is False for attempt in case_reruns
            )
            economics["all_attempts_cost_microusd"] = (
                sum(r["cost_microusd"] for r in [item, *case_reruns])
                if provenance and complete_metrics([item, *case_reruns]) else None
            )
            economics["measured_model_tool_time_ms"] = (
                item["model_time_ms"] + item["tool_time_ms"]
                if _day8_uint(item.get("model_time_ms"))
                and _day8_uint(item.get("tool_time_ms"))
                else None
            )
            record[label] = economics
        record["quality_retained"] = (
            not record["baseline"]["human_accepted"]
            or record["bounded_context_compact_observations"]["human_accepted"]
        )
        record["paired_measured_deltas_candidate_minus_baseline"] = {
            field: (
                record["bounded_context_compact_observations"][field]
                - record["baseline"][field]
                if _day8_uint(record["baseline"].get(field))
                and _day8_uint(record["bounded_context_compact_observations"].get(field))
                else None
            )
            for field in DAY8_CASE_FIELDS
        }
        # Cost deltas include rerun attempts, not only the first 40 rows.
        record["paired_measured_deltas_candidate_minus_baseline"]["cost_microusd"] = (
            record["bounded_context_compact_observations"]["all_attempts_cost_microusd"]
            - record["baseline"]["all_attempts_cost_microusd"]
            if _day8_uint(record["baseline"]["all_attempts_cost_microusd"])
            and _day8_uint(record["bounded_context_compact_observations"]["all_attempts_cost_microusd"])
            else None
        )
        record["measured_cost_savings_microusd"] = (
            record["baseline"]["all_attempts_cost_microusd"]
            - record["bounded_context_compact_observations"]["all_attempts_cost_microusd"]
            if qualified_savings
            and baseline.get("generation_identity_verified") is True
            and candidate.get("generation_identity_verified") is True
            and baseline.get("receipts_independently_verified") is True
            and candidate.get("receipts_independently_verified") is True
            and _day8_uint(record["baseline"]["all_attempts_cost_microusd"])
            and _day8_uint(record["bounded_context_compact_observations"]["all_attempts_cost_microusd"])
            else None
        )
        per_task.append(record)
    return {
        "schema_version": 1,
        "evidence_scope": "development_40_only",
        "profile_summaries": summaries,
        "per_task_comparison": per_task,
        "candidate_quality_retained": retained_quality,
        "candidate_exclusion_reason": (
            "quality_regression_vs_baseline" if not retained_quality
            else "failed_quality_or_safety_gate" if not b["quality_gate_passed"]
            else "missing_operational_measurements_or_policy"
            if not b["metrics_complete"] or not policy_complete
            else "latency_slo_breached" if not b["latency_gate_passed"]
            else "cost_ceiling_breached" if policy_complete and not b["cost_gate_passed"]
            else None
        ),
        "measured_cost_savings_microusd": cost_delta,
        "selected_least_cost_qualified_profile": selected,
        "status": "FROZEN_FOR_DAY9" if selected is not None else "BLOCKED",
        "blockers": blockers,
        "freeze": frozen,
        "posthog_status": "incomplete_pending_privacy_approval_and_verified_ingestion",
        "limitations": [
            "Per-task evidence is operator-supplied and must be checked against independently held receipts.",
            "Development results do not qualify protected holdout or production.",
            "No PostHog ingestion or provider capability is inferred from this report.",
        ],
    }


def _read_day8_input(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("Day 8 input must be a regular non-symlink file <=2 MB")
    def unique(pairs):
        value = {}
        for key, element in pairs:
            if key in value:
                raise ValueError("duplicate Day 8 JSON key")
            value[key] = element
        return value
    def invalid_constant(value):
        raise ValueError(f"non-finite Day 8 JSON constant: {value}")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                       parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("Day 8 input must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Phase 10 Core Agent observability and economics.")
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--prom-output", type=Path)
    parser.add_argument("--day8-baseline", type=Path)
    parser.add_argument("--day8-candidate", type=Path)
    parser.add_argument("--day8-report", type=Path)
    args = parser.parse_args()
    if any((args.day8_baseline, args.day8_candidate, args.day8_report)):
        if not all((args.day8_baseline, args.day8_candidate, args.day8_report)):
            parser.error("Day 8 mode requires baseline, candidate and report paths")
        from scripts.pilot_workflow_eval import load_suite
        result = compare_day8_development(
            _read_day8_input(args.day8_baseline),
            _read_day8_input(args.day8_candidate),
            load_suite(),
        )
        atomic_write(args.day8_report, json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"status": result["status"], "blockers": result["blockers"],
                          "day8_report": str(args.day8_report)}, indent=2))
        return 0 if result["status"] == "FROZEN_FOR_DAY9" else 1
    if not args.json_output or not args.prom_output:
        parser.error("normal export requires --json-output and --prom-output")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
