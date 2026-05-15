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
import { DEFAULT_PREFERENCES, normalizePreferences, type ShuddhoPreferences } from "./preferences";

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

type GatewaySuggestion = {
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
  severity?: string;
  suppressionKey?: string;
  suppression_key?: string;
};

type GatewayCheckResponse = {
  normalizedText?: string;
  normalized_text?: string;
  suggestions?: GatewaySuggestion[];
  warnings?: string[];
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

  const url = `${getApiBaseUrl()}${path}`;
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
  const path = useGateway ? "/api/check" : "/analyze";

  if (!useGateway) {
    return request<AnalyzeResponse>(path, { method: "POST", body: JSON.stringify(payload) });
  }

  const response = await request<GatewayCheckResponse>(path, {
    method: "POST",
    body: JSON.stringify({
      text: payload.text,
      language: "bn",
      userId: payload.user_id,
      client: { surface: "web", version: "vite-editor" },
    }),
  });

  return gatewayCheckToAnalyzeResponse(response, payload);
}

export function sendFeedback(payload: FeedbackRequest): Promise<void> {
  return request<void>("/api/events", {
    method: "POST",
    body: JSON.stringify({ type: "suggestion_accepted", language: "bn", suggestionId: payload.suggestion_id, metadata: { action: payload.action, ruleId: payload.feedback_key } }),
  });
}

export function getHealth(): Promise<BackendHealthResponse> {
  return request<BackendHealthResponse>("/health/deep", {
    method: "GET",
  });
}

export async function checkBackendHealth(): Promise<{
  ok: boolean;
  message?: string;
}> {
  if (!apiConfiguration.backendAllowed) {
    return {
      ok: false,
      message: apiConfiguration.hardWarning ?? "Backend health checks are disabled by frontend API configuration.",
    };
  }

  try {
    const response = await fetch(`${getApiBaseUrl()}/health`, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    });

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
      message: "Backend is not reachable. Check VITE_API_BASE_URL and make sure your tunnel is running.",
    };
  }
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

async function safeJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function fetchPreferences(): Promise<ShuddhoPreferences> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/api/preferences`, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      console.warn(`Preferences request failed with ${response.status}. Using defaults.`);
      return DEFAULT_PREFERENCES;
    }

    const data = await safeJson(response);
    return normalizePreferences(data as Partial<ShuddhoPreferences> | null | undefined);
  } catch (error) {
    console.warn("Preferences request failed. Using defaults.", error);
    return DEFAULT_PREFERENCES;
  }
}

export async function savePreferences(preferences: ShuddhoPreferences): Promise<ShuddhoPreferences> {
  const normalized = normalizePreferences(preferences);

  try {
    const response = await fetch(`${getApiBaseUrl()}/api/preferences`, {
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
    return normalizePreferences(data as Partial<ShuddhoPreferences> | null | undefined);
  } catch (error) {
    console.warn("Save preferences failed.", error);
    return normalized;
  }
}

export function getUserPreferences(_userId: string): Promise<ShuddhoPreferences> {
  return fetchPreferences();
}

export function saveUserPreferences(_userId: string, payload: ShuddhoPreferences): Promise<ShuddhoPreferences> {
  return savePreferences(payload);
}

function gatewayCheckToAnalyzeResponse(response: GatewayCheckResponse, payload: AnalyzeRequest): AnalyzeResponse {
  const normalizedText = response.normalizedText ?? response.normalized_text ?? payload.text;
  const suggestions = Array.isArray(response.suggestions) ? response.suggestions : [];

  return {
    text: payload.text,
    corrected_text: normalizedText,
    analysis_profile: "gateway",
    runtime_source: "gateway",
    runtime_source_path: null,
    runtime_lexicon_version: null,
    runtime_lexicon_checksum: null,
    detector_enabled: false,
    corrector_enabled: false,
    degraded_reasons: response.warnings ?? [],
    normalized_text: normalizedText,
    suggestions: suggestions.map((suggestion) => ({
      id: suggestion.id,
      rule_id: suggestion.ruleId ?? suggestion.rule_id,
      category: suggestion.type ?? suggestion.category,
      subtype: suggestion.subtype ?? suggestion.ruleId ?? suggestion.rule_id,
      span_start: suggestion.span?.codePointStartIndex ?? suggestion.span?.startIndex ?? suggestion.span_start ?? 0,
      span_end: suggestion.span?.codePointEndIndex ?? suggestion.span?.endIndex ?? suggestion.span_end ?? 0,
      original_text: suggestion.originalText ?? suggestion.original_text ?? "",
      replacement_options: suggestion.replacementOptions ?? suggestion.replacement_options ?? [],
      confidence: suggestion.confidence ?? 0,
      explanation_bn: suggestion.explanationBn ?? suggestion.explanation_bn ?? "",
      explanation_en: suggestion.explanationEn ?? suggestion.explanation_en ?? "",
      source: suggestion.source,
      severity: suggestion.severity,
      suppression_key: suggestion.suppressionKey ?? suggestion.suppression_key,
    })),
    warnings: response.warnings ?? [],
  } as unknown as AnalyzeResponse;
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
