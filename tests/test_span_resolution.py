from services.analysis.shuddho_analysis.span_resolution import SentenceSpan, resolve_sentence_span, split_sentences


def test_split_sentences_returns_absolute_offsets() -> None:
    sentences = split_sentences("আমি বাংলা লিখি। তুমি আসো।")

    assert [sentence.sentence_index for sentence in sentences] == [0, 1]
    assert sentences[0].text == "আমি বাংলা লিখি।"
    assert sentences[0].start == 0
    assert sentences[0].end == len("আমি বাংলা লিখি।")
    assert sentences[1].text == "তুমি আসো।"
    assert sentences[1].start > sentences[0].end


def test_resolve_sentence_span_uses_occurrence_index_for_repeated_text() -> None:
    sentence = SentenceSpan(sentence_index=0, start=0, end=len("আজও আজও ভালো।"), text="আজও আজও ভালো।")

    resolved = resolve_sentence_span(
        sentence=sentence,
        span_text="আজও",
        occurrence_index=1,
        anchor_before="আজও ",
        anchor_after=" ভালো।",
        confidence=0.95,
    )

    assert resolved is not None
    assert resolved.match.start == 4
    assert resolved.match.end == 7
    assert resolved.source_trace == ["occurrence_index"]


def test_resolve_sentence_span_uses_anchor_triplet_when_occurrence_missing() -> None:
    sentence = SentenceSpan(sentence_index=0, start=0, end=len("আজও আজও ভালো।"), text="আজও আজও ভালো।")

    resolved = resolve_sentence_span(
        sentence=sentence,
        span_text="আজও",
        occurrence_index=None,
        anchor_before="আজও ",
        anchor_after=" ভালো।",
        confidence=0.96,
    )

    assert resolved is not None
    assert resolved.match.start == 4
    assert resolved.match.end == 7
    assert resolved.source_trace == ["anchor_triplet"]


def test_resolve_sentence_span_drops_ambiguous_repeated_word_without_safe_anchor() -> None:
    sentence = SentenceSpan(sentence_index=0, start=0, end=len("আমি আমি স্কুলে যাই।"), text="আমি আমি স্কুলে যাই।")

    resolved = resolve_sentence_span(
        sentence=sentence,
        span_text="আমি",
        occurrence_index=None,
        anchor_before=None,
        anchor_after=None,
        confidence=0.95,
    )

    assert resolved is None
