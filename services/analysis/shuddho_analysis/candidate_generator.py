from __future__ import annotations

from shared.schemas.python_models import Suggestion
from shared.utils.text import stable_id

from .models import CandidateBundle, DetectorFinding


class CandidateGenerator:
    def generate(
        self,
        *,
        spell_suggestions: list[Suggestion],
        rule_suggestions: list[Suggestion],
        detector_findings: list[DetectorFinding],
        model_suggestions: list[Suggestion] | None = None,
    ) -> CandidateBundle:
        return CandidateBundle(
            spell_suggestions=self._rulebacked_candidates(spell_suggestions),
            rule_suggestions=self._rulebacked_candidates(rule_suggestions),
            detector_suggestions=[self._to_suggestion(finding) for finding in detector_findings],
            model_suggestions=self._rulebacked_candidates(model_suggestions or []),
        )

    def _rulebacked_candidates(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        return list(suggestions)

    def _to_suggestion(self, finding: DetectorFinding) -> Suggestion:
        return Suggestion(
            id=stable_id(
                "detector",
                f"{finding.rule_id}:{finding.subtype}:{finding.span_start}:{finding.span_end}:{finding.original_text}",
            ),
            rule_id=finding.rule_id,
            category=finding.category,
            subtype=finding.subtype,
            span_start=finding.span_start,
            span_end=finding.span_end,
            original_text=finding.original_text,
            replacement_options=list(finding.replacement_options),
            confidence=finding.confidence,
            explanation_bn=finding.explanation_bn,
            explanation_en=finding.explanation_en,
            source=finding.source,
            severity=finding.severity,
        )
