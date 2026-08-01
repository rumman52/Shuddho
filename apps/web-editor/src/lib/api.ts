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
import { normalizeGatewaySuggestions } from "./suggestionAdapter";
import {
  AI_REVIEW_TIMEOUT_MS,
  DEFAULT_REQUEST_TIMEOUT_MS,
  FetchTimeoutError,
  fetchWithTimeout,
  GRAMMAR_CHECK_TIMEOUT_MS,
  HEALTH_REQUEST_TIMEOUT_MS,
} from "./fetchWithTimeout";

export { fetchWithTimeout } from "./fetchWithTimeout";

const DEFAULT_LOCAL_API_BASE_URL = "http://127.0.0.1:4000";
// Vercel rewrites this same-origin prefix to the Render API.  Keeping a
// production-safe default means a missing build-time VITE_API_BASE_URL no
// longer disables the editor, and browser CORS policy is avoided entirely.
const DEFAULT_PRODUCTION_API_BASE_URL = "/backend";
const API_BASE_URL_STORAGE_KEY = "shuddho-api-base-url";

export interface ApiConfigurationState {
  apiBaseUrl: string;
  source: "default_local" | "same_origin_proxy" | "environment" | "override";
  apiBaseUrlSource: "default_local" | "same_origin_proxy" | "environment" | "override";
  envApiBaseUrlPresent: boolean;
  localStorageOverridePresent: boolean;
  localStorageOverrideIgnored: boolean;
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

export type LlmDebugResponse = {
  enabled?: boolean;
  configured?: boolean;
  provider?: string;
  model?: string;
  status?: string;
  warnings?: string[];
  api_key_present?: boolean;
  on_check?: string;
  timeout_settings?: Record<string, unknown>;
  circuit_state?: string;
  circuit_open?: boolean;
  [key: string]: unknown;
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
  ai_raw_suggestion_count?: number;
  ai_valid_suggestion_count?: number;
  ai_rejected_suggestion_count?: number;
  rejected_ai_suggestion_count?: number;
  ai_empty_reason?: string | null;
  provider_attempts?: Record<string, unknown>[];
  usage?: Record<string, unknown>;
  llm?: Record<string, unknown> | null;
  timings?: Record<string, number | boolean | string>;
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
  allowLocalStorageOverride?: boolean | null;
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
  const envApiBaseUrlPresent = Boolean(configuredValue);
  const localStorageOverridePresent = Boolean(storedValue);
  // Production deployments must always use the configured backend URL.
  // A stale localStorage override from a previous debug session can otherwise
  // pin the Vercel app to an old backend and make /api/check look unavailable.
  const storedValueCanOverride = Boolean(
    normalizedStoredValue &&
    !isProd &&
    !(isLocalApiBaseUrl(normalizedStoredValue) && !isLocalOrigin),
  );
  const localStorageOverrideIgnored = Boolean(
    storedValue && !storedValueCanOverride && (isProd || configuredValue),
  );
  const rawBaseUrl = storedValueCanOverride
    ? storedValue!
    : (configuredValue ?? (isProd ? DEFAULT_PRODUCTION_API_BASE_URL : DEFAULT_LOCAL_API_BASE_URL));
  const source = storedValueCanOverride
    ? "override"
    : configuredValue
      ? "environment"
      : isProd
        ? "same_origin_proxy"
        : "default_local";
  const apiBaseUrl = normalizeApiBaseUrl(rawBaseUrl);
  const targetsLocalhost = isLocalApiBaseUrl(apiBaseUrl);
  const localFallbackEnabled = Boolean(enableLocalFallback);
  const hardWarning =
    !isLocalOrigin && targetsLocalhost
      ? "This deployed editor is still pointing to localhost. Use a public HTTPS backend URL."
      : null;

  return {
    apiBaseUrl,
    source,
    apiBaseUrlSource: source,
    envApiBaseUrlPresent,
    localStorageOverridePresent,
    localStorageOverrideIgnored,
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
  headers.set("Accept", "application/json");
  const method = (init.method ?? "GET").toUpperCase();
  const hasBody = init.body !== undefined && init.body !== null;
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (hasBody && !isFormData && method !== "GET" && method !== "HEAD" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

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
    throw new Error(describeRequestFailure(error, url));
  }

  if (response.status === 422 || response.status === 500) {
    const detailJson = await safeJson(response);
    const detail = detailJson ?? response.statusText;
    throw new Error(
      `Backend failed: HTTP ${response.status}; backend HTTP status error for ${url}; check response validation failed. ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
    );
  }

  if (!response.ok) {
    const responseText = await response.text().catch(() => "");
    const detail = responseText.trim() || response.statusText;
    throw new Error(
      `Backend HTTP status error for ${url}: HTTP ${response.status}; ${detail}`,
    );
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  const json = await safeJson(response);
  if (json === null) {
    throw new Error(`Backend JSON invalid for ${url}: response was not valid JSON.`);
  }
  return json as TResponse;
}

export function describeRequestFailure(error: unknown, url: string): string {
  if (
    error instanceof FetchTimeoutError ||
    (error instanceof Error && error.name === "FetchTimeoutError")
  ) {
    const timeoutMs =
      typeof (error as { timeoutMs?: unknown }).timeoutMs === "number"
        ? (error as unknown as { timeoutMs: number }).timeoutMs
        : "the configured timeout";
    return `Backend timeout for ${url} after ${timeoutMs}ms. Render may still be cold-starting; try again shortly.`;
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return `Request aborted for ${url}.`;
  }
  const message =
    error instanceof Error ? error.message : String(error ?? "Unknown network error");
  const lower = message.toLowerCase();
  if (
    error instanceof TypeError ||
    lower.includes("failed to fetch") ||
    lower.includes("networkerror")
  ) {
    return `CORS/network failure for ${url}. Check VITE_API_BASE_URL, backend deployment, and SHUDDHO_ALLOWED_ORIGINS. ${message}`;
  }
  return `Network request failed for ${url}: ${message}`;
}

export async function analyzeText(
  payload: AnalyzeRequest,
  options: AnalyzeGatewayOptions = {},
): Promise<AnalyzeResponse> {
  const useGateway = readViteBoolean("VITE_USE_GATEWAY", true);
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
  if ((import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV) {
    console.info("SHUDDHO_API_CHECK_REQUEST", {
      url: `${getApiBaseUrl()}${path}`,
      includeLLM: body.options.includeLLM,
      llmMode: body.options.llmMode,
      mode: body.options.mode,
    });
  }

  const startedAt = performance.now();
  const url = `${getApiBaseUrl()}${path}`;
  let httpResponse: Response;
  try {
    httpResponse = await fetchWithTimeout(
      url,
      {
        method: "POST",
        signal: options.signal,
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      options.includeLLM ? AI_REVIEW_TIMEOUT_MS : GRAMMAR_CHECK_TIMEOUT_MS,
    );
  } catch (error) {
    throw new Error(describeRequestFailure(error, url));
  }

  const httpStatus = httpResponse.status;
  const json = await safeJson(httpResponse);
  if (!httpResponse.ok) {
    throw new Error(
      `Backend failed: HTTP ${httpStatus}; backend HTTP status error for ${url}; check response validation failed. ${sanitizeApiErrorDetail(json ?? httpResponse.statusText)}`,
    );
  }
  if (json === null) {
    throw new Error(`Backend JSON invalid for ${url}: response was not valid JSON.`);
  }

  const validation = validateGatewayCheckResponse(json);
  if (!validation.ok) {
    throw new Error(`Backend response validation failed: ${validation.reason}`);
  }

  const response = json as GatewayCheckResponse;
  return gatewayCheckToAnalyzeResponse(
    {
      ...response,
      diagnostics: {
        ...(response.diagnostics ?? {}),
        http_status: httpStatus,
        duration_ms: Math.round(performance.now() - startedAt),
      },
    },
    payload,
  );
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


export type LlmReviewJobResponse = GatewayCheckResponse & {
  job_id?: string;
  status?: string;
  llm_status?: string;
  provider?: string;
  model?: string;
};

export function getLlmReviewJob(jobId: string, options: { signal?: AbortSignal } = {}): Promise<LlmReviewJobResponse> {
  return request<LlmReviewJobResponse>(
    `/api/llm/review/${encodeURIComponent(jobId)}`,
    { method: "GET", signal: options.signal },
    DEFAULT_REQUEST_TIMEOUT_MS,
  );
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

function validateGatewayCheckResponse(input: unknown): { ok: true } | { ok: false; reason: string } {
  if (!input || typeof input !== "object") {
    return { ok: false, reason: "response_body_not_object" };
  }
  const record = input as Record<string, unknown>;
  if (!("suggestions" in record)) {
    return { ok: false, reason: "missing_suggestions_array" };
  }
  if (!Array.isArray(record.suggestions)) {
    return { ok: false, reason: "suggestions_not_array" };
  }
  return { ok: true };
}

function sanitizeApiErrorDetail(detail: unknown): string {
  return String(typeof detail === "string" ? detail : JSON.stringify(detail))
    .replace(/(authorization|api[_-]?key|token)["'=:\s]+[^,"'\s}]+/gi, "$1=[redacted]")
    .slice(0, 500);
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

export function getHealthDeep(): Promise<BackendHealthResponse> {
  return request<BackendHealthResponse>(
    "/health/deep",
    {
      method: "GET",
    },
    HEALTH_REQUEST_TIMEOUT_MS,
  );
}

export function getLlmDebug(): Promise<LlmDebugResponse> {
  return request<LlmDebugResponse>(
    "/api/llm/debug",
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

    const health = (await safeJson(response)) as BackendHealthResponse | null;
    if (health?.ok === true) {
      return { ok: true };
    }

    return {
      ok: false,
      message: health
        ? "Backend health response did not report ok:true."
        : "Backend health response was not valid JSON.",
    };
  } catch (error) {
    return {
      ok: false,
      message: describeRequestFailure(error, `${getApiBaseUrl()}/health`),
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
    usage: response.usage,
    provider_attempts: response.provider_attempts,
    local_suggestion_count: response.local_suggestion_count,
    ai_suggestion_count: response.ai_suggestion_count,
    rejected_ai_suggestion_count: response.rejected_ai_suggestion_count,
    diagnostics: { ...(response.diagnostics ?? {}), llm: response.llm ?? (response.diagnostics as { llm?: unknown } | undefined)?.llm },
    llm: response.llm ?? null,
    suggestions: normalizeGatewaySuggestions(suggestions, payload.text),
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
  const skipReason = String(llm.skip_reason ?? "");
  const warnings = [
    ...(Array.isArray(response.warnings) ? response.warnings.map(String) : []),
    ...(Array.isArray(llm.warnings) ? llm.warnings.map(String) : []),
  ];
  const provider = rawProvider || "gemma";
  const providerLabel = provider === "gemma" ? "Gemma" : "AI";
  const httpStatus = Number(llm.http_status ?? 0);
  const rejectedCount = Number(response.rejected_ai_suggestion_count ?? llm.rejected_ai_suggestion_count ?? 0);
  if (!status) return null;
  if (status === "completed") {
    return null;
  }
  if (rejectedCount > 0 || status === "completed_rejected") {
    return "AI reviewed the text, but its suggestions were rejected by validation. Showing local suggestions.";
  }
  if (status === "completed_empty") return "AI reviewed the text but found no extra high-confidence suggestions.";
  if (status === "skipped") {
    if (response.llm_requested === false || skipReason === "include_llm_false") {
      return "AI review was not requested. Showing local suggestions.";
    }
    return `AI review skipped: ${skipReason || "not requested"}.`;
  }
  if (status === "missing_key") return "Gemma is not configured: missing backend GOOGLE_API_KEY.";
  if (status === "unsupported_provider") return "Invalid configuration: Shuddho supports only the Gemma provider and Gemma models.";
  if (status === "timeout") return "AI review timed out; showing local suggestions.";
  if (status === "rate_limited") return "AI provider rate limit/quota hit; showing local suggestions.";
  if (["auth_or_forbidden", "credits_or_payment_required", "model_not_found"].includes(status)) return `${providerLabel} configuration error; showing local suggestions.`;
  if (status === "provider_error" && (httpStatus === 401 || httpStatus === 403 || warnings.some((w) => w.includes("401") || w.includes("403")))) return `${providerLabel} authentication failed. Check backend API key.`;
  if (status === "invalid_json") return "Gemma returned malformed JSON, so Shuddho safely ignored it and kept local suggestions.";
  if (status === "invalid_schema") return "Gemma returned a response in the wrong format, so Shuddho safely kept local suggestions.";
  if (status === "queued" || status === "attempted") return `Reviewing with ${providerLabel}.`;
  if (["provider_error", "network_error", "failed"].includes(status)) return "Gemma is unavailable. Showing local suggestions.";
  if (status === "content_filter") return `${providerLabel} could not review this content. Showing local suggestions.`;
  return `LLM status: ${status}`;
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
      allowLocalStorageOverride: readApiOverrideDebugFlag(),
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
    allowLocalStorageOverride: readApiOverrideDebugFlag(),
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
  return readViteBoolean("VITE_ENABLE_LOCAL_FALLBACK", false);
}

function readApiOverrideDebugFlag(): boolean {
  // Kept for compatibility with tests/callers of deriveApiConfiguration, but
  // deriveApiConfiguration intentionally ignores overrides in production.
  if (readProductionFlag()) {
    return false;
  }
  if (readViteBoolean("VITE_ALLOW_API_BASE_URL_OVERRIDE", false)) {
    return true;
  }
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem("shuddho-web-editor-debug") === "1";
}

function readViteBoolean(key: string, fallback: boolean): boolean {
  const importMetaEnv =
    (import.meta as ImportMeta & { env?: Record<string, string | boolean | undefined> })
      .env ?? {};
  const rawValue = importMetaEnv[key];
  if (typeof rawValue === "boolean") {
    return rawValue;
  }
  if (rawValue === undefined || rawValue === null || String(rawValue).trim() === "") {
    return fallback;
  }
  const normalized = String(rawValue).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "off"].includes(normalized)) {
    return false;
  }
  return fallback;
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
