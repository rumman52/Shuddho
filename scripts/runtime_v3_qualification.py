"""Opt-in live model + Temporal qualification helpers for Agent Runtime v3.

The recording transport never stores prompts, completions, credentials, or provider
error bodies. It records provider usage metadata and latency; the evidence writer stores
only explicitly selected metadata plus a bounded generated-output preview for review.
"""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import json
import math
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx


MAX_CAPTURE_BYTES = 1_048_576


def _usage_int(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


class RecordingTransport(httpx.AsyncBaseTransport):
    """Measure live DeepSeek responses without retaining request/response text."""

    def __init__(
        self,
        *,
        model: str,
        inner_transport: httpx.AsyncBaseTransport | None = None,
        hold_first_successful_response: bool = False,
    ) -> None:
        self.model = model
        self._inner_transport = inner_transport or httpx.AsyncHTTPTransport()
        self._call_kind = contextvars.ContextVar(
            f"runtime_v3_call_kind_{id(self)}", default="unknown"
        )
        self.records: list[dict[str, Any]] = []
        self._hold_first_successful_response = hold_first_successful_response
        self._held_response = False
        self.response_ready = asyncio.Event()
        self.release_response = asyncio.Event()
        if not hold_first_successful_response:
            self.release_response.set()

    @contextmanager
    def measure_as(self, kind: str):
        token = self._call_kind.set(kind)
        try:
            yield
        finally:
            self._call_kind.reset(token)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        started = time.perf_counter()
        response = await self._inner_transport.handle_async_request(request)
        status_code = response.status_code

        if status_code != 200:
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            retry_after = response.headers.get("retry-after")
            await response.aclose()
            self.records.append({
                "kind": self._call_kind.get(),
                "model": self.model,
                "status_code": status_code,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "latency_ms": latency_ms,
            })
            headers = {"retry-after": retry_after} if retry_after else {}
            return httpx.Response(status_code, headers=headers, request=request)

        chunks: list[bytes] = []
        size = 0
        try:
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_CAPTURE_BYTES:
                    raise RuntimeError(
                        "Runtime v3 qualification response exceeded the 1 MiB capture limit."
                    )
                chunks.append(chunk)
        finally:
            await response.aclose()

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        body = b"".join(chunks)
        try:
            envelope = json.loads(body)
            usage = envelope.get("usage") if isinstance(envelope, dict) else {}
            usage = usage if isinstance(usage, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            usage = {}

        self.records.append({
            "kind": self._call_kind.get(),
            "model": self.model,
            "status_code": status_code,
            "input_tokens": _usage_int(usage, "prompt_tokens"),
            "output_tokens": _usage_int(usage, "completion_tokens"),
            "total_tokens": _usage_int(usage, "total_tokens"),
            "cached_input_tokens": _usage_int(usage, "prompt_cache_hit_tokens"),
            "latency_ms": latency_ms,
        })

        if self._hold_first_successful_response and not self._held_response:
            self._held_response = True
            self.response_ready.set()
            await self.release_response.wait()

        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in {"content-length", "content-encoding", "transfer-encoding"}
        }
        return httpx.Response(
            status_code,
            headers=headers,
            content=body,
            request=request,
        )

    async def aclose(self) -> None:
        # _post_review creates a short-lived AsyncClient per call. Keep the
        # shared transport alive until the qualification test explicitly closes it.
        return None

    async def close(self) -> None:
        await self._inner_transport.aclose()


def percentile(values: Iterable[int | float], quantile: float) -> int | None:
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(int(value) for value in values if value is not None)
    if not ordered:
        return None
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize_model_calls(
    calls: Iterable[dict[str, Any]],
    cost_rate_microusd_per_1k_tokens: int,
) -> dict[str, Any]:
    items = [dict(item) for item in calls]
    successful = [item for item in items if item.get("status_code") == 200]
    token_values = [
        item.get("total_tokens")
        for item in successful
        if isinstance(item.get("total_tokens"), int)
        and not isinstance(item.get("total_tokens"), bool)
        and item["total_tokens"] >= 0
    ]
    token_usage_complete = bool(successful) and len(token_values) == len(successful)
    total_tokens = sum(token_values) if token_usage_complete else None
    rate = max(0, int(cost_rate_microusd_per_1k_tokens))
    estimated_cost = (
        (total_tokens * rate + 999) // 1000
        if total_tokens is not None and rate > 0
        else None
    )
    latencies = [
        item["latency_ms"]
        for item in items
        if isinstance(item.get("latency_ms"), int) and item["latency_ms"] >= 0
    ]
    safe_calls = [
        {
            "kind": item.get("kind", "unknown"),
            "model": item.get("model"),
            "status_code": item.get("status_code"),
            "input_tokens": item.get("input_tokens"),
            "output_tokens": item.get("output_tokens"),
            "total_tokens": item.get("total_tokens"),
            "cached_input_tokens": item.get("cached_input_tokens"),
            "latency_ms": item.get("latency_ms"),
        }
        for item in items
    ]
    return {
        "model_call_count": len(items),
        "successful_model_call_count": len(successful),
        "failed_model_call_count": len(items) - len(successful),
        "token_usage_complete": token_usage_complete,
        "total_tokens": total_tokens,
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "max_latency_ms": max(latencies) if latencies else None,
        "cost_rate_microusd_per_1k_tokens": rate,
        "cost_rate_basis": (
            "operator-configured blended effective rate; estimate, not provider invoice"
        ),
        "estimated_cost_microusd": estimated_cost,
        "provider_calls": safe_calls,
    }


def require_live_configuration(environ: dict[str, str]) -> dict[str, Any]:
    api_key = str(environ.get("DEEPSEEK_API_KEY", "")).strip()
    model = str(environ.get("DEEPSEEK_MODEL", "deepseek-flash")).strip()
    source_revision = str(
        environ.get("GITHUB_SHA")
        or environ.get("SHUDDHO_SOURCE_REVISION")
        or ""
    ).strip().lower()
    try:
        cost_rate = int(
            environ.get("SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS", "0")
        )
    except (TypeError, ValueError):
        cost_rate = 0

    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY must be configured as a protected workflow secret.")
    if not model:
        raise ValueError("DEEPSEEK_MODEL must identify the model used for qualification.")
    if len(source_revision) != 40 or any(char not in "0123456789abcdef" for char in source_revision):
        raise ValueError("GITHUB_SHA or SHUDDHO_SOURCE_REVISION must be a full 40-character commit SHA.")
    if cost_rate <= 0:
        raise ValueError(
            "SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS must be a reviewed positive integer; "
            "zero would make cost evidence misleading."
        )
    return {
        "api_key": api_key,
        "model": model,
        "source_revision": source_revision,
        "cost_rate_microusd_per_1k_tokens": cost_rate,
    }


def write_evidence(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    if destination.exists():
        try:
            previous = json.loads(destination.read_text(encoding="utf-8"))
            if isinstance(previous, list):
                rows = previous
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Existing Runtime v3 evidence is unreadable; refusing to overwrite it.") from error
    rows.append({
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    })
    destination.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run opt-in live DeepSeek + Temporal Agent Runtime v3 qualification."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/runtime-v3-live-qualification.json"),
    )
    args = parser.parse_args()

    try:
        require_live_configuration(dict(os.environ))
        import temporalio  # noqa: F401
        import pytest
    except (ValueError, ImportError) as error:
        parser.error(str(error))

    os.environ["SHUDDHO_RUNTIME_V3_LIVE_QUALIFICATION"] = "true"
    os.environ["SHUDDHO_RUNTIME_V3_EVIDENCE_PATH"] = str(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    junit_path = args.output.with_suffix(".junit.xml")
    result = pytest.main([
        "tests/test_runtime_v3_live_qualification.py",
        "-q",
        "-rs",
        f"--junitxml={junit_path}",
    ])
    raise SystemExit(int(result))


if __name__ == "__main__":
    main()
