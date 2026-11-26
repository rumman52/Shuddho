"""Unicode and strict JSON round-trip regressions for release evidence."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.staging_release_evidence import (
    StagingReleaseEvidenceError,
    parse_evidence_json,
    release_context,
    write_private_json,
)


@pytest.mark.parametrize("raw", [
    rb'"\ud800"',
    rb'{"release_id":"\udfff"}',
    rb'{"\ud800":"value"}',
    rb'{"metadata":[{"text":"\udc00\ud800"}]}',
    rb'{"metadata":["\ud800A"]}',
])
def test_strict_evidence_decoder_rejects_unpaired_surrogates(raw):
    with pytest.raises(StagingReleaseEvidenceError, match="Invalid rollout manifest"):
        parse_evidence_json(raw)


def test_release_context_rejects_invalid_nested_unicode_before_hashing(tmp_path):
    rollout = tmp_path / "rollout.json"
    rollout.write_bytes(rb'{"release_id":"valid","nested":{"\ud800":true}}')
    with pytest.raises(StagingReleaseEvidenceError, match="Invalid rollout manifest"):
        release_context(SimpleNamespace(source_revision="a" * 40), rollout)


@pytest.mark.parametrize("value", [
    {"text": "\ud800"},
    {"\udfff": "text"},
    {"nested": [{"text": "\udc00\ud800"}]},
    {"cost": float("nan")},
    {"cost": float("inf")},
    {1: "first", "1": "second"},
])
def test_private_writer_refuses_evidence_its_strict_reader_cannot_decode(tmp_path, value):
    target = tmp_path / "receipt.json"
    with pytest.raises(StagingReleaseEvidenceError):
        write_private_json(target, value)
    assert list(tmp_path.iterdir()) == []


def test_valid_bangla_supplementary_and_replacement_characters_round_trip(tmp_path):
    text = "বাংলা 🚀 \ufffd"
    data = {"release_id": text, "metadata": {text: [text, 1.25, True, None]}}
    escaped = json.dumps(data, ensure_ascii=True).encode("utf-8")
    literal = json.dumps(data, ensure_ascii=False).encode("utf-8")
    assert parse_evidence_json(escaped) == parse_evidence_json(literal) == data
    target = tmp_path / "receipt.json"
    write_private_json(target, data)
    raw = target.read_bytes()
    assert raw == (json.dumps(data, indent=2) + "\n").encode("utf-8")
    assert parse_evidence_json(raw) == data
    context = release_context(SimpleNamespace(source_revision="a" * 40), target)
    assert context["release_id"] == text
    assert context["rollout_manifest_sha256"] == hashlib.sha256(raw).hexdigest()
