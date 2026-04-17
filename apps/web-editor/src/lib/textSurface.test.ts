import assert from "node:assert/strict";
import test from "node:test";

import type { Suggestion } from "@shared/schemas/contracts";

import { matchSuggestionByContext, resolveSuggestionMatch } from "./textSurface";

function buildSuggestion(overrides: Partial<Suggestion> = {}): Suggestion {
  return {
    id: "s1",
    rule_id: "LLM_GRAMMAR_001",
    category: "grammar",
    subtype: "repeated_word",
    span_start: 4,
    span_end: 7,
    original_text: "আজও",
    replacement_options: ["আজ"],
    confidence: 0.95,
    explanation_bn: "'আজও' নয়, এখানে 'আজ' হবে।",
    explanation_en: "Use 'আজ' here.",
    source: "model",
    severity: "medium",
    occurrence_index: 1,
    anchor_before: "আজও ",
    anchor_after: " ভালো।",
    sentence_index: 0,
    sentence_start: 0,
    sentence_end: 13,
    source_trace: ["occurrence_index", "anchor_triplet"],
    ...overrides,
  };
}

test("resolveSuggestionMatch anchors repeated Bengali spans safely", () => {
  const suggestion = buildSuggestion();
  const match = resolveSuggestionMatch("আজও আজও ভালো।", suggestion);

  assert.equal(match.status, "current");
  assert.equal(match.spanStart, 4);
  assert.equal(match.spanEnd, 7);
});

test("resolveSuggestionMatch marks stale suggestions when anchors disappear", () => {
  const suggestion = buildSuggestion();
  const match = resolveSuggestionMatch("আজ ভালো।", suggestion);

  assert.equal(match.status, "stale");
});

test("matchSuggestionByContext keeps popup anchoring strict instead of fuzzy", () => {
  const previous = buildSuggestion({ id: "old" });
  const matching = buildSuggestion({ id: "new" });
  const wrongOccurrence = buildSuggestion({ id: "wrong", occurrence_index: 0, span_start: 0, span_end: 4, anchor_before: null });

  assert.equal(matchSuggestionByContext(previous, [wrongOccurrence, matching])?.id, "new");
  assert.equal(matchSuggestionByContext(previous, [wrongOccurrence])?.id ?? null, null);
});
