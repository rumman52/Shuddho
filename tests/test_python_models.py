from shared.schemas.python_models import AnalyzeMode, AnalyzeRequest


def test_analyze_request_normalizes_personal_dictionary_entries() -> None:
    request = AnalyzeRequest(
        text="বাংলা",
        personal_dictionary=["  শব্দ  ", "", "শব্দ", "ব্যক্তিগত   শব্দ  "],
    )

    assert request.personal_dictionary == ["শব্দ", "ব্যক্তিগত শব্দ"]
    assert request.mode == AnalyzeMode.STANDARD


def test_analyze_request_accepts_explicit_mode() -> None:
    request = AnalyzeRequest(text="বাংলা", mode=AnalyzeMode.FORMAL)

    assert request.mode == AnalyzeMode.FORMAL
