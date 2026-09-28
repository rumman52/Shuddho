from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .action_schemas import address, clean_text


class NegotiationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NegotiationLimit(NegotiationModel):
    name: str = Field(min_length=1, max_length=100)
    comparison: Literal["at_most", "at_least", "exact", "avoid"]
    value: str = Field(min_length=1, max_length=500)

    @field_validator("name", "value")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Negotiation limits cannot be blank")
        return value


class NegotiationOfferTerm(NegotiationModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)

    @field_validator("name", "value")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Offer terms cannot be blank")
        return value


class NegotiationCaseCreate(NegotiationModel):
    connection_id: UUID
    counterparty_name: str = Field(min_length=1, max_length=300)
    counterparty_address: str
    subject: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=4000)
    limits: list[NegotiationLimit] = Field(default_factory=list, max_length=20)

    @field_validator("counterparty_address")
    @classmethod
    def valid_address(cls, value: str) -> str:
        return address(value)

    @field_validator("counterparty_name", "subject", "objective")
    @classmethod
    def safe_case_text(cls, value: str) -> str:
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Negotiation case text cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_limits(self):
        names = [item.name.casefold() for item in self.limits]
        if len(names) != len(set(names)):
            raise ValueError("Negotiation limit names must be unique")
        return self


class NegotiationCasePatch(NegotiationModel):
    expected_revision: int = Field(ge=1)
    subject: str | None = Field(default=None, min_length=1, max_length=300)
    objective: str | None = Field(default=None, min_length=1, max_length=4000)
    limits: list[NegotiationLimit] | None = Field(default=None, max_length=20)

    @field_validator("subject", "objective")
    @classmethod
    def safe_case_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Negotiation case text cannot be blank")
        return value

    @model_validator(mode="after")
    def has_change(self):
        fields = self.model_fields_set - {"expected_revision"}
        if not fields:
            raise ValueError("Patch at least one negotiation case field")
        null_fields = sorted(
            field
            for field in fields & {"subject", "objective", "limits"}
            if getattr(self, field) is None
        )
        if null_fields:
            raise ValueError(
                "Negotiation case fields cannot be null: "
                + ", ".join(null_fields)
            )
        if self.limits is not None:
            names = [item.name.casefold() for item in self.limits]
            if len(names) != len(set(names)):
                raise ValueError("Negotiation limit names must be unique")
        return self


class NegotiationCaseTransition(NegotiationModel):
    expected_revision: int = Field(ge=1)
    state: Literal["active", "paused", "closed", "cancelled"]


class NegotiationOfferCreate(NegotiationModel):
    direction: Literal["ours", "theirs"]
    kind: Literal["proposal", "counteroffer", "commitment", "response"]
    summary: str = Field(min_length=1, max_length=4000)
    terms: list[NegotiationOfferTerm] = Field(default_factory=list, max_length=20)
    external_action_id: UUID | None = None
    occurred_at: datetime

    @field_validator("summary")
    @classmethod
    def safe_summary(cls, value: str) -> str:
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Offer summary cannot be blank")
        return value

    @field_validator("occurred_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Offer time must include a timezone offset")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Offer time cannot be more than five minutes in the future")
        return value

    @model_validator(mode="after")
    def linked_action_boundary(self):
        if self.external_action_id is not None and (
            self.direction != "ours" or self.kind != "commitment"
        ):
            raise ValueError(
                "Only an outgoing commitment may link a confirmed PA-09 action"
            )
        names = [item.name.casefold() for item in self.terms]
        if len(names) != len(set(names)):
            raise ValueError("Offer term names must be unique")
        return self
