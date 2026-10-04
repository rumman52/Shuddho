"""Only registered, explicitly typed actions may cross the external-action boundary."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Text = Annotated[str, StringConstraints(max_length=20000)]
Short = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Capability = Literal["email", "calendar", "drive", "social", "email_read", "calendar_read"]


def address(value: str) -> str:
    # Bare ASCII mailboxes only in v1. International text remains fully UTF-8;
    # IDN domains may be supplied as punycode. Reject headers/display names.
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9.-]+", value):
        raise ValueError("Use a complete email address without a display name")
    local, domain = value.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("Invalid email address")
    if "." not in domain or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part) for part in domain.split(".")):
        raise ValueError("Invalid email domain")
    return local + "@" + domain.lower()


def clean_text(value: str) -> str:
    if any(ord(c) < 32 and c not in "\n\t" or 0x7f <= ord(c) <= 0x9f or 0xd800 <= ord(c) <= 0xdfff for c in value):
        raise ValueError("Unsupported control characters")
    return value


class EmailSend(Strict):
    kind: Literal["email_send"]
    to: list[str] = Field(min_length=1, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    bcc: list[str] = Field(default_factory=list, max_length=20)
    subject: Short
    body: Text = Field(min_length=1)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def addresses(cls, values):
        return [address(value) for value in values]

    @field_validator("subject", "body")
    @classmethod
    def text(cls, value):
        return clean_text(value)

    @model_validator(mode="after")
    def recipients(self):
        values = [x.casefold() for x in self.to + self.cc + self.bcc]
        if len(values) > 20 or len(values) != len(set(values)) or "\n" in self.subject or not self.subject.strip() or not self.body.strip():
            raise ValueError("Use unique recipients (up to 20) and a subject on one line")
        return self


def zoned_time(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is not None:
        local = value.astimezone(zone)
        if value.replace(tzinfo=None) != local.replace(tzinfo=None) or value.utcoffset() != local.utcoffset():
            raise ValueError("The UTC offset does not match the selected time zone")
        return local
    candidates = {}
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        utc = candidate.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == value:
            candidates[utc] = candidate
    if len(candidates) != 1:
        raise ValueError("This local time is ambiguous or skipped by daylight saving; choose another time or supply its explicit offset")
    return next(iter(candidates.values()))


class EmailSendWithAttachments(EmailSend):
    kind: Literal["email_send_with_attachments"]


class EmailThreadReply(EmailSend):
    kind: Literal["email_thread_reply"]
    parent_action_id: UUID

    @model_validator(mode="after")
    def thread_boundary(self):
        if self.bcc:
            raise ValueError("Thread replies do not allow Bcc recipients")
        return self


class NegotiationTerm(Strict):
    name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    value: Annotated[str, StringConstraints(min_length=1, max_length=500)]

    @field_validator("name", "value")
    @classmethod
    def safe_term(cls, value):
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Negotiation terms cannot be blank")
        return value


class NegotiationCommitmentEmail(EmailSend):
    kind: Literal["negotiation_commitment_email"]
    counterparty: Short
    commitment_summary: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    terms: list[NegotiationTerm] = Field(min_length=1, max_length=20)

    @field_validator("counterparty", "commitment_summary")
    @classmethod
    def safe_commitment_text(cls, value):
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Commitment details cannot be blank")
        return value

    @model_validator(mode="after")
    def exact_terms(self):
        names = [item.name.casefold() for item in self.terms]
        if len(names) != len(set(names)):
            raise ValueError("Negotiation term names must be unique")
        if len(self.to) != 1 or self.bcc:
            raise ValueError("Binding negotiation commitments require exactly one primary counterparty and do not allow Bcc")
        return self


class CalendarCreate(Strict):
    kind: Literal["calendar_create"]
    title: Short
    description: Text = ""
    location: Annotated[str, StringConstraints(max_length=500)] = ""
    start_at: datetime
    end_at: datetime
    time_zone: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    attendees: list[str] = Field(default_factory=list, max_length=20)
    # Primary calendar, notifications to all listed guests, no recurrence,
    # conference or attachment. Base calendar_create has no reminder; the
    # explicit reminder variant below adds one bounded reminder. These
    # policies appear in the immutable preview.

    @field_validator("title", "description", "location")
    @classmethod
    def text(cls, value):
        return clean_text(value)

    @field_validator("attendees")
    @classmethod
    def guests(cls, values):
        values = [address(value) for value in values]
        if len(set(x.casefold() for x in values)) != len(values):
            raise ValueError("Use unique attendees")
        return values

    @model_validator(mode="after")
    def times(self):
        try:
            zone = ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Select a valid IANA time zone") from None
        self.start_at = zoned_time(self.start_at, zone)
        self.end_at = zoned_time(self.end_at, zone)
        duration = self.end_at.astimezone(timezone.utc) - self.start_at.astimezone(timezone.utc)
        if duration <= timedelta() or duration > timedelta(days=7) or not self.title.strip():
            raise ValueError("Use a title and an end after the start, within seven days")
        return self


class CalendarCreateWithReminder(CalendarCreate):
    kind: Literal["calendar_create_with_reminder"]
    reminder_minutes_before_start: Literal[5, 10, 15, 30, 60, 120, 1440]


class DocumentShare(Strict):
    kind: Literal["document_share"]
    recipients: list[str] = Field(min_length=1, max_length=1)

    @field_validator("recipients")
    @classmethod
    def recipient(cls, values):
        normalized = [address(value) for value in values]
        if len({value.casefold() for value in normalized}) != 1:
            raise ValueError("Choose exactly one recipient")
        return normalized


class RestaurantReservationCreate(Strict):
    """One exact no-payment OpenTable restaurant reservation."""

    kind: Literal["restaurant_reservation_create"]
    restaurant_id: StrictInt = Field(ge=1)
    restaurant_name: Short
    date_time: datetime
    time_zone: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    party_size: StrictInt = Field(ge=1, le=20)
    reservation_attribute: Literal["default", "hightop", "bar", "counter", "outdoor"] = "default"
    dining_area_id: StrictInt | None = Field(default=None, ge=1)
    environment: Literal["Indoor", "Outdoor"] | None = None
    guest_first_name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    guest_last_name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    guest_email: Annotated[str, StringConstraints(min_length=3, max_length=254)]
    guest_phone_number: Annotated[str, StringConstraints(min_length=5, max_length=20)]
    guest_phone_country_code: Annotated[str, StringConstraints(min_length=2, max_length=2)]
    special_request: Annotated[str, StringConstraints(max_length=75)] = ""
    opentable_terms_accepted: Literal[True]
    opentable_terms_version: Literal["2026-07-22"] = "2026-07-22"
    guest_contact_sharing_approved: Literal[True]
    availability_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    availability_observed_at: datetime
    no_payment_required: Literal[True] = True

    @field_validator(
        "restaurant_name",
        "guest_first_name",
        "guest_last_name",
        "special_request",
    )
    @classmethod
    def reservation_text(cls, value):
        value = clean_text(value)
        if value != "" and not value.strip():
            raise ValueError("Reservation text cannot be blank")
        return value.strip()

    @field_validator("guest_email")
    @classmethod
    def reservation_email(cls, value):
        return address(value)

    @field_validator("guest_phone_number")
    @classmethod
    def reservation_phone(cls, value):
        value = value.strip()
        if not re.fullmatch(r"\+?[0-9]{5,19}", value):
            raise ValueError("Use a phone number with digits and an optional leading +")
        return value

    @field_validator("guest_phone_country_code")
    @classmethod
    def reservation_country(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", value):
            raise ValueError("Phone country code must be a two-letter code")
        return value

    @field_validator("availability_observed_at")
    @classmethod
    def observed_at(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Availability observation must include a timezone offset")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Availability observation cannot be in the future")
        return value

    @model_validator(mode="after")
    def reservation_time(self):
        try:
            zone = ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Select a valid IANA time zone") from None
        local = zoned_time(self.date_time, zone)
        now = datetime.now(timezone.utc)
        instant = local.astimezone(timezone.utc)
        if instant <= now or instant > now + timedelta(days=366):
            raise ValueError("Reservation time must be in the future within one year")
        if local.second or local.microsecond or local.minute % 15:
            raise ValueError("Reservation time must use a 15-minute boundary")
        self.date_time = local
        if self.reservation_attribute == "outdoor" and self.environment not in {None, "Outdoor"}:
            raise ValueError("Outdoor reservations cannot select an indoor environment")
        return self


class LinkedInSocialPublish(Strict):
    kind: Literal["social_publish_linkedin"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=3000)]

    @field_validator("text")
    @classmethod
    def validate_text(cls, value):
        value = clean_text(value)
        if not value.strip():
            raise ValueError("Write the exact LinkedIn post before review")
        return value


ActionPayload = Annotated[
    EmailSend | EmailSendWithAttachments | EmailThreadReply | NegotiationCommitmentEmail | CalendarCreate | CalendarCreateWithReminder | DocumentShare | RestaurantReservationCreate | LinkedInSocialPublish,
    Field(discriminator="kind"),
]


class ActionPrepare(Strict):
    connection_id: UUID
    payload: ActionPayload
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=3)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def owned_artifacts(self):
        attachment_ids = [str(value) for value in self.attachment_ids]
        artifact_ids = [str(value) for value in self.artifact_ids]
        if len(attachment_ids) != len(set(attachment_ids)):
            raise ValueError("Use each attachment only once")
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("Use each shared artifact only once")
        if self.payload.kind == "email_send_with_attachments":
            if not attachment_ids:
                raise ValueError("Select at least one approved attachment")
            if artifact_ids:
                raise ValueError("Document sharing artifacts cannot be mixed with email attachments")
        elif self.payload.kind == "document_share":
            if len(artifact_ids) != 1:
                raise ValueError("Select exactly one owned Shuddho artifact to share")
            if attachment_ids:
                raise ValueError("Email attachments cannot be mixed with document sharing")
        elif attachment_ids or artifact_ids:
            raise ValueError("Owned artifacts are not supported by this action")
        return self


class ActionApproval(Strict):
    preview_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class OAuthStart(Strict):
    capability: Capability


class OAuthFinish(Strict):
    state: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$")]
    code: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
