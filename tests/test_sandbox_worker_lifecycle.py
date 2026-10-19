"""Real local subprocess supervision; namespace isolation is not claimed here."""
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import pytest

from scripts import sandbox_worker as worker


def claim(source, *, wall=5):
    return {
        "id": "lifecycle-execution", "runtime": "python311", "purpose": "code_task",
        "source": source, "source_bytes": len(source.encode()),
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "policy": {
            "version": "sandbox-control-v1", "network": "none", "dependencies": [],
            "mounts": [], "host_filesystem": False, "docker_socket": False,
            "production_secrets": False, "connector_credentials": False,
            "privileged_api_bridge": False,
            "resource_limits": {"wall_seconds": wall, "cpu_seconds": 1,
                                "memory_mb": 256, "disk_mb": 16, "output_bytes": 1024},
            "artifacts": {"interactive_html": {"path": "/tmp/shuddho-preview.html",
                "content_type": "text/html; charset=utf-8", "max_bytes": 4096}},
            "executor": {"contract": "bwrap-python311-v1", "network_namespace": "private_empty",
                "filesystem": "minimal_readonly_runtime", "environment": "cleared", "packages": "stdlib_only"},
        },
    }


def local_command(monkeypatch):
    paths = {}

    def build(source_path, scratch_path, *_args, **_kwargs):
        paths.update(source=source_path, scratch=scratch_path)
        # Replace only namespace launch; use the real Popen, limits and cleanup.
        return [sys.executable, "-I", "-S", str(source_path)]

    monkeypatch.setattr(worker, "build_bwrap_command", build)
    return paths


@pytest.mark.parametrize("lose_response", [False, True])
def test_worker_removes_private_files_before_publishing_completion(monkeypatch, lose_response):
    paths = local_command(monkeypatch)
    completed = []

    class Client:
        def post(self, path, payload):
            if path.endswith("/control"):
                return {"action": "continue"}
            assert path.endswith("/complete")
            assert not paths["source"].parent.exists()
            assert not paths["scratch"].exists()
            assert payload["stdout"] == "bounded result\n"
            assert payload["sandbox_destroyed"] is True
            completed.append(payload)
            if lose_response:
                raise worker.WorkerError("sandbox_worker_api_unavailable")
            return {"state": "succeeded"}

    if lose_response:
        with pytest.raises(worker.WorkerError, match="sandbox_worker_api_unavailable"):
            worker.execute_claim(Client(), "worker", claim("print('bounded result')\n"), "/usr/bin/bwrap")
    else:
        worker.execute_claim(Client(), "worker", claim("print('bounded result')\n"), "/usr/bin/bwrap")
    assert len(completed) == 1


def test_worker_never_publishes_destruction_when_cleanup_fails(monkeypatch):
    paths = local_command(monkeypatch)
    original = tempfile.TemporaryDirectory

    class CleanupFailure(original):
        def __exit__(self, *args):
            if "scratch" in self.name:
                raise OSError("scratch cleanup denied")
            return super().__exit__(*args)

    monkeypatch.setattr(worker.tempfile, "TemporaryDirectory", CleanupFailure)
    completed = []

    class Client:
        def post(self, path, payload):
            if path.endswith("/control"):
                return {"action": "continue"}
            completed.append(payload)
            return {"state": "succeeded"}

    try:
        with pytest.raises(OSError, match="cleanup denied"):
            worker.execute_claim(Client(), "worker", claim("print(1)\n"), "/usr/bin/bwrap")
        assert completed == []
    finally:
        shutil.rmtree(paths["scratch"], ignore_errors=True)


def test_worker_wall_bound_survives_blocked_control_request(monkeypatch, tmp_path):
    local_command(monkeypatch)
    marker = tmp_path / "ran-after-wall-bound"
    source = f"import time\nfrom pathlib import Path\ntime.sleep(1.4)\nPath({str(marker)!r}).write_text('late')\ntime.sleep(10)\n"
    completed = []

    class Client:
        def post(self, path, payload):
            if path.endswith("/control"):
                time.sleep(2.0)
                return {"action": "continue"}
            completed.append(payload)
            return {}

    with pytest.raises(worker.WorkerError, match="sandbox_timeout"):
        worker.execute_claim(Client(), "worker", claim(source, wall=1), "/usr/bin/bwrap")
    assert not marker.exists(), "The code ran beyond its reviewed one-second wall bound"
    assert completed == []


def test_worker_kills_live_process_on_unexpected_supervisor_failure(monkeypatch):
    local_command(monkeypatch)
    original_spawn = subprocess.Popen
    children = []

    def spawn(*args, **kwargs):
        process = original_spawn(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(worker.subprocess, "Popen", spawn)

    class Client:
        def post(self, path, payload):
            raise RuntimeError("unexpected control transport failure")

    try:
        with pytest.raises(RuntimeError, match="unexpected control"):
            worker.execute_claim(Client(), "worker", claim("import time\ntime.sleep(10)\n"), "/usr/bin/bwrap")
        assert children[0].poll() is not None, "Supervisor failure left untrusted code alive"
    finally:
        for process in children:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)


def test_worker_watchdog_inspection_exception_stops_code_during_control(monkeypatch, tmp_path):
    import threading

    local_command(monkeypatch)
    marker = tmp_path / "ran-after-watchdog-failure"
    original_size = worker.directory_size

    def inspect(path, limit):
        if threading.current_thread() is not threading.main_thread():
            # Python 3.11 can raise this walking a deeply nested legal tree.
            raise RecursionError("untrusted scratch nesting")
        return original_size(path, limit)

    monkeypatch.setattr(worker, "directory_size", inspect)
    source = f"import time\nfrom pathlib import Path\ntime.sleep(0.4)\nPath({str(marker)!r}).write_text('late')\ntime.sleep(10)\n"

    class Client:
        def post(self, path, payload):
            assert path.endswith("/control"), "A failed watchdog cannot publish completion"
            time.sleep(0.8)
            return {"action": "continue"}

    with pytest.raises(worker.WorkerError, match="sandbox_resource_limit"):
        worker.execute_claim(Client(), "worker", claim(source, wall=1), "/usr/bin/bwrap")
    assert not marker.exists(), "A failed watchdog left untrusted code running"
