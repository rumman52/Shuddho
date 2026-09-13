from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UploadRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=160)
    byte_size: int = Field(gt=0, le=8 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        if any(char in value for char in '/\\') or any(ord(char) < 32 or ord(char) == 127 for char in value) or value in {".", ".."}:
            raise ValueError("Use a filename without paths or control characters")
        if not value.lower().endswith((".txt", ".docx", ".pdf")):
            raise ValueError("Supported files: TXT, DOCX, and text-based PDF")
        return value


class TaskCreate(StrictModel):
    instruction: str = Field(min_length=3, max_length=2000)
    notes: str = Field(default="", max_length=20000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=5)
    output_language: str = Field(default="en", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)

    @model_validator(mode="after")
    def input_required(self):
        if not self.notes and not self.document_ids:
            raise ValueError("Add notes or a supported document")
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("A document may be included only once")
        return self


class ReportSection(StrictModel):
    heading: str = Field(min_length=1, max_length=180)
    paragraphs: list[str] = Field(min_length=1, max_length=8)
    source_ids: list[str] = Field(min_length=1, max_length=6)

    @field_validator("paragraphs")
    @classmethod
    def paragraph_lengths(cls, values):
        if any(not value or len(value) > 2400 for value in values):
            raise ValueError("Paragraph is empty or too long")
        return values


class Report(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=1800)
    sections: list[ReportSection] = Field(min_length=1, max_length=10)


class EmailDraft(StrictModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=6000)


class DraftPackage(StrictModel):
    report: Report
    email: EmailDraft
    output_language: str = Field(pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$", max_length=35)
    missing_information: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def bounded_output(self):
        if len(self.model_dump_json()) > 60000 or any(len(item) > 400 for item in self.missing_information):
            raise ValueError("Draft exceeds the output limit")
        # Word XML cannot represent these control characters.
        def invalid(value):
            if isinstance(value, str):
                return bool(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value))
            if isinstance(value, dict):
                return any(invalid(item) for item in value.values())
            if isinstance(value, list):
                return any(invalid(item) for item in value)
            return False
        if invalid(self.model_dump()):
            raise ValueError("Draft contains unsupported control characters")
        return self


class PreferencesRequest(StrictModel):
    personal_dictionary: list[str] = Field(default_factory=list, max_length=500)
    writing_goal: Literal["general", "formal", "academic", "business", "casual", "social"] = "general"
    tone_goal: str = Field(default="neutral", max_length=60)
    language: str = Field(default="bn", min_length=2, max_length=35)

    @field_validator("personal_dictionary")
    @classmethod
    def dictionary_limits(cls, value):
        if any(not word.strip() or len(word) > 100 for word in value):
            raise ValueError("Dictionary entries must contain 1–100 characters")
        return list(dict.fromkeys(word.strip() for word in value))
