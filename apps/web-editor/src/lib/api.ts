import type {
  AnalyzeRequest,
  AnalyzeResponse,
  FeedbackRequest,
  HealthDeepResponse,
  RewriteRequest,
  RewriteResponse,
  ToneAnalysisRequest,
  ToneAnalysisResponse,
} from "@shared/schemas/contracts";
import {
  DEFAULT_PREFERENCES,
  normalizePreferences,
  type ShuddhoPreferences,
} from "./preferences";
import { approximateSentenceCount, normalizeAnalyzeResponse } from "./analysis";
import {
  AI_REVIEW_TIMEOUT_MS,
  DEFAULT_REQUEST_TIMEOUT_MS,
  fetchWithTimeout,
  GRAMMAR_CHECK_TIMEOUT_MS,
  HEALTH_REQUEST_TIMEOUT_MS,
} from "./fetchWithTimeout";

export { fetchWithTimeout } from "./fetchWithTimeout";

const DEFAULT_LOCAL_API_BASE_URL = "http://127.0.0.1:4000";
const API_BASE_URL_STORAGE_KEY = "shuddho-api-base-url";

export interface ApiConfigurationState {
  apiBaseUrl: string;
  source: "default_local" | "environment" | "override" | "unconfigured";
  isLocalBrowserOrigin: boolean;
  isProductionBuild: boolean;
  targetsLocalhost: boolean;
  hardWarning: string | null;
  backendAllowed: boolean;
  localFallbackEnabled: boolean;
}

export type BackendHealthResponse = Partial<HealthDeepResponse> & {
  ok?: boolean;
  service?: string;
  provider?: string;
};

export type GatewaySuggestion = {
  id?: string;
  ruleId?: string;
  rule_id?: string;
  type?: string;
  category?: string;
  subtype?: string;
  span?: {
    startIndex?: number;
    endIndex?: number;
    codePointStartIndex?: number;
    codePointEndIndex?: number;
  };
  span_start?: number;
  span_end?: number;
  originalText?: string;
  original_text?: string;
  suggestedText?: string;
  suggested_text?: string;
  replacementOptions?: string[];
  replacement_options?: string[];
  confidence?: number;
  explanationBn?: string;
  explanation_bn?: string;
  explanationEn?: string;
  explanation_en?: string;
  source?: string;
  provider?: string;
  metadata?: Record<string, unknown>;
  severity?: string;
  suppressionKey?: string;
  suppression_key?: string;
};

export type GatewayCheckResponse = {
  normalizedText?: string;
  normalized_text?: string;
  correctedText?: string;
  corrected_text?: string;
  documentAssessment?: Record<string, unknown>;
  suggestions?: GatewaySuggestion[];
  warnings?: string[];
  llm_requested?: boolean;
  llm_attempted?: boolean;
  llm_used?: boolean;
  llm_provider?: string;
  llm_model?: string;
  llm_status?: string;
  llm_response_mode?: string;
  rejected_ai_suggestion_count?: number;
  llm?: Record<string, unknown> | null;
  timings?: Record<string, number>;
  diagnostics?: Record<string, unknown>;
  local_suggestion_count?: number;
  ai_suggestion_count?: number;
};

type AnalyzeGatewayOptions = {
  includeLLM?: boolean;
  asyncLLM?: boolean;
  llmMode?: string;
  mode?: string;
  signal?: AbortSignal;
};
export type AiCheckApiResponse = {
  suggestions?: GatewaySuggestion[];
  warnings?: string[];
  provider?: string;
  model?: string;
  called?: boolean;
  llm_enabled?: boolean;
  llm_status?: string;
};
type AnalyzeOptions = Pick<
  AnalyzeGatewayOptions,
  "includeLLM" | "asyncLLM" | "llmMode" | "mode"
>;

let apiConfiguration = resolveApiConfiguration();

export function deriveApiConfiguration(args: {
  configuredBaseUrl?: string | null;
  storedBaseUrl?: string | null;
  browserHostname?: string | null;
  enableLocalFallback?: boolean | null;
  isProductionBuild?: boolean | null;
}): ApiConfigurationState {
  const {
    configuredBaseUrl,
    storedBaseUrl,
    browserHostname,
    enableLocalFallback,
    isProductionBuild,
  } = args;
  const isLocalOrigin = isLocalBrowserOrigin(browserHostname);
  const isProd = Boolean(isProductionBuild);
  const configuredValue = configuredBaseUrl?.trim() || null;
  const storedValue = storedBaseUrl?.trim() || null;
  const normalizedStoredValue = storedValue
    ? normalizeApiBaseUrl(storedValue)
    : null;
  const storedValueCanOverride = Boolean(
    normalizedStoredValue &&
    !(isLocalApiBaseUrl(normalizedStoredValue) && !isLocalOrigin) &&
    (!isProd || isNonLocalHttpsApiBaseUrl(normalizedStoredValue)),
  );
  const hasConfiguredBaseUrl = Boolean(configuredValue || storedValueCanOverride);
  const rawBaseUrl = storedValueCanOverride
    ? storedValue!
    : (configuredValue ?? (isProd ? "" : DEFAULT_LOCAL_API_BASE_URL));
  const source = storedValueCanOverride
    ? "override"
    : configuredValue
      ? "environment"
      : isProd
        ? "unconfigured"
        : "default_local";
  const apiBaseUrl = normalizeApiBaseUrl(rawBaseUrl);
  const targetsLocalhost = isLocalApiBaseUrl(apiBaseUrl);
  const localFallbackEnabled = Boolean(enableLocalFallback);
  const hardWarning =
    !isLocalOrigin && targetsLocalhost
      ? `This deployed editor is still pointing to ${apiBaseUrl}. Set VITE_API_BASE_URL to a public HTTPS tunnel URL; localhost is only valid from local browser sessions.`
      : isProd && !hasConfiguredBaseUrl
        ? "API URL is not configured. Set VITE_API_BASE_URL in Vercel."
        : null;

  return {
    apiBaseUrl,
    source,
    isLocalBrowserOrigin: isLocalOrigin,
    isProductionBuild: isProd,
    targetsLocalhost,
    hardWarning,
    backendAllowed: hardWarning === null && apiBaseUrl.length > 0,
    localFallbackEnabled,
  };
}

async function request<TResponse>(
  path: string,
  init: RequestInit,
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<TResponse> {
  if (!apiConfiguration.backendAllowed) {
    throw new Error(
      apiConfiguration.hardWarning ??
        "Backend analysis is disabled by frontend API configuration.",
    );
  }

  const url = `${getApiBaseUrl()}${path}`;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetchWithTimeout(
      url,
      {
        ...init,
        headers,
      },
      timeoutMs,
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown network error";
    throw new Error(`Network request failed for ${url}: ${message}`);
  }

  if (response.status === 422 || response.status === 500) {
    const detailJson = await response.json().catch(() => null);
    const detailText =
      detailJson === null ? (await response.text().catch(() => "")).trim() : "";
    const detail = detailJson ?? detailText ?? response.statusText;
    throw new Error(
      `Backend failed: HTTP ${response.status}; check response validation failed. ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
    );
  }

  if (!response.ok) {
    const responseText = await response.text();
    const detail = responseText.trim() || response.statusText;
    throw new Error(
      `Request failed for ${url} with ${response.status}: ${detail}`,
    );
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return response.json() as Promise<TResponse>;
}

export async function analyzeText(
  payload: AnalyzeRequest,
  options: AnalyzeGatewayOptions = {},
): Promise<AnalyzeResponse> {
  const useGateway =
    ((import.meta as ImportMeta & { env?: Record<string, string | undefined> })
      .env?.VITE_USE_GATEWAY ?? "true") !== "false";
  const path = useGateway ? "/api/check" : "/analyze";

  if (!useGateway) {
    const response = await request<Partial<AnalyzeResponse>>(
      path,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      GRAMMAR_CHECK_TIMEOUT_MS,
    );
    return normalizeAnalyzeResponse(
      response,
      payload.text,
      payload.mode ?? "standard",
    );
  }

  const body = buildCheckRequestBody(payload.text, options);
  const response = await request<GatewayCheckResponse>(
    path,
    {
      method: "POST",
      signal: options.signal,
      body: JSON.stringify(body),
    },
    options.includeLLM ? AI_REVIEW_TIMEOUT_MS : GRAMMAR_CHECK_TIMEOUT_MS,
  );

  return gatewayCheckToAnalyzeResponse(response, payload);
}

export function buildCheckRequestBody(
  text: string,
  options: AnalyzeOptions = {},
) {
  const includeLLM = Boolean(options.includeLLM);
  const asyncLLM = Boolean(options.asyncLLM);
  return {
    text: String(text ?? ""),
    language: "bn",
    options: {
      includeLLM,
      asyncLLM,
      llmMode: options.llmMode ?? (includeLLM ? "review_candidates" : "none"),
      mode: options.mode ?? (includeLLM ? "smart" : "fast"),
    },
  };
}

export async function runAiCheck(
  text: string,
  options: { signal?: AbortSignal } = {},
): Promise<AiCheckApiResponse> {
  return request<AiCheckApiResponse>(
    "/api/ai/check",
    {
      method: "POST",
      signal: options.signal,
      body: JSON.stringify({ text, language: "bn" }),
    },
    AI_REVIEW_TIMEOUT_MS,
  );
}

export function sendFeedback(payload: FeedbackRequest): Promise<void> {
  return request<void>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getHealth(): Promise<BackendHealthResponse> {
  return request<BackendHealthResponse>(
    "/health",
    {
      method: "GET",
    },
    HEALTH_REQUEST_TIMEOUT_MS,
  );
}

export async function checkBackendHealth(): Promise<{
  ok: boolean;
  message?: string;
}> {
  if (!apiConfiguration.backendAllowed) {
    return {
      ok: false,
      message:
        apiConfiguration.hardWarning ??
        "Backend health checks are disabled by frontend API configuration.",
    };
  }

  try {
    const response = await fetchWithTimeout(
      `${getApiBaseUrl()}/health`,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
        },
      },
      HEALTH_REQUEST_TIMEOUT_MS,
    );

    if (!response.ok) {
      return {
        ok: false,
        message: `Backend health check failed with status ${response.status}`,
      };
    }

    return { ok: true };
  } catch {
    return {
      ok: false,
      message:
        "Backend is unavailable. You can still use local checks. AI review will be disabled until the server is reachable.",
    };
  }
}

export async function rewriteText(
  payload: RewriteRequest,
): Promise<RewriteResponse> {
  const response = await request<
    { result?: RewriteResponse } | RewriteResponse
  >(
    "/api/rewrite",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    AI_REVIEW_TIMEOUT_MS,
  );
  return (
    "result" in response && response.result ? response.result : response
  ) as RewriteResponse;
}

export async function analyzeTone(
  payload: ToneAnalysisRequest,
): Promise<ToneAnalysisResponse> {
  const response = await request<
    { result?: ToneAnalysisResponse } | ToneAnalysisResponse
  >(
    "/api/tone",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    AI_REVIEW_TIMEOUT_MS,
  );
  return (
    "result" in response && response.result ? response.result : response
  ) as ToneAnalysisResponse;
}

async function safeJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function fetchPreferences(): Promise<ShuddhoPreferences> {
  try {
    if (!apiConfiguration.backendAllowed) {
      return DEFAULT_PREFERENCES;
    }

    const response = await fetchWithTimeout(`${getApiBaseUrl()}/api/preferences`, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      console.warn(
        `Preferences request failed with ${response.status}. Using defaults.`,
      );
      return DEFAULT_PREFERENCES;
    }

    const data = await safeJson(response);
    return normalizePreferences(
      data as Partial<ShuddhoPreferences> | null | undefined,
    );
  } catch (error) {
    console.warn("Preferences request failed. Using defaults.", error);
    return DEFAULT_PREFERENCES;
  }
}

export async function savePreferences(
  preferences: ShuddhoPreferences,
): Promise<ShuddhoPreferences> {
  const normalized = normalizePreferences(preferences);

  try {
    if (!apiConfiguration.backendAllowed) {
      return normalized;
    }

    const response = await fetchWithTimeout(`${getApiBaseUrl()}/api/preferences`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(normalized),
    });

    if (!response.ok) {
      console.warn(`Save preferences failed with ${response.status}.`);
      return normalized;
    }

    const data = await safeJson(response);
    return normalizePreferences(
      data as Partial<ShuddhoPreferences> | null | undefined,
    );
  } catch (error) {
    console.warn("Save preferences failed.", error);
    return normalized;
  }
}

export function getUserPreferences(
  _userId: string,
): Promise<ShuddhoPreferences> {
  return fetchPreferences();
}

export function saveUserPreferences(
  _userId: string,
  payload: ShuddhoPreferences,
): Promise<ShuddhoPreferences> {
  return savePreferences(payload);
}

export function gatewayCheckToAnalyzeResponse(
  response: GatewayCheckResponse,
  payload: AnalyzeRequest,
): AnalyzeResponse {
  const normalizedText =
    response.normalizedText ?? response.normalized_text ?? payload.text;
  const correctedText =
    response.correctedText ?? response.corrected_text ?? normalizedText;
  const suggestions = Array.isArray(response.suggestions)
    ? response.suggestions
    : [];
  const mode = payload.mode ?? "standard";

  const mapped = {
    text: payload.text,
    corrected_text: correctedText,
    normalized_text: normalizedText,
    analysis_profile: "gateway",
    runtime_source: "gateway",
    runtime_warnings: Array.isArray(response.warnings)
      ? response.warnings
      : [],
    warnings: Array.isArray(response.warnings) ? response.warnings : [],
    used_detector: false,
    used_corrector: false,
    backend_warning: friendlyLlmWarning(response),
    lexicon_source: "gateway",
    lexicon_version: null,
    backend_version: null,
    sentence_count: approximateSentenceCount(payload.text),
    request_mode_applied: mode,
    llm_requested: response.llm_requested,
    llm_attempted: response.llm_attempted,
    llm_used: response.llm_used,
    llm_status: response.llm_status,
    llm_provider: response.llm_provider,
    llm_model: response.llm_model,
    llm_response_mode: response.llm_response_mode,
    local_suggestion_count: response.local_suggestion_count,
    ai_suggestion_count: response.ai_suggestion_count,
    rejected_ai_suggestion_count: response.rejected_ai_suggestion_count,
    diagnostics: { ...(response.diagnostics ?? {}), llm: response.llm ?? (response.diagnostics as { llm?: unknown } | undefined)?.llm },
    llm: response.llm ?? null,
    suggestions: suggestions.map((suggestion, index) => ({
      id:
        suggestion.id ??
        `${suggestion.ruleId ?? suggestion.rule_id ?? "suggestion"}-${index}`,
      rule_id: suggestion.ruleId ?? suggestion.rule_id ?? "unknown_rule",
      category: suggestion.type ?? suggestion.category ?? "grammar",
      subtype:
        suggestion.subtype ??
        suggestion.ruleId ??
        suggestion.rule_id ??
        "suggestion",
      span_start:
        suggestion.span?.codePointStartIndex ??
        suggestion.span?.startIndex ??
        suggestion.span_start ??
        0,
      span_end:
        suggestion.span?.codePointEndIndex ??
        suggestion.span?.endIndex ??
        suggestion.span_end ??
        0,
      original_text: suggestion.originalText ?? suggestion.original_text ?? "",
      replacement_options: Array.isArray(suggestion.replacementOptions)
        ? suggestion.replacementOptions
        : Array.isArray(suggestion.replacement_options)
          ? suggestion.replacement_options
          : suggestion.suggestedText || suggestion.suggested_text
            ? [suggestion.suggestedText ?? suggestion.suggested_text ?? ""]
            : [],
      confidence: suggestion.confidence ?? 0,
      explanation_bn:
        suggestion.explanationBn ?? suggestion.explanation_bn ?? "",
      explanation_en:
        suggestion.explanationEn ?? suggestion.explanation_en ?? "",
      source: normalizeGatewaySuggestionSource(suggestion.source),
      provider: suggestion.provider ?? null,
      metadata: suggestion.metadata ?? null,
      severity: suggestion.severity ?? "low",
      suppression_key:
        suggestion.suppressionKey ?? suggestion.suppression_key ?? "",
    })),
  };

  return normalizeAnalyzeResponse(
    mapped as Partial<AnalyzeResponse>,
    payload.text,
    mode,
  );
}

export function friendlyLlmWarning(response: GatewayCheckResponse): string | null {
  const status = response.llm_status;
  const llm = (response.llm ?? {}) as Record<string, unknown>;
  const rawProvider = String(response.llm_provider ?? llm.provider ?? "").toLowerCase();
  const model = String(response.llm_model ?? llm.model ?? "");
  const skipReason = String(llm.skip_reason ?? "");
  const warnings = [
    ...(Array.isArray(response.warnings) ? response.warnings.map(String) : []),
    ...(Array.isArray(llm.warnings) ? llm.warnings.map(String) : []),
  ];
  const inferredProvider = warnings.some((w) => w.includes("openrouter")) || model.includes("/") || model.includes(":free") ? "openrouter" : warnings.some((w) => w.includes("openai")) ? "openai" : rawProvider;
  const provider = inferredProvider || rawProvider;
  const providerLabel = provider === "openrouter" ? "OpenRouter" : provider === "openai" ? "OpenAI" : "AI";
  const httpStatus = Number(llm.http_status ?? 0);
  if (!status) return null;
  if (status === "completed") {
    return (response.ai_suggestion_count ?? 0) > 0 ? `${providerLabel} reviewed the text and suggestions were merged.` : null;
  }
  if (status === "completed_empty") return `${providerLabel} reviewed the text but found no extra high-confidence suggestions.`;
  if (status === "skipped") {
    return skipReason === "include_llm_false" ? null : `AI review skipped: ${skipReason || "not requested"}.`;
  }
  if (status === "missing_key") {
    return provider === "openrouter"
      ? "OpenRouter is not configured: missing backend OPENROUTER_API_KEY."
      : "OpenAI is not configured: missing backend OPENAI_API_KEY.";
  }
  if (status === "unsupported_provider") {
    if (warnings.some((w) => w.includes("openai_model_id_suspicious_use_openrouter_provider")) || model.includes("/") || model.includes(":free")) {
      return `Invalid config: ${model || "this model"} must use SHUDDHO_LLM_PROVIDER=openrouter.`;
    }
    return "AI provider configuration is unsupported.";
  }
  if (status === "timeout") return "AI review timed out; showing local suggestions.";
  if (status === "rate_limited") return "AI provider rate limit/quota hit; showing local suggestions.";
  if (["auth_or_forbidden", "credits_or_payment_required", "model_not_found"].includes(status)) return `${providerLabel} configuration error; showing local suggestions.`;
  if (status === "provider_error" && (httpStatus === 401 || httpStatus === 403 || warnings.some((w) => w.includes("401") || w.includes("403")))) return `${providerLabel} authentication failed. Check backend API key.`;
  if (status === "invalid_json") return "AI returned invalid JSON; showing local suggestions.";
  if (status === "invalid_schema") return "AI response failed Shuddho validation.";
  if (status === "queued" || status === "attempted") return `Reviewing with ${providerLabel}.`;
  if (["provider_error", "network_error", "failed", "content_filter"].includes(status)) return "AI review unavailable; showing local suggestions.";
  return `LLM status: ${status}`;
}

function normalizeGatewaySuggestionSource(
  source: string | undefined,
): "rule" | "spell" | "model" | "hybrid" {
  if (
    source === "rule" ||
    source === "spell" ||
    source === "model" ||
    source === "hybrid"
  ) {
    return source;
  }
  if (source === "ml") {
    return "model";
  }
  return "rule";
}

export function getApiBaseUrl(): string {
  if (apiConfiguration.isProductionBuild && apiConfiguration.hardWarning) {
    console.warn(apiConfiguration.hardWarning);
  }
  return apiConfiguration.apiBaseUrl;
}

export function getApiConfiguration(): ApiConfigurationState {
  return apiConfiguration;
}

export function setApiBaseUrlOverride(nextBaseUrl: string): string {
  const trimmedValue = nextBaseUrl.trim();
  if (typeof window !== "undefined") {
    if (trimmedValue) {
      window.localStorage.setItem(API_BASE_URL_STORAGE_KEY, trimmedValue);
    } else {
      window.localStorage.removeItem(API_BASE_URL_STORAGE_KEY);
    }
    apiConfiguration = resolveApiConfiguration();
  } else {
    apiConfiguration = deriveApiConfiguration({
      configuredBaseUrl: readConfiguredBaseUrl(),
      storedBaseUrl: trimmedValue || null,
      browserHostname: readBrowserHostname(),
      enableLocalFallback: readLocalFallbackFlag(),
      isProductionBuild: readProductionFlag(),
    });
  }
  return apiConfiguration.apiBaseUrl;
}

export function clearApiBaseUrlOverride(): string {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(API_BASE_URL_STORAGE_KEY);
  }

  apiConfiguration = resolveApiConfiguration();
  return apiConfiguration.apiBaseUrl;
}

function resolveApiConfiguration(): ApiConfigurationState {
  return deriveApiConfiguration({
    configuredBaseUrl: readConfiguredBaseUrl(),
    storedBaseUrl: readStoredApiBaseUrl(),
    browserHostname: readBrowserHostname(),
    enableLocalFallback: readLocalFallbackFlag(),
    isProductionBuild: readProductionFlag(),
  });
}

function readConfiguredBaseUrl(): string | null {
  const importMetaEnv =
    (import.meta as ImportMeta & { env?: Record<string, string | undefined> })
      .env ?? {};
  const configuredBaseUrl = importMetaEnv.VITE_API_BASE_URL;
  return configuredBaseUrl?.trim() || null;
}

function readProductionFlag(): boolean {
  const importMetaEnv =
    (
      import.meta as ImportMeta & {
        env?: Record<string, string | boolean | undefined>;
      }
    ).env ?? {};
  return importMetaEnv.PROD === true || String(importMetaEnv.PROD) === "true";
}

function readLocalFallbackFlag(): boolean {
  const importMetaEnv =
    (import.meta as ImportMeta & { env?: Record<string, string | undefined> })
      .env ?? {};
  const rawValue = importMetaEnv.VITE_ENABLE_LOCAL_FALLBACK;
  if (!rawValue) {
    return false;
  }
  return /^(1|true|yes|on)$/i.test(rawValue.trim());
}

function readBrowserHostname(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.location.hostname;
}

export function readStoredApiBaseUrl(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const storedValue = window.localStorage.getItem(API_BASE_URL_STORAGE_KEY);
  if (!storedValue) {
    return null;
  }

  const trimmedValue = storedValue.trim();
  if (!trimmedValue) {
    return null;
  }

  const normalized = normalizeApiBaseUrl(trimmedValue);
  const browserHostname = readBrowserHostname();

  if (!isLocalBrowserOrigin(browserHostname) && isLocalApiBaseUrl(normalized)) {
    window.localStorage.removeItem(API_BASE_URL_STORAGE_KEY);
    return null;
  }

  return trimmedValue;
}

export function isLocalBrowserOrigin(
  hostname: string | null | undefined,
): boolean {
  if (!hostname) {
    return false;
  }
  return /^(localhost|127\.0\.0\.1)$/i.test(hostname);
}

export function isLocalApiBaseUrl(baseUrl: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(baseUrl);
}

function isNonLocalHttpsApiBaseUrl(baseUrl: string): boolean {
  return /^https:\/\//i.test(baseUrl) && !isLocalApiBaseUrl(baseUrl);
}

function normalizeApiBaseUrl(rawBaseUrl: string): string {
  const trimmedValue = rawBaseUrl.trim();
  if (!trimmedValue) {
    return "";
  }

  if (/^[a-z]+:\/\//i.test(trimmedValue) || trimmedValue.startsWith("/")) {
    return trimmedValue.replace(/\/+$/, "");
  }

  if (/^(localhost|127\.0\.0\.1)(:\d+)?$/i.test(trimmedValue)) {
    return `http://${trimmedValue}`.replace(/\/+$/, "");
  }

  return `https://${trimmedValue}`.replace(/\/+$/, "");
}
