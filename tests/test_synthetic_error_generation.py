from scripts.generate_synthetic_errors import create_variants


def test_create_variants_emits_detector_ready_issue_records() -> None:
    variants = create_variants("আমি কিন্তু স্কুলে যাই।")
    by_subtype = {record.issues[0].subtype: record for record in variants}

    assert "repeated_word" in by_subtype
    assert "space_before_punctuation" in by_subtype
    assert "duplicate_punctuation" in by_subtype
    assert "variant_mapping" in by_subtype
    assert by_subtype["variant_mapping"].source_text.startswith("আমি কিন্ত")
