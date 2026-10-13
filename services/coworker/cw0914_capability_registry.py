"""CW-09 to CW-14 capability qualification boundaries.

This module keeps capability activation explicit. A capability may have code present
without being production enabled until its qualification evidence exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CapabilityState = Literal["disabled", "experimental", "qualified"]


@dataclass(frozen=True)
class CapabilityQualification:
    name: str
    state: CapabilityState
    requires_evidence: tuple[str, ...]
    default_enabled: bool = False

    def enabled(self) -> bool:
        return self.state == "qualified" and self.default_enabled


CW09_14_CAPABILITIES = {
    "browser_research": CapabilityQualification(
        name="browser_research",
        state="experimental",
        requires_evidence=(
            "typed_tool_contract",
            "isolated_browser_worker",
            "source_provenance",
        ),
    ),
    "generated_code_execution": CapabilityQualification(
        name="generated_code_execution",
        state="experimental",
        requires_evidence=(
            "sandbox_isolation",
            "code_review_boundary",
            "execution_audit",
        ),
    ),
    "versioned_skills": CapabilityQualification(
        name="versioned_skills",
        state="experimental",
        requires_evidence=(
            "skill_manifest",
            "compatibility_check",
            "rollback_metadata",
        ),
    ),
    "proactive_scheduled_work": CapabilityQualification(
        name="proactive_scheduled_work",
        state="experimental",
        requires_evidence=(
            "consent_record",
            "scheduler_recovery",
            "notification_ledger",
        ),
    ),
    "event_driven_work": CapabilityQualification(
        name="event_driven_work",
        state="experimental",
        requires_evidence=(
            "event_freshness",
            "revocation_path",
            "duplicate_delivery_test",
        ),
    ),
    "transaction_provider_proofs": CapabilityQualification(
        name="transaction_provider_proofs",
        state="disabled",
        requires_evidence=(
            "provider_contract",
            "idempotency_proof",
            "receipt_reconciliation",
        ),
    ),
}


def capability_status(name: str) -> dict:
    capability = CW09_14_CAPABILITIES[name]
    return {
        "name": capability.name,
        "state": capability.state,
        "enabled": capability.enabled(),
        "requires_evidence": list(capability.requires_evidence),
    }


def list_capabilities() -> list[dict]:
    return [capability_status(name) for name in CW09_14_CAPABILITIES]
