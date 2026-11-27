"""Deterministic, non-secret runtime build and configuration identity.

The build digest is a runtime fingerprint over the checked-out source revision,
locked project inputs, interpreter/platform identity and installed distribution
inventory. It is not represented as a signed OCI image digest.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import stat
import sys
from pathlib import Path
from typing import Iterable

from services.coworker.config import Settings, enabled

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_TOOL_ID = "uv==0.7.22"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DISTRIBUTION_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,159}$")
MAX_BUILD_INPUT_BYTES = 5 * 1024 * 1024


class RuntimeIdentityError(ValueError):
    """Build or runtime identity cannot be established safely."""


def canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        raise RuntimeIdentityError("Runtime identity is not canonical JSON.") from None


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _read_build_input(root: Path, name: str) -> bytes:
    base = root.resolve(strict=True)
    path = base / name
    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeIdentityError(f"Required build input {name} is unavailable.") from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeIdentityError(f"Build input {name} must be a regular non-symlink file.")
    if metadata.st_size <= 0 or metadata.st_size > MAX_BUILD_INPUT_BYTES:
        raise RuntimeIdentityError(f"Build input {name} has an invalid size.")
    resolved = path.resolve(strict=True)
    if resolved.parent != base:
        raise RuntimeIdentityError(f"Build input {name} escapes the project root.")
    try:
        return resolved.read_bytes()
    except OSError:
        raise RuntimeIdentityError(f"Required build input {name} cannot be read.") from None


def _normalise_distributions(
    distributions: Iterable[tuple[str, str]] | None,
) -> list[dict[str, str]]:
    if distributions is None:
        observed: list[tuple[str, str]] = []
        try:
            for distribution in importlib.metadata.distributions():
                name = distribution.metadata.get("Name")
                version = distribution.version
                if not isinstance(name, str) or not isinstance(version, str):
                    raise RuntimeIdentityError("Installed distribution metadata is incomplete.")
                observed.append((name, version))
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeIdentityError("Installed distribution inventory is unavailable.") from None
        distributions = observed

    normalised: dict[str, str] = {}
    for name, version in distributions:
        if not isinstance(name, str) or not isinstance(version, str) or not version.strip():
            raise RuntimeIdentityError("Installed distribution metadata is invalid.")
        canonical_name = re.sub(r"[-_.]+", "-", name.strip()).lower()
        if not DISTRIBUTION_NAME_RE.fullmatch(canonical_name):
            raise RuntimeIdentityError("Installed distribution name is invalid.")
        if canonical_name in normalised and normalised[canonical_name] != version.strip():
            raise RuntimeIdentityError("Conflicting installed distribution versions were found.")
        normalised[canonical_name] = version.strip()
    if not normalised:
        raise RuntimeIdentityError("Installed distribution inventory is empty.")
    return [{"name": name, "version": normalised[name]} for name in sorted(normalised)]


def compute_build_digest(
    *,
    root: Path,
    source_revision: str,
    distributions: Iterable[tuple[str, str]] | None = None,
    python_implementation: str | None = None,
    python_version: str | None = None,
    platform_identity: str | None = None,
    allow_unknown_revision: bool = False,
) -> str:
    """Fingerprint exact source/build inputs without exposing package or host data."""
    if not isinstance(source_revision, str) or not (
        SHA1_RE.fullmatch(source_revision)
        or (allow_unknown_revision and source_revision == "unknown")
    ):
        raise RuntimeIdentityError("Build source revision must be a full lowercase commit SHA.")
    project_bytes = _read_build_input(Path(root), "pyproject.toml")
    lock_bytes = _read_build_input(Path(root), "uv.lock")
    inventory = _normalise_distributions(distributions)
    implementation = python_implementation or platform.python_implementation()
    version = python_version or platform.python_version()
    platform_value = platform_identity or f"{platform.system().lower()}-{platform.machine().lower()}"
    if not isinstance(implementation, str) or not implementation.strip():
        raise RuntimeIdentityError("Python implementation identity is invalid.")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise RuntimeIdentityError("Python version identity is invalid.")
    if not isinstance(platform_value, str) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", platform_value):
        raise RuntimeIdentityError("Build platform identity is invalid.")
    payload = {
        "schema_version": 1,
        "source_revision": source_revision,
        "build_tool": BUILD_TOOL_ID,
        "pyproject_sha256": hashlib.sha256(project_bytes).hexdigest(),
        "uv_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "python_implementation": implementation,
        "python_version": version,
        "platform_identity": platform_value,
        "installed_distributions_sha256": canonical_sha256(inventory),
    }
    return canonical_sha256(payload)


def runtime_manifest_payload(settings: Settings, repository) -> dict:
    """Return the stable v2 capability payload shared by API and worker."""
    reviewed_skills = repository.reviewed_skill_runtime_manifest()
    capabilities = {
        "coworker": enabled(),
        "work_services": settings.work_services_enabled,
        "artifact_services": settings.artifact_services_enabled,
        "agent_runtime": settings.agent_runtime_enabled,
        "conversations": settings.conversations_enabled,
        "projects": settings.projects_enabled and settings.conversations_enabled,
        "fly_github": settings.fly_github_enabled,
        "conversation_replies": settings.conversations_enabled and settings.conversation_replies_enabled and settings.chat_provider_configured,
        "grounded_conversation_replies": settings.conversations_enabled and settings.conversation_replies_enabled and settings.chat_provider_configured,
        "runtime_v3": settings.agent_runtime_v3_enabled,
        "context_retrieval": settings.context_retrieval_enabled,
        "personal_goals": settings.personal_goals_enabled,
        "automations": settings.automations_enabled,
        "intelligent_planner": settings.intelligent_planner_enabled,
        "memory": settings.agent_memory_enabled,
        "handoffs": settings.agent_handoffs_enabled,
        "multi_handoffs": settings.agent_multi_handoffs_enabled,
        "dependency_graph": settings.agent_dependency_graph_enabled,
        "parallel_execution": settings.agent_parallel_execution_enabled,
        "outcome_replan": settings.agent_outcome_replan_enabled,
        "research": settings.research_services_enabled,
        "actions": settings.actions_enabled,
        "connector_trust_boundary": settings.connector_trust_boundary_enabled,
        "connector_reads": settings.connector_reads_enabled,
        "browser": settings.browser_enabled,
        "agent_browser_read": settings.agent_browser_read_enabled,
        "code_execution": settings.code_execution_enabled,
        "agent_sandbox_tool": settings.agent_sandbox_tool_enabled,
        "action_attachments": settings.action_attachments_enabled,
        "action_reminders": settings.action_reminders_enabled,
        "action_recipients": settings.action_recipients_enabled,
        "action_document_sharing": settings.action_document_sharing_enabled,
        "action_email_threading": settings.action_email_threading_enabled,
        "action_social_publishing": settings.action_social_publishing_enabled,
        "personal_transactions": settings.personal_transactions_enabled,
        "restaurant_reservations": settings.restaurant_reservations_enabled,
        "shopping_checkout": settings.shopping_checkout_enabled,
        "travel_booking": settings.travel_booking_enabled,
        "action_selection": settings.agent_action_selection_enabled,
        "action_proposals": settings.agent_action_proposals_enabled,
        "negotiation_proposal_promotion": settings.negotiation_proposal_promotion_enabled,
        "agent_linkedin_proposals": settings.agent_linkedin_proposals_enabled,
        "browser_push": settings.browser_push_enabled,
        "reviewed_research": (
            settings.agent_reviewed_research_skill_enabled
            and reviewed_skills["research"]["state"] == "selected"
        ),
    }
    providers: list[str] = []
    if settings.actions_enabled:
        providers.append("google")
        if settings.microsoft_actions_enabled:
            providers.append("microsoft")
        if settings.action_social_publishing_enabled:
            providers.append("linkedin")
        if settings.restaurant_reservations_enabled:
            providers.append("opentable")
        if settings.shopping_checkout_enabled or settings.travel_booking_enabled:
            for operation in sorted(settings.transaction_operations):
                provider, separator, kind = operation.partition(":")
                if (
                    separator
                    and kind in {"shopping_checkout_create", "travel_booking_create"}
                    and provider not in providers
                ):
                    providers.append(provider)
    return {
        "source_revision": settings.source_revision,
        "environment": settings.environment,
        "capabilities": capabilities,
        "canonical_only_capabilities": {
            "suggestion_model_relevance": settings.suggestion_model_relevance_enabled,
        },
        "reviewed_skills": reviewed_skills,
        "action_providers": providers,
        "cohort": {
            "enforced": settings.cohort_enforced,
            "configured_members": len(settings.cohort_account_ids),
            "max_users": settings.cohort_max_users,
        },
    }


def build_runtime_identity(
    settings: Settings,
    repository,
    *,
    root: Path = PROJECT_ROOT,
    distributions: Iterable[tuple[str, str]] | None = None,
    python_implementation: str | None = None,
    python_version: str | None = None,
    platform_identity: str | None = None,
    task_queue: str | None = None,
) -> dict:
    """Build a stable API/worker identity from the same process configuration."""
    source_revision = settings.source_revision or "unknown"
    if settings.environment != "development" and not SHA1_RE.fullmatch(source_revision):
        raise RuntimeIdentityError("Runtime source revision is not an immutable commit SHA.")
    schema_revision = repository.current_schema_revision()
    if not isinstance(schema_revision, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,128}", schema_revision):
        raise RuntimeIdentityError("Runtime database schema revision is unavailable.")
    provider = settings.chat_provider
    if provider == "deepseek":
        model_id = settings.deepseek_model
    elif provider == "gemma":
        model_id = settings.gemma_model
    else:
        raise RuntimeIdentityError("Runtime model provider is unsupported.")
    if not isinstance(model_id, str) or not MODEL_ID_RE.fullmatch(model_id):
        raise RuntimeIdentityError("Runtime model identity is invalid.")
    queue = task_queue or settings.task_queue
    if not isinstance(queue, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", queue):
        raise RuntimeIdentityError("Runtime task queue identity is invalid.")
    build_digest = compute_build_digest(
        root=root,
        source_revision=source_revision,
        distributions=distributions,
        python_implementation=python_implementation,
        python_version=python_version,
        platform_identity=platform_identity,
        allow_unknown_revision=settings.environment == "development",
    )
    payload = {
        "schema_version": 3,
        **runtime_manifest_payload(settings, repository),
        "source_revision": source_revision,
        "build_digest": build_digest,
        "schema_revision": schema_revision,
        "model_provider": provider,
        "model_id": model_id,
        "task_queue": queue,
    }
    payload["runtime_identity_sha256"] = canonical_sha256(payload)
    return payload


def _build_source_revision() -> str:
    for name in ("RENDER_GIT_COMMIT", "GITHUB_SHA", "SHUDDHO_SOURCE_REVISION"):
        value = os.getenv(name, "").strip()
        if value:
            if not SHA1_RE.fullmatch(value):
                raise RuntimeIdentityError(f"{name} must contain a full lowercase commit SHA.")
            return value
    raise RuntimeIdentityError("Render/Git build source revision is unavailable.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print the non-secret Shuddho build fingerprint.")
    parser.add_argument("command", choices=("print-build-digest",))
    args = parser.parse_args(argv)
    if args.command == "print-build-digest":
        digest = compute_build_digest(root=PROJECT_ROOT, source_revision=_build_source_revision())
        sys.stdout.write(json.dumps({"source_revision": _build_source_revision(), "build_digest": digest}, sort_keys=True) + "\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
