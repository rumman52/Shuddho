from __future__ import annotations

import re
from dataclasses import dataclass

from shared.schemas.python_models import AnalyzeMode, RewriteIntent, RewriteOption, RewriteRequest, RewriteResponse, ToneGoal, UserPreferences, WritingGoal
from shared.utils.text import stable_id

from .pipeline import AnalysisPipeline

FILLER_PATTERNS = [
    re.compile(r"^(আসলে|মূলত|মানে|সত্যি বলতে|বস্তুত)\s+", re.IGNORECASE),
    re.compile(r"\s+(আসলে|মূলত|মানে)\s+", re.IGNORECASE),
]
FORMAL_REPLACEMENTS = (
    ("প্লিজ", "অনুগ্রহ করে"),
    ("pls", "অনুগ্রহ করে"),
    ("তুমি", "আপনি"),
    ("তোমার", "আপনার"),
    ("ধন্যবাদ!!", "ধন্যবাদ।"),
)
PROFESSIONAL_REPLACEMENTS = (
    ("ওকে", "ঠিক আছে"),
    ("okay", "ঠিক আছে"),
    ("ASAP", "যত দ্রুত সম্ভব"),
    ("প্লিজ", "অনুগ্রহ করে"),
)


@dataclass(frozen=True)
class RewriteCandidate:
    label: str
    rewritten_text: str
    confidence: float
    explanation_bn: str
    explanation_en: str
    source: str


class RewriteService:
    def __init__(self, analysis_pipeline: AnalysisPipeline) -> None:
        self.analysis_pipeline = analysis_pipeline

    def rewrite(self, request: RewriteRequest, preferences: UserPreferences | None = None) -> RewriteResponse:
        segment_start, segment_end, segment_text = _resolve_target_segment(request)
        warnings: list[str] = []
        mode = _mode_from_goals(
            request.writing_goal or (preferences.writing_goal if preferences else None),
            request.tone_goal or (preferences.tone_goal if preferences else None),
        )
        personal_dictionary = preferences.personal_dictionary if preferences is not None else None
        analysis = self.analysis_pipeline.analyze(segment_text, personal_dictionary=personal_dictionary, mode=mode)
        if analysis.runtime_warnings:
            warnings.append("rewrite_running_in_degraded_backend_mode")

        options: list[RewriteOption] = []
        seen_texts: set[str] = {segment_text}

        for candidate in self._generate_candidates(request.intent, segment_text, analysis.corrected_text):
            if candidate.rewritten_text in seen_texts:
                continue
            is_valid, warning = _validate_rewrite(segment_text, candidate.rewritten_text)
            if warning:
                warnings.append(warning)
            if not is_valid:
                continue
            seen_texts.add(candidate.rewritten_text)
            options.append(
                RewriteOption(
                    id=stable_id("rw", f"{request.intent.value}:{candidate.label}:{candidate.rewritten_text}"),
                    label=candidate.label,
                    rewritten_text=candidate.rewritten_text,
                    confidence=candidate.confidence,
                    explanation_bn=candidate.explanation_bn,
                    explanation_en=candidate.explanation_en,
                    source=candidate.source,
                )
            )

        if not options:
            warnings.append("No high-confidence rewrite was available for this text.")

        return RewriteResponse(
            original_text=segment_text,
            target_text=options[0].rewritten_text if options else segment_text,
            selection_start=segment_start,
            selection_end=segment_end,
            intent=request.intent,
            options=options[:3],
            warnings=_dedupe_strings(warnings),
        )

    def _generate_candidates(self, intent: RewriteIntent, original_text: str, corrected_text: str) -> list[RewriteCandidate]:
        candidates: list[RewriteCandidate] = []
        normalized = _normalize_sentence(corrected_text)

        if normalized != original_text:
            candidates.append(
                RewriteCandidate(
                    label="Cleaned draft",
                    rewritten_text=normalized,
                    confidence=0.91,
                    explanation_bn="নিরাপদ সংশোধন ও বিরামচিহ্ন ঠিক করে পাঠটি একটু পরিষ্কার করা হয়েছে।",
                    explanation_en="Safe corrections and punctuation cleanup make the draft clearer.",
                    source="analysis_pipeline",
                )
            )

        if intent == RewriteIntent.CLARITY:
            clarity_text = _clarify_text(normalized)
            if clarity_text != normalized:
                candidates.append(
                    RewriteCandidate(
                        label="Clearer phrasing",
                        rewritten_text=clarity_text,
                        confidence=0.87,
                        explanation_bn="অপ্রয়োজনীয় পুনরাবৃত্তি ও ভঙ্গি একটু গুছিয়ে দেওয়া হয়েছে।",
                        explanation_en="Unnecessary repetition and rough phrasing were smoothed out.",
                        source="heuristic_clarity",
                    )
                )

        if intent == RewriteIntent.CONCISE:
            concise_text = _make_concise(normalized)
            if concise_text != normalized:
                candidates.append(
                    RewriteCandidate(
                        label="Shorter version",
                        rewritten_text=concise_text,
                        confidence=0.85,
                        explanation_bn="অর্থ না বদলে বাড়তি ভরাট শব্দ কমানো হয়েছে।",
                        explanation_en="Filler wording was reduced without changing the core meaning.",
                        source="heuristic_concise",
                    )
                )

        if intent == RewriteIntent.FORMAL:
            formal_text = _replace_pairs(normalized, FORMAL_REPLACEMENTS)
            if formal_text != normalized:
                candidates.append(
                    RewriteCandidate(
                        label="More formal",
                        rewritten_text=formal_text,
                        confidence=0.82,
                        explanation_bn="কিছু অনানুষ্ঠানিক শব্দকে বেশি আনুষ্ঠানিক রূপে বদলানো হয়েছে।",
                        explanation_en="Informal wording was shifted toward a more formal register.",
                        source="heuristic_formal",
                    )
                )

        if intent == RewriteIntent.FRIENDLY:
            friendly_text = _make_friendly(normalized)
            if friendly_text != normalized:
                candidates.append(
                    RewriteCandidate(
                        label="Friendlier tone",
                        rewritten_text=friendly_text,
                        confidence=0.79,
                        explanation_bn="বাক্যটি একটু নরম ও সহযোগিতামূলকভাবে সাজানো হয়েছে।",
                        explanation_en="The sentence was softened to sound more collaborative.",
                        source="heuristic_friendly",
                    )
                )

        if intent == RewriteIntent.PROFESSIONAL:
            professional_text = _replace_pairs(_make_concise(normalized), PROFESSIONAL_REPLACEMENTS)
            professional_text = _make_professional(professional_text)
            if professional_text != normalized:
                candidates.append(
                    RewriteCandidate(
                        label="More professional",
                        rewritten_text=professional_text,
                        confidence=0.82,
                        explanation_bn="অনানুষ্ঠানিক বা অতিরিক্ত জোরালো অংশ কমিয়ে পেশাদার ভঙ্গি আনা হয়েছে।",
                        explanation_en="Informal and overly emphatic wording was reduced for a more professional tone.",
                        source="heuristic_professional",
                    )
                )

        return candidates


def _resolve_target_segment(request: RewriteRequest) -> tuple[int | None, int | None, str]:
    if request.selection_start is None or request.selection_end is None:
        return None, None, request.text
    safe_start = max(0, request.selection_start)
    safe_end = max(safe_start, min(len(request.text), request.selection_end))
    if safe_end <= safe_start:
        return None, None, request.text
    return safe_start, safe_end, request.text[safe_start:safe_end]


def _mode_from_goals(writing_goal: WritingGoal | None, tone_goal: ToneGoal | None) -> AnalyzeMode:
    if writing_goal in {WritingGoal.FORMAL, WritingGoal.ACADEMIC, WritingGoal.BUSINESS}:
        return AnalyzeMode.FORMAL
    if tone_goal == ToneGoal.PROFESSIONAL:
        return AnalyzeMode.FORMAL
    return AnalyzeMode.STANDARD


def _clarify_text(text: str) -> str:
    clarified = _normalize_sentence(text)
    clarified = re.sub(r"\b(\S+)\s+\1\b", r"\1", clarified)
    return clarified


def _make_concise(text: str) -> str:
    concise = text
    for pattern in FILLER_PATTERNS:
        concise = pattern.sub(" ", concise)
    concise = re.sub(r"\s{2,}", " ", concise)
    return _normalize_sentence(concise)


def _make_friendly(text: str) -> str:
    friendly = _normalize_sentence(text)
    if friendly.startswith("অনুগ্রহ করে") or friendly.startswith("দয়া করে"):
        return friendly
    if re.match(r"^[\u0980-\u09FF ]+(করুন|পাঠান|জানান|দিন)\b", friendly):
        return f"দয়া করে {friendly}"
    return friendly


def _make_professional(text: str) -> str:
    professional = _normalize_sentence(text)
    professional = re.sub(r"[!]{2,}", "।", professional)
    professional = professional.replace("!!", "।").replace("!", "।")
    return _normalize_sentence(professional)


def _replace_pairs(text: str, replacements: tuple[tuple[str, str], ...]) -> str:
    updated = text
    for old, new in replacements:
        updated = re.sub(rf"(?<!\w){re.escape(old)}(?!\w)", new, updated, flags=re.IGNORECASE)
    return _normalize_sentence(updated)


def _normalize_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    normalized = re.sub(r"\s+([,.;:!?।])", r"\1", normalized)
    normalized = re.sub(r"([,.;:!?।])([^\s\"')\]}])", r"\1 \2", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    return normalized.strip()


def _validate_rewrite(original_text: str, rewritten_text: str) -> tuple[bool, str | None]:
    if not rewritten_text.strip():
        return False, "Rewrite produced empty text."
    if rewritten_text == original_text:
        return False, None
    if not re.search(r"[\u0980-\u09FF]", rewritten_text):
        return False, "Rewrite must stay in Bengali."
    if re.search(r"\s{2,}", rewritten_text):
        return False, "Rewrite produced unstable spacing."
    if len(rewritten_text) > max(len(original_text) * 2.5, len(original_text) + 48):
        return False, "Rewrite changed the sentence too aggressively."
    if _important_ascii_tokens_missing(original_text, rewritten_text):
        return False, "Rewrite would drop named entities or critical tokens."
    if _token_overlap_ratio(original_text, rewritten_text) < 0.45:
        return False, "Rewrite may distort the original meaning."
    return True, None


def _important_ascii_tokens_missing(original_text: str, rewritten_text: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9_./:@#-]+", original_text)
    return any(token not in rewritten_text for token in tokens)


def _token_overlap_ratio(original_text: str, rewritten_text: str) -> float:
    original_tokens = {token for token in re.findall(r"[\u0980-\u09FFA-Za-z0-9]+", original_text) if token}
    rewritten_tokens = {token for token in re.findall(r"[\u0980-\u09FFA-Za-z0-9]+", rewritten_text) if token}
    if not original_tokens:
        return 1.0
    return len(original_tokens & rewritten_tokens) / len(original_tokens)


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
