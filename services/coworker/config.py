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
        if self.research_services_enabled and (self.search_provider != "tavily" or not self.search_api_key):
            raise ValueError("Research requires SHUDDHO_SEARCH_PROVIDER=tavily and backend-only TAVILY_API_KEY")
        if not self.database_url:
            raise ValueError("SHUDDHO_COWORKER_DATABASE_URL is required")
        issuer = urlparse(self.auth_issuer)
        if issuer.scheme != "https" or not issuer.netloc or issuer.username or issuer.password or issuer.query or issuer.fragment:
            raise ValueError("SHUDDHO_AUTH_ISSUER must be the HTTPS issuer of the managed identity provider")
        if min(self.max_daily_tasks, self.max_active_tasks, self.daily_token_budget,
               self.task_token_budget, self.max_account_bytes) < 1:
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
