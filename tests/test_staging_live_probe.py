import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("temporalio")

from scripts import staging_live_probe as probe


def test_status_helpers_do_not_expose_secret_values():
    assert probe.passed("ok") == {"status": "passed", "evidence": "ok"}
    assert probe.partial("needs manual check")["status"] == "partial"
    assert probe.failed("boom")["status"] == "failed"


def test_storage_probe_requires_cleanup(monkeypatch):
    calls = []

    class Store:
        def __init__(self, _settings):
            pass

        def put(self, key, data, content_type):
            calls.append(("put", content_type))

        def get(self, key, max_bytes):
            calls.append(("get", max_bytes))
            return b"shuddho-staging-probe"

        def delete(self, key):
            calls.append(("delete", None))
            raise RuntimeError("provider body must not leak")

    monkeypatch.setattr(probe, "S3ObjectStore", Store)
    result = probe.probe_storage(SimpleNamespace())
    assert result["status"] == "failed"
    assert result["evidence"] == "private object storage cleanup failed: RuntimeError"
    assert [item[0] for item in calls] == ["put", "get", "delete"]


def test_collect_marks_connectivity_only_checks_partial(monkeypatch):
    async def identity(_settings):
        return probe.partial("identity connectivity")

    def database(_settings):
        return probe.passed("database tls and migrations")

    def storage(_settings):
        return probe.partial("storage connectivity")

    async def temporal(_settings):
        return probe.partial("temporal connectivity")

    monkeypatch.setattr(probe, "probe_identity", identity)
    monkeypatch.setattr(probe, "probe_database", database)
    monkeypatch.setattr(probe, "probe_storage", storage)
    monkeypatch.setattr(probe, "probe_temporal", temporal)

    result = asyncio.run(probe.collect(SimpleNamespace(), live_model=False, cases=Path("unused")))
    assert result["identity"]["status"] == "partial"
    assert result["database"]["status"] == "passed"
    assert result["storage"]["status"] == "partial"
    assert result["temporal"]["status"] == "partial"
    assert "model" not in result


def test_live_model_probe_requires_full_eval_pass(monkeypatch):
    settings = SimpleNamespace(deepseek_api_key="secret")

    def cases(_path):
        return [{"id": "x"}]

    async def eval_live(_cases):
        return {"pass_rate": 0.5, "passed": 1, "cases": 2}

    monkeypatch.setattr(probe, "load_cases", cases)
    monkeypatch.setattr(probe, "evaluate_live", eval_live)
    result = asyncio.run(probe.probe_model(settings, Path("cases.jsonl")))
    assert result["status"] == "failed"
    assert "pass_rate=0.5" in result["evidence"]
