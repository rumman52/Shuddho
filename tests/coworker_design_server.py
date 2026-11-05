"""Local-only design acceptance fixture. Identity/model are synthetic test data.

Exercises real API ownership, database, streaming and private file storage. It
never contacts an AI provider or starts external actions. Not deployed/shipped.
"""
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.coworker.api import mount
from services.coworker.auth import JwtVerifier
from services.coworker.config import Settings
from services.coworker.container import Container
from services.coworker.conversation_replies import ConversationReplyService
from services.coworker.migrate import upgrade

if os.environ.get("SHUDDHO_BROWSER_TESTS") != "true":
    raise RuntimeError("Local test fixture requires SHUDDHO_BROWSER_TESTS=true")
folder = Path(os.environ["SHUDDHO_TEST_WORKDIR"])
folder.mkdir(parents=True, exist_ok=True)
issuer = "https://identity.example.test/auth/v1"
settings = Settings(database_url=f"sqlite:///{folder / 'design.sqlite3'}", auth_issuer=issuer,
                    environment="development", storage_backend="local", local_storage_path=folder / "files",
                    projects_enabled=True, conversations_enabled=True, conversation_replies_enabled=True, deepseek_api_key="fixture-only")
upgrade(settings.database_url)
container = Container.create(settings)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True) | {"kid": "design-test", "alg": "RS256"}
container.verifier = JwtVerifier(issuer, "authenticated", httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [jwk]})))
now = int(time.time())
sessions = {}
for subject in ["alice", "bob"]:
    user = {"id": subject, "aud": "authenticated", "role": "authenticated", "email": subject + "@example.test",
            "app_metadata": {"provider": "email"}, "user_metadata": {}, "created_at": "2026-11-05T00:00:00Z"}
    token = jwt.encode({"iss": issuer, "sub": subject, "aud": "authenticated", "role": "authenticated", "iat": now, "exp": now + 3600},
                       key, algorithm="RS256", headers={"kid": "design-test"})
    sessions[subject] = {"access_token": token, "refresh_token": "fixture-refresh-" + subject, "token_type": "bearer", "expires_in": 3600, "expires_at": now + 3600, "user": user}
(folder / "sessions.json").write_text(json.dumps(sessions))
(folder / "sessions.json").chmod(0o600)


class SyntheticModel:
    async def stream(self, history):
        for chunk in ["Synthetic browser-test reply. ", "বাংলা লেখা সংরক্ষিত থাকে।"]:
            await asyncio.sleep(.1)
            yield chunk

container.conversation_replies = ConversationReplyService(container.conversations, settings, SyntheticModel())
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5174"], allow_methods=["*"], allow_headers=["*"])
mount(app, container)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
