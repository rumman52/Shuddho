import type { Suggestion } from "@shared/schemas/contracts";
import { resolveSuggestionMatch } from "./textSurface";

export type SuggestionTransactionSuccess = {
  ok: true;
  text: string;
  suggestions: Suggestion[];
  appliedId: string;
  caret: number;
};

export type SuggestionTransactionFailure = {
  ok: false;
  reason: "stale" | "ambiguous";
  message: string;
};

export type SuggestionTransactionResult = SuggestionTransactionSuccess | SuggestionTransactionFailure;

export function applySuggestionTransaction(
  currentText: string,
  selectedSuggestion: Suggestion,
  chosenReplacement: string,
  currentSuggestions: Suggestion[],
): SuggestionTransactionResult {
  const match = resolveSuggestionMatch(currentText, selectedSuggestion);
  if (match.status !== "current") {
    return staleResult();
  }
  const start = match.spanStart;
  const end = match.spanEnd;
  if (currentText.slice(start, end) !== selectedSuggestion.original_text) {
    return staleResult();
  }
  const text = `${currentText.slice(0, start)}${chosenReplacement}${currentText.slice(end)}`;
  const delta = chosenReplacement.length - (end - start);
  const suggestions: Suggestion[] = [];
  for (const suggestion of currentSuggestions) {
    if (suggestion.id === selectedSuggestion.id) continue;
    const suggestionMatch = resolveSuggestionMatch(currentText, suggestion);
    if (suggestionMatch.status !== "current") continue;
    const overlaps = suggestionMatch.spanStart < end && suggestionMatch.spanEnd > start;
    if (overlaps) continue;
    const rebased = { ...suggestion };
    if (suggestionMatch.spanStart >= end) {
      rebased.span_start = suggestionMatch.spanStart + delta;
      rebased.span_end = suggestionMatch.spanEnd + delta;
    } else {
      rebased.span_start = suggestionMatch.spanStart;
      rebased.span_end = suggestionMatch.spanEnd;
    }
    const revalidated = resolveSuggestionMatch(text, rebased);
    if (revalidated.status !== "current") continue;
    if (text.slice(revalidated.spanStart, revalidated.spanEnd) !== rebased.original_text) continue;
    suggestions.push({ ...rebased, span_start: revalidated.spanStart, span_end: revalidated.spanEnd });
  }
  return { ok: true, text, suggestions, appliedId: selectedSuggestion.id, caret: start + chosenReplacement.length };
}

export function applySuggestionBatchTransaction(currentText: string, currentSuggestions: Suggestion[]) {
  let text = currentText;
  let suggestions = [...currentSuggestions];
  const appliedIds: string[] = [];
  let skipped = 0;
  for (const suggestion of [...suggestions].sort((a, b) => b.span_start - a.span_start)) {
    const replacement = firstReplacement(suggestion);
    if (!replacement) {
      skipped += 1;
      continue;
    }
    const result = applySuggestionTransaction(text, suggestion, replacement, suggestions);
    if (!result.ok) {
      skipped += 1;
      continue;
    }
    text = result.text;
    suggestions = result.suggestions;
    appliedIds.push(result.appliedId);
  }
  return { text, suggestions, appliedIds, applied: appliedIds.length, skipped };
}

function staleResult(): SuggestionTransactionFailure {
  return { ok: false, reason: "stale", message: "This suggestion is outdated; the review has been refreshed." };
}

function firstReplacement(suggestion: Suggestion): string | null {
  const options = suggestion.replacement_options;
  return Array.isArray(options) && typeof options[0] === "string" && options[0].length > 0 ? options[0] : null;
}
