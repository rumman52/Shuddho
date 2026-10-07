from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from .connector_actions import ConnectorFailure
from .errors import CoworkerError


STANDARD_TOOL_ERRORS = {
    "provider_unavailable",
    "provider_rate_limited",
    "permission_denied",
    "invalid_tool_input",
    "tool_timeout",
    "outcome_unknown",
    "tool_not_supported",
    "approval_required",
}


@dataclass
class _CircuitState:
    failures: int = 0
    open_until: float = 0.0


_CIRCUITS: dict[str, _CircuitState] = {}


def _state(name: str) -> _CircuitState:
    return _CIRCUITS.setdefault(name, _CircuitState())


def reset_tool_circuits() -> None:
    _CIRCUITS.clear()


def normalize_tool_error(error: Exception, *, consequential: bool = False) -> CoworkerError:
    if isinstance(error, CoworkerError):
        if error.code in STANDARD_TOOL_ERRORS:
            return error
        if error.code in {
            "agent_cancelled",
            "action_cancelled",
            "sandbox_cancelled",
        }:
            return CoworkerError("agent_cancelled", error.message, 409)
        if error.code in {
            "permission_denied",
            "connection_scope_missing",
            "oauth_scope_missing",
            "action_scope",
        }:
            return CoworkerError("permission_denied", "The tool does not have the required permission.", 403)
        if error.code in {
            "tool_unavailable",
            "connection_provider_disabled",
            "connector_trust_boundary_unavailable",
            "connector_read_unregistered",
            "connector_reads_disabled",
            "connection_unavailable",
            "attachment_unavailable",
            "document_share_unavailable",
        }:
            return CoworkerError("provider_unavailable", "The required provider or connector is unavailable.", 503)
        if error.code in {"unknown_tool", "unsupported_agent_tool"}:
            return CoworkerError("tool_not_supported", "This tool is not supported by the current runtime.", 409)
        if error.code in {"invalid_tool_arguments", "validation_error"}:
            return CoworkerError("invalid_tool_input", "The tool input is invalid.", 422)
        if error.code in {"action_outcome_unknown", "worker_interrupted"}:
            return CoworkerError("outcome_unknown", "The provider outcome is uncertain and must be reconciled.", 409)
        if error.status_code == 429:
            return CoworkerError("provider_rate_limited", "The provider rate limit was reached.", 429)
        if error.status_code >= 500:
            return CoworkerError("provider_unavailable", "The provider is currently unavailable.", 503)
        return error

    if isinstance(error, ConnectorFailure):
        code = str(error.code or "")
        if "rate" in code or "429" in code:
            return CoworkerError("provider_rate_limited", "The provider rate limit was reached.", 429)
        if consequential and not error.definitive:
            return CoworkerError("outcome_unknown", "The provider outcome is uncertain and must be reconciled.", 409)
        if "scope" in code or "permission" in code:
            return CoworkerError("permission_denied", "The provider denied the required permission.", 403)
        return CoworkerError("provider_unavailable", "The provider is currently unavailable.", 503)

    status = getattr(error, "status_code", None)
    if status == 429:
        return CoworkerError("provider_rate_limited", "The provider rate limit was reached.", 429)
    return CoworkerError("provider_unavailable", "The tool provider failed unexpectedly.", 503)


def _result_size(value: dict) -> int:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CoworkerError("provider_unavailable", "The tool returned a malformed response.", 502) from error
    return len(encoded)


def validate_tool_result(spec, raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise CoworkerError("provider_unavailable", "The tool returned a malformed response.", 502)
    value = spec.validate_output(raw).model_dump(mode="json")
    if _result_size(value) > spec.max_result_bytes:
        raise CoworkerError(
            "provider_unavailable",
            "The tool result exceeded its registered size limit.",
            502,
        )
    return value


async def execute_tool_contract(
    spec,
    operation: Callable[[], Awaitable[dict]],
    *,
    cancellation_check: Callable[[], bool] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict:
    """Execute one non-consequential tool behind the Phase-4 reliability contract."""

    if spec.consequential or spec.approval_required:
        raise CoworkerError(
            "approval_required",
            "Consequential tools must use the immutable approved-action path.",
            409,
        )

    circuit = _state(spec.name)
    now = time.monotonic()
    if circuit.open_until > now:
        raise CoworkerError(
            "provider_unavailable",
            "The tool circuit breaker is open after repeated provider failures.",
            503,
        )

    attempts = spec.retry_policy.max_attempts
    last_error: CoworkerError | None = None

    for attempt in range(1, attempts + 1):
        if cancellation_check is not None and cancellation_check():
            raise CoworkerError("agent_cancelled", "This Agent run was cancelled.", 409)

        try:
            raw = await asyncio.wait_for(operation(), timeout=spec.timeout_seconds)
            if cancellation_check is not None and cancellation_check():
                raise CoworkerError("agent_cancelled", "This Agent run was cancelled.", 409)
            value = validate_tool_result(spec, raw)
            circuit.failures = 0
            circuit.open_until = 0.0
            return value
        except asyncio.TimeoutError:
            normalized = CoworkerError("tool_timeout", "The tool exceeded its registered timeout.", 504)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            normalized = normalize_tool_error(error, consequential=False)

        last_error = normalized
        retryable = (
            spec.retry_policy.mode == "bounded"
            and normalized.code in spec.retry_policy.retryable_errors
            and attempt < attempts
        )
        if normalized.code in {
            "provider_unavailable",
            "provider_rate_limited",
            "tool_timeout",
        }:
            circuit.failures += 1
            if circuit.failures >= spec.circuit_breaker_failures:
                circuit.open_until = time.monotonic() + spec.circuit_breaker_cooldown_seconds

        if not retryable:
            raise normalized
        delay = spec.retry_policy.initial_backoff_seconds * (2 ** (attempt - 1))
        if delay > 0:
            await sleep(delay)

    raise last_error or CoworkerError("provider_unavailable", "The tool failed.", 503)
