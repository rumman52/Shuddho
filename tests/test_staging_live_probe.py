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


def test_temporal_probe_requires_workflow_and_activity_pollers(monkeypatch):
    settings = SimpleNamespace(
        temporal_address="example:7233",
        temporal_namespace="staging",
        temporal_api_key="secret",
        temporal_tls=True,
        task_queue="shuddho-documents-v1",
    )

    class WorkflowService:
        def __init__(self, counts):
            self.counts = iter(counts)

        async def describe_task_queue(self, _request, timeout=None):
            assert timeout is not None
            return SimpleNamespace(pollers=[object()] * next(self.counts))

    class FakeClient:
        def __init__(self, counts):
            self.workflow_service = WorkflowService(counts)

    async def connect(*_args, **_kwargs):
        return FakeClient([1, 0])

    monkeypatch.setattr(probe.Client, "connect", connect)
    result = asyncio.run(probe.probe_temporal(settings))
    assert result["status"] == "failed"
    assert "activity" in result["evidence"]
    assert "workflow_pollers=1" in result["evidence"]
    assert "activity_pollers=0" in result["evidence"]


def test_temporal_probe_records_live_worker_pollers_as_partial(monkeypatch):
    settings = SimpleNamespace(
        temporal_address="example:7233",
        temporal_namespace="staging",
        temporal_api_key="secret",
        temporal_tls=True,
        task_queue="shuddho-documents-v1",
    )

    class WorkflowService:
        def __init__(self):
            self.counts = iter([2, 3])

        async def describe_task_queue(self, request, timeout=None):
            assert request.namespace == "staging"
            assert request.task_queue.name == "shuddho-documents-v1"
            assert timeout is not None
            return SimpleNamespace(pollers=[object()] * next(self.counts))

    class FakeClient:
        workflow_service = WorkflowService()

    async def connect(*_args, **_kwargs):
        return FakeClient()

    monkeypatch.setattr(probe.Client, "connect", connect)
    result = asyncio.run(probe.probe_temporal(settings))
    assert result["status"] == "partial"
    assert "workflow_pollers=2" in result["evidence"]
    assert "activity_pollers=3" in result["evidence"]
    assert "restart/replay" in result["evidence"]


def test_storage_privacy_requires_anonymous_read_and_list_denial(monkeypatch):
    from botocore.exceptions import ClientError

    settings = SimpleNamespace(
        storage_bucket="shuddho-coworker-staging",
        storage_endpoint="https://storage.example.test/storage/v1/s3",
        storage_region="us-west-1",
    )

    class Client:
        def get_object(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {"Code": "AccessDenied", "Message": "denied"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "GetObject",
            )

        def list_objects_v2(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {"Code": "AccessDenied", "Message": "denied"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "ListObjectsV2",
            )

    monkeypatch.setattr(probe, "anonymous_s3_client", lambda _settings: Client())

    result = probe.probe_storage_privacy(settings, "staging-probes/probe.txt")
    assert result["status"] == "passed"
    assert "anonymous object read" in result["evidence"]
    assert "bucket listing" in result["evidence"]


def test_storage_privacy_fails_if_anonymous_object_read_succeeds(monkeypatch):
    settings = SimpleNamespace(
        storage_bucket="shuddho-coworker-staging",
        storage_endpoint="https://storage.example.test/storage/v1/s3",
        storage_region="us-west-1",
    )

    class Body:
        def close(self):
            pass

    class Client:
        def get_object(self, **_kwargs):
            return {"Body": Body()}

        def list_objects_v2(self, **_kwargs):
            raise AssertionError("listing should not be reached after public object read")

    monkeypatch.setattr(probe, "anonymous_s3_client", lambda _settings: Client())

    result = probe.probe_storage_privacy(settings, "staging-probes/probe.txt")
    assert result["status"] == "failed"
    assert "publicly accessible" in result["evidence"]
    assert "object read" in result["evidence"]


def test_storage_privacy_fails_if_anonymous_bucket_listing_succeeds(monkeypatch):
    from botocore.exceptions import ClientError

    settings = SimpleNamespace(
        storage_bucket="shuddho-coworker-staging",
        storage_endpoint="https://storage.example.test/storage/v1/s3",
        storage_region="us-west-1",
    )

    class Client:
        def get_object(self, **_kwargs):
            raise ClientError(
                {
                    "Error": {"Code": "AccessDenied", "Message": "denied"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "GetObject",
            )

        def list_objects_v2(self, **_kwargs):
            return {"Contents": []}

    monkeypatch.setattr(probe, "anonymous_s3_client", lambda _settings: Client())

    result = probe.probe_storage_privacy(settings, "staging-probes/probe.txt")
    assert result["status"] == "failed"
    assert "publicly accessible" in result["evidence"]
    assert "bucket listing" in result["evidence"]


def test_storage_cleanup_failure_overrides_privacy_probe_failure(monkeypatch):
    calls = []

    class Store:
        def __init__(self, _settings):
            pass

        def put(self, key, data, content_type):
            calls.append(("put", key, content_type))

        def get(self, key, max_bytes):
            calls.append(("get", key, max_bytes))
            return b"shuddho-staging-probe"

        def delete(self, key):
            calls.append(("delete", key))
            raise RuntimeError("cleanup failed")

    monkeypatch.setattr(probe, "S3ObjectStore", Store)
    monkeypatch.setattr(
        probe,
        "probe_storage_privacy",
        lambda _settings, _key: probe.failed("privacy probe failed first"),
    )

    result = probe.probe_storage(SimpleNamespace())
    assert result == {
        "status": "failed",
        "evidence": "private object storage cleanup failed: RuntimeError",
    }
    assert [item[0] for item in calls] == ["put", "get", "delete"]
