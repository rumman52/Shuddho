from __future__ import annotations

from services.feedback.shuddho_feedback.store import FeedbackStore
from shared.schemas.python_models import Suggestion, SuggestionDensity, UserPreferences


class UserPreferencesService:
    def __init__(self, feedback_store: FeedbackStore) -> None:
        self.feedback_store = feedback_store

    def load(self, user_id: str | None) -> UserPreferences | None:
        if not user_id or not hasattr(self.feedback_store, "load_user_preferences"):
            return None
        return self.feedback_store.load_user_preferences(user_id)

    def save(self, user_id: str, preferences: UserPreferences) -> UserPreferences:
        return self.feedback_store.save_user_preferences(user_id, preferences)

    def merge_personal_dictionary(self, request_entries: list[str], preferences: UserPreferences | None) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for entry in [*request_entries, *(preferences.personal_dictionary if preferences else [])]:
            normalized = " ".join(entry.split())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged

    def filter_suggestions(self, suggestions: list[Suggestion], preferences: UserPreferences | None) -> list[Suggestion]:
        if preferences is None:
            return suggestions

        visible = [
            suggestion
            for suggestion in suggestions
            if not self._is_rule_suppressed(suggestion, preferences)
        ]
        return _apply_density(visible, preferences.suggestion_density)

    def is_site_disabled(self, preferences: UserPreferences | None, hostname: str) -> bool:
        if preferences is None:
            return False
        normalized_hostname = hostname.strip().lower()
        if not normalized_hostname:
            return False
        return normalized_hostname in {value.strip().lower() for value in preferences.disabled_sites}

    def _is_rule_suppressed(self, suggestion: Suggestion, preferences: UserPreferences) -> bool:
        suppressed_keys = set(preferences.suppressed_rule_keys)
        candidate_keys = {
            suggestion.rule_id,
            f"{suggestion.rule_id}:{suggestion.subtype}",
        }
        if suggestion.suppression_key:
            candidate_keys.add(suggestion.suppression_key)
        return bool(candidate_keys & suppressed_keys)


def _apply_density(suggestions: list[Suggestion], density: SuggestionDensity) -> list[Suggestion]:
    if density == SuggestionDensity.HIGH:
        return suggestions
    if density == SuggestionDensity.BALANCED:
        return suggestions

    hard_suggestions = [
        suggestion
        for suggestion in suggestions
        if suggestion.ui_group not in {"register", "clarity"}
    ]
    soft_candidates = [
        suggestion
        for suggestion in suggestions
        if suggestion.ui_group in {"register", "clarity"} or suggestion.category in {"register", "clarity"}
    ]
    soft_candidates.sort(
        key=lambda suggestion: (
            -(suggestion.ranking_score or suggestion.confidence),
            -suggestion.confidence,
            suggestion.span_start,
        )
    )
    return [*hard_suggestions, *soft_candidates[:3]]
