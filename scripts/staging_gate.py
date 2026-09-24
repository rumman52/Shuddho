from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_GATES = {
    "ci": "Dedicated repository CI, including Coworker/Temporal recovery, is green.",
    "identity": "Managed identity is configured and owner isolation is verified.",
    "database": "Production PostgreSQL is configured with TLS and migrations applied.",
    "storage": "Private object storage is configured and owner-scoped download checks pass.",
    "temporal": "Production Temporal is reachable and worker restart/replay has been verified.",
    "model": "A live DeepSeek call and planner evaluation have passed in staging.",
    "quality": "Curated multilingual live Coworker quality/fidelity evaluation passed with recorded latency and token evidence.",
    "backup_restore": "Database/object backup and restore has been exercised successfully.",
    "deletion": "Retention/deletion operations have been verified against owned data.",
    "parallel_restart": "Two-branch AgentWorkflow v2 restart completes without duplicate child tasks or artifacts.",
    "fan_in": "Fan-in starts only after every persisted dependency completes.",
    "flag_rollback": "Disabling Agent parallel execution routes new runs back to v1.",
}
CONDITIONAL_GATES = {
    "research": "Live search provider retrieval/citation validation passed.",
    "actions": "Live Google approval/execution/receipt validation passed without auto-approval.",
    "action_attachments": "Live approved email attachment validation passed with an immutable artifact manifest and provider receipt.",
    "action_reminders_google": "Live Google Calendar explicit-reminder validation passed through immutable approval and exact provider receipt checks.",
    "action_reminders_microsoft": "Live Microsoft Calendar explicit-reminder validation passed through immutable approval and exact provider receipt checks.",
    "action_recipients": "Live saved-recipient CRUD, exact value preservation, owner isolation, cross-owner denial, deletion and cleanup passed.",
    "action_document_sharing": "Live Google Drive sharing passed exact owned-artifact hash binding, explicit approval, reader-only permission and provider receipt validation.",
    "action_email_threading": "Live Gmail owned-thread follow-up passed send-only parent binding, explicit approval, exact recipient/subject preservation and stable provider thread identity.",
    "action_social_publishing": "Live LinkedIn personal text publishing passed exact member/text binding, no auto-publish, wrong-hash denial, explicit approval and confirmed provider post receipt.",
    "microsoft_actions": "Live Microsoft Graph approval/execution/receipt validation passed without auto-approval.",
    "action_selection": "Live Agent planner selected only opaque attached-action handles and still paused for explicit user approval.",
    "action_proposals": "Live Agent generated only inert typed action proposals; promotion created a separate preview and never auto-approved or executed it.",
    "agent_linkedin_proposals": "Live intelligent planner generated only an inert personal LinkedIn text proposal; wrong-hash promotion failed; exact user-selected LinkedIn promotion created one unapproved immutable preview with no provider mutation.",
}


def load_evidence(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Staging evidence must be a JSON object")
    return value


def evaluate(
    evidence: dict,
    *,
    require_research: bool,
    require_actions: bool,
    require_microsoft_actions: bool = False,
    require_action_attachments: bool = False,
    require_action_reminders: bool = False,
    require_microsoft_action_reminders: bool = False,
    require_action_recipients: bool = False,
    require_action_document_sharing: bool = False,
    require_action_email_threading: bool = False,
    require_action_social_publishing: bool = False,
    require_action_selection: bool = False,
    require_action_proposals: bool = False,
    require_agent_linkedin_proposals: bool = False,
) -> dict:
    required = dict(REQUIRED_GATES)
    if require_research:
        required["research"] = CONDITIONAL_GATES["research"]
    if require_actions:
        required["actions"] = CONDITIONAL_GATES["actions"]
    if require_microsoft_actions:
        required["microsoft_actions"] = CONDITIONAL_GATES["microsoft_actions"]
    if require_action_attachments:
        required["action_attachments"] = CONDITIONAL_GATES["action_attachments"]
    if require_action_reminders:
        required["action_reminders_google"] = CONDITIONAL_GATES["action_reminders_google"]
    if require_microsoft_action_reminders:
        required["action_reminders_microsoft"] = CONDITIONAL_GATES["action_reminders_microsoft"]
    if require_action_recipients:
        required["action_recipients"] = CONDITIONAL_GATES["action_recipients"]
    if require_action_document_sharing:
        required["action_document_sharing"] = CONDITIONAL_GATES["action_document_sharing"]
    if require_action_email_threading:
        required["action_email_threading"] = CONDITIONAL_GATES["action_email_threading"]
    if require_action_social_publishing:
        required["action_social_publishing"] = CONDITIONAL_GATES["action_social_publishing"]
    if require_action_selection:
        required["action_selection"] = CONDITIONAL_GATES["action_selection"]
    if require_action_proposals:
        required["action_proposals"] = CONDITIONAL_GATES["action_proposals"]
    if require_agent_linkedin_proposals:
        required["agent_linkedin_proposals"] = CONDITIONAL_GATES["agent_linkedin_proposals"]
    checks = []
    for key, description in required.items():
        record = evidence.get(key)
        evidence_ref = record.get("evidence") if isinstance(record, dict) else None
        passed = (
            isinstance(record, dict)
            and record.get("status") == "passed"
            and isinstance(evidence_ref, str)
            and bool(evidence_ref.strip())
        )
        checks.append({
            "id": key,
            "passed": passed,
            "description": description,
            "evidence": evidence_ref,
        })
    missing = [item["id"] for item in checks if not item["passed"]]
    return {
        "decision": "GO" if not missing else "NO-GO",
        "required": len(checks),
        "passed": len(checks) - len(missing),
        "missing": missing,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Shuddho Coworker production staging evidence.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--require-research", action="store_true")
    parser.add_argument("--require-actions", action="store_true")
    parser.add_argument("--require-microsoft-actions", action="store_true")
    parser.add_argument("--require-action-attachments", action="store_true")
    parser.add_argument("--require-action-reminders", action="store_true")
    parser.add_argument("--require-microsoft-action-reminders", action="store_true")
    parser.add_argument("--require-action-recipients", action="store_true")
    parser.add_argument("--require-action-document-sharing", action="store_true")
    parser.add_argument("--require-action-email-threading", action="store_true")
    parser.add_argument("--require-action-social-publishing", action="store_true")
    parser.add_argument("--require-action-selection", action="store_true")
    parser.add_argument("--require-action-proposals", action="store_true")
    parser.add_argument("--require-agent-linkedin-proposals", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(
        load_evidence(args.evidence),
        require_research=args.require_research,
        require_actions=args.require_actions,
        require_microsoft_actions=args.require_microsoft_actions,
        require_action_attachments=args.require_action_attachments,
        require_action_reminders=args.require_action_reminders,
        require_microsoft_action_reminders=args.require_microsoft_action_reminders,
        require_action_recipients=args.require_action_recipients,
        require_action_document_sharing=args.require_action_document_sharing,
        require_action_email_threading=args.require_action_email_threading,
        require_action_social_publishing=args.require_action_social_publishing,
        require_action_selection=args.require_action_selection,
        require_action_proposals=args.require_action_proposals,
        require_agent_linkedin_proposals=args.require_agent_linkedin_proposals,
    )
    encoded = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    if result["decision"] != "GO":
        raise SystemExit("Staging gate is NO-GO: " + ", ".join(result["missing"]))


if __name__ == "__main__":
    main()
