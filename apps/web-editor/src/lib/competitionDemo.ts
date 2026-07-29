import fixtures from "@shared/fixtures/competition_demo_bn.json";
import type { AnalyzeResponse, Suggestion } from "@shared/schemas/contracts";
import { normalizeAnalyzeResponse } from "./analysis";
import { analyzeTextLocally } from "./localAnalysis";
import { getPrimaryReplacement } from "./suggestionAdapter";

export const COMPETITION_DEMO_TITLE = "Competition Demo · Local Engine";
export const COMPETITION_DEMO_DISCLOSURE =
  "This prepared competition example is reviewed locally for a reliable offline demonstration.";

type CompetitionRole = "student" | "journalist" | "government_officer";
type CompetitionCategory = "spelling" | "grammar" | "punctuation" | "spacing" | "clarity" | "style";

export type CompetitionDemoAnnotation = {
  id: string;
  ruleId: string;
  category: CompetitionCategory;
  originalText: string;
  replacementText: string;
  occurrenceIndex?: number;
  explanationBn: string;
  explanationEn: string;
  confidence: number;
  severity: "low" | "medium" | "high";
  source: "rule" | "demo_fixture";
};

export type CompetitionDemoFixture = {
  id: string;
  title: string;
  role: CompetitionRole;
  description: string;
  incorrectText: string;
  expectedCorrectedText: string;
  annotations: CompetitionDemoAnnotation[];
};

export const competitionDemoFixtures = fixtures as CompetitionDemoFixture[];

export function isCompetitionDemoModeEnabled(): boolean {
  return ((import.meta as ImportMeta & { env?: Record<string, string | boolean | undefined> }).env?.VITE_COMPETITION_DEMO_MODE ?? "false") === "true";
}

export function getCompetitionDemoFixture(fixtureId: string): CompetitionDemoFixture | null {
  return competitionDemoFixtures.find((fixture) => fixture.id === fixtureId) ?? null;
}

export function compileCompetitionDemoAnnotations(
  fixture: CompetitionDemoFixture,
  currentText: string,
): Suggestion[] {
  const suggestions: Suggestion[] = [];
  if (!currentText.trim() || currentText.length < Math.floor(fixture.incorrectText.length * 0.8)) return [];
  const annotations = [...fixture.annotations, ...buildFixturePunctuationAnnotations(fixture)];

  for (const annotation of annotations) {
    const spans = findAllOccurrences(currentText, annotation.originalText);
    if (spans.length === 0) continue;
    const occurrenceIndex = annotation.occurrenceIndex ?? 0;
    if (annotation.occurrenceIndex === undefined && spans.length > 1) continue;
    const span = spans[occurrenceIndex];
    if (!span) continue;
    const [start, end] = span;
    if (currentText.slice(start, end) !== annotation.originalText || !annotation.replacementText) continue;
    suggestions.push({
      id: `competition-${annotation.id}-${start}-${end}`,
      rule_id: annotation.ruleId,
      category: annotation.category,
      subtype: annotation.ruleId,
      span_start: start,
      span_end: end,
      original_text: annotation.originalText,
      replacement_options: [annotation.replacementText],
      confidence: annotation.confidence,
      explanation_bn: annotation.explanationBn,
      explanation_en: annotation.explanationEn,
      source: annotation.source,
      severity: annotation.severity,
      feedback_key: `competition:${annotation.id}`,
      suppression_key: `competition:${annotation.ruleId}`,
      provider: null,
      source_trace: [annotation.source === "demo_fixture" ? "prepared_competition_fixture" : "frontend_local_fallback"],
      metadata: { competition_demo: true },
    });
  }

  return suggestions;
}

export function runCompetitionDemoReview(fixtureId: string, currentText: string): AnalyzeResponse {
  if (!isCompetitionDemoModeEnabled()) {
    return normalizeAnalyzeResponse(analyzeTextLocally({ text: currentText, mode: "standard" }), currentText, "standard");
  }
  const fixture = getCompetitionDemoFixture(fixtureId);
  const local = normalizeAnalyzeResponse(analyzeTextLocally({ text: currentText, mode: "standard" }), currentText, "standard");
  const prepared = fixture ? compileCompetitionDemoAnnotations(fixture, currentText) : [];
  const suggestions = resolveSuggestionOverlaps(dedupeSuggestions([...local.suggestions, ...prepared]), currentText);
  const corrected_text = applyCompetitionSuggestions(currentText, suggestions);
  return {
    ...local,
    corrected_text,
    suggestions,
    analysis_profile: "frontend_local_fallback",
    runtime_source: "frontend_local_fallback",
    runtime_warnings: ["competition_demo_mode", "local_demo_review", ...(prepared.length ? ["prepared_fixture_annotations_used"] : [])],
    backend_warning: null,
    llm_requested: false,
    llm_attempted: false,
    llm_used: false,
    llm_status: "not_requested",
    llm_provider: null,
    llm_model: null,
    llm_response_mode: "none",
    local_suggestion_count: suggestions.filter((s) => s.source === "rule" || s.source === "spell").length,
    ai_suggestion_count: 0,
    diagnostics: { competition_demo_mode: true, local_demo_review: true, prepared_fixture_annotations_used: prepared.length },
  };
}

export function applyCompetitionSuggestions(text: string, suggestions: Suggestion[]): string {
  let draft = text;
  const selected = resolveSuggestionOverlaps(dedupeSuggestions(suggestions), text);
  for (const suggestion of [...selected].sort((a, b) => b.span_start - a.span_start)) {
    const replacement = getPrimaryReplacement(suggestion);
    if (!replacement) continue;
    if (draft.slice(suggestion.span_start, suggestion.span_end) !== suggestion.original_text) continue;
    draft = draft.slice(0, suggestion.span_start) + replacement + draft.slice(suggestion.span_end);
  }
  return draft;
}

function findAllOccurrences(text: string, needle: string): Array<[number, number]> {
  const spans: Array<[number, number]> = [];
  let from = 0;
  while (from <= text.length) {
    const start = text.indexOf(needle, from);
    if (start === -1) break;
    spans.push([start, start + needle.length]);
    from = start + Math.max(needle.length, 1);
  }
  return spans;
}

function buildFixturePunctuationAnnotations(fixture: CompetitionDemoFixture): CompetitionDemoAnnotation[] {
  const annotations: CompetitionDemoAnnotation[] = [];
  const exclamations = findAllOccurrences(fixture.incorrectText, " !!");
  exclamations.forEach((_, occurrenceIndex) => annotations.push({
    id: `demo.${fixture.id}.formal_exclamation_${occurrenceIndex}`,
    ruleId: "bn.punctuation.repeated_exclamation.formal_demo",
    category: "punctuation",
    originalText: " !!",
    replacementText: "।",
    occurrenceIndex,
    explanationBn: "আনুষ্ঠানিক ডেমো লেখায় বিস্ময়চিহ্নের বদলে পূর্ণচ্ছেদ ব্যবহার করা হয়েছে।",
    explanationEn: "Uses a Bangla full stop instead of emphatic exclamation marks in this formal demo sample.",
    confidence: 0.98,
    severity: "low",
    source: "demo_fixture",
  }));
  return annotations;
}

function dedupeSuggestions(suggestions: Suggestion[]): Suggestion[] {
  const byKey = new Map<string, Suggestion>();
  for (const suggestion of suggestions) {
    const replacement = getPrimaryReplacement(suggestion);
    if (!replacement || suggestion.provider === "gemma") continue;
    const key = `${suggestion.span_start}:${suggestion.span_end}:${suggestion.original_text}:${replacement}`;
    const existing = byKey.get(key);
    if (!existing || sourcePriority(suggestion) > sourcePriority(existing)) byKey.set(key, suggestion);
  }
  return [...byKey.values()].sort((a, b) => a.span_start - b.span_start || a.span_end - b.span_end);
}

function resolveSuggestionOverlaps(suggestions: Suggestion[], text: string): Suggestion[] {
  const selected: Suggestion[] = [];
  for (const suggestion of suggestions.sort((a, b) => a.span_start - b.span_start || sourcePriority(b) - sourcePriority(a) || b.confidence - a.confidence || a.id.localeCompare(b.id))) {
    if (text.slice(suggestion.span_start, suggestion.span_end) !== suggestion.original_text) continue;
    const overlapping = selected.find((s) => suggestion.span_start < s.span_end && suggestion.span_end > s.span_start);
    if (overlapping && (sourcePriority(overlapping) >= sourcePriority(suggestion) || overlapping.source === "demo_fixture" || suggestion.source === "demo_fixture")) continue;
    if (overlapping) selected.splice(selected.indexOf(overlapping), 1);
    selected.push(suggestion);
  }
  return selected.sort((a, b) => a.span_start - b.span_start || a.span_end - b.span_end || a.id.localeCompare(b.id));
}

function sourcePriority(suggestion: Suggestion): number {
  return suggestion.source === "demo_fixture" ? 3 : suggestion.source === "rule" ? 2 : 1;
}
