import asyncio
import json
from pathlib import Path

import httpx
import pytest

from scripts.runtime_v3_qualification import (
    RecordingTransport,
    percentile,
    require_live_configuration,
    summarize_model_calls,
    write_evidence,
)


def test_percentile_uses_nearest_rank_and_handles_empty_values():
    assert percentile([], 0.95) is None
    assert percentile([100, 20, 40, 80], 0.50) == 40
    assert percentile([100, 20, 40, 80], 0.95) == 100


def test_model_call_summary_requires_usage_and_calculates_estimated_cost():
    summary = summarize_model_calls(
        [
            {
                "kind": "planner",
                "model": "deepseek-test",
                "status_code": 200,
                "input_tokens": 80,
                "output_tokens": 20,
                "total_tokens": 100,
                "latency_ms": 40,
            },
            {
                "kind": "draft",
                "model": "deepseek-test",
                "status_code": 200,
                "input_tokens": 200,
                "output_tokens": 100,
                "total_tokens": 300,
                "latency_ms": 120,
            },
        ],
        cost_rate_microusd_per_1k_tokens=2000,
    )
    assert summary["model_call_count"] == 2
    assert summary["successful_model_call_count"] == 2
    assert summary["total_tokens"] == 400
    assert summary["p50_latency_ms"] == 40
    assert summary["p95_latency_ms"] == 120
    assert summary["estimated_cost_microusd"] == 800
    assert summary["token_usage_complete"] is True
    assert "not provider invoice" in summary["cost_rate_basis"]


def test_model_call_summary_does_not_turn_missing_usage_into_zero_cost():
    summary = summarize_model_calls(
        [{"kind": "planner", "status_code": 200, "total_tokens": None, "latency_ms": 10}],
        cost_rate_microusd_per_1k_tokens=2000,
    )
    assert summary["token_usage_complete"] is False
    assert summary["total_tokens"] is None
    assert summary["estimated_cost_microusd"] is None


def test_live_configuration_fails_closed_without_secret_sha_or_reviewed_rate():
    base = {
        "DEEPSEEK_API_KEY": "test-only-secret",
        "DEEPSEEK_MODEL": "deepseek-test",
        "GITHUB_SHA": "a" * 40,
        "SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS": "2000",
    }
    config = require_live_configuration(base)
    assert config["model"] == "deepseek-test"
    assert config["source_revision"] == "a" * 40
    assert config["cost_rate_microusd_per_1k_tokens"] == 2000
    assert config["api_key"] == "test-only-secret"

    for changes in (
        {"DEEPSEEK_API_KEY": ""},
        {"GITHUB_SHA": "short"},
        {"SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS": "0"},
        {"SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS": "unknown"},
    ):
        with pytest.raises(ValueError):
            require_live_configuration(base | changes)


def test_recording_transport_keeps_only_usage_metadata_not_model_text():
    async def scenario():
        private_output = "PRIVATE_SYNTHETIC_MODEL_OUTPUT"

        async def respond(request):
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": private_output}}],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 7,
                        "total_tokens": 19,
                        "prompt_cache_hit_tokens": 2,
                    },
                },
                request=request,
            )

        transport = RecordingTransport(
            model="deepseek-test",
            inner_transport=httpx.MockTransport(respond),
        )
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                with transport.measure_as("planner"):
                    response = await client.post(
                        "https://api.deepseek.com/chat/completions",
                        json={"model": "deepseek-test"},
                    )
                assert response.status_code == 200
                assert private_output in response.text
            encoded = json.dumps(transport.records)
            assert private_output not in encoded
            assert len(transport.records) == 1
            record = transport.records[0]
            assert record["kind"] == "planner"
            assert record["model"] == "deepseek-test"
            assert record["input_tokens"] == 12
            assert record["output_tokens"] == 7
            assert record["total_tokens"] == 19
            assert record["cached_input_tokens"] == 2
        finally:
            await transport.close()

    asyncio.run(scenario())


def test_write_evidence_appends_versioned_rows_without_credentials(tmp_path):
    path = tmp_path / "evidence" / "runtime-v3.json"
    write_evidence(path, {"case_id": "en-multistep", "source_revision": "a" * 40})
    write_evidence(path, {"case_id": "bn-multistep", "source_revision": "b" * 40})
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert all(row["schema_version"] == 1 for row in rows)
    assert [row["case_id"] for row in rows] == ["en-multistep", "bn-multistep"]
    assert "api_key" not in json.dumps(rows).lower()


def test_live_temporal_module_is_syntactically_valid():
    path = Path(__file__).with_name("test_runtime_v3_live_qualification.py")
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
