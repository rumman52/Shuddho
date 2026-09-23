"""User-owned recipient shortcuts; never executable authority."""
from __future__ import annotations

import unicodedata
from typing import Annotated

from pydantic import StringConstraints, field_validator

from .action_schemas import Strict, address, clean_text


RecipientName = Annotated[str, StringConstraints(min_length=1, max_length=80)]


def normalize_recipient_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", clean_text(value))
    value = " ".join(value.split())
    if not value or len(value) > 80:
        raise ValueError("Use a recipient name between 1 and 80 characters")
    return value


class RecipientUpsert(Strict):
    name: RecipientName
    email: Annotated[str, StringConstraints(min_length=3, max_length=254)]

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        return normalize_recipient_name(value)

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value: str) -> str:
        return address(value)
