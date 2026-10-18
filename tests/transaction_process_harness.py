"""CI-only crash harness. All provider traffic stays on loopback.

The counted provider lives outside the worker process and intentionally does
NOT deduplicate sends: a second submission must be visible to the tests.
Nothing here registers a provider or emits live/staging qualification evidence.
"""
from __future__ import annotations

import asyncio
import base64
import json
import multiprocessing
import socket
import threading
import time
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from services.coworker.action_repository import ActionRepository
from services.coworker.actions import ActionService
from services.coworker.credential_broker import CredentialBroker
from services.coworker.database import session_factory
from services.coworker.google_actions import GoogleActions, SCOPES, SEND_URL, TOKEN_URL, USERINFO_URL
from services.coworker.permission_gateway import PermissionGateway

BOUNDARIES = ("before_claim", "after_claim", "after_provider_apply", "after_receipt_commit")
CONTEXT = multiprocessing.get_context("spawn")


def require_disposable_database(sessions, *, postgres_required=False):
    engine = sessions.kw["bind"]
    if engine.dialect.name == "sqlite":
        if postgres_required:
            raise RuntimeError("Mandatory process qualification requires PostgreSQL")
        return
    url = make_url(engine.url)
    target_overrides = {
        "host", "hostaddr", "port", "service", "servicefile",
        "dbname", "user", "replication", "target_session_attrs",
        "load_balance_hosts",
    }
    if target_overrides & {str(key).lower() for key in url.query}:
        # This check intentionally runs before opening a connection or requesting
        # the shared repository fixture, whose setup may apply database migrations.
        raise RuntimeError("Refusing PostgreSQL target override for disposable process tests")
    if (engine.dialect.name != "postgresql" or url.host not in {"localhost", "127.0.0.1"}
            or url.database != "shuddho_coworker_test" or url.username != "shuddho_test"):
        raise RuntimeError("Process faults require the disposable loopback CI PostgreSQL database")
    from ipaddress import ip_address

    with engine.connect() as connection:
        info = connection.connection.driver_connection.info
        if info.host not in {"localhost", "127.0.0.1"}:
            raise RuntimeError("Refusing PostgreSQL test operation: effective host is not loopback")
        if info.hostaddr and not ip_address(info.hostaddr).is_loopback:
            raise RuntimeError("Refusing PostgreSQL test operation: effective hostaddr is not loopback")
        expected_port = url.port if url.port is not None else 5432
        if int(info.port) != expected_port:
            raise RuntimeError("Refusing PostgreSQL test operation: effective port differs from URL")
        if (info.dbname, info.user) != ("shuddho_coworker_test", "shuddho_test"):
            raise RuntimeError("Refusing PostgreSQL test operation: effective database or role differs")
        if connection.execute(text("SELECT current_database(), current_user")).one() != (
            "shuddho_coworker_test", "shuddho_test",
        ):
            raise RuntimeError("Refusing PostgreSQL test operation: connected database or role differs")


class LoopbackGoogleTransport(httpx.AsyncBaseTransport):
    """Exercise Google's actual adapter over TCP without contacting Google."""

    def __init__(self, origin):
        parsed = urlsplit(origin)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("Provider simulator must be a loopback origin")
        self.origin = origin

    async def handle_async_request(self, request):
        paths = {TOKEN_URL: "/token", USERINFO_URL: "/profile", SEND_URL: "/send"}
        path = paths.get(str(request.url))
        if path is None or (request.method, path) not in {
            ("POST", "/token"), ("GET", "/profile"), ("POST", "/send"),
        }:
            raise AssertionError("Unexpected provider operation in transaction crash test")
        async with httpx.AsyncClient(trust_env=False, timeout=20) as client:
            response = await client.request(
                request.method, self.origin + path,
                content=await request.aread(), headers=dict(request.headers),
            )
            return httpx.Response(response.status_code, content=response.content,
                                  headers=response.headers, request=request)


class CountedProvider:
    def __init__(self, *, fault="none", hold_after_apply=False):
        self.fault, self.hold_after_apply = fault, hold_after_apply
        self.lock = threading.Lock()
        self.applied = threading.Event()
        self.release = threading.Event()
        self.dispatch_count = 0
        self.mutation_count = 0
        self.action_ids = []
        counter = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass  # Never log OAuth headers or message contents.

            def reply(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The worker was intentionally killed.

            def do_GET(self):
                assert self.path == "/profile"
                self.reply(200, {"sub": "simulated-google-subject", "email": "alice@example.test",
                                 "email_verified": True})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path == "/token":
                    self.reply(200, {"token_type": "Bearer", "access_token": "simulated-access-token",
                                     "scope": "openid email " + SCOPES["email"]})
                    return
                assert self.path == "/send"
                payload = json.loads(body)
                message = message_from_bytes(base64.urlsafe_b64decode(payload["raw"]))
                action_id = str(message["Message-ID"]).removeprefix("<").split("@", 1)[0]
                with counter.lock:
                    counter.dispatch_count += 1
                if counter.fault in {"provider_401", "provider_403", "provider_429"}:
                    self.reply(int(counter.fault[-3:]), {"error": {"message": "synthetic rejection"}})
                    return
                with counter.lock:
                    counter.mutation_count += 1
                    counter.action_ids.append(action_id)
                    receipt_id = "mail-" + str(counter.mutation_count)
                counter.applied.set()
                if counter.hold_after_apply:
                    counter.release.wait(30)
                if counter.fault == "lost_provider_response":
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                if counter.fault == "provider_500":
                    self.reply(500, {"error": {"message": "accepted before synthetic server failure"}})
                    return
                if counter.fault == "malformed_response":
                    self.reply(200, {"unexpected": "no provider receipt"})
                    return
                self.reply(200, {"id": receipt_id, "threadId": "thread-" + receipt_id})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)

    def counts(self):
        with self.lock:
            return self.dispatch_count, self.mutation_count, list(self.action_ids)

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


def service_for(settings, sessions, origin):
    repo = ActionRepository(sessions, settings)
    gateway = PermissionGateway(sessions, settings)
    providers = {"google": GoogleActions(settings, LoopbackGoogleTransport(origin))}
    broker = CredentialBroker(repo, gateway, providers)
    return ActionService(repo, providers, permission_gateway=gateway, credential_broker=broker)


def action_worker(settings, origin, action_id, boundary, entered, release, ready,
                  temporal_address=None, polling_gate=None):
    """A disposable process with a new pool; never inherit parent's DB sockets."""
    sessions = session_factory(settings.database_url)
    try:
        require_disposable_database(sessions)
        service = service_for(settings, sessions, origin)
        original_execute = service.execute

        async def diagnosed_execute(identity):
            try:
                return await original_execute(identity)
            except Exception as error:
                # Production activities intentionally redact exception details.
                # A class name identifies setup failures without printing an
                # OAuth token, SQL parameters or recipient/message contents.
                print("Transaction test worker exception: " + type(error).__name__, flush=True)
                raise

        service.execute = diagnosed_execute
        claim = service.repo.claim_execution
        finish = service.repo.finish

        def pause(phase):
            if boundary == phase:
                entered.set()
                if not release.wait(30):
                    raise RuntimeError("Parent did not interrupt the test worker")

        def claim_at_boundary(identity):
            pause("before_claim")
            result = claim(identity)
            if result is not None:
                pause("after_claim")
            return result

        def finish_at_boundary(identity, state, *args, **kwargs):
            result = finish(identity, state, *args, **kwargs)
            if state == "succeeded":
                pause("after_receipt_commit")
            return result

        service.repo.claim_execution = claim_at_boundary
        service.repo.finish = finish_at_boundary

        async def execute():
            if temporal_address is None:
                await service.execute(action_id)
                return
            from datetime import timedelta
            from temporalio.client import Client
            from temporalio.worker import Worker
            from services.coworker.worker import ActionActivities
            from services.coworker.workflow import ApprovedActionWorkflow

            client = await Client.connect(temporal_address)
            activities = ActionActivities(service)
            if polling_gate is not None:
                # Keep this restarted process connected but not polling until
                # the parent finishes advancing only the lost activity timer.
                ready.set()
                if not polling_gate.wait(25):
                    raise RuntimeError("Parent did not release restarted worker polling")
            worker = Worker(
                client, task_queue=settings.task_queue, workflows=[ApprovedActionWorkflow],
                activities=[activities.execute, activities.interrupted],
                max_cached_workflows=0, graceful_shutdown_timeout=timedelta(seconds=1),
            )
            async with worker:
                # Context entry schedules the SDK pollers; it does not prove
                # that a workflow/activity task has reached this process.
                ready.set()
                await asyncio.Event().wait()

        asyncio.run(execute())
    finally:
        sessions.kw["bind"].dispose()


def api_worker(settings, public_jwk, listener, drop_after_create_key):
    """Run the actual API; drop one reply only AFTER its DB commit returns."""
    from fastapi import FastAPI
    import uvicorn
    from services.coworker.api import mount
    from services.coworker.auth import JwtVerifier
    from services.coworker.container import Container

    assert settings.environment == "development"
    preflight = session_factory(settings.database_url)
    try:
        require_disposable_database(preflight)
    finally:
        preflight.kw["bind"].dispose()
    container = Container.create(settings)
    container.verifier = JwtVerifier(settings.auth_issuer, settings.auth_audience,
                                    httpx.MockTransport(lambda _request: httpx.Response(
                                        200, json={"keys": [public_jwk]},
                                    )))
    create = container.transactions.create_public

    def commit_then_drop(owner, request, key):
        result = create(owner, request, key)
        if key == drop_after_create_key and result[1] is True:
            # This is our disposable child, never a provider or shared server.
            import os
            os._exit(87)
        return result

    container.transactions.create_public = commit_then_drop
    app = FastAPI()
    mount(app, container)
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off"))
    server.run(sockets=[listener])


def wait_api_ready(origin, process):
    deadline = time.monotonic() + 15
    with httpx.Client(trust_env=False, timeout=1) as client:
        while time.monotonic() < deadline:
            if not process.is_alive():
                raise AssertionError("Disposable API exited before readiness")
            try:
                if client.get(origin + "/api/v1/me").status_code == 401:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
    raise AssertionError("Disposable API did not become ready")


class WorkerProcesses:
    def __init__(self):
        self.processes = []
        self.controls = []
        self.listeners = []

    def start_api(self, settings, public_jwk, drop_after_create_key=None):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(32)
        self.listeners.append(listener)  # Keep the FD alive through spawn.
        origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
        process = CONTEXT.Process(target=api_worker, args=(
            settings, public_jwk, listener, drop_after_create_key,
        ))
        process.start()
        self.processes.append(process)
        wait_api_ready(origin, process)
        return process, origin

    def start(self, settings, origin, action_id, boundary="none", temporal_address=None,
              *, polling_gate=None):
        entered, release, ready = CONTEXT.Event(), CONTEXT.Event(), CONTEXT.Event()
        # Spawn deserializes these asynchronously. Keep both controls alive
        # until children exit so their semaphore names cannot be unlinked by GC.
        self.controls.append((entered, release, ready, polling_gate))
        process = CONTEXT.Process(target=action_worker, args=(
            settings, origin, action_id, boundary, entered, release, ready, temporal_address, polling_gate,
        ))
        process.start()
        self.processes.append(process)
        if temporal_address is not None:
            assert ready.wait(25), "Temporal worker did not initialize before recovery"
        return process, entered

    @staticmethod
    def kill(process):
        assert process.is_alive(), "Test worker died before the injected fault"
        process.kill()
        process.join(10)
        assert not process.is_alive() and process.exitcode != 0

    def close(self):
        for process in self.processes:
            if process.is_alive():
                process.kill()
            process.join(10)
            assert not process.is_alive(), "Disposable transaction worker leaked"
            process.close()
        for listener in self.listeners:
            listener.close()
