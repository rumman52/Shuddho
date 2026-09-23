"""Only these two typed tools may cross the external-action boundary."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Text = Annotated[str, StringConstraints(max_length=20000)]
Short = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Capability = Literal["email", "calendar"]


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
    # conference, attachment, or reminders. These policies appear in preview.

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


ActionPayload = Annotated[
    EmailSend | EmailSendWithAttachments | CalendarCreate | CalendarCreateWithReminder,
    Field(discriminator="kind"),
]


class ActionPrepare(Strict):
    connection_id: UUID
    payload: ActionPayload
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def attachments(self):
        ids = [str(value) for value in self.attachment_ids]
        if len(ids) != len(set(ids)):
            raise ValueError("Use each attachment only once")
        if self.payload.kind == "email_send_with_attachments":
            if not ids:
                raise ValueError("Select at least one approved attachment")
        elif ids:
            raise ValueError("Attachments are only supported by the attachment email action")
        return self


class ActionApproval(Strict):
    preview_hash: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class OAuthStart(Strict):
    capability: Capability


class OAuthFinish(Strict):
    state: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$")]
    code: Annotated[str, StringConstraints(min_length=1, max_length=4096)]
