from services.normalizer.shuddho_normalizer.normalizer import BanglaNormalizer


def test_normalizer_collapses_whitespace_and_space_before_punctuation() -> None:
    normalizer = BanglaNormalizer()
    result = normalizer.normalize("আমি  বাংলা লিখি  । ")
    assert result.text == "আমি বাংলা লিখি।"


def test_normalizer_preserves_mixed_text() -> None:
    normalizer = BanglaNormalizer()
    result = normalizer.normalize("Bangla editor এ  check  করা দরকার")
    assert result.text == "Bangla editor এ check করা দরকার"

