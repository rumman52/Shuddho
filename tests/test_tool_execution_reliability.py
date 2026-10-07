from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel, ConfigDict

from services.coworker.agent_tools import (
    IdempotencyPolicy,
    RetryPolicy,
    ToolExecutionOutput,
    ToolSpec,
    TOOLS,
)
from services.coworker.connector_actions import ConnectorFailure
from services.coworker.errors import CoworkerError
from services.coworker.tool_execution import (
    STANDARD_TOOL_ERRORS,
    execute_tool_contract,
    normalize_tool_error,
    reset_tool_circuits,
    validate_tool_result,
)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def spec(
    *,
    timeout_seconds: int = 1,
    max_result_bytes: int = 65536,
    retry_policy: RetryPolicy | None = None,
    circuit_breaker_failures: int = 3,
) -> ToolSpec:
    return ToolSpec(
        name="test.read",
        version="1",
        kind="task",
        input_model=EmptyInput,
        output_model=ToolExecutionOutput,
        capability="test",
        permissions=("fixture:read",),
        read_write_classification="read",
        risk_class="low",
        retry_policy=retry_policy or RetryPolicy(),
        idempotency_policy=IdempotencyPolicy(
            mode="server_idempotency_key",
            key_scope="test",
            outcome_unknown_policy="resume",
        ),
        approval_requirement="none",
        skill_id="document",
        timeout_seconds=timeout_seconds,
        max_result_bytes=max_result_bytes,
        circuit_breaker_failures=circuit_breaker_failures,
        circuit_breaker_cooldown_seconds=30,
    )


@pytest.fixture(autouse=True)
def clean_circuits():
    reset_tool_circuits()
    yield
    reset_tool_circuits()


def completed(summary: dict | None = None) -> dict:
    return {
        "status": "completed",
        "resource_type": "fixture",
        "resource_id": "fixture-1",
        "summary": summary or {},
    }


def test_phase4_all_registered_tools_expose_complete_execution_contract():
    required = {
        "name",
        "version",
        "capability",
        "input_schema",
        "output_schema",
        "permissions",
        "read_write_classification",
        "risk_class",
        "timeout",
        "timeout_seconds",
        "retry_policy",
        "idempotency_policy",
        "approval_requirement",
        "max_result_bytes",
        "circuit_breaker",
    }
    assert TOOLS
    for value in TOOLS.values():
        public = value.public()
        assert required <= set(public)
        assert public["input_schema"]["type"] == "object"
        assert public["output_schema"]["type"] == "object"
        assert public["timeout"] == public["timeout_seconds"]
        assert public["timeout_seconds"] > 0
        assert public["max_result_bytes"] > 0
        assert public["retry_policy"]["max_attempts"] in {1, 2, 3}
        assert public["approval_requirement"] in {
            "none",
            "explicit_user_approval",
        }

    for name in ("email.send", "calendar.create"):
        public = TOOLS[name].public()
        assert public["approval_requirement"] == "explicit_user_approval"
        assert public["retry_policy"]["max_attempts"] == 1
        assert public["idempotency_policy"]["mode"] == "reconcile_only"


def test_phase4_schema_validation_uses_standard_invalid_tool_input():
    with pytest.raises(CoworkerError) as error:
        TOOLS["document.create"].validate({"instruction": "x"})
    assert error.value.code == "invalid_tool_input"
    assert error.value.status_code == 422


def test_phase4_unknown_tool_uses_standard_tool_not_supported():
    from services.coworker.agent_tools import tool

    with pytest.raises(CoworkerError) as error:
        tool("does.not.exist")
    assert error.value.code == "tool_not_supported"


def test_phase4_success_validates_output_and_result_size():
    value = asyncio.run(execute_tool_contract(spec(), lambda: _return(completed())))
    assert value["status"] == "completed"
    assert value["resource_id"] == "fixture-1"


async def _return(value):
    return value


def test_phase4_malformed_provider_result_is_structured():
    async def malformed():
        return {"unexpected": True}

    with pytest.raises(CoworkerError) as error:
        asyncio.run(execute_tool_contract(spec(), malformed))
    assert error.value.code == "provider_unavailable"


def test_phase4_non_json_provider_result_is_structured():
    async def malformed():
        return {
            "status": "completed",
            "resource_type": "fixture",
            "resource_id": "fixture-1",
            "summary": {"bad": {1, 2, 3}},
        }

    with pytest.raises(CoworkerError) as error:
        asyncio.run(execute_tool_contract(spec(), malformed))
    assert error.value.code == "provider_unavailable"


def test_phase4_result_size_limit_fails_closed():
    small = spec(max_result_bytes=1024)
    with pytest.raises(CoworkerError) as error:
        validate_tool_result(
            small,
            completed({"value": "x" * 2000}),
        )
    assert error.value.code == "provider_unavailable"


def test_phase4_tool_timeout_is_structured():
    async def slow():
        await asyncio.sleep(0.05)
        return completed()

    value = spec(timeout_seconds=1)
    object.__setattr__(value, "timeout_seconds", 0.01)
    with pytest.raises(CoworkerError) as error:
        asyncio.run(execute_tool_contract(value, slow))
    assert error.value.code == "tool_timeout"
    assert error.value.status_code == 504


def test_phase4_bounded_retry_recovers_once():
    calls = 0
    delays: list[float] = []

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CoworkerError("provider_unavailable", "temporary", 503)
        return completed()

    async def no_sleep(delay: float):
        delays.append(delay)

    value = asyncio.run(
        execute_tool_contract(
            spec(
                retry_policy=RetryPolicy(
                    mode="bounded",
                    max_attempts=2,
                    initial_backoff_seconds=0.25,
                    retryable_errors=("provider_unavailable",),
                )
            ),
            operation,
            sleep=no_sleep,
        )
    )
    assert value["status"] == "completed"
    assert calls == 2
    assert delays == [0.25]


def test_phase4_retry_is_bounded():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        raise CoworkerError("provider_unavailable", "temporary", 503)

    with pytest.raises(CoworkerError) as error:
        asyncio.run(
            execute_tool_contract(
                spec(
                    retry_policy=RetryPolicy(
                        mode="bounded",
                        max_attempts=2,
                        retryable_errors=("provider_unavailable",),
                    )
                ),
                operation,
                sleep=lambda _delay: _return(None),
            )
        )
    assert error.value.code == "provider_unavailable"
    assert calls == 2


def test_phase4_circuit_breaker_opens_after_bounded_failures():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        raise CoworkerError("provider_unavailable", "temporary", 503)

    value = spec(
        retry_policy=RetryPolicy(),
        circuit_breaker_failures=2,
    )
    for _ in range(2):
        with pytest.raises(CoworkerError):
            asyncio.run(execute_tool_contract(value, operation))

    with pytest.raises(CoworkerError) as error:
        asyncio.run(execute_tool_contract(value, operation))
    assert error.value.code == "provider_unavailable"
    assert calls == 2


def test_phase4_provider_rate_limit_is_standardized():
    class RateLimit(Exception):
        status_code = 429

    normalized = normalize_tool_error(RateLimit())
    assert normalized.code == "provider_rate_limited"
    assert normalized.status_code == 429


def test_phase4_connector_permission_error_is_standardized():
    normalized = normalize_tool_error(
        ConnectorFailure("connection_scope_missing", definitive=True)
    )
    assert normalized.code == "permission_denied"
    assert normalized.status_code == 403


def test_phase4_unavailable_connector_is_standardized():
    normalized = normalize_tool_error(
        CoworkerError(
            "connection_provider_disabled",
            "disabled",
            503,
        )
    )
    assert normalized.code == "provider_unavailable"


def test_phase4_uncertain_consequential_provider_failure_is_outcome_unknown():
    normalized = normalize_tool_error(
        ConnectorFailure("provider_timeout", definitive=False),
        consequential=True,
    )
    assert normalized.code == "outcome_unknown"


def test_phase4_cancellation_propagates_before_provider_call():
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        return completed()

    with pytest.raises(CoworkerError) as error:
        asyncio.run(
            execute_tool_contract(
                spec(),
                operation,
                cancellation_check=lambda: True,
            )
        )
    assert error.value.code == "agent_cancelled"
    assert calls == 0


def test_phase4_asyncio_cancellation_is_not_rewritten():
    async def operation():
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(execute_tool_contract(spec(), operation))


def test_phase4_consequential_tool_cannot_enter_generic_retry_executor():
    with pytest.raises(CoworkerError) as error:
        asyncio.run(
            execute_tool_contract(
                TOOLS["email.send"],
                lambda: _return(completed()),
            )
        )
    assert error.value.code == "approval_required"


def test_phase4_standard_error_vocabulary_contains_required_contract():
    assert {
        "provider_unavailable",
        "provider_rate_limited",
        "permission_denied",
        "invalid_tool_input",
        "tool_timeout",
        "outcome_unknown",
        "tool_not_supported",
        "approval_required",
    } <= STANDARD_TOOL_ERRORS
