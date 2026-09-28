from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import resource
import shutil
import stat
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


POLICY_VERSION = "sandbox-control-v1"
EXECUTOR_CONTRACT = "bwrap-python311-v1"
POLL_SECONDS = 1.0
CONTROL_SECONDS = 1.0
WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


class WorkerError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normalized_base_url(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (
        not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.scheme not in ({"https"} | ({"http"} if loopback else set()))
    ):
        raise WorkerError("sandbox_worker_api_origin_invalid")
    return value.rstrip("/")


def safe_worker_id(value: str) -> str:
    if not WORKER_ID_PATTERN.fullmatch(value):
        raise WorkerError("sandbox_worker_id_invalid")
    return value


def validate_claim_policy(claim: dict) -> dict:
    policy = claim.get("policy")
    if not isinstance(policy, dict):
        raise WorkerError("sandbox_policy_invalid")
    executor = policy.get("executor")
    limits = policy.get("resource_limits")
    if (
        policy.get("version") != POLICY_VERSION
        or policy.get("network") != "none"
        or policy.get("dependencies") != []
        or policy.get("mounts") != []
        or policy.get("host_filesystem") is not False
        or policy.get("docker_socket") is not False
        or policy.get("production_secrets") is not False
        or policy.get("connector_credentials") is not False
        or policy.get("privileged_api_bridge") is not False
        or not isinstance(executor, dict)
        or executor.get("contract") != EXECUTOR_CONTRACT
        or executor.get("network_namespace") != "private_empty"
        or executor.get("filesystem") != "minimal_readonly_runtime"
        or executor.get("environment") != "cleared"
        or executor.get("packages") != "stdlib_only"
        or not isinstance(limits, dict)
    ):
        raise WorkerError("sandbox_policy_invalid")
    required = {"wall_seconds", "cpu_seconds", "memory_mb", "disk_mb", "output_bytes"}
    artifacts = policy.get("artifacts")
    if (
        set(limits) != required
        or not isinstance(artifacts, dict)
        or artifacts.get("interactive_html") != {
            "path": "/tmp/shuddho-preview.html",
            "content_type": "text/html; charset=utf-8",
            "max_bytes": artifacts.get("interactive_html", {}).get("max_bytes")
            if isinstance(artifacts.get("interactive_html"), dict)
            else None,
        }
        or not isinstance(artifacts["interactive_html"]["max_bytes"], int)
        or not 4096 <= artifacts["interactive_html"]["max_bytes"] <= 65536
    ):
        raise WorkerError("sandbox_policy_invalid")
    wall = limits["wall_seconds"]
    cpu = limits["cpu_seconds"]
    memory = limits["memory_mb"]
    disk = limits["disk_mb"]
    output = limits["output_bytes"]
    if not (
        isinstance(wall, int)
        and isinstance(cpu, int)
        and isinstance(memory, int)
        and isinstance(disk, int)
        and isinstance(output, int)
        and 1 <= cpu <= wall <= 120
        and 64 <= memory <= 1024
        and 16 <= disk <= 512
        and 1024 <= output <= 262144
    ):
        raise WorkerError("sandbox_policy_invalid")
    return policy


def build_bwrap_command(
    source_path: Path,
    scratch_path: Path,
    policy: dict,
    *,
    bwrap_path: str = "/usr/bin/bwrap",
    python_executable: str = sys.executable,
) -> list[str]:
    validate_claim_policy({"policy": policy})
    source = source_path.resolve()
    scratch = scratch_path.resolve()
    if not source.is_file():
        raise WorkerError("sandbox_source_missing")
    if not scratch.is_dir():
        raise WorkerError("sandbox_scratch_missing")
    if not os.path.isabs(bwrap_path) or not os.path.isabs(python_executable):
        raise WorkerError("sandbox_runner_path_invalid")
    return [
        bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-net",
        "--unshare-uts",
        "--cap-drop",
        "ALL",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--dir",
        "/usr",
        "--ro-bind",
        "/usr/local",
        "/usr/local",
        "--ro-bind-try",
        "/usr/lib",
        "/usr/lib",
        "--ro-bind-try",
        "/lib",
        "/lib",
        "--ro-bind-try",
        "/lib64",
        "/lib64",
        "--bind",
        str(scratch),
        "/tmp",
        "--dir",
        "/work",
        "--ro-bind",
        str(source),
        "/work/main.py",
        "--chdir",
        "/work",
        "--clearenv",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/local/bin",
        "--setenv",
        "PYTHONNOUSERSITE",
        "1",
        "--setenv",
        "PYTHONDONTWRITEBYTECODE",
        "1",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--",
        python_executable,
        "-I",
        "-S",
        "/work/main.py",
    ]


def resource_limiter(policy: dict):
    limits = policy["resource_limits"]
    cpu_seconds = int(limits["cpu_seconds"])
    memory_bytes = int(limits["memory_mb"]) * 1024 * 1024
    file_bytes = min(
        int(limits["disk_mb"]) * 1024 * 1024,
        int(limits["output_bytes"]),
    )

    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        if hasattr(resource, "RLIMIT_NPROC"):
            resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
        if hasattr(resource, "RLIMIT_CORE"):
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


class ApiClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = normalized_base_url(base_url)
        if len(token) < 32:
            raise WorkerError("sandbox_worker_token_invalid")
        self.token = token

    def post(self, path: str, payload: dict) -> dict:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=raw,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Shuddho-Sandbox-Worker-Token": self.token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read(1024 * 1024)
        except urllib.error.HTTPError as error:
            body = error.read(65536)
            try:
                value = json.loads(body.decode("utf-8"))
                code = value.get("error", {}).get("code")
            except Exception:
                code = None
            raise WorkerError(code or f"http_{error.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise WorkerError("sandbox_worker_api_unavailable") from None
        try:
            value = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WorkerError("sandbox_worker_api_invalid") from None
        if not isinstance(value, dict):
            raise WorkerError("sandbox_worker_api_invalid")
        return value


def terminate_group(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def read_bounded(handle, limit: int) -> bytes:
    handle.seek(0)
    value = handle.read(limit + 1)
    if len(value) > limit:
        raise WorkerError("sandbox_output_limit")
    return value


def read_artifact_file(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise WorkerError("sandbox_artifact_missing") from None
    except OSError:
        raise WorkerError("sandbox_artifact_invalid") from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size < 1
            or metadata.st_size > limit
        ):
            raise WorkerError("sandbox_artifact_invalid")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise WorkerError("sandbox_artifact_limit")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def directory_size(path: Path, limit: int) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except FileNotFoundError:
                continue
            if total > limit:
                return total
    return total


def execute_claim(client: ApiClient, worker_id: str, claim: dict, bwrap_path: str) -> None:
    policy = validate_claim_policy(claim)
    execution_id = claim.get("id")
    source = claim.get("source")
    expected_hash = claim.get("source_sha256")
    expected_bytes = claim.get("source_bytes")
    runtime = claim.get("runtime")
    purpose = claim.get("purpose")
    if (
        not isinstance(execution_id, str)
        or not isinstance(source, str)
        or not isinstance(expected_hash, str)
        or not isinstance(expected_bytes, int)
        or runtime != "python311"
        or purpose not in {"data_analysis", "code_task", "interactive_artifact"}
    ):
        raise WorkerError("sandbox_claim_invalid")
    source_bytes = source.encode("utf-8")
    if (
        len(source_bytes) != expected_bytes
        or hashlib.sha256(source_bytes).hexdigest() != expected_hash
    ):
        raise WorkerError("sandbox_source_integrity_failed")
    output_limit = int(policy["resource_limits"]["output_bytes"])
    wall_seconds = int(policy["resource_limits"]["wall_seconds"])
    disk_limit = int(policy["resource_limits"]["disk_mb"]) * 1024 * 1024

    with (
        tempfile.TemporaryDirectory(prefix="shuddho-sandbox-source-") as folder,
        tempfile.TemporaryDirectory(prefix="shuddho-sandbox-scratch-") as scratch_folder,
    ):
        source_path = Path(folder) / "main.py"
        scratch_path = Path(scratch_folder)
        source_path.write_bytes(source_bytes)
        source_path.chmod(0o400)
        command = build_bwrap_command(
            source_path,
            scratch_path,
            policy,
            bwrap_path=bwrap_path,
            python_executable=sys.executable,
        )
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            started = time.monotonic()
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                    preexec_fn=resource_limiter(policy),
                    start_new_session=True,
                    close_fds=True,
                )
            except (OSError, subprocess.SubprocessError):
                raise WorkerError("sandbox_runner_unavailable") from None

            next_control = started
            interrupted = None
            timed_out = False
            while process.poll() is None:
                now = time.monotonic()
                if now - started >= wall_seconds:
                    timed_out = True
                    terminate_group(process)
                    break
                if directory_size(scratch_path, disk_limit) > disk_limit:
                    terminate_group(process)
                    raise WorkerError("sandbox_resource_limit")
                if now >= next_control:
                    try:
                        control = client.post(
                            f"/api/v1/internal/sandbox-worker/executions/{execution_id}/control",
                            {"worker_id": worker_id},
                        )
                    except WorkerError as error:
                        if error.code == "sandbox_worker_claim_invalid":
                            interrupted = "claim_lost"
                            terminate_group(process)
                            break
                    else:
                        if control.get("action") == "stop":
                            interrupted = str(control.get("reason") or "worker_interrupted")
                            terminate_group(process)
                            break
                    next_control = now + CONTROL_SECONDS
                time.sleep(0.1)

            elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
            if timed_out:
                raise WorkerError("sandbox_timeout")
            if interrupted:
                raise WorkerError("worker_interrupted")

            return_code = process.wait()
            try:
                stdout_raw = read_bounded(stdout_file, output_limit)
                stderr_raw = read_bounded(stderr_file, output_limit)
            except WorkerError:
                raise
            if return_code == -getattr(signal, "SIGXFSZ", 25):
                raise WorkerError("sandbox_output_limit")
            if return_code in {
                -getattr(signal, "SIGKILL", 9),
                -getattr(signal, "SIGSEGV", 11),
            }:
                raise WorkerError("sandbox_resource_limit")

            stdout = stdout_raw.decode("utf-8", errors="replace")
            stderr = stderr_raw.decode("utf-8", errors="replace")
            artifact = None
            if return_code == 0 and purpose == "interactive_artifact":
                artifact_limit = int(policy["artifacts"]["interactive_html"]["max_bytes"])
                artifact_body = read_artifact_file(
                    scratch_path / "shuddho-preview.html",
                    artifact_limit,
                )
                artifact = {
                    "kind": "interactive_html",
                    "body_b64": base64.b64encode(artifact_body).decode("ascii"),
                    "sha256": hashlib.sha256(artifact_body).hexdigest(),
                    "byte_size": len(artifact_body),
                }
            client.post(
                f"/api/v1/internal/sandbox-worker/executions/{execution_id}/complete",
                {
                    "worker_id": worker_id,
                    "policy_version": POLICY_VERSION,
                    "executor_contract": EXECUTOR_CONTRACT,
                    "exit_code": return_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "elapsed_ms": elapsed_ms,
                    "sandbox_destroyed": True,
                    "network_isolated": True,
                    "filesystem_isolated": True,
                    "environment_sanitized": True,
                    "artifact": artifact,
                },
            )


def main() -> int:
    try:
        api_base = os.environ.get("SHUDDHO_SANDBOX_API_BASE_URL", "")
        token = os.environ.get("SHUDDHO_SANDBOX_WORKER_TOKEN", "")
        worker_id = safe_worker_id(
            os.environ.get("SHUDDHO_SANDBOX_WORKER_ID")
            or f"sandbox-{os.uname().nodename[:48]}"
        )
        bwrap_path = os.environ.get("SHUDDHO_SANDBOX_BWRAP_PATH", "/usr/bin/bwrap")
        if not os.path.isabs(bwrap_path) or shutil.which(bwrap_path) != bwrap_path:
            raise WorkerError("sandbox_runner_unavailable")
        client = ApiClient(api_base, token)
    except WorkerError as error:
        sys.stderr.write(f"Sandbox worker startup refused: {error.code}\n")
        return 1

    while True:
        try:
            value = client.post(
                "/api/v1/internal/sandbox-worker/claim",
                {"worker_id": worker_id, "limit": 1},
            )
            execution = (value.get("executions") or [None])[0]
            if execution:
                try:
                    execute_claim(client, worker_id, execution, bwrap_path)
                except WorkerError as error:
                    try:
                        client.post(
                            f"/api/v1/internal/sandbox-worker/executions/{execution['id']}/fail",
                            {
                                "worker_id": worker_id,
                                "error_code": error.code
                                if error.code
                                in {
                                    "sandbox_timeout",
                                    "sandbox_output_limit",
                                    "sandbox_resource_limit",
                                    "sandbox_runner_unavailable",
                                    "sandbox_policy_invalid",
                                    "sandbox_source_integrity_failed",
                                    "sandbox_artifact_missing",
                                    "sandbox_artifact_invalid",
                                    "sandbox_artifact_unsafe",
                                    "sandbox_artifact_limit",
                                    "sandbox_artifact_encoding",
                                    "sandbox_artifact_integrity_failed",
                                    "worker_interrupted",
                                }
                                else "sandbox_execution_failed",
                                "sandbox_destroyed": True,
                            },
                        )
                    except (WorkerError, KeyError):
                        pass
            else:
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            return 0
        except WorkerError as error:
            if error.code in {
                "sandbox_worker_unauthorized",
                "sandbox_worker_api_origin_invalid",
                "sandbox_worker_token_invalid",
            }:
                sys.stderr.write("Sandbox worker authentication or policy check failed; refusing to continue.\n")
                return 1
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
