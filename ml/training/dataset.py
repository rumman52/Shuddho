from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ml.detector.labels import DETECTOR_LABEL_TO_ID, DETECTOR_PAD_TOKEN, DETECTOR_UNK_TOKEN, normalize_detector_label
from shared.constants.bangla import TOKEN_PATTERN


def load_jsonl(path: str | Path) -> list[dict]:
    records: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        records.append(json.loads(stripped))
    return records


@dataclass(frozen=True)
class TokenSpan:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class DetectorIssue:
    start: int
    end: int
    label: str
    subtype: str = ""


@dataclass(frozen=True)
class DetectorExample:
    text: str
    tokens: tuple[str, ...]
    token_spans: tuple[TokenSpan, ...]
    token_labels: tuple[int, ...]
    target_text: str | None = None
    issues: tuple[DetectorIssue, ...] = ()


def tokenize_with_offsets(text: str) -> list[TokenSpan]:
    return [TokenSpan(text=match.group(0), start=match.start(), end=match.end()) for match in TOKEN_PATTERN.finditer(text)]


def load_detector_examples(path: str | Path) -> list[DetectorExample]:
    return [build_detector_example(record) for record in load_jsonl(path)]


def build_detector_example(record: dict) -> DetectorExample:
    text = _resolve_input_text(record)
    token_spans = tuple(tokenize_with_offsets(text))
    tokens = tuple(token.text for token in token_spans)
    issues = tuple(_parse_issue(issue) for issue in record.get("issues", []))
    token_labels = _resolve_token_labels(record, token_spans, issues)

    return DetectorExample(
        text=text,
        tokens=tokens,
        token_spans=token_spans,
        token_labels=token_labels,
        target_text=record.get("target_text"),
        issues=issues,
    )


def build_token_vocabulary(
    examples: list[DetectorExample],
    *,
    max_size: int | None = None,
) -> dict[str, int]:
    frequencies: dict[str, int] = {}
    for example in examples:
        for token in example.tokens:
            frequencies[token] = frequencies.get(token, 0) + 1

    ordered_tokens = sorted(frequencies.items(), key=lambda item: (-item[1], item[0]))
    if max_size is not None:
        ordered_tokens = ordered_tokens[: max(0, max_size - 2)]

    vocabulary = {
        DETECTOR_PAD_TOKEN: 0,
        DETECTOR_UNK_TOKEN: 1,
    }
    for token, _count in ordered_tokens:
        if token in vocabulary:
            continue
        vocabulary[token] = len(vocabulary)
    return vocabulary


def encode_tokens(tokens: tuple[str, ...] | list[str], vocabulary: dict[str, int]) -> list[int]:
    unknown_token_id = vocabulary[DETECTOR_UNK_TOKEN]
    return [vocabulary.get(token, unknown_token_id) for token in tokens]


def _resolve_input_text(record: dict) -> str:
    for key in ("input_text", "source_text", "text"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    raise ValueError("Detector record must include one of: input_text, source_text, text")


def _parse_issue(issue: dict) -> DetectorIssue:
    return DetectorIssue(
        start=int(issue["start"]),
        end=int(issue["end"]),
        label=normalize_detector_label(issue.get("label", "ok")),
        subtype=str(issue.get("subtype", "")),
    )


def _resolve_token_labels(
    record: dict,
    token_spans: tuple[TokenSpan, ...],
    issues: tuple[DetectorIssue, ...],
) -> tuple[int, ...]:
    if issues:
        return tuple(_label_token_from_issues(token, issues) for token in token_spans)

    raw_labels = record.get("token_labels")
    if raw_labels is None:
        return tuple(DETECTOR_LABEL_TO_ID["ok"] for _ in token_spans)

    if len(raw_labels) != len(token_spans):
        raise ValueError("Detector token_labels length must match tokenized input length")

    return tuple(DETECTOR_LABEL_TO_ID[normalize_detector_label(label)] for label in raw_labels)


def _label_token_from_issues(token: TokenSpan, issues: tuple[DetectorIssue, ...]) -> int:
    for issue in issues:
        if issue.start < token.end and token.start < issue.end:
            return DETECTOR_LABEL_TO_ID[issue.label]
    return DETECTOR_LABEL_TO_ID["ok"]
