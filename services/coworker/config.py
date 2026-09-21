from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def enabled() -> bool:
    return os.getenv("SHUDDHO_COWORKER_ENABLED", "false").lower() == "true"


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    auth_issuer: str
    auth_audience: str = "authenticated"
    storage_backend: str = "s3"
    storage_bucket: str = ""
    storage_endpoint: str | None = None
    storage_region: str = "us-east-1"
    local_storage_path: Path = Path("data/coworker-files")
    environment: str = "production"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_api_key: str = field(default="", repr=False)
    temporal_tls: bool = True
    task_queue: str = "shuddho-documents-v1"
    work_services_enabled: bool = False
    artifact_services_enabled: bool = False
    research_services_enabled: bool = False
    actions_enabled: bool = False
    agent_runtime_enabled: bool = False
    agent_memory_enabled: bool = False
    intelligent_planner_enabled: bool = False
    google_client_id: str = ""
    google_client_secret: str = field(default="", repr=False)
    google_redirect_uri: str = ""
    connector_encryption_key: str = field(default="", repr=False)
    max_daily_actions: int = 20
    max_active_agent_runs: int = 2
    agent_run_timeout_seconds: int = 1800
    max_memory_facts: int = 200
    max_memory_context_facts: int = 20
    max_memory_context_bytes: int = 8192
    max_agent_planner_calls: int = 2
    agent_planner_token_budget: int = 16000
    agent_planner_max_output_tokens: int = 1200
    search_provider: str = "tavily"
    search_api_key: str = field(default="", repr=False)
    search_timeout_seconds: int = 40
    max_upload_bytes: int = 8 * 1024 * 1024
    max_account_bytes: int = 256 * 1024 * 1024
    max_source_chars: int = 20000
    max_daily_tasks: int = 20
    max_active_tasks: int = 2
    daily_token_budget: int = 500000
    task_token_budget: int = 100000
    max_model_attempts: int = 2
    task_timeout_seconds: int = 1200
    deepseek_model: str = "deepseek-flash"
    deepseek_api_key: str = field(default="", repr=False)
    model_timeout_seconds: int = 90
    max_output_tokens: int = 4096

    @classmethod
    def from_env(cls) -> "Settings":
        value = cls(
            database_url=os.getenv("SHUDDHO_COWORKER_DATABASE_URL", ""),
            auth_issuer=os.getenv("SHUDDHO_AUTH_ISSUER", "").rstrip("/"),
            auth_audience=os.getenv("SHUDDHO_AUTH_AUDIENCE", "authenticated"),
            storage_backend=os.getenv("SHUDDHO_COWORKER_STORAGE", "s3"),
            storage_bucket=os.getenv("SHUDDHO_COWORKER_BUCKET", ""),
            storage_endpoint=os.getenv("SHUDDHO_COWORKER_S3_ENDPOINT") or None,
            storage_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            local_storage_path=Path(os.getenv("SHUDDHO_COWORKER_LOCAL_STORAGE", "data/coworker-files")),
            environment=os.getenv("SHUDDHO_COWORKER_ENV", "production"),
            temporal_address=os.getenv("SHUDDHO_TEMPORAL_ADDRESS", "localhost:7233"),
            temporal_namespace=os.getenv("SHUDDHO_TEMPORAL_NAMESPACE", "default"),
            temporal_api_key=os.getenv("SHUDDHO_TEMPORAL_API_KEY", ""),
            temporal_tls=os.getenv("SHUDDHO_TEMPORAL_TLS", "true").lower() == "true",
            task_queue=os.getenv("SHUDDHO_TEMPORAL_TASK_QUEUE", "shuddho-documents-v1"),
            work_services_enabled=os.getenv("SHUDDHO_WORK_SERVICES_ENABLED", "false").lower() == "true",
            artifact_services_enabled=os.getenv("SHUDDHO_ARTIFACT_SERVICES_ENABLED", "false").lower() == "true",
            research_services_enabled=os.getenv("SHUDDHO_RESEARCH_SERVICES_ENABLED", "false").lower() == "true",
            actions_enabled=os.getenv("SHUDDHO_ACTIONS_ENABLED", "false").lower() == "true",
            agent_runtime_enabled=os.getenv("SHUDDHO_AGENT_RUNTIME_ENABLED", "false").lower() == "true",
            agent_memory_enabled=os.getenv("SHUDDHO_AGENT_MEMORY_ENABLED", "false").lower() == "true",
            intelligent_planner_enabled=os.getenv("SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED", "false").lower() == "true",
            google_client_id=os.getenv("SHUDDHO_GOOGLE_CLIENT_ID", ""),
            google_client_secret=os.getenv("SHUDDHO_GOOGLE_CLIENT_SECRET", ""),
            google_redirect_uri=os.getenv("SHUDDHO_GOOGLE_REDIRECT_URI", ""),
            connector_encryption_key=os.getenv("SHUDDHO_CONNECTOR_ENCRYPTION_KEY", ""),
            max_daily_actions=int(os.getenv("SHUDDHO_COWORKER_DAILY_ACTIONS", "20")),
            max_active_agent_runs=int(os.getenv("SHUDDHO_COWORKER_ACTIVE_AGENT_RUNS", "2")),
            agent_run_timeout_seconds=int(os.getenv("SHUDDHO_AGENT_RUN_TIMEOUT_SECONDS", "1800")),
            max_memory_facts=int(os.getenv("SHUDDHO_AGENT_MEMORY_FACTS", "200")),
            max_memory_context_facts=int(os.getenv("SHUDDHO_AGENT_MEMORY_CONTEXT_FACTS", "20")),
            max_memory_context_bytes=int(os.getenv("SHUDDHO_AGENT_MEMORY_CONTEXT_BYTES", "8192")),
            max_agent_planner_calls=int(os.getenv("SHUDDHO_AGENT_PLANNER_CALLS", "2")),
            agent_planner_token_budget=int(os.getenv("SHUDDHO_AGENT_PLANNER_TOKEN_BUDGET", "16000")),
            agent_planner_max_output_tokens=int(os.getenv("SHUDDHO_AGENT_PLANNER_MAX_OUTPUT_TOKENS", "1200")),
            search_provider=os.getenv("SHUDDHO_SEARCH_PROVIDER", "tavily"),
            search_api_key=os.getenv("TAVILY_API_KEY", ""),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            max_daily_tasks=int(os.getenv("SHUDDHO_COWORKER_DAILY_TASKS", "20")),
            max_active_tasks=int(os.getenv("SHUDDHO_COWORKER_ACTIVE_TASKS", "2")),
            daily_token_budget=int(os.getenv("SHUDDHO_COWORKER_DAILY_TOKENS", "500000")),
            task_token_budget=int(os.getenv("SHUDDHO_COWORKER_TASK_TOKENS", "100000")),
            max_account_bytes=int(os.getenv("SHUDDHO_COWORKER_STORAGE_BYTES", "268435456")),
        )
        value.validate()
        return value

    def validate(self) -> None:
        if self.actions_enabled:
            from .action_security import TokenVault
            TokenVault(self.connector_encryption_key)
            callback = urlparse(self.google_redirect_uri)
            local = self.environment == "development" and callback.hostname in {"localhost", "127.0.0.1"}
            if (not self.google_client_id or not self.google_client_secret or not callback.netloc or
                    callback.scheme != "https" and not (local and callback.scheme == "http") or
                    callback.username or callback.password or callback.query or callback.fragment or
                    callback.path != "/oauth/google/callback"):
                raise ValueError("Actions require Google OAuth credentials and an HTTPS frontend /oauth/google/callback redirect URI")
        if self.research_services_enabled and (self.search_provider != "tavily" or not self.search_api_key):
            raise ValueError("Research requires SHUDDHO_SEARCH_PROVIDER=tavily and backend-only TAVILY_API_KEY")
        if not self.database_url:
            raise ValueError("SHUDDHO_COWORKER_DATABASE_URL is required")
        issuer = urlparse(self.auth_issuer)
        if issuer.scheme != "https" or not issuer.netloc or issuer.username or issuer.password or issuer.query or issuer.fragment:
            raise ValueError("SHUDDHO_AUTH_ISSUER must be the HTTPS issuer of the managed identity provider")
        if min(self.max_daily_tasks, self.max_active_tasks, self.daily_token_budget,
               self.task_token_budget, self.max_account_bytes, self.max_daily_actions,
               self.max_active_agent_runs, self.agent_run_timeout_seconds, self.max_memory_facts,
               self.max_memory_context_facts, self.max_memory_context_bytes, self.max_agent_planner_calls,
               self.agent_planner_token_budget, self.agent_planner_max_output_tokens) < 1:
            raise ValueError("Coworker limits must be positive")
        if self.storage_backend not in {"s3", "local"}:
            raise ValueError("Unsupported coworker storage backend")
        if self.environment != "development":
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production coworker requires PostgreSQL with psycopg")
            if parse_qs(urlparse(self.database_url).query).get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
                raise ValueError("Production PostgreSQL requires sslmode=require, verify-ca, or verify-full")
            if self.storage_backend != "s3" or not self.storage_bucket:
                raise ValueError("Production coworker requires a private S3-compatible bucket")
            if self.storage_endpoint and urlparse(self.storage_endpoint).scheme != "https":
                raise ValueError("Production object storage requires HTTPS")
            if not self.temporal_tls:
                raise ValueError("Production Temporal connections require TLS")
