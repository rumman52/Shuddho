import type {
  AnalyzeMode,
  AnalyzeResponse,
  Suggestion,
} from "@shared/schemas/contracts";
import { normalizeGatewaySuggestions } from "./suggestionAdapter";

export function approximateSentenceCount(text: string): number {
  return text
    .split(/[.!?\u0964]+/u)
    .map((sentence) => sentence.trim())
    .filter(Boolean).length;
}

export function createEmptyAnalysis(
  text: string,
  mode: AnalyzeMode,
  profile: AnalyzeResponse["analysis_profile"] = "backend_rules_and_spell_only",
): AnalyzeResponse {
  return {
    text,
    normalized_text: text,
    corrected_text: text,
    suggestions: [],
    analysis_profile: profile,
    runtime_source: profile,
    runtime_warnings: [],
    used_detector: false,
    used_corrector: false,
    backend_warning: null,
    lexicon_source: "unknown",
    lexicon_version: null,
    backend_version: null,
    sentence_count: approximateSentenceCount(text),
    request_mode_applied: mode,
  };
}

export function normalizeAnalyzeResponse(
  input: Partial<AnalyzeResponse> | null | undefined,
  fallbackText: string,
  fallbackMode: AnalyzeMode,
): AnalyzeResponse {
  const base = createEmptyAnalysis(fallbackText, fallbackMode);

  const suggestions = normalizeGatewaySuggestions(input?.suggestions, input?.text ?? fallbackText);

  return {
    ...base,
    ...(input || {}),
    text: input?.text ?? fallbackText,
    normalized_text: input?.normalized_text ?? input?.text ?? fallbackText,
    corrected_text:
      input?.corrected_text ??
      input?.normalized_text ??
      input?.text ??
      fallbackText,
    suggestions,
    runtime_warnings: Array.isArray(input?.runtime_warnings)
      ? input.runtime_warnings
      : Array.isArray(
            (input as { warnings?: unknown } | null | undefined)?.warnings,
          )
        ? (input as { warnings: string[] }).warnings
        : [],
    backend_warning: input?.backend_warning ?? null,
    lexicon_source: input?.lexicon_source ?? "unknown",
    lexicon_version: input?.lexicon_version ?? null,
    backend_version: input?.backend_version ?? null,
    sentence_count:
      typeof input?.sentence_count === "number"
        ? input.sentence_count
        : approximateSentenceCount(input?.text ?? fallbackText),
    request_mode_applied: input?.request_mode_applied ?? fallbackMode,
    llm_requested: input?.llm_requested,
    llm_attempted: input?.llm_attempted,
    llm_used: input?.llm_used,
    llm_status: input?.llm_status,
    llm_provider: input?.llm_provider,
    llm_model: input?.llm_model,
    llm_response_mode: input?.llm_response_mode,
    local_suggestion_count: input?.local_suggestion_count,
    ai_suggestion_count: input?.ai_suggestion_count,
    rejected_ai_suggestion_count: input?.rejected_ai_suggestion_count,
    diagnostics: input?.diagnostics,
    llm: input?.llm,
  };
}

export function safeSuggestions(
  input: Partial<AnalyzeResponse> | null | undefined,
): Suggestion[] {
  return normalizeGatewaySuggestions(input?.suggestions, input?.text ?? "");
}
