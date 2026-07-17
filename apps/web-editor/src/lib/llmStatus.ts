import type { AnalyzeResponse } from "@shared/schemas/contracts";
import { normalizeGatewaySuggestions } from "./suggestionAdapter";
import type { LlmReviewJobResponse } from "./api";

export const AI_UNAVAILABLE_STATUSES = new Set([
  "missing_key",
  "unsupported_provider",
  "auth_or_forbidden",
  "credits_or_payment_required",
  "model_not_found",
  "timeout",
  "rate_limited",
  "network_error",
  "provider_error",
  "invalid_json",
  "invalid_schema",
  "failed",
  "expired",
]);

export const LLM_TERMINAL_STATUSES = new Set([
  "completed",
  "completed_empty",
  "completed_rejected",
  ...AI_UNAVAILABLE_STATUSES,
  "cancelled",
  "succeeded",
]);

export function normalizeLlmStatus(status: unknown): string {
  const value = String(status ?? "not_requested");
  return value === "succeeded" ? "completed" : value;
}

export function isAiUnavailableStatus(status: unknown, requested?: boolean): boolean {
  return Boolean(requested) && AI_UNAVAILABLE_STATUSES.has(normalizeLlmStatus(status));
}

export function isProviderFailureStatus(status: unknown): boolean {
  return AI_UNAVAILABLE_STATUSES.has(normalizeLlmStatus(status));
}

export function mergeLlmJobIntoAnalysis(
  current: AnalyzeResponse,
  job: LlmReviewJobResponse,
): Partial<AnalyzeResponse> {
  const status = normalizeLlmStatus(job.llm_status ?? job.status);
  const currentSuggestions = normalizeGatewaySuggestions(current.suggestions, current.text);
  const jobSuggestions = normalizeGatewaySuggestions(job.suggestions, current.text);
  const providerFailureWithNoSuggestions = isProviderFailureStatus(status) && jobSuggestions.length === 0;
  const terminalSuccess = ["completed", "completed_empty", "completed_rejected"].includes(status);
  const selectedSuggestions = providerFailureWithNoSuggestions
    ? currentSuggestions
    : terminalSuccess || jobSuggestions.length > 0
      ? jobSuggestions
      : currentSuggestions;
  const dedupedSuggestions = Array.from(new Map(selectedSuggestions.map((suggestion) => [suggestion.id, suggestion])).values());
  return {
    ...current,
    ...job,
    suggestions: dedupedSuggestions,
    llm_status: status,
    llm_requested: job.llm_requested ?? current.llm_requested,
    llm_attempted: job.llm_attempted ?? current.llm_attempted,
    llm_used: job.llm_used ?? current.llm_used,
    llm_provider: job.llm_provider ?? job.provider ?? current.llm_provider,
    llm_model: job.llm_model ?? job.model ?? current.llm_model,
    llm_response_mode: job.llm_response_mode ?? current.llm_response_mode,
    diagnostics: job.diagnostics ?? current.diagnostics,
    llm: job.llm ?? current.llm,
  };
}

export function llmReviewStatusMessage(job: Partial<LlmReviewJobResponse>): string {
  const status = normalizeLlmStatus(job.llm_status ?? job.status);
  const attempts = Array.isArray(job.provider_attempts)
    ? job.provider_attempts
    : Array.isArray((job.llm as { provider_attempts?: unknown[] } | undefined)?.provider_attempts)
      ? ((job.llm as { provider_attempts: unknown[] }).provider_attempts)
      : [];
  const warnings = Array.isArray(job.warnings) ? job.warnings : [];
  const usedOpenRouterFallback =
    warnings.includes("fallback_provider_used:openrouter") ||
    (job.llm_provider === "openrouter" && attempts.some((attempt) => (attempt as { provider?: string }).provider === "gemini"));
  if (usedOpenRouterFallback && ["completed", "completed_empty", "completed_rejected"].includes(status)) {
    return "Gemini was unavailable, so OpenRouter completed the review.";
  }
  if (status === "completed") return "AI review complete.";
  if (status === "completed_empty") return "AI reviewed the text and found no additional high-confidence issues.";
  if (status === "completed_rejected") return "AI reviewed the text, but its suggestions did not pass validation. Local suggestions are still shown.";
  if (status === "queued" || status === "running") return "AI review is checking…";
  if (isProviderFailureStatus(status)) return "AI review is temporarily unavailable. Local suggestions are still shown.";
  return "AI review complete.";
}
