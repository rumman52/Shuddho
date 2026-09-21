from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import uuid
from pathlib import Path

import httpx
from sqlalchemy import text
from temporalio.client import Client

from scripts.agent_eval import evaluate_live, load_cases
from services.coworker.config import Settings
from services.coworker.database import session_factory
from services.coworker.storage import S3ObjectStore

PROBE_PREFIX = "staging-probes"


def passed(evidence: str) -> dict:
    return {"status": "passed", "evidence": evidence}


def failed(evidence: str) -> dict:
    return {"status": "failed", "evidence": evidence}


async def probe_identity(settings: Settings) -> dict:
    url = settings.auth_issuer + "/.well-known/jwks.json"
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            body = response.json()
        keys = [
            item for item in body.get("keys", [])
            if item.get("alg") in {"RS256", "ES256"} and item.get("use", "sig") == "sig"
        ]
        if not keys:
            return failed("managed identity JWKS reachable but no supported asymmetric signing key was found")
        return passed(f"managed identity JWKS reachable with {len(keys)} supported asymmetric signing key(s)")
    except Exception as error:
        return failed(f"managed identity JWKS probe failed: {type(error).__name__}")


def probe_database(settings: Settings) -> dict:
    sessions = session_factory(settings.database_url)
    engine = sessions.kw["bind"]
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1")).scalar_one()
            schema = connection.execute(text("select current_schema()")).scalar_one()
            tls = connection.execute(text("select ssl from pg_stat_ssl where pid = pg_backend_pid()")).scalar_one()
            version = connection.execute(text("select version_num from cw_alembic_version")).scalar_one()
        if schema != "shuddho_coworker" or not tls or not version:
            return failed("PostgreSQL reachable but schema, TLS, or migration evidence is incomplete")
        return passed(f"PostgreSQL reachable over TLS; schema={schema}; migration={version}")
    except Exception as error:
        return failed(f"PostgreSQL probe failed: {type(error).__name__}")
    finally:
        engine.dispose()


def probe_storage(settings: Settings) -> dict:
    key = f"{PROBE_PREFIX}/{uuid.uuid4().hex}.txt"
    payload = b"shuddho-staging-probe"
    store = S3ObjectStore(settings)
    cleanup_error = None
    try:
        store.put(key, payload, "text/plain")
        downloaded = store.get(key, 1024)
        if downloaded != payload:
            return failed("private object storage round trip returned unexpected bytes")
        return passed("private object storage write/read/delete round trip succeeded")
    except Exception as error:
        return failed(f"private object storage probe failed: {type(error).__name__}")
    finally:
        try:
            store.delete(key)
        except Exception as error:
            cleanup_error = type(error).__name__
        if cleanup_error:
            # Never expose object keys or provider response bodies.
            pass


async def probe_temporal(settings: Settings) -> dict:
    try:
        client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            api_key=settings.temporal_api_key or None,
            tls=settings.temporal_tls,
        )
        await client.service_client.workflow_service.describe_namespace(
            {"namespace": settings.temporal_namespace}
        )
        return passed(f"Temporal namespace reachable over TLS: {settings.temporal_namespace}")
    except Exception as error:
        return failed(f"Temporal probe failed: {type(error).__name__}")


async def probe_model(settings: Settings, cases: Path) -> dict:
    if not settings.deepseek_api_key:
        return failed("live DeepSeek planner evaluation skipped because DEEPSEEK_API_KEY is missing")
    try:
        result = await evaluate_live(load_cases(cases))
        if result["pass_rate"] != 1.0:
            return failed(f"live DeepSeek planner evaluation pass_rate={result['pass_rate']}")
        return passed(f"live DeepSeek planner evaluation passed {result['passed']}/{result['cases']} cases")
    except Exception as error:
        return failed(f"live DeepSeek planner evaluation failed: {type(error).__name__}")


async def collect(settings: Settings, *, live_model: bool, cases: Path) -> dict:
    evidence = {
        "identity": await probe_identity(settings),
        "database": probe_database(settings),
        "storage": probe_storage(settings),
        "temporal": await probe_temporal(settings),
    }
    if live_model:
        evidence["model"] = await probe_model(settings, cases)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Run non-destructive Shuddho Coworker staging probes.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--cases", type=Path, default=Path("tests/fixtures/agent_eval_cases.jsonl"))
    args = parser.parse_args()

    settings = Settings.from_env()
    evidence = asyncio.run(collect(settings, live_model=args.live_model, cases=args.cases))
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(args.output), "checks": {key: value["status"] for key, value in evidence.items()}}, indent=2))
    if any(value["status"] != "passed" for value in evidence.values()):
        raise SystemExit("One or more live staging probes failed.")


if __name__ == "__main__":
    main()
