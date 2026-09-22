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
    agent_handoffs_enabled: bool = False
    agent_multi_handoffs_enabled: bool = False
    agent_dependency_graph_enabled: bool = False
    agent_parallel_execution_enabled: bool = False
    agent_outcome_replan_enabled: bool = False
    cohort_enforced: bool = False
    cohort_account_ids: frozenset[str] = field(default_factory=frozenset)
    cohort_max_users: int = 25
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
    max_agent_handoff_bytes: int = 12000
    max_agent_handoff_sources: int = 2
    max_agent_parallel_steps: int = 2
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
            agent_handoffs_enabled=os.getenv("SHUDDHO_AGENT_HANDOFFS_ENABLED", "false").lower() == "true",
            agent_multi_handoffs_enabled=os.getenv("SHUDDHO_AGENT_MULTI_HANDOFFS_ENABLED", "false").lower() == "true",
            agent_dependency_graph_enabled=os.getenv("SHUDDHO_AGENT_DEPENDENCY_GRAPH_ENABLED", "false").lower() == "true",
            agent_parallel_execution_enabled=os.getenv("SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED", "false").lower() == "true",
            agent_outcome_replan_enabled=os.getenv("SHUDDHO_AGENT_OUTCOME_REPLAN_ENABLED", "false").lower() == "true",
            cohort_enforced=os.getenv("SHUDDHO_COWORKER_COHORT_ENFORCED", "false").lower() == "true",
            cohort_account_ids=frozenset(
                value.strip().lower()
                for value in os.getenv("SHUDDHO_COWORKER_COHORT_ACCOUNT_IDS", "").split(",")
                if value.strip()
            ),
            cohort_max_users=int(os.getenv("SHUDDHO_COWORKER_COHORT_MAX_USERS", "25")),
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
            max_agent_handoff_bytes=int(os.getenv("SHUDDHO_AGENT_HANDOFF_BYTES", "12000")),
            max_agent_handoff_sources=int(os.getenv("SHUDDHO_AGENT_HANDOFF_SOURCES", "2")),
            max_agent_parallel_steps=int(os.getenv("SHUDDHO_AGENT_MAX_PARALLEL_STEPS", "2")),
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
               self.agent_planner_token_budget, self.agent_planner_max_output_tokens,
               self.max_agent_handoff_bytes, self.max_agent_handoff_sources,
               self.max_agent_parallel_steps, self.cohort_max_users) < 1:
            raise ValueError("Coworker limits must be positive")
        if self.max_agent_parallel_steps > 4:
            raise ValueError("SHUDDHO_AGENT_MAX_PARALLEL_STEPS must be between 1 and 4")
        if self.cohort_enforced:
            if not self.cohort_account_ids:
                raise ValueError("Cohort enforcement requires SHUDDHO_COWORKER_COHORT_ACCOUNT_IDS")
            if len(self.cohort_account_ids) > self.cohort_max_users:
                raise ValueError("Configured Coworker cohort exceeds SHUDDHO_COWORKER_COHORT_MAX_USERS")
            if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
                   for value in self.cohort_account_ids):
                raise ValueError("Coworker cohort account IDs must be 64-character lowercase SHA-256 hex values")
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
