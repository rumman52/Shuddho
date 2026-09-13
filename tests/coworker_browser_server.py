"""Local-only browser fixture: real auth verification, DB, Temporal and exports.

The identity and model responses are test fixtures. This file is excluded from
the Docker image and must never be installed as a deployed service.
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from temporalio.testing import WorkflowEnvironment

from test_coworker import FakeModel, draft
from test_coworker_temporal import make_worker
from services.coworker.api import mount
from services.coworker.auth import JwtVerifier
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.drafting import DraftResult
from services.coworker.migrate import upgrade
from services.coworker.runner import DocumentRunner
from services.coworker.worker import Dispatcher

if os.getenv("SHUDDHO_BROWSER_TESTS") != "true":
    raise RuntimeError("This fixture requires SHUDDHO_BROWSER_TESTS=true")
folder = Path(os.environ["SHUDDHO_TEST_WORKDIR"])
folder.mkdir(parents=True, exist_ok=True)
issuer = "https://identity.example.test/auth/v1"
settings = Settings(database_url=f"sqlite:///{folder / 'browser.sqlite3'}", auth_issuer=issuer,
                    environment="development", storage_backend="local", local_storage_path=folder / "files")
upgrade(settings.database_url)
container = Container.create(settings)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": "browser-test", "alg": "RS256"}
container.verifier = JwtVerifier(issuer, "authenticated", httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [jwk]})))
now = int(time.time())
sessions = {}
for subject in ["alice", "bob"]:
    user = {"id": subject, "aud": "authenticated", "role": "authenticated", "email": subject + "@example.test",
            "app_metadata": {"provider": "email"}, "user_metadata": {}, "created_at": "2026-09-13T00:00:00Z"}
    token = jwt.encode({"iss": issuer, "sub": subject, "aud": "authenticated", "role": "authenticated", "iat": now, "exp": now + 3600},
                       key, algorithm="RS256", headers={"kid": "browser-test"})
    sessions[subject] = {"access_token": token, "refresh_token": "test-only-refresh-" + subject, "token_type": "bearer", "expires_in": 3600, "expires_at": now + 3600, "user": user}
(folder / "sessions.json").write_text(json.dumps(sessions))
(folder / "sessions.json").chmod(0o600)


class BrowserModel(FakeModel):
    async def generate(self, _messages, language, source_ids):
        await asyncio.sleep(2)  # Exercise progress, navigation and refresh.
        value = draft(language)
        value.report.sections[0].source_ids = sorted(source_ids)
        return DraftResult(value, 180, 2000)


@asynccontextmanager
async def lifespan(_app):
    async with await WorkflowEnvironment.start_time_skipping() as env:
        stop = asyncio.Event()
        async with make_worker(env, DocumentRunner(container, BrowserModel())):
            dispatcher = asyncio.create_task(Dispatcher(container, env.client).run(stop))
            try:
                yield
            finally:
                stop.set()
                await dispatcher


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
mount(app, container)


@app.get("/health")
def health():
    return {"status": "ok", "fixture": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
