import json
from pathlib import Path

from scripts.generate_synthetic_errors import create_variants


def test_synthetic_generator_covers_requested_error_taxonomy() -> None:
    clean_sentences = [
        "আমি আগামিকাল ১২ কেজি বই নিয়ে স্কুলে যাই।",
        "আপনি বন্ধুর সাথে সুন্দরভাবে কথা বলেন।",
        "তুমি খুব ভালো বাংলা লিখো।",
        "আমি আজ বাংলা লিখি।",
        "আমি ভাত খাই।",
        "আমি বইগুলো সুন্দরভাবে সাজাই।",
    ]

    fine_labels = {
        issue.fine_label
        for sentence in clean_sentences
        for record in create_variants(sentence)
        for issue in record.issues
        if issue.fine_label is not None
    }

    assert {
        "spelling",
        "punctuation",
        "spacing",
        "repeated_word",
        "verb_agreement",
        "pronoun_mismatch",
        "suffix_error",
        "postposition_error",
        "missing_word",
        "extra_word",
        "formal_informal_mismatch",
        "word_order",
        "mixed_digit_style",
        "code_mix",
        "orthography_variant",
    }.issubset(fine_labels)


def test_synthetic_generator_is_deterministic_for_same_input() -> None:
    text = "আমি আজ বাংলা লিখি।"

    first = [
        record.as_combined_record()
        for record in create_variants(text)
    ]
    second = [
        record.as_combined_record()
        for record in create_variants(text)
    ]

    assert first == second


def test_materialized_dataset_splits_use_new_layout() -> None:
    expected_paths = [
        Path("data/datasets/train/detector.synthetic.jsonl"),
        Path("data/datasets/train/corrector.synthetic.jsonl"),
        Path("data/datasets/valid/detector.synthetic.jsonl"),
        Path("data/datasets/valid/corrector.synthetic.jsonl"),
        Path("data/datasets/test/detector.synthetic.jsonl"),
        Path("data/datasets/test/corrector.synthetic.jsonl"),
        Path("data/datasets/human_gold/sample_annotations.jsonl"),
    ]

    for path in expected_paths:
        assert path.exists(), f"Expected dataset artifact missing: {path}"

    detector_record = json.loads(Path("data/datasets/train/detector.synthetic.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert detector_record["source_split"] == "synthetic"
    assert detector_record["generation_method"] == "rule_mutation"
    assert "fine_label" in detector_record["issues"][0]
