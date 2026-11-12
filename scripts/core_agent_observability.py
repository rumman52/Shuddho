from __future__ import annotations

import argparse
import hashlib
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
        # The current persistence schema has aggregate/reserved tokens, not
        # provider-verified per-direction usage; null means unknown, not zero.
        "input_tokens": None,
        "output_tokens": None,
        "token_direction_breakdown_available": False,
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
    model_latencies = [
        value for item in records for value in item.get("model_latency_ms", [])
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    tool_latencies = [
        value for item in records for value in item.get("tool_latency_ms", [])
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    retry_count = sum(max(0, int(item.get("retries", 0))) for item in records)
    execution_attempts = model_calls + tool_calls
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
DAY8_SHA_FIELDS = ("model_settings_sha256", "behavior_sha256", "prompt_sha256", "tool_sha256")
DAY8_CASE_FIELDS = ("input_tokens", "output_tokens", "model_time_ms", "tool_time_ms",
                    "retry_count", "cost_microusd")


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


def _day8_cases(report: dict, expected: dict, label: str) -> dict:
    if not isinstance(report, dict) or report.get("schema_version") != 1 or report.get("split") != "development":
        raise ValueError(f"{label}: require development-only schema v1")
    config = report.get("configuration")
    if not isinstance(config, dict) or config.get("profile") not in DAY8_PROFILES:
        raise ValueError(f"{label}: missing bounded configuration identity")
    if config["profile"] != label:
        raise ValueError(f"{label}: mismatched profile")
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
        raise ValueError(f"{label}: exactly 40 development task results required")
    by_id = {}
    for row in results:
        if not isinstance(row, dict):
            raise ValueError(f"{label}: invalid task evidence")
        case_id = row.get("id")
        if not isinstance(case_id, str) or case_id not in expected or case_id in by_id:
            raise ValueError(f"{label}: unknown or duplicated development task ID")
        if (row.get("workflow"), row.get("language")) != expected[case_id]:
            raise ValueError(f"{label}: task workflow/language differs from frozen corpus")
        for field in ("passed", "human_accepted", "safety_passed"):
            if type(row.get(field)) is not bool:
                raise ValueError(f"{label}: {field} must be an explicit reviewed boolean")
        for field in DAY8_CASE_FIELDS:
            if row.get(field) is not None and not _day8_uint(row[field]):
                raise ValueError(f"{label}: {field} must be a measured nonnegative integer or null")
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
        by_id[case_id] = row
    if set(by_id) != set(expected):
        raise ValueError(f"{label}: incomplete frozen development task coverage")
    return by_id


def compare_day8_development(baseline: dict, candidate: dict, suite: dict) -> dict:
    """Compare two externally evidenced, matched 40-task development results.

    Evidence references and approval are furnished by an authorized evaluator;
    this function checks their completeness and consistency but cannot attest
    to remote receipt authenticity or replace independent human review.
    """
    expected = {
        item["id"]: (item["workflow"], item["language"])
        for item in suite["cases"] if item["split"] == "development"
    }
    if len(expected) != 40:
        raise ValueError("expected exactly 40 frozen development cases")
    identity = {
        "suite_id": suite["manifest"]["suite_id"],
        "source_revision": suite["manifest"]["source_revision"],
        "case_file_sha256": suite["manifest"]["files"]["development"]["sha256"],
    }
    for label, report in (("baseline", baseline), ("bounded_context_compact_observations", candidate)):
        if any(report.get(key) != value for key, value in identity.items()):
            raise ValueError(f"{label}: development corpus identity mismatch")
    base_cases = _day8_cases(baseline, expected, "baseline")
    candidate_cases = _day8_cases(candidate, expected, "bounded_context_compact_observations")
    base_config = baseline["configuration"]
    candidate_config = candidate["configuration"]
    if any(base_config[key] != candidate_config[key] for key in (
        "provider", "model", "model_settings_sha256", "tool_sha256"
    )):
        raise ValueError("paired context experiment must preserve provider, model, parameters and tool surface")

    summaries = {}
    for label, report, items in (
        ("baseline", baseline, base_cases),
        ("bounded_context_compact_observations", candidate, candidate_cases),
    ):
        records = list(items.values())
        accepted = [r for r in records if r["human_accepted"] and r["passed"] and r["safety_passed"]]
        by_cell = {}
        for workflow in ("research_brief", "project_report_email"):
            for language in ("bn", "en"):
                cell = [r for r in records if (r["workflow"], r["language"]) == (workflow, language)]
                if len(cell) != 10:
                    raise ValueError("frozen corpus requires ten cases in each workflow/language cell")
                by_cell[f"{workflow}/{language}"] = sum(
                    r["human_accepted"] and r["passed"] and r["safety_passed"] for r in cell
                )
        metrics_complete = all(
            all(_day8_uint(row.get(field)) for field in DAY8_CASE_FIELDS)
            for row in records
        )
        safety_ok = all(r["safety_passed"] for r in records)
        artifact_coverage = all(r["verified_artifact_refs"] for r in accepted)
        quality_ok = len(accepted) >= 36 and all(n >= 9 for n in by_cell.values()) and safety_ok and artifact_coverage
        totals = {
            field: sum(int(r[field]) for r in records) if metrics_complete else None
            for field in DAY8_CASE_FIELDS
        }
        summaries[label] = {
            "cases": 40,
            "human_accepted": len(accepted),
            "by_cell": by_cell,
            "quality_gate_passed": quality_ok,
            "metrics_complete": metrics_complete,
            "total_input_tokens": totals["input_tokens"],
            "total_output_tokens": totals["output_tokens"],
            "total_model_time_ms": totals["model_time_ms"],
            "total_tool_time_ms": totals["tool_time_ms"],
            "total_retries": totals["retry_count"],
            "total_cost_microusd": totals["cost_microusd"],
            "mean_cost_microusd_per_task": (
                round(totals["cost_microusd"] / 40, 2) if totals["cost_microusd"] is not None else None
            ),
            "configuration_sha256": _sha256_json(report["configuration"]),
            "evidence_sha256": _sha256_json(report),
        }
    a, b = summaries["baseline"], summaries["bounded_context_compact_observations"]
    retained_quality = b["human_accepted"] >= a["human_accepted"] and all(
        b["by_cell"][key] >= a["by_cell"][key] for key in a["by_cell"]
    )
    blockers = []
    if not a["metrics_complete"] or not b["metrics_complete"]:
        blockers.append("missing measured input/output tokens, model/tool time, retries or cost")
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
        if summary["quality_gate_passed"]
        and (label == "baseline" or retained_quality)
    ]
    if not blockers and len(eligible) > 0:
        selected = min(eligible, key=lambda pair: (pair[1]["total_cost_microusd"], pair[0] != "baseline"))[0]
    if selected is None and not blockers:
        blockers.append("no eligible candidate with retained quality")
    cost_delta = (
        a["total_cost_microusd"] - b["total_cost_microusd"]
        if a["total_cost_microusd"] is not None
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
            "scripts/core_agent_observability.py",
        )
        frozen = {
            "profile": selected,
            "configuration": (baseline if selected == "baseline" else candidate)["configuration"],
            "source_file_sha256": {path: _sha256_file(root / path) for path in files},
            "baseline_evidence_sha256": a["evidence_sha256"],
            "candidate_evidence_sha256": b["evidence_sha256"],
            **identity,
            "promotion_authorized": False,
            "qualification_note": "Operator evidence must be independently checked; this freeze does not activate a deployment.",
        }
        frozen["freeze_sha256"] = _sha256_json(frozen)
    # Keep matched, numeric per-task economics in the access-controlled local
    # JSON report. This data is intentionally never rendered to OpenMetrics.
    per_task = []
    task_fields = (*DAY8_CASE_FIELDS, "passed", "human_accepted",
                   "safety_passed", "verified_artifact_refs", "accepted_outcome_ref")
    for case_id in sorted(expected):
        record = {"id": case_id, "workflow": expected[case_id][0],
                  "language": expected[case_id][1]}
        for label, cases in (("baseline", base_cases),
                             ("bounded_context_compact_observations", candidate_cases)):
            item = cases[case_id]
            economics = {field: item.get(field) for field in task_fields}
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
        record["measured_cost_savings_microusd"] = (
            record["baseline"]["cost_microusd"]
            - record["bounded_context_compact_observations"]["cost_microusd"]
            if retained_quality
            and baseline.get("generation_identity_verified") is True
            and candidate.get("generation_identity_verified") is True
            and baseline.get("receipts_independently_verified") is True
            and candidate.get("receipts_independently_verified") is True
            and _day8_uint(record["baseline"]["cost_microusd"])
            and _day8_uint(record["bounded_context_compact_observations"]["cost_microusd"])
            else None
        )
        per_task.append(record)
    return {
        "schema_version": 1,
        "evidence_scope": "development_40_only",
        "profile_summaries": summaries,
        "per_task_comparison": per_task,
        "candidate_quality_retained": retained_quality,
        "candidate_exclusion_reason": None if retained_quality else "quality_regression_vs_baseline",
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
