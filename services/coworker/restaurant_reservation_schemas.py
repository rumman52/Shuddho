from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StrictInt, StringConstraints, field_validator, model_validator

from .action_schemas import Strict, address, clean_text, zoned_time


class RestaurantReservationRequest(Strict):
    restaurant_id: StrictInt = Field(ge=1)
    restaurant_name: Annotated[str, StringConstraints(min_length=1, max_length=300)]
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

    @field_validator(
        "restaurant_name",
        "guest_first_name",
        "guest_last_name",
        "special_request",
    )
    @classmethod
    def text(cls, value: str) -> str:
        value = clean_text(value).strip()
        return value

    @field_validator("guest_email")
    @classmethod
    def email(cls, value: str) -> str:
        return address(value)

    @field_validator("guest_phone_number")
    @classmethod
    def phone(cls, value: str) -> str:
        import re
        value = value.strip()
        if not re.fullmatch(r"\+?[0-9]{5,19}", value):
            raise ValueError("Use a phone number with digits and an optional leading +")
        return value

    @field_validator("guest_phone_country_code")
    @classmethod
    def country(cls, value: str) -> str:
        import re
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", value):
            raise ValueError("Phone country code must be a two-letter code")
        return value

    @model_validator(mode="after")
    def exact_time(self):
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


class RestaurantReservationPrepare(Strict):
    expected_revision: int = Field(ge=1)
    terms_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
