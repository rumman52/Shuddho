from __future__ import annotations

import os
import re
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
    source_revision: str | None = None
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_api_key: str = field(default="", repr=False)
    temporal_tls: bool = True
    task_queue: str = "shuddho-documents-v1"
    work_services_enabled: bool = False
    artifact_services_enabled: bool = False
    research_services_enabled: bool = False
    actions_enabled: bool = False
    connector_trust_boundary_enabled: bool = False
    connector_reads_enabled: bool = False
    browser_enabled: bool = False
    action_attachments_enabled: bool = False
    action_reminders_enabled: bool = False
    action_recipients_enabled: bool = False
    action_document_sharing_enabled: bool = False
    action_email_threading_enabled: bool = False
    action_social_publishing_enabled: bool = False
    agent_runtime_enabled: bool = False
    agent_runtime_v3_enabled: bool = False
    personal_goals_enabled: bool = False
    automations_enabled: bool = False
    agent_memory_enabled: bool = False
    context_retrieval_enabled: bool = False
    intelligent_planner_enabled: bool = False
    agent_handoffs_enabled: bool = False
    agent_multi_handoffs_enabled: bool = False
    agent_dependency_graph_enabled: bool = False
    agent_parallel_execution_enabled: bool = False
    agent_outcome_replan_enabled: bool = False
    agent_action_selection_enabled: bool = False
    agent_action_proposals_enabled: bool = False
    agent_linkedin_proposals_enabled: bool = False
    cohort_enforced: bool = False
    cohort_account_ids: frozenset[str] = field(default_factory=frozenset)
    cohort_max_users: int = 25
    google_client_id: str = ""
    google_client_secret: str = field(default="", repr=False)
    google_redirect_uri: str = ""
    connector_webhook_base_url: str = ""
    google_gmail_pubsub_topic: str = ""
    google_gmail_pubsub_subscription: str = ""
    google_gmail_push_audience: str = ""
    google_gmail_push_service_account: str = ""
    microsoft_actions_enabled: bool = False
    microsoft_client_id: str = ""
    microsoft_client_secret: str = field(default="", repr=False)
    microsoft_redirect_uri: str = ""
    microsoft_tenant: str = "organizations"
    linkedin_client_id: str = ""
    linkedin_client_secret: str = field(default="", repr=False)
    linkedin_redirect_uri: str = ""
    linkedin_api_version: str = "202609"
    connector_encryption_key: str = field(default="", repr=False)
    max_daily_actions: int = 20
    max_action_recipients: int = 100
    max_active_agent_runs: int = 2
    max_active_browser_sessions: int = 2
    browser_session_ttl_seconds: int = 900
    browser_worker_lease_seconds: int = 30
    browser_command_max_attempts: int = 2
    agent_run_timeout_seconds: int = 1800
    max_personal_goals: int = 100
    max_automations: int = 100
    max_memory_facts: int = 200
    max_memory_context_facts: int = 20
    max_memory_context_bytes: int = 8192
    max_agent_context_items: int = 5
    max_agent_context_item_bytes: int = 4096
    max_agent_context_bytes: int = 12288
    max_memory_proposals: int = 20
    max_agent_planner_calls: int = 2
    agent_planner_token_budget: int = 16000
    agent_planner_max_output_tokens: int = 1200
    max_agent_v3_planner_calls: int = 4
    agent_v3_planner_token_budget: int = 24000
    agent_v3_planner_cost_microusd_per_1k_tokens: int = 0
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
    provider_max_concurrent_calls: int = 8
    provider_max_concurrent_per_workspace: int = 2
    provider_max_reserved_tokens: int = 800000
    provider_max_reserved_tokens_per_workspace: int = 200000
    provider_daily_token_budget: int = 5000000
    provider_lease_seconds: int = 120

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
            source_revision=(
                os.getenv("SHUDDHO_SOURCE_REVISION")
                or os.getenv("RENDER_GIT_COMMIT")
                or os.getenv("GITHUB_SHA")
                or ""
            ).strip().lower() or None,
            temporal_address=os.getenv("SHUDDHO_TEMPORAL_ADDRESS", "localhost:7233"),
            temporal_namespace=os.getenv("SHUDDHO_TEMPORAL_NAMESPACE", "default"),
            temporal_api_key=os.getenv("SHUDDHO_TEMPORAL_API_KEY", ""),
            temporal_tls=os.getenv("SHUDDHO_TEMPORAL_TLS", "true").lower() == "true",
            task_queue=os.getenv("SHUDDHO_TEMPORAL_TASK_QUEUE", "shuddho-documents-v1"),
            work_services_enabled=os.getenv("SHUDDHO_WORK_SERVICES_ENABLED", "false").lower() == "true",
            artifact_services_enabled=os.getenv("SHUDDHO_ARTIFACT_SERVICES_ENABLED", "false").lower() == "true",
            research_services_enabled=os.getenv("SHUDDHO_RESEARCH_SERVICES_ENABLED", "false").lower() == "true",
            actions_enabled=os.getenv("SHUDDHO_ACTIONS_ENABLED", "false").lower() == "true",
            connector_trust_boundary_enabled=os.getenv("SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED", "false").lower() == "true",
            connector_reads_enabled=os.getenv("SHUDDHO_CONNECTOR_READS_ENABLED", "false").lower() == "true",
            browser_enabled=os.getenv("SHUDDHO_BROWSER_ENABLED", "false").lower() == "true",
            action_attachments_enabled=os.getenv("SHUDDHO_ACTION_ATTACHMENTS_ENABLED", "false").lower() == "true",
            action_reminders_enabled=os.getenv("SHUDDHO_ACTION_REMINDERS_ENABLED", "false").lower() == "true",
            action_recipients_enabled=os.getenv("SHUDDHO_ACTION_RECIPIENTS_ENABLED", "false").lower() == "true",
            action_document_sharing_enabled=os.getenv("SHUDDHO_ACTION_DOCUMENT_SHARING_ENABLED", "false").lower() == "true",
            action_email_threading_enabled=os.getenv("SHUDDHO_ACTION_EMAIL_THREADING_ENABLED", "false").lower() == "true",
            action_social_publishing_enabled=os.getenv("SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED", "false").lower() == "true",
            agent_runtime_enabled=os.getenv("SHUDDHO_AGENT_RUNTIME_ENABLED", "false").lower() == "true",
            agent_runtime_v3_enabled=os.getenv("SHUDDHO_AGENT_RUNTIME_V3_ENABLED", "false").lower() == "true",
            personal_goals_enabled=os.getenv("SHUDDHO_PERSONAL_GOALS_ENABLED", "false").lower() == "true",
            automations_enabled=os.getenv("SHUDDHO_AUTOMATIONS_ENABLED", "false").lower() == "true",
            agent_memory_enabled=os.getenv("SHUDDHO_AGENT_MEMORY_ENABLED", "false").lower() == "true",
            context_retrieval_enabled=os.getenv("SHUDDHO_CONTEXT_RETRIEVAL_ENABLED", "false").lower() == "true",
            intelligent_planner_enabled=os.getenv("SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED", "false").lower() == "true",
            agent_handoffs_enabled=os.getenv("SHUDDHO_AGENT_HANDOFFS_ENABLED", "false").lower() == "true",
            agent_multi_handoffs_enabled=os.getenv("SHUDDHO_AGENT_MULTI_HANDOFFS_ENABLED", "false").lower() == "true",
            agent_dependency_graph_enabled=os.getenv("SHUDDHO_AGENT_DEPENDENCY_GRAPH_ENABLED", "false").lower() == "true",
            agent_parallel_execution_enabled=os.getenv("SHUDDHO_AGENT_PARALLEL_EXECUTION_ENABLED", "false").lower() == "true",
            agent_outcome_replan_enabled=os.getenv("SHUDDHO_AGENT_OUTCOME_REPLAN_ENABLED", "false").lower() == "true",
            agent_action_selection_enabled=os.getenv("SHUDDHO_AGENT_ACTION_SELECTION_ENABLED", "false").lower() == "true",
            agent_action_proposals_enabled=os.getenv("SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED", "false").lower() == "true",
            agent_linkedin_proposals_enabled=os.getenv("SHUDDHO_AGENT_LINKEDIN_PROPOSALS_ENABLED", "false").lower() == "true",
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
            connector_webhook_base_url=os.getenv("SHUDDHO_CONNECTOR_WEBHOOK_BASE_URL", "").rstrip("/"),
            google_gmail_pubsub_topic=os.getenv("SHUDDHO_GOOGLE_GMAIL_PUBSUB_TOPIC", ""),
            google_gmail_pubsub_subscription=os.getenv("SHUDDHO_GOOGLE_GMAIL_PUBSUB_SUBSCRIPTION", ""),
            google_gmail_push_audience=os.getenv("SHUDDHO_GOOGLE_GMAIL_PUSH_AUDIENCE", ""),
            google_gmail_push_service_account=os.getenv("SHUDDHO_GOOGLE_GMAIL_PUSH_SERVICE_ACCOUNT", "").lower(),
            microsoft_actions_enabled=os.getenv("SHUDDHO_MICROSOFT_ACTIONS_ENABLED", "false").lower() == "true",
            microsoft_client_id=os.getenv("SHUDDHO_MICROSOFT_CLIENT_ID", ""),
            microsoft_client_secret=os.getenv("SHUDDHO_MICROSOFT_CLIENT_SECRET", ""),
            microsoft_redirect_uri=os.getenv("SHUDDHO_MICROSOFT_REDIRECT_URI", ""),
            microsoft_tenant=os.getenv("SHUDDHO_MICROSOFT_TENANT", "organizations"),
            linkedin_client_id=os.getenv("SHUDDHO_LINKEDIN_CLIENT_ID", ""),
            linkedin_client_secret=os.getenv("SHUDDHO_LINKEDIN_CLIENT_SECRET", ""),
            linkedin_redirect_uri=os.getenv("SHUDDHO_LINKEDIN_REDIRECT_URI", ""),
            linkedin_api_version=os.getenv("SHUDDHO_LINKEDIN_API_VERSION", "202609"),
            connector_encryption_key=os.getenv("SHUDDHO_CONNECTOR_ENCRYPTION_KEY", ""),
            max_daily_actions=int(os.getenv("SHUDDHO_COWORKER_DAILY_ACTIONS", "20")),
            max_action_recipients=int(os.getenv("SHUDDHO_ACTION_RECIPIENTS_MAX", "100")),
            max_active_agent_runs=int(os.getenv("SHUDDHO_COWORKER_ACTIVE_AGENT_RUNS", "2")),
            max_active_browser_sessions=int(os.getenv("SHUDDHO_BROWSER_MAX_ACTIVE_SESSIONS", "2")),
            browser_session_ttl_seconds=int(os.getenv("SHUDDHO_BROWSER_SESSION_TTL_SECONDS", "900")),
            browser_worker_lease_seconds=int(os.getenv("SHUDDHO_BROWSER_WORKER_LEASE_SECONDS", "30")),
            browser_command_max_attempts=int(os.getenv("SHUDDHO_BROWSER_COMMAND_MAX_ATTEMPTS", "2")),
            agent_run_timeout_seconds=int(os.getenv("SHUDDHO_AGENT_RUN_TIMEOUT_SECONDS", "1800")),
            max_personal_goals=int(os.getenv("SHUDDHO_PERSONAL_GOALS_MAX", "100")),
            max_automations=int(os.getenv("SHUDDHO_AUTOMATIONS_MAX", "100")),
            max_memory_facts=int(os.getenv("SHUDDHO_AGENT_MEMORY_FACTS", "200")),
            max_memory_context_facts=int(os.getenv("SHUDDHO_AGENT_MEMORY_CONTEXT_FACTS", "20")),
            max_memory_context_bytes=int(os.getenv("SHUDDHO_AGENT_MEMORY_CONTEXT_BYTES", "8192")),
            max_agent_context_items=int(os.getenv("SHUDDHO_AGENT_CONTEXT_ITEMS", "5")),
            max_agent_context_item_bytes=int(os.getenv("SHUDDHO_AGENT_CONTEXT_ITEM_BYTES", "4096")),
            max_agent_context_bytes=int(os.getenv("SHUDDHO_AGENT_CONTEXT_BYTES", "12288")),
            max_memory_proposals=int(os.getenv("SHUDDHO_AGENT_MEMORY_PROPOSALS", "20")),
            max_agent_planner_calls=int(os.getenv("SHUDDHO_AGENT_PLANNER_CALLS", "2")),
            agent_planner_token_budget=int(os.getenv("SHUDDHO_AGENT_PLANNER_TOKEN_BUDGET", "16000")),
            agent_planner_max_output_tokens=int(os.getenv("SHUDDHO_AGENT_PLANNER_MAX_OUTPUT_TOKENS", "1200")),
            max_agent_v3_planner_calls=int(os.getenv("SHUDDHO_AGENT_V3_PLANNER_CALLS", "4")),
            agent_v3_planner_token_budget=int(os.getenv("SHUDDHO_AGENT_V3_PLANNER_TOKEN_BUDGET", "24000")),
            agent_v3_planner_cost_microusd_per_1k_tokens=int(os.getenv("SHUDDHO_AGENT_V3_PLANNER_COST_MICROUSD_PER_1K_TOKENS", "0")),
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
            provider_max_concurrent_calls=int(os.getenv("SHUDDHO_PROVIDER_MAX_CONCURRENT_CALLS", "8")),
            provider_max_concurrent_per_workspace=int(os.getenv("SHUDDHO_PROVIDER_MAX_CONCURRENT_PER_WORKSPACE", "2")),
            provider_max_reserved_tokens=int(os.getenv("SHUDDHO_PROVIDER_MAX_RESERVED_TOKENS", "800000")),
            provider_max_reserved_tokens_per_workspace=int(os.getenv("SHUDDHO_PROVIDER_MAX_RESERVED_TOKENS_PER_WORKSPACE", "200000")),
            provider_daily_token_budget=int(os.getenv("SHUDDHO_PROVIDER_DAILY_TOKEN_BUDGET", "5000000")),
            provider_lease_seconds=int(os.getenv("SHUDDHO_PROVIDER_LEASE_SECONDS", "120")),
        )
        value.validate()
        return value

    def validate(self) -> None:
        if self.source_revision is not None:
            if (
                len(self.source_revision) != 40
                or self.source_revision != self.source_revision.lower()
                or any(char not in "0123456789abcdef" for char in self.source_revision)
            ):
                raise ValueError(
                    "SHUDDHO_SOURCE_REVISION/RENDER_GIT_COMMIT must be a full lowercase 40-character Git commit hash"
                )
        if self.connector_trust_boundary_enabled and not self.actions_enabled:
            raise ValueError("Connector trust boundary requires SHUDDHO_ACTIONS_ENABLED=true")
        if self.connector_reads_enabled:
            if not self.actions_enabled or not self.connector_trust_boundary_enabled:
                raise ValueError("Connector reads require SHUDDHO_ACTIONS_ENABLED=true and SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=true")
            if not self.context_retrieval_enabled or not self.agent_runtime_v3_enabled:
                raise ValueError("Connector reads require SHUDDHO_CONTEXT_RETRIEVAL_ENABLED=true and SHUDDHO_AGENT_RUNTIME_V3_ENABLED=true")
            if self.connector_webhook_base_url:
                parsed = urlparse(self.connector_webhook_base_url)
                if (
                    parsed.scheme != "https"
                    or not parsed.netloc
                    or parsed.username
                    or parsed.password
                    or parsed.path not in {"", "/"}
                    or parsed.params
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError("SHUDDHO_CONNECTOR_WEBHOOK_BASE_URL must be a clean HTTPS origin")
            gmail_push = any((
                self.google_gmail_pubsub_topic,
                self.google_gmail_pubsub_subscription,
                self.google_gmail_push_audience,
                self.google_gmail_push_service_account,
            ))
            if gmail_push and not all((
                self.connector_webhook_base_url,
                self.google_gmail_pubsub_topic,
                self.google_gmail_pubsub_subscription,
                self.google_gmail_push_audience,
                self.google_gmail_push_service_account,
            )):
                raise ValueError("Gmail push requires webhook base URL, topic, subscription, audience, and service account")
            if self.google_gmail_pubsub_topic and not re.fullmatch(r"projects/[A-Za-z0-9._:-]+/topics/[A-Za-z0-9._~-]+", self.google_gmail_pubsub_topic):
                raise ValueError("SHUDDHO_GOOGLE_GMAIL_PUBSUB_TOPIC is invalid")
            if self.google_gmail_pubsub_subscription and not re.fullmatch(r"projects/[A-Za-z0-9._:-]+/subscriptions/[A-Za-z0-9._~-]+", self.google_gmail_pubsub_subscription):
                raise ValueError("SHUDDHO_GOOGLE_GMAIL_PUBSUB_SUBSCRIPTION is invalid")
            if self.google_gmail_push_service_account and not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.gserviceaccount\.com", self.google_gmail_push_service_account):
                raise ValueError("SHUDDHO_GOOGLE_GMAIL_PUSH_SERVICE_ACCOUNT is invalid")
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
        if self.browser_enabled:
            if not self.agent_runtime_v3_enabled:
                raise ValueError("Browser broker requires Agent Runtime v3 (SHUDDHO_AGENT_RUNTIME_V3_ENABLED=true)")
            if not self.connector_trust_boundary_enabled:
                raise ValueError("Browser broker requires SHUDDHO_CONNECTOR_TRUST_BOUNDARY_ENABLED=true")
            if not 1 <= self.max_active_browser_sessions <= 4:
                raise ValueError("SHUDDHO_BROWSER_MAX_ACTIVE_SESSIONS must be between 1 and 4")
            if not 60 <= self.browser_session_ttl_seconds <= 1800:
                raise ValueError("SHUDDHO_BROWSER_SESSION_TTL_SECONDS must be between 60 and 1800")
            if not 10 <= self.browser_worker_lease_seconds <= 120:
                raise ValueError("SHUDDHO_BROWSER_WORKER_LEASE_SECONDS must be between 10 and 120")
            if not 1 <= self.browser_command_max_attempts <= 3:
                raise ValueError("SHUDDHO_BROWSER_COMMAND_MAX_ATTEMPTS must be between 1 and 3")
        if self.agent_runtime_v3_enabled:
            if not self.agent_runtime_enabled or not self.intelligent_planner_enabled:
                raise ValueError("Agent Runtime v3 requires SHUDDHO_AGENT_RUNTIME_ENABLED=true and SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true")
            if not 1 <= self.max_agent_v3_planner_calls <= 4:
                raise ValueError("SHUDDHO_AGENT_V3_PLANNER_CALLS must be between 1 and 4")
            if self.agent_v3_planner_token_budget < self.max_agent_v3_planner_calls:
                raise ValueError("SHUDDHO_AGENT_V3_PLANNER_TOKEN_BUDGET is too small for the planner-call limit")
        if self.context_retrieval_enabled and not self.agent_runtime_v3_enabled:
            raise ValueError("Context retrieval requires SHUDDHO_AGENT_RUNTIME_V3_ENABLED=true")
        if self.automations_enabled:
            if not self.personal_goals_enabled or not self.agent_runtime_enabled:
                raise ValueError("Automations require SHUDDHO_PERSONAL_GOALS_ENABLED=true and SHUDDHO_AGENT_RUNTIME_ENABLED=true")
            if self.max_automations < 1 or self.max_automations > 1000:
                raise ValueError("SHUDDHO_AUTOMATIONS_MAX must be between 1 and 1000")
        if self.action_attachments_enabled and not self.actions_enabled:
            raise ValueError("Action attachments require SHUDDHO_ACTIONS_ENABLED=true")
        if self.action_reminders_enabled and not self.actions_enabled:
            raise ValueError("Action reminders require SHUDDHO_ACTIONS_ENABLED=true")
        if self.action_recipients_enabled and not self.actions_enabled:
            raise ValueError("Action recipients require SHUDDHO_ACTIONS_ENABLED=true")
        if self.action_document_sharing_enabled:
            if not self.actions_enabled:
                raise ValueError("Action document sharing requires SHUDDHO_ACTIONS_ENABLED=true")
            if not self.artifact_services_enabled:
                raise ValueError("Action document sharing requires SHUDDHO_ARTIFACT_SERVICES_ENABLED=true")
        if self.action_email_threading_enabled and not self.actions_enabled:
            raise ValueError("Action email threading requires SHUDDHO_ACTIONS_ENABLED=true")
        if self.action_social_publishing_enabled:
            if not self.actions_enabled:
                raise ValueError("Action social publishing requires SHUDDHO_ACTIONS_ENABLED=true")
            callback = urlparse(self.linkedin_redirect_uri)
            local = self.environment == "development" and callback.hostname in {"localhost", "127.0.0.1"}
            if (
                not self.linkedin_client_id
                or not self.linkedin_client_secret
                or not callback.netloc
                or callback.scheme != "https" and not (local and callback.scheme == "http")
                or callback.username
                or callback.password
                or callback.query
                or callback.fragment
                or callback.path != "/oauth/linkedin/callback"
                or not re.fullmatch(r"20\d{4}", self.linkedin_api_version)
            ):
                raise ValueError(
                    "LinkedIn social publishing requires OAuth credentials, a YYYYMM API version, and an HTTPS frontend /oauth/linkedin/callback redirect URI"
                )
        if self.microsoft_actions_enabled:
            if not self.actions_enabled:
                raise ValueError("Microsoft actions require SHUDDHO_ACTIONS_ENABLED=true")
            callback = urlparse(self.microsoft_redirect_uri)
            local = self.environment == "development" and callback.hostname in {"localhost", "127.0.0.1"}
            if (
                not self.microsoft_client_id
                or not self.microsoft_client_secret
                or not callback.netloc
                or callback.scheme != "https" and not (local and callback.scheme == "http")
                or callback.username
                or callback.password
                or callback.query
                or callback.fragment
                or callback.path != "/oauth/microsoft/callback"
                or not self.microsoft_tenant
                or len(self.microsoft_tenant) > 200
                or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for char in self.microsoft_tenant)
            ):
                raise ValueError(
                    "Microsoft actions require OAuth credentials, a safe tenant, and an HTTPS frontend /oauth/microsoft/callback redirect URI"
                )
        if self.agent_action_selection_enabled:
            if not self.agent_runtime_enabled:
                raise ValueError("Agent action selection requires SHUDDHO_AGENT_RUNTIME_ENABLED=true")
            if not self.intelligent_planner_enabled:
                raise ValueError("Agent action selection requires SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true")
            if not self.actions_enabled:
                raise ValueError("Agent action selection requires SHUDDHO_ACTIONS_ENABLED=true")
        if self.agent_action_proposals_enabled:
            if not self.agent_runtime_enabled:
                raise ValueError("Agent action proposals require SHUDDHO_AGENT_RUNTIME_ENABLED=true")
            if not self.intelligent_planner_enabled:
                raise ValueError("Agent action proposals require SHUDDHO_AGENT_INTELLIGENT_PLANNER_ENABLED=true")
            if not self.actions_enabled:
                raise ValueError("Agent action proposals require SHUDDHO_ACTIONS_ENABLED=true")
        if self.agent_linkedin_proposals_enabled:
            if not self.agent_action_proposals_enabled:
                raise ValueError("LinkedIn Agent proposals require SHUDDHO_AGENT_ACTION_PROPOSALS_ENABLED=true")
            if not self.action_social_publishing_enabled:
                raise ValueError("LinkedIn Agent proposals require SHUDDHO_ACTION_SOCIAL_PUBLISHING_ENABLED=true")
        if self.research_services_enabled and (self.search_provider != "tavily" or not self.search_api_key):
            raise ValueError("Research requires SHUDDHO_SEARCH_PROVIDER=tavily and backend-only TAVILY_API_KEY")
        if not self.database_url:
            raise ValueError("SHUDDHO_COWORKER_DATABASE_URL is required")
        issuer = urlparse(self.auth_issuer)
        if issuer.scheme != "https" or not issuer.netloc or issuer.username or issuer.password or issuer.query or issuer.fragment:
            raise ValueError("SHUDDHO_AUTH_ISSUER must be the HTTPS issuer of the managed identity provider")
        if min(self.max_daily_tasks, self.max_active_tasks, self.daily_token_budget,
               self.task_token_budget, self.max_account_bytes, self.max_daily_actions, self.max_action_recipients,
               self.max_active_agent_runs, self.agent_run_timeout_seconds, self.max_active_browser_sessions, self.browser_session_ttl_seconds, self.max_personal_goals, self.max_automations, self.max_memory_facts,
               self.max_memory_context_facts, self.max_memory_context_bytes, self.max_agent_context_items, self.max_agent_context_item_bytes,
               self.max_agent_context_bytes, self.max_memory_proposals, self.max_agent_planner_calls, self.max_agent_v3_planner_calls,
               self.agent_planner_token_budget, self.agent_planner_max_output_tokens, self.agent_v3_planner_token_budget,
               self.max_agent_handoff_bytes, self.max_agent_handoff_sources,
               self.max_agent_parallel_steps, self.cohort_max_users,
               self.provider_max_concurrent_calls, self.provider_max_concurrent_per_workspace,
               self.provider_max_reserved_tokens, self.provider_max_reserved_tokens_per_workspace,
               self.provider_daily_token_budget, self.provider_lease_seconds) < 1:
            raise ValueError("Coworker limits must be positive")
        if self.provider_max_concurrent_per_workspace > self.provider_max_concurrent_calls:
            raise ValueError("Per-workspace provider concurrency cannot exceed global concurrency")
        if self.provider_max_reserved_tokens_per_workspace > self.provider_max_reserved_tokens:
            raise ValueError("Per-workspace provider token reserve cannot exceed the global reserve")
        if self.daily_token_budget > self.provider_daily_token_budget:
            raise ValueError("Per-workspace daily token budget cannot exceed the global provider daily budget")
        if self.provider_lease_seconds <= self.model_timeout_seconds:
            raise ValueError("SHUDDHO_PROVIDER_LEASE_SECONDS must exceed the model timeout")
        if self.max_agent_parallel_steps > 4:
            raise ValueError("SHUDDHO_AGENT_MAX_PARALLEL_STEPS must be between 1 and 4")
        if self.max_action_recipients > 500:
            raise ValueError("SHUDDHO_ACTION_RECIPIENTS_MAX must be between 1 and 500")
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
