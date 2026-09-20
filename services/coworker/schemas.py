from __future__ import annotations

import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator, model_validator

from .skills import SkillId


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
        if not value.lower().endswith((".txt", ".docx", ".pdf", ".csv", ".xlsx", ".pptx")):
            raise ValueError("Unsupported source file type")
        return value


class TaskCreate(StrictModel):
    skill_id: SkillId = "report_email"
    instruction: str = Field(min_length=3, max_length=2000)
    notes: str = Field(default="", max_length=20000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=5)
    output_language: str = Field(default="en", pattern=r"^(auto|[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)$", max_length=35)

    @model_validator(mode="after")
    def input_required(self):
        if self.skill_id == "report_email" and not self.notes and not self.document_ids:
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


class DraftContent(StrictModel):
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


class DraftPackage(DraftContent):
    """Original Part 2 shape, still accepted for stored report_email_v1 tasks."""
    report: Report
    email: EmailDraft


OutputText = Annotated[str, Field(min_length=1, max_length=2400)]
SourceId = Annotated[str, Field(min_length=1, max_length=100)]
SourceIds = Annotated[list[SourceId], Field(min_length=1, max_length=7)]


class WorkSection(StrictModel):
    heading: str = Field(default="", max_length=180)
    paragraphs: list[OutputText] = Field(default_factory=list, max_length=8)
    bullets: list[OutputText] = Field(default_factory=list, max_length=12)
    source_ids: SourceIds

    @model_validator(mode="after")
    def has_content(self):
        if not self.paragraphs and not self.bullets:
            raise ValueError("A section needs text or bullets")
        return self


class WorkDocument(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(default="", max_length=1800)
    sections: list[WorkSection] = Field(min_length=1, max_length=15)


class EmailPackage(DraftContent):
    kind: Literal["email"] = "email"
    email: EmailDraft
    source_ids: SourceIds


class DocumentPackage(DraftContent):
    kind: Literal["document"] = "document"
    document: WorkDocument


class SocialPost(StrictModel):
    platform: Literal["facebook", "linkedin", "other"]
    label: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=5000)
    suggested_timing: str | None = Field(default=None, max_length=160)
    source_ids: SourceIds


class SocialPackage(DraftContent):
    kind: Literal["social"] = "social"
    title: str = Field(min_length=1, max_length=180)
    posts: list[SocialPost] = Field(min_length=1, max_length=6)


class MeetingNote(StrictModel):
    text: OutputText
    source_ids: SourceIds


class MeetingAction(MeetingNote):
    owner: str | None = Field(default=None, max_length=160)
    deadline: str | None = Field(default=None, max_length=160)
    basis: Literal["recorded", "suggested"]


Label = Annotated[str, Field(min_length=1, max_length=100)]


class MeetingLabels(StrictModel):
    notes: Label
    decisions: Label
    actions: Label
    owner: Label
    deadline: Label
    recorded: Label
    suggested: Label


class MeetingPackage(DraftContent):
    kind: Literal["meeting"] = "meeting"
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=1800)
    labels: MeetingLabels
    notes: list[MeetingNote] = Field(min_length=1, max_length=15)
    decisions: list[MeetingNote] = Field(default_factory=list, max_length=12)
    actions: list[MeetingAction] = Field(default_factory=list, max_length=15)


class PlanItem(StrictModel):
    task: OutputText
    when: str = Field(default="", max_length=160)
    priority: Literal["high", "normal", "low"] = "normal"
    basis: Literal["provided", "suggested"]
    source_ids: SourceIds


class PlanLabels(StrictModel):
    high: Label
    normal: Label
    low: Label
    provided: Label
    suggested: Label


class PlanPackage(DraftContent):
    kind: Literal["plan"] = "plan"
    title: str = Field(min_length=1, max_length=180)
    overview: str = Field(min_length=1, max_length=1800)
    labels: PlanLabels
    items: list[PlanItem] = Field(min_length=1, max_length=25)


Number = Annotated[StrictFloat | StrictInt, Field(ge=-1e12, le=1e12, allow_inf_nan=False)]
ColumnId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,23}$")]


class ChartSeries(StrictModel):
    label: str = Field(min_length=1, max_length=40)
    values: list[Number] = Field(min_length=1, max_length=8)


class SlideChart(StrictModel):
    kind: Literal["bar", "line"] = "bar"
    categories: list[Annotated[str, Field(min_length=1, max_length=35)]] = Field(min_length=1, max_length=8)
    series: list[ChartSeries] = Field(min_length=1, max_length=3)
    unit: str = Field(default="", max_length=40)

    @model_validator(mode="after")
    def dimensions(self):
        if any(any(char in value for char in "\n\r\t") for value in [self.unit, *self.categories, *[series.label for series in self.series]]):
            raise ValueError("Chart labels use one paragraph each")
        if any(len(series.values) != len(self.categories) for series in self.series):
            raise ValueError("Every chart series must match the categories")
        return self


class PresentationSlide(StrictModel):
    layout: Literal["cover", "content", "chart"] = "content"
    title: str = Field(min_length=1, max_length=60)
    bullets: list[Annotated[str, Field(min_length=1, max_length=110)]] = Field(default_factory=list, max_length=3)
    speaker_notes: str = Field(default="", max_length=600)
    chart: SlideChart | None = None
    source_ids: SourceIds

    @model_validator(mode="after")
    def layout_content(self):
        if any(any(char in value for char in "\n\r\t") for value in [self.title, *self.bullets]):
            raise ValueError("Slide headings and bullets use one paragraph each; put extra lines in speaker notes")
        if (self.layout == "chart") != (self.chart is not None):
            raise ValueError("Only chart slides contain chart data")
        if self.layout in {"cover", "chart"} and len(self.bullets) > 1:
            raise ValueError("Cover and chart slides allow one short subtitle")
        if self.layout == "content" and not self.bullets:
            raise ValueError("A content slide needs at least one point")
        return self


class PresentationPackage(DraftContent):
    kind: Literal["presentation"] = "presentation"
    title: str = Field(min_length=1, max_length=120)
    slides: list[PresentationSlide] = Field(min_length=1, max_length=8)


class SheetColumn(StrictModel):
    id: ColumnId
    label: str = Field(min_length=1, max_length=50)
    format: Literal["text", "number", "integer", "percent"] = "text"
    aggregate: Literal["none", "sum", "average"] = "none"


class CalculatedColumn(SheetColumn):
    format: Literal["number", "integer", "percent"] = "number"
    operation: Literal["sum", "difference", "product", "ratio"]
    inputs: list[ColumnId] = Field(min_length=2, max_length=4)


class SheetChart(StrictModel):
    kind: Literal["bar", "line"] = "bar"
    title: str = Field(min_length=1, max_length=100)
    category: ColumnId
    series: list[ColumnId] = Field(min_length=1, max_length=3)


Cell = Annotated[str, Field(max_length=160)] | Number | None


class SpreadsheetPackage(DraftContent):
    kind: Literal["spreadsheet"] = "spreadsheet"
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=600)
    sheet_name: str = Field(min_length=1, max_length=31)
    columns: list[SheetColumn] = Field(min_length=1, max_length=8)
    rows: list[Annotated[list[Cell], Field(min_length=1, max_length=8)]] = Field(min_length=1, max_length=40)
    calculations: list[CalculatedColumn] = Field(default_factory=list, max_length=3)
    summary_label: str = Field(default="", max_length=60)
    chart: SheetChart | None = None
    source_ids: SourceIds

    @model_validator(mode="after")
    def table_contract(self):
        if re.search(r"[\[\]:*?/\\]", self.sheet_name) or self.sheet_name.startswith("'") or self.sheet_name.endswith("'") or self.sheet_name.lower() == "history":
            raise ValueError("Unsupported worksheet name")
        columns = self.columns + self.calculations
        if self.title.count("\n") > 1 or self.summary.count("\n") > 4 or self.summary_label.count("\n") > 1 or any(column.label.count("\n") > 1 for column in columns):
            raise ValueError("Keep worksheet titles, labels, and summaries concise")
        ids = [column.id for column in columns]
        if len(ids) != len(set(ids)) or len(columns) > 10:
            raise ValueError("Use unique column IDs and at most ten total columns")
        if any(column.format == "text" and column.aggregate != "none" for column in columns):
            raise ValueError("Text cannot be aggregated")
        if any(column.aggregate != "none" for column in columns) and not self.summary_label:
            raise ValueError("Provide a localized label for the summary row")
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("Row width must match the input columns")
            for value, column in zip(row, self.columns):
                if isinstance(value, str) and value.count("\n") > 4:
                    raise ValueError("Use at most five text lines per cell")
                if value is not None and ((column.format == "text") != isinstance(value, str)):
                    raise ValueError("Use typed numbers and text in the matching columns")
                if value is not None and column.format == "integer" and int(value) != value:
                    raise ValueError("Integer columns require whole numbers")
        available = {column.id for column in self.columns if column.format != "text"}
        for column in self.calculations:
            if not set(column.inputs).issubset(available) or len(column.inputs) != len(set(column.inputs)):
                raise ValueError("Calculations reference distinct earlier numeric columns only")
            if column.operation in {"difference", "ratio"} and len(column.inputs) != 2:
                raise ValueError("Difference and ratio require exactly two inputs")
            available.add(column.id)
        if self.chart and (self.chart.category not in ids or not set(self.chart.series).issubset(available) or len(self.chart.series) != len(set(self.chart.series))):
            raise ValueError("The chart must reference existing numeric series")
        from .calculations import table_values
        preview = table_values(self)  # Reject excessive calculated values before saving a draft.
        if self.chart:
            if len(self.rows) > 8:
                raise ValueError("Charts support up to eight rows; omit the chart for a larger table")
            category = ids.index(self.chart.category)
            if any(isinstance(row[category], str) and (len(row[category]) > 35 or any(c in row[category] for c in "\n\r\t")) for row in preview["rows"]):
                raise ValueError("Chart categories require short single-paragraph labels")
            indexes = [ids.index(key) for key in [self.chart.category, *self.chart.series]]
            if any(row[index] is None for row in preview["rows"] for index in indexes):
                raise ValueError("Charts require known category and series values; omit the chart when data are missing")
        return self


AnyDraft = DraftPackage | EmailPackage | DocumentPackage | SocialPackage | MeetingPackage | PlanPackage | PresentationPackage | SpreadsheetPackage
DRAFT_TYPES = {
    "report_email": DraftPackage, "email": EmailPackage, "document": DocumentPackage,
    "career": DocumentPackage, "social": SocialPackage, "meeting": MeetingPackage,
    "daily_plan": PlanPackage, "personal_plan": PlanPackage,
    "presentation": PresentationPackage, "spreadsheet": SpreadsheetPackage,
}


def parse_draft(skill_id: SkillId, value) -> AnyDraft:
    return DRAFT_TYPES[skill_id].model_validate(value)


def source_references(draft: AnyDraft) -> set[str]:
    def collect(value):
        if isinstance(value, dict):
            found = set(value.get("source_ids", []))
            for item in value.values():
                found.update(collect(item))
            return found
        if isinstance(value, list):
            return set().union(*(collect(item) for item in value))
        return set()
    return collect(draft.model_dump())


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
