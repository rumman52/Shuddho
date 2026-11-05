"""Run all local acceptance services in one isolated network namespace."""
import os
from pathlib import Path
import subprocess
import time
import tempfile
import urllib.request

root = Path(__file__).resolve().parents[3]
folder = Path(os.environ.get("SHUDDHO_TEST_WORKDIR", "/tmp/rukh-design-check"))
folder.mkdir(parents=True, exist_ok=True)
folder = Path(tempfile.mkdtemp(prefix="run-", dir=folder))
env = {**os.environ, "SHUDDHO_BROWSER_TESTS": "true", "SHUDDHO_TEST_WORKDIR": str(folder), "PYTHONPATH": str(root),
       "VITE_COWORKER_ENABLED": "true", "VITE_SUPABASE_URL": "https://identity.example.test", "VITE_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_fixture_only",
       "VITE_COWORKER_API_BASE_URL": "http://127.0.0.1:8000"}
processes = []
try:
    for name, command in [
        ("api", ["uv", "run", "--extra", "coworker", "python", "tests/coworker_design_server.py"]),
        ("frontend", ["npm", "run", "dev", "--workspace", "@shuddho/web-editor", "--", "--host", "127.0.0.1", "--port", "5174", "--strictPort"]),
    ]:
        output = open(folder / (name + ".log"), "w")
        processes.append(subprocess.Popen(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True))
    for url in ["http://127.0.0.1:5174/coworker", "http://127.0.0.1:8000/openapi.json"]:
        for _ in range(100):
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("Fixture exited; inspect logs in " + str(folder))
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    if response.status == 200: break
            except Exception:
                time.sleep(.2)
        else: raise RuntimeError("Fixture startup timed out for " + url)
    result = subprocess.run(["node", "apps/web-editor/test/coworker-design-browser.mjs"], cwd=root, env=env)
    raise SystemExit(result.returncode)
finally:
    import signal
    for process in processes:
        if process.poll() is None: os.killpg(process.pid, signal.SIGTERM)
    for process in processes:
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL)
