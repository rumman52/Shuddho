from __future__ import annotations

import re
from collections import defaultdict

from shared.schemas.python_models import ToneAnalysisResponse, ToneLabel

HONORIFIC_MARKERS = {"আপনি", "অনুগ্রহ করে", "ধন্যবাদ", "শ্রদ্ধেয়", "মহোদয়", "দয়া করে"}
CASUAL_MARKERS = {"তুমি", "তুই", "আরে", "হাই", "প্লিজ", "দোস্ত", "বন্ধু"}
CONFIDENT_MARKERS = {"অবশ্যই", "নিশ্চিত", "নিশ্চিতভাবে", "স্পষ্ট", "অবিলম্বে"}
SOFTENING_MARKERS = {"হয়তো", "সম্ভবত", "মনে হয়", "পারলে", "অনুগ্রহ করে"}
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF]")
UPPER_LATIN_RE = re.compile(r"\b[A-Z]{2,}\b")
MULTI_PUNCT_RE = re.compile(r"[!?]{2,}")
LONG_SENTENCE_RE = re.compile(r"[^\n.!?।]{140,}")


class ToneAnalyzer:
    def analyze(self, text: str) -> ToneAnalysisResponse:
        normalized = " ".join(text.split())
        if not normalized:
            return ToneAnalysisResponse(
                detected_tones=[ToneLabel.NEUTRAL],
                primary_tone=ToneLabel.NEUTRAL,
                confidence=0.0,
                explanation_bn="টেক্সট খালি, তাই টোন নির্ধারণ করা যায়নি।",
                explanation_en="The text is empty, so no tone could be detected.",
                suggestions=[],
            )

        scores: dict[ToneLabel, float] = defaultdict(float)
        suggestions: list[str] = []
        reason_bn: list[str] = []
        reason_en: list[str] = []

        exclamation_count = text.count("!")
        question_count = text.count("?")
        if MULTI_PUNCT_RE.search(text) or exclamation_count >= 2:
            scores[ToneLabel.URGENT] += 0.38
            scores[ToneLabel.UNCLEAR] += 0.14
            suggestions.append("যতিচিহ্ন একটু সংযত রাখলে বার্তাটি বেশি স্থির শোনাবে।")
            reason_bn.append("একাধিক বিস্ময়সূচক চিহ্ন বা জোরালো যতিচিহ্ন টেক্সটকে তাড়াহুড়ো ধরনের শোনাচ্ছে।")
            reason_en.append("Repeated emphasis punctuation makes the message feel more urgent.")

        if UPPER_LATIN_RE.search(text):
            scores[ToneLabel.URGENT] += 0.18
            suggestions.append("ALL CAPS বা ইংরেজি জোর কমালে টোনটি আরও ভারসাম্যপূর্ণ হবে।")
            reason_bn.append("বড়হাতের ইংরেজি জোরালো ভঙ্গি তৈরি করছে।")
            reason_en.append("Uppercase English words add a forceful tone.")

        honorific_hits = sum(1 for marker in HONORIFIC_MARKERS if marker in text)
        if honorific_hits:
            scores[ToneLabel.PROFESSIONAL] += 0.24 + (honorific_hits * 0.05)
            scores[ToneLabel.RESPECTFUL] += 0.22 + (honorific_hits * 0.04)
            reason_bn.append("সম্মানসূচক বা ভদ্র শব্দচয়ন টেক্সটকে বেশি পেশাদার শোনাচ্ছে।")
            reason_en.append("Honorific and polite wording makes the text sound professional and respectful.")

        casual_hits = sum(1 for marker in CASUAL_MARKERS if marker in text)
        if casual_hits or EMOJI_RE.search(text):
            scores[ToneLabel.FRIENDLY] += 0.2 + (casual_hits * 0.05)
            scores[ToneLabel.CASUAL] += 0.22 + (casual_hits * 0.05)
            suggestions.append("প্রয়োজনে আরও আনুষ্ঠানিক শব্দ বেছে নিলে বার্তাটি পেশাদার হবে।")
            reason_bn.append("কথ্য বা আলাপচারিতার শব্দচয়ন টেক্সটকে অনানুষ্ঠানিক করছে।")
            reason_en.append("Conversational wording makes the text feel more casual.")

        confident_hits = sum(1 for marker in CONFIDENT_MARKERS if marker in text)
        if confident_hits:
            scores[ToneLabel.CONFIDENT] += 0.22 + (confident_hits * 0.05)
            reason_bn.append("দৃঢ় শব্দচয়ন টেক্সটে আত্মবিশ্বাসী সুর আনছে।")
            reason_en.append("Assertive wording gives the text a confident tone.")

        softening_hits = sum(1 for marker in SOFTENING_MARKERS if marker in text)
        if softening_hits and scores[ToneLabel.CONFIDENT] > 0:
            scores[ToneLabel.CONFIDENT] = max(scores[ToneLabel.CONFIDENT] - 0.06, 0.0)
        if softening_hits and not honorific_hits:
            scores[ToneLabel.FRIENDLY] += 0.08

        if question_count >= 2:
            scores[ToneLabel.UNCLEAR] += 0.16
            suggestions.append("এক বাক্যে একাধিক প্রশ্ন থাকলে আলাদা করলে বার্তাটি পরিষ্কার হবে।")
            reason_bn.append("একাধিক প্রশ্ন বার্তাটিকে কিছুটা অস্পষ্ট করে তুলছে।")
            reason_en.append("Several questions in the same draft can make the message feel less clear.")

        if LONG_SENTENCE_RE.search(text) or (len(normalized) > 120 and "।" not in text and "." not in text and "?" not in text):
            scores[ToneLabel.UNCLEAR] += 0.3
            suggestions.append("লম্বা বাক্য ভেঙে ছোট করলে টোন ও অর্থ দুটোই পরিষ্কার হবে।")
            reason_bn.append("খুব লম্বা বা বিরামচিহ্নবিহীন বাক্য টেক্সটকে কম পরিষ্কার করছে।")
            reason_en.append("Long unbroken sentences reduce clarity.")

        primary_tone, confidence = _resolve_primary_tone(scores)
        detected = _resolve_detected_tones(scores, primary_tone)
        if not detected:
            detected = [ToneLabel.NEUTRAL]
        if primary_tone is None:
            primary_tone = ToneLabel.NEUTRAL
            confidence = 0.56

        if primary_tone == ToneLabel.NEUTRAL and not suggestions:
            suggestions.append("টোন নিরপেক্ষ আছে; প্রয়োজনে উদ্দেশ্য অনুযায়ী আরও বন্ধুসুলভ বা পেশাদার করা যেতে পারে।")
            reason_bn.append("শব্দচয়ন তুলনামূলকভাবে নিরপেক্ষ ও স্থির।")
            reason_en.append("The wording is relatively neutral and even.")

        return ToneAnalysisResponse(
            detected_tones=detected,
            primary_tone=primary_tone,
            confidence=confidence,
            explanation_bn=" ".join(_dedupe_strings(reason_bn)) or "টেক্সটের ভঙ্গি মোটের ওপর নিরপেক্ষ।",
            explanation_en=" ".join(_dedupe_strings(reason_en)) or "Overall, the text reads as neutral.",
            suggestions=_dedupe_strings(suggestions)[:3],
        )


def _resolve_primary_tone(scores: dict[ToneLabel, float]) -> tuple[ToneLabel | None, float]:
    if not scores:
        return None, 0.0
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
    label, score = ordered[0]
    if score < 0.18:
        return None, max(score, 0.0)
    return label, min(round(score, 2), 0.99)


def _resolve_detected_tones(scores: dict[ToneLabel, float], primary_tone: ToneLabel | None) -> list[ToneLabel]:
    if not scores:
        return []
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
    detected = [
        label
        for label, score in ordered
        if score >= 0.18 or label == primary_tone
    ]
    return detected[:3]


def _dedupe_strings(values: list[str]) -> list[str]:
    compact: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        compact.append(normalized)
    return compact
