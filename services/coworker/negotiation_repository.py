from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from .action_registry import transaction_operation_key
from .config import Settings
from .errors import CoworkerError
from .models import (
    Account,
    AuditEvent,
    Connection,
    ExternalAction,
    NegotiationCase,
    NegotiationCaseRevision,
    NegotiationOffer,
    NegotiationProposal,
    Workspace,
    utcnow,
)
from .negotiation_schemas import (
    NegotiationCaseCreate,
    NegotiationCasePatch,
    NegotiationCaseTransition,
    NegotiationOfferCreate,
    NegotiationProposalDraft,
    NegotiationProposalRequest,
    NegotiationProposalReview,
)
from .repository import iso, not_found

CASE_LIMIT = 100
OFFER_LIMIT = 200
PROPOSAL_LIMIT = 100
PROPOSAL_TTL_HOURS = 24


class NegotiationRepository:
    """Owner-scoped durable negotiation context with append-only offer history."""

    def __init__(self, sessions, settings: Settings):
        self.sessions = sessions
        self.settings = settings

    def _require_enabled(self) -> None:
        if not self.settings.personal_transactions_enabled:
            raise CoworkerError(
                "personal_transactions_disabled",
                "Personal transaction workflows are not enabled in this deployment.",
                503,
            )

    @staticmethod
    def _fingerprint(value: dict) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _audit(db, owner: str, resource: str, action: str) -> None:
        db.add(
            AuditEvent(
                id=str(uuid4()),
                owner_id=owner,
                resource_id=resource,
                action=action,
            )
        )

    @staticmethod
    def _workspace(db, owner: str) -> str:
        workspace = db.scalar(
            select(Workspace.id).where(Workspace.owner_id == owner)
        )
        if workspace is None:
            raise not_found()
        return workspace

    @staticmethod
    def _case(
        db,
        owner: str,
        case_id: str,
        *,
        lock: bool = False,
    ) -> NegotiationCase:
        query = select(NegotiationCase).where(
            NegotiationCase.id == case_id,
            NegotiationCase.owner_id == owner,
        )
        if lock:
            query = query.with_for_update()
        value = db.scalar(query)
        if value is None:
            raise not_found()
        return value

    def _connection(self, db, owner: str, connection_id: str) -> Connection:
        row = db.scalar(
            select(Connection).where(
                Connection.id == connection_id,
                Connection.owner_id == owner,
            ).with_for_update()
        )
        if row is None:
            raise not_found()
        if not row.active or row.capability != "email":
            raise CoworkerError(
                "connection_removed",
                "Connect the matching email account before using this negotiation case.",
                409,
            )
        operation = transaction_operation_key(
            row.provider,
            "negotiation_commitment_email",
        )
        if operation not in self.settings.transaction_operations:
            raise CoworkerError(
                "personal_transaction_operation_disabled",
                "This provider negotiation operation has not been individually qualified for this deployment.",
                503,
            )
        return row

    @staticmethod
    def _snapshot(row: NegotiationCase) -> dict:
        return {
            "connection_id": row.connection_id,
            "provider": row.provider,
            "counterparty_name": row.counterparty_name,
            "counterparty_address": row.counterparty_address,
            "subject": row.subject,
            "objective": row.objective,
            "limits": list(row.limits),
            "state": row.state,
        }

    def _record_revision(self, db, row: NegotiationCase) -> None:
        db.add(
            NegotiationCaseRevision(
                case_id=row.id,
                revision=row.revision,
                owner_id=row.owner_id,
                snapshot=self._snapshot(row),
            )
        )

    @staticmethod
    def _offer_dto(row: NegotiationOffer) -> dict:
        return {
            "id": row.id,
            "sequence": row.sequence,
            "direction": row.direction,
            "kind": row.kind,
            "summary": row.summary,
            "terms": list(row.terms),
            "external_action_id": row.external_action_id,
            "occurred_at": iso(row.occurred_at),
            "created_at": iso(row.created_at),
        }

    @staticmethod
    def _proposal_hash(
        case_id: str,
        case_revision: int,
        history_sequence: int,
        kind: str,
        output_language: str,
        draft: dict,
    ) -> str:
        payload = {
            "schema_version": 1,
            "case_id": case_id,
            "case_revision": case_revision,
            "history_sequence": history_sequence,
            "kind": kind,
            "output_language": output_language,
            "draft": draft,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

    def _proposal_dto(
        self,
        row: NegotiationProposal,
        *,
        current_revision: int,
        current_history_sequence: int,
    ) -> dict:
        now = utcnow()
        state = row.state
        if state == "suggested" and row.expires_at <= now:
            state = "expired"
        elif state == "suggested" and (
            row.case_revision != current_revision
            or row.history_sequence != current_history_sequence
        ):
            state = "stale"
        return {
            "id": row.id,
            "case_id": row.case_id,
            "case_revision": row.case_revision,
            "history_sequence": row.history_sequence,
            "kind": row.kind,
            "output_language": row.output_language,
            "summary": row.summary,
            "terms": list(row.terms),
            "message": row.message,
            "rationale": row.rationale,
            "risk_notes": list(row.risk_notes),
            "proposal_hash": row.proposal_hash,
            "state": state,
            "model": row.model,
            "prompt_sha256": row.prompt_sha256,
            "created_at": iso(row.created_at),
            "expires_at": iso(row.expires_at),
            "reviewed_at": iso(row.reviewed_at),
        }

    @staticmethod
    def _history_sequence(db, case_id: str, owner: str) -> int:
        return int(
            db.scalar(
                select(func.coalesce(func.max(NegotiationOffer.sequence), 0)).where(
                    NegotiationOffer.case_id == case_id,
                    NegotiationOffer.owner_id == owner,
                )
            )
            or 0
        )

    def _dto(self, db, row: NegotiationCase) -> dict:
        offers = db.scalars(
            select(NegotiationOffer)
            .where(
                NegotiationOffer.case_id == row.id,
                NegotiationOffer.owner_id == row.owner_id,
            )
            .order_by(NegotiationOffer.sequence)
            .limit(OFFER_LIMIT)
        ).all()
        history_sequence = offers[-1].sequence if offers else 0
        proposals = db.scalars(
            select(NegotiationProposal)
            .where(
                NegotiationProposal.case_id == row.id,
                NegotiationProposal.owner_id == row.owner_id,
            )
            .order_by(NegotiationProposal.created_at.desc())
            .limit(PROPOSAL_LIMIT)
        ).all()
        return {
            "id": row.id,
            "connection_id": row.connection_id,
            "provider": row.provider,
            "counterparty_name": row.counterparty_name,
            "counterparty_address": row.counterparty_address,
            "subject": row.subject,
            "objective": row.objective,
            "limits": list(row.limits),
            "revision": row.revision,
            "state": row.state,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
            "offers": [self._offer_dto(item) for item in offers],
            "proposals": [
                self._proposal_dto(
                    item,
                    current_revision=row.revision,
                    current_history_sequence=history_sequence,
                )
                for item in proposals
            ],
        }

    @staticmethod
    def _check_revision(row: NegotiationCase, expected_revision: int) -> None:
        if row.revision != expected_revision:
            raise CoworkerError(
                "negotiation_revision_conflict",
                "This negotiation case changed. Review the latest revision before editing it.",
                409,
            )

    def create(
        self,
        owner: str,
        request: NegotiationCaseCreate,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        payload = request.model_dump(mode="json")
        fingerprint = self._fingerprint(payload)
        with self.sessions.begin() as db:
            if db.scalar(
                select(Account.id)
                .where(Account.id == owner)
                .with_for_update()
            ) is None:
                raise not_found()
            previous = db.scalar(
                select(NegotiationCase).where(
                    NegotiationCase.owner_id == owner,
                    NegotiationCase.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if not hmac.compare_digest(previous.fingerprint, fingerprint):
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different negotiation case.",
                        409,
                    )
                return self._dto(db, previous), False
            if db.scalar(
                select(func.count())
                .select_from(NegotiationCase)
                .where(NegotiationCase.owner_id == owner)
            ) >= CASE_LIMIT:
                raise CoworkerError(
                    "negotiation_case_limit",
                    "This workspace reached its negotiation case limit.",
                    429,
                )
            connection = self._connection(
                db,
                owner,
                str(request.connection_id),
            )
            now = utcnow()
            row = NegotiationCase(
                id=str(uuid4()),
                owner_id=owner,
                workspace_id=self._workspace(db, owner),
                connection_id=connection.id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                provider=connection.provider,
                counterparty_name=request.counterparty_name,
                counterparty_address=request.counterparty_address,
                subject=request.subject,
                objective=request.objective,
                limits=[
                    item.model_dump(mode="json")
                    for item in request.limits
                ],
                revision=1,
                state="active",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            self._record_revision(db, row)
            self._audit(db, owner, row.id, "negotiation_case.created")
            return self._dto(db, row), True

    def list(self, owner: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            rows = db.scalars(
                select(NegotiationCase)
                .where(NegotiationCase.owner_id == owner)
                .order_by(NegotiationCase.updated_at.desc())
                .limit(CASE_LIMIT)
            ).all()
            return [self._dto(db, row) for row in rows]

    def get(self, owner: str, case_id: str) -> dict:
        self._require_enabled()
        with self.sessions() as db:
            return self._dto(db, self._case(db, owner, case_id))

    def revisions(self, owner: str, case_id: str) -> list[dict]:
        self._require_enabled()
        with self.sessions() as db:
            self._case(db, owner, case_id)
            rows = db.scalars(
                select(NegotiationCaseRevision)
                .where(
                    NegotiationCaseRevision.case_id == case_id,
                    NegotiationCaseRevision.owner_id == owner,
                )
                .order_by(NegotiationCaseRevision.revision)
            ).all()
            return [
                {
                    "revision": row.revision,
                    "snapshot": row.snapshot,
                    "created_at": iso(row.created_at),
                }
                for row in rows
            ]

    def update(
        self,
        owner: str,
        case_id: str,
        request: NegotiationCasePatch,
    ) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = self._case(db, owner, case_id, lock=True)
            self._check_revision(row, request.expected_revision)
            if row.state in {"closed", "cancelled"}:
                raise CoworkerError(
                    "negotiation_case_not_editable",
                    "Closed or cancelled negotiation cases cannot be edited.",
                    409,
                )
            fields = request.model_fields_set - {"expected_revision"}
            if "subject" in fields:
                row.subject = request.subject
            if "objective" in fields:
                row.objective = request.objective
            if "limits" in fields:
                row.limits = [
                    item.model_dump(mode="json")
                    for item in request.limits or []
                ]
            row.revision += 1
            row.updated_at = utcnow()
            self._record_revision(db, row)
            self._audit(db, owner, row.id, "negotiation_case.updated")
            db.flush()
            return self._dto(db, row)

    def transition(
        self,
        owner: str,
        case_id: str,
        request: NegotiationCaseTransition,
    ) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            row = self._case(db, owner, case_id, lock=True)
            self._check_revision(row, request.expected_revision)
            if row.state in {"closed", "cancelled"}:
                raise CoworkerError(
                    "negotiation_case_terminal",
                    "Closed or cancelled negotiation cases cannot change state.",
                    409,
                )
            if request.state == row.state:
                return self._dto(db, row)
            if request.state == "active" and row.state != "paused":
                raise CoworkerError(
                    "negotiation_state",
                    "Only a paused negotiation case can be resumed.",
                    409,
                )
            row.state = request.state
            row.revision += 1
            row.updated_at = utcnow()
            self._record_revision(db, row)
            self._audit(
                db,
                owner,
                row.id,
                f"negotiation_case.{request.state}",
            )
            db.flush()
            return self._dto(db, row)

    def _confirmed_action(
        self,
        db,
        owner: str,
        case: NegotiationCase,
        action_id: str,
        request: NegotiationOfferCreate,
    ) -> ExternalAction:
        action = db.scalar(
            select(ExternalAction).where(
                ExternalAction.id == action_id,
                ExternalAction.owner_id == owner,
            )
        )
        if (
            action is None
            or action.state != "succeeded"
            or action.kind != "negotiation_commitment_email"
            or action.connection_id != case.connection_id
            or not isinstance(action.receipt, dict)
            or action.receipt.get("provider") != case.provider
            or action.receipt.get("status")
            != (
                "accepted_by_gmail"
                if case.provider == "google"
                else "accepted_by_microsoft_graph"
            )
        ):
            raise CoworkerError(
                "negotiation_action_unverified",
                "Link only a confirmed owned negotiation commitment from this case connection.",
                409,
            )
        payload = action.preview.get("payload")
        expected_terms = [
            item.model_dump(mode="json")
            for item in request.terms
        ]
        if (
            not isinstance(payload, dict)
            or payload.get("to") != [case.counterparty_address]
            or payload.get("counterparty") != case.counterparty_name
            or payload.get("commitment_summary") != request.summary
            or payload.get("terms") != expected_terms
        ):
            raise CoworkerError(
                "negotiation_action_changed",
                "The confirmed action does not exactly match this recorded commitment.",
                409,
            )
        return action

    def proposal_context(
        self,
        owner: str,
        case_id: str,
        request: NegotiationProposalRequest,
        idempotency_key: str,
    ) -> tuple[dict, dict | None]:
        self._require_enabled()
        with self.sessions() as db:
            case = self._case(db, owner, case_id)
            self._check_revision(case, request.expected_revision)
            if case.state != "active":
                raise CoworkerError(
                    "negotiation_case_inactive",
                    "Resume this negotiation case before generating a proposal.",
                    409,
                )
            self._connection(db, owner, case.connection_id)
            history_sequence = self._history_sequence(db, case.id, owner)
            fingerprint = self._fingerprint({
                "case_id": case.id,
                "case_revision": case.revision,
                "history_sequence": history_sequence,
                "kind": request.kind,
                "output_language": request.output_language,
            })
            previous = db.scalar(
                select(NegotiationProposal).where(
                    NegotiationProposal.owner_id == owner,
                    NegotiationProposal.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if not hmac.compare_digest(previous.fingerprint, fingerprint):
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different negotiation proposal.",
                        409,
                    )
                return {}, self._proposal_dto(
                    previous,
                    current_revision=case.revision,
                    current_history_sequence=history_sequence,
                )
            if db.scalar(
                select(func.count())
                .select_from(NegotiationProposal)
                .where(NegotiationProposal.owner_id == owner)
            ) >= PROPOSAL_LIMIT:
                raise CoworkerError(
                    "negotiation_proposal_limit",
                    "This workspace reached its saved negotiation proposal limit.",
                    429,
                )
            offers = db.scalars(
                select(NegotiationOffer)
                .where(
                    NegotiationOffer.case_id == case.id,
                    NegotiationOffer.owner_id == owner,
                )
                .order_by(NegotiationOffer.sequence.desc())
                .limit(40)
            ).all()
            context = {
                "fingerprint": fingerprint,
                "case_id": case.id,
                "case_revision": case.revision,
                "history_sequence": history_sequence,
                "subject": case.subject,
                "objective": case.objective,
                "counterparty_name": case.counterparty_name,
                "limits": list(case.limits),
                "offers": [
                    {
                        "sequence": item.sequence,
                        "direction": item.direction,
                        "kind": item.kind,
                        "summary": item.summary,
                        "terms": list(item.terms),
                        "occurred_at": iso(item.occurred_at),
                    }
                    for item in reversed(offers)
                ],
            }
            return context, None

    def save_proposal(
        self,
        owner: str,
        case_id: str,
        request: NegotiationProposalRequest,
        idempotency_key: str,
        context: dict,
        draft: NegotiationProposalDraft,
        *,
        model: str,
        prompt_sha256: str,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        draft_value = draft.model_dump(mode="json")
        with self.sessions.begin() as db:
            case = self._case(db, owner, case_id, lock=True)
            self._check_revision(case, request.expected_revision)
            history_sequence = self._history_sequence(db, case.id, owner)
            if (
                context.get("case_revision") != case.revision
                or context.get("history_sequence") != history_sequence
            ):
                raise CoworkerError(
                    "negotiation_proposal_stale",
                    "This negotiation changed while the proposal was being prepared. Generate a fresh proposal.",
                    409,
                )
            previous = db.scalar(
                select(NegotiationProposal).where(
                    NegotiationProposal.owner_id == owner,
                    NegotiationProposal.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if not hmac.compare_digest(
                    previous.fingerprint,
                    str(context.get("fingerprint", "")),
                ):
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different negotiation proposal.",
                        409,
                    )
                return self._proposal_dto(
                    previous,
                    current_revision=case.revision,
                    current_history_sequence=history_sequence,
                ), False
            proposal_hash = self._proposal_hash(
                case.id,
                case.revision,
                history_sequence,
                request.kind,
                request.output_language,
                draft_value,
            )
            now = utcnow()
            row = NegotiationProposal(
                id=str(uuid4()),
                case_id=case.id,
                owner_id=owner,
                idempotency_key=idempotency_key,
                fingerprint=str(context["fingerprint"]),
                case_revision=case.revision,
                history_sequence=history_sequence,
                kind=request.kind,
                output_language=request.output_language,
                summary=draft.summary,
                terms=[item.model_dump(mode="json") for item in draft.terms],
                message=draft.message,
                rationale=draft.rationale,
                risk_notes=list(draft.risk_notes),
                proposal_hash=proposal_hash,
                state="suggested",
                model=model,
                prompt_sha256=prompt_sha256,
                created_at=now,
                expires_at=now + timedelta(hours=PROPOSAL_TTL_HOURS),
                reviewed_at=None,
            )
            db.add(row)
            self._audit(db, owner, row.id, "negotiation_proposal.generated")
            db.flush()
            return self._proposal_dto(
                row,
                current_revision=case.revision,
                current_history_sequence=history_sequence,
            ), True

    def dismiss_proposal(
        self,
        owner: str,
        case_id: str,
        proposal_id: str,
        review: NegotiationProposalReview,
    ) -> dict:
        self._require_enabled()
        with self.sessions.begin() as db:
            case = self._case(db, owner, case_id)
            row = db.scalar(
                select(NegotiationProposal).where(
                    NegotiationProposal.id == proposal_id,
                    NegotiationProposal.case_id == case.id,
                    NegotiationProposal.owner_id == owner,
                ).with_for_update()
            )
            if row is None:
                raise not_found()
            if not hmac.compare_digest(row.proposal_hash, review.proposal_hash):
                raise CoworkerError(
                    "negotiation_proposal_changed",
                    "This negotiation proposal changed. Review the latest proposal before acting on it.",
                    409,
                )
            if row.state == "suggested":
                row.state = "dismissed"
                row.reviewed_at = utcnow()
                self._audit(db, owner, row.id, "negotiation_proposal.dismissed")
            history_sequence = self._history_sequence(db, case.id, owner)
            return self._proposal_dto(
                row,
                current_revision=case.revision,
                current_history_sequence=history_sequence,
            )

    def append_offer(
        self,
        owner: str,
        case_id: str,
        request: NegotiationOfferCreate,
        idempotency_key: str,
    ) -> tuple[dict, bool]:
        self._require_enabled()
        payload = request.model_dump(mode="json")
        fingerprint = self._fingerprint(
            {"case_id": case_id, "payload": payload}
        )
        with self.sessions.begin() as db:
            case = self._case(db, owner, case_id, lock=True)
            previous = db.scalar(
                select(NegotiationOffer).where(
                    NegotiationOffer.owner_id == owner,
                    NegotiationOffer.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if not hmac.compare_digest(previous.fingerprint, fingerprint):
                    raise CoworkerError(
                        "idempotency_conflict",
                        "This request key belongs to a different negotiation offer.",
                        409,
                    )
                return self._offer_dto(previous), False
            if case.state != "active":
                raise CoworkerError(
                    "negotiation_case_inactive",
                    "Resume this negotiation case before adding an offer.",
                    409,
                )
            self._connection(db, owner, case.connection_id)
            count = db.scalar(
                select(func.count())
                .select_from(NegotiationOffer)
                .where(NegotiationOffer.case_id == case.id)
            )
            if count >= OFFER_LIMIT:
                raise CoworkerError(
                    "negotiation_offer_limit",
                    "This negotiation case reached its offer-history limit.",
                    429,
                )
            action_id = (
                str(request.external_action_id)
                if request.external_action_id is not None
                else None
            )
            if action_id is not None:
                self._confirmed_action(
                    db,
                    owner,
                    case,
                    action_id,
                    request,
                )
            sequence = int(count) + 1
            row = NegotiationOffer(
                id=str(uuid4()),
                case_id=case.id,
                owner_id=owner,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                sequence=sequence,
                direction=request.direction,
                kind=request.kind,
                summary=request.summary,
                terms=[
                    item.model_dump(mode="json")
                    for item in request.terms
                ],
                external_action_id=action_id,
                occurred_at=request.occurred_at,
                created_at=utcnow(),
            )
            db.add(row)
            case.updated_at = utcnow()
            self._audit(db, owner, case.id, "negotiation_offer.appended")
            db.flush()
            return self._offer_dto(row), True
