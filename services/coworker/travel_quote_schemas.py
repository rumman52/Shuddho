from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StringConstraints, field_validator, model_validator

from .action_schemas import Strict, clean_text, zoned_time
from .transaction_schemas import TransactionPrice


ShortText = Annotated[str, StringConstraints(min_length=1, max_length=300)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=1000)]


class TravelTraveler(Strict):
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    traveler_type: Literal["adult", "child", "infant"] = "adult"

    @field_validator("display_name")
    @classmethod
    def safe_name(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Traveler name cannot be blank")
        return value


class TravelFlightSegment(Strict):
    origin_code: Annotated[str, StringConstraints(min_length=3, max_length=3)]
    destination_code: Annotated[str, StringConstraints(min_length=3, max_length=3)]
    departure_at: datetime
    arrival_at: datetime
    origin_time_zone: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    destination_time_zone: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    marketing_carrier: Annotated[str, StringConstraints(min_length=2, max_length=3)] | None = None
    flight_number: Annotated[str, StringConstraints(min_length=1, max_length=8)] | None = None

    @field_validator("origin_code", "destination_code")
    @classmethod
    def airport_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("Airport code must be a three-letter IATA-style code")
        return value

    @field_validator("marketing_carrier")
    @classmethod
    def carrier_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{2,3}", value):
            raise ValueError("Carrier code must contain two or three letters/digits")
        return value

    @field_validator("flight_number")
    @classmethod
    def safe_flight_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{1,8}", value):
            raise ValueError("Flight number contains unsupported characters")
        return value

    @model_validator(mode="after")
    def exact_times(self):
        try:
            origin_zone = ZoneInfo(self.origin_time_zone)
            destination_zone = ZoneInfo(self.destination_time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Select valid IANA time zones for every flight segment") from None
        self.departure_at = zoned_time(self.departure_at, origin_zone)
        self.arrival_at = zoned_time(self.arrival_at, destination_zone)
        departure = self.departure_at.astimezone(timezone.utc)
        arrival = self.arrival_at.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if departure <= now or departure > now + timedelta(days=366):
            raise ValueError("Flight departure must be in the future within one year")
        if arrival <= departure or arrival - departure > timedelta(days=2):
            raise ValueError("Flight arrival must be after departure within 48 hours")
        if self.origin_code == self.destination_code:
            raise ValueError("Flight origin and destination must differ")
        return self


class TravelLodgingStay(Strict):
    property_id: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    property_name: ShortText
    address: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    check_in_at: datetime
    check_out_at: datetime
    time_zone: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    room_name: Annotated[str, StringConstraints(min_length=1, max_length=200)]

    @field_validator("property_id", "property_name", "address", "room_name")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Lodging details cannot be blank")
        return value

    @model_validator(mode="after")
    def exact_stay(self):
        try:
            zone = ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Select a valid IANA lodging time zone") from None
        self.check_in_at = zoned_time(self.check_in_at, zone)
        self.check_out_at = zoned_time(self.check_out_at, zone)
        check_in = self.check_in_at.astimezone(timezone.utc)
        check_out = self.check_out_at.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if check_in <= now or check_in > now + timedelta(days=366):
            raise ValueError("Check-in must be in the future within one year")
        if check_out <= check_in or check_out - check_in > timedelta(days=60):
            raise ValueError("Check-out must be after check-in and within 60 days")
        return self


class TravelQuoteRequest(Strict):
    """TX-08 review-only travel quote.

    This records exact user-supplied quote evidence. It does not claim provider
    verification and cannot create a booking or payment action.
    """

    travel_kind: Literal["flight", "lodging"]
    quote_source: Literal["user_supplied"] = "user_supplied"
    provider_name: ShortText
    provider_quote_id: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    travelers: list[TravelTraveler] = Field(min_length=1, max_length=9)
    flight_segments: list[TravelFlightSegment] = Field(default_factory=list, max_length=8)
    lodging: TravelLodgingStay | None = None
    price: TransactionPrice
    cancellation_terms: LongText
    change_terms: LongText
    quoted_at: datetime
    quote_expires_at: datetime

    @field_validator("provider_name", "provider_quote_id", "cancellation_terms", "change_terms")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value).strip()
        if not value:
            raise ValueError("Travel quote text cannot be blank")
        return value

    @field_validator("quoted_at", "quote_expires_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Travel quote times must include a timezone offset")
        return value

    @model_validator(mode="after")
    def exact_quote(self):
        now = datetime.now(timezone.utc)
        quoted = self.quoted_at.astimezone(timezone.utc)
        expires = self.quote_expires_at.astimezone(timezone.utc)
        if quoted > now + timedelta(minutes=5):
            raise ValueError("Quote time cannot be more than five minutes in the future")
        if expires <= quoted or expires <= now:
            raise ValueError("Quote expiry must be later than the quote time and still current")
        if expires - quoted > timedelta(days=30):
            raise ValueError("Travel quote validity cannot exceed 30 days")
        names = [item.display_name.casefold() for item in self.travelers]
        if len(names) != len(set(names)):
            raise ValueError("Traveler names must be unique within this quote")
        if self.travel_kind == "flight":
            if not self.flight_segments or self.lodging is not None:
                raise ValueError("Flight quotes require flight segments and cannot include lodging")
            for previous, current in zip(self.flight_segments, self.flight_segments[1:]):
                if previous.destination_code != current.origin_code:
                    raise ValueError("Flight segments must form one continuous itinerary")
                if current.departure_at.astimezone(timezone.utc) <= previous.arrival_at.astimezone(timezone.utc):
                    raise ValueError("Each flight segment must depart after the prior arrival")
        else:
            if self.flight_segments or self.lodging is None:
                raise ValueError("Lodging quotes require one lodging stay and no flight segments")
        return self
