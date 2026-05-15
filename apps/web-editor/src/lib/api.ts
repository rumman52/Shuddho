import type {
  AnalyzeRequest,
  AnalyzeResponse,
  FeedbackRequest,
  HealthDeepResponse,
  RewriteRequest,
  RewriteResponse,
  ToneAnalysisRequest,
  ToneAnalysisResponse,
  UserPreferences,
} from "@shared/schemas/contracts";

const DEFAULT_LOCAL_API_BASE_URL = "http://127.0.0.1:4000";
const API_BASE_URL_STORAGE_KEY = "shuddho-api-base-url";

export interface ApiConfigurationState {
  apiBaseUrl: string;
  source: "default_local" | "environment" | "override";
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

let apiConfiguration = resolveApiConfiguration();

export function deriveApiConfiguration(args: {
  configuredBaseUrl?: string | null;
  storedBaseUrl?: string | null;
  browserHostname?: string | null;
  enableLocalFallback?: boolean | null;
  isProductionBuild?: boolean | null;
}): ApiConfigurationState {
  const { configuredBaseUrl, storedBaseUrl, browserHostname, enableLocalFallback, isProductionBuild } = args;
  const isLocalOrigin = isLocalBrowserOrigin(browserHostname);
  const isProd = Boolean(isProductionBuild);
  const hasConfiguredBaseUrl = Boolean(configuredBaseUrl?.trim() || storedBaseUrl?.trim());
  const rawBaseUrl = storedBaseUrl?.trim() || configuredBaseUrl?.trim() || DEFAULT_LOCAL_API_BASE_URL;
  const source =
    storedBaseUrl?.trim() ? "override" : configuredBaseUrl?.trim() ? "environment" : "default_local";
  const apiBaseUrl = normalizeApiBaseUrl(rawBaseUrl);
  const targetsLocalhost = isLocalApiBaseUrl(apiBaseUrl);
  const localFallbackEnabled = Boolean(enableLocalFallback);
  const hardWarning =
    !isLocalOrigin && targetsLocalhost
      ? `This deployed editor is still pointing to ${apiBaseUrl}. Set VITE_API_BASE_URL to a public HTTPS tunnel URL; localhost is only valid from local browser sessions.`
      : isProd && !hasConfiguredBaseUrl
        ? "VITE_API_BASE_URL is not set. Deployed frontend cannot call local backend without a public HTTPS tunnel."
        : null;

  return {
    apiBaseUrl,
    source,
    isLocalBrowserOrigin: isLocalOrigin,
    isProductionBuild: isProd,
    targetsLocalhost,
    hardWarning,
    backendAllowed: hardWarning === null,
    localFallbackEnabled,
  };
}

async function request<TResponse>(path: string, init: RequestInit): Promise<TResponse> {
  if (!apiConfiguration.backendAllowed) {
    throw new Error(apiConfiguration.hardWarning ?? "Backend analysis is disabled by frontend API configuration.");
  }

  const url = `${apiConfiguration.apiBaseUrl}${path}`;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown network error";
    throw new Error(`Network request failed for ${url}: ${message}`);
  }

  if (!response.ok) {
    const responseText = await response.text();
    const detail = responseText.trim() || response.statusText;
    throw new Error(`Request failed for ${url} with ${response.status}: ${detail}`);
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return response.json() as Promise<TResponse>;
}

export async function analyzeText(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  const useGateway = ((import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env?.VITE_USE_GATEWAY ?? "true") !== "false";
  if (!useGateway) {
    return request<AnalyzeResponse>("/analyze", { method: "POST", body: JSON.stringify(payload) });
  }
  const response = await request<any>("/api/check", {
    method: "POST",
    body: JSON.stringify({ text: payload.text, language: "bn", userId: payload.user_id, client: { surface: "web", version: "vite-editor" } }),
  });
  return {
    text: payload.text,
    corrected_text: response.normalizedText ?? payload.text,
    analysis_profile: "frontend_local_fallback",
    runtime_source: "gateway",
    runtime_source_path: null,
    runtime_lexicon_version: null,
    runtime_lexicon_checksum: null,
    detector_enabled: false,
    corrector_enabled: false,
    degraded_reasons: response.warnings ?? [],
    normalized_text: response.normalizedText,
    suggestions: response.suggestions.map((s: any) => ({
      id: s.id, rule_id: s.ruleId, category: s.type, subtype: s.ruleId,
      span_start: s.span.codePointStartIndex ?? s.span.startIndex, span_end: s.span.codePointEndIndex ?? s.span.endIndex,
      original_text: s.originalText, replacement_options: s.replacementOptions, confidence: s.confidence,
      explanation_bn: s.explanationBn, explanation_en: s.explanationEn ?? "", source: s.source, severity: s.severity,
      suppression_key: s.suppressionKey,
    })),
    warnings: response.warnings ?? [],
  } as unknown as AnalyzeResponse;
}

export function sendFeedback(payload: FeedbackRequest): Promise<void> {
  return request<void>("/api/events", {
    method: "POST",
    body: JSON.stringify({ type: "suggestion_accepted", language: "bn", suggestionId: payload.suggestion_id, metadata: { action: payload.action, ruleId: payload.feedback_key } }),
  });
}

export function getHealth(): Promise<BackendHealthResponse> {
  return request<BackendHealthResponse>("/health", {
    method: "GET",
  });
}

export async function rewriteText(payload: RewriteRequest): Promise<RewriteResponse> {
  const response = await request<{ result?: RewriteResponse } | RewriteResponse>("/api/rewrite", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return ("result" in response && response.result ? response.result : response) as RewriteResponse;
}

export async function analyzeTone(payload: ToneAnalysisRequest): Promise<ToneAnalysisResponse> {
  const response = await request<{ result?: ToneAnalysisResponse } | ToneAnalysisResponse>("/api/tone", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return ("result" in response && response.result ? response.result : response) as ToneAnalysisResponse;
}

export function getUserPreferences(_userId: string): Promise<UserPreferences> {
  return request<UserPreferences>("/api/preferences", {
    method: "GET",
  });
}

export function saveUserPreferences(_userId: string, payload: UserPreferences): Promise<UserPreferences> {
  return request<UserPreferences>("/api/preferences", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
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
  }

  apiConfiguration = deriveApiConfiguration({
    configuredBaseUrl: readConfiguredBaseUrl(),
    storedBaseUrl: trimmedValue || null,
    browserHostname: readBrowserHostname(),
    enableLocalFallback: readLocalFallbackFlag(),
    isProductionBuild: readProductionFlag(),
  });
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
  const importMetaEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {};
  const configuredBaseUrl = importMetaEnv.VITE_API_BASE_URL ?? importMetaEnv.VITE_API_URL;
  return configuredBaseUrl?.trim() || null;
}

function readProductionFlag(): boolean {
  const importMetaEnv = (import.meta as ImportMeta & { env?: Record<string, string | boolean | undefined> }).env ?? {};
  return importMetaEnv.PROD === true || String(importMetaEnv.PROD) === "true";
}

function readLocalFallbackFlag(): boolean {
  const importMetaEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {};
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

function readStoredApiBaseUrl(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const storedValue = window.localStorage.getItem(API_BASE_URL_STORAGE_KEY);
  if (!storedValue) {
    return null;
  }

  const trimmedValue = storedValue.trim();
  return trimmedValue || null;
}

export function isLocalBrowserOrigin(hostname: string | null | undefined): boolean {
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
    return DEFAULT_LOCAL_API_BASE_URL;
  }

  if (/^[a-z]+:\/\//i.test(trimmedValue) || trimmedValue.startsWith("/")) {
    return trimmedValue.replace(/\/+$/, "");
  }

  if (/^(localhost|127\.0\.0\.1)(:\d+)?$/i.test(trimmedValue)) {
    return `http://${trimmedValue}`.replace(/\/+$/, "");
  }

  return `https://${trimmedValue}`.replace(/\/+$/, "");
}
