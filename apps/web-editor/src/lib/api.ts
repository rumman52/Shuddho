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

const DEFAULT_LOCAL_API_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_URL_STORAGE_KEY = "shuddho-api-base-url";

export interface ApiConfigurationState {
  apiBaseUrl: string;
  source: "default_local" | "environment" | "override";
  isLocalBrowserOrigin: boolean;
  targetsLocalhost: boolean;
  hardWarning: string | null;
  backendAllowed: boolean;
  localFallbackEnabled: boolean;
}

let apiConfiguration = resolveApiConfiguration();

export function deriveApiConfiguration(args: {
  configuredBaseUrl?: string | null;
  storedBaseUrl?: string | null;
  browserHostname?: string | null;
  enableLocalFallback?: boolean | null;
}): ApiConfigurationState {
  const { configuredBaseUrl, storedBaseUrl, browserHostname, enableLocalFallback } = args;
  const isLocalOrigin = isLocalBrowserOrigin(browserHostname);
  const rawBaseUrl = storedBaseUrl?.trim() || configuredBaseUrl?.trim() || DEFAULT_LOCAL_API_BASE_URL;
  const source =
    storedBaseUrl?.trim() ? "override" : configuredBaseUrl?.trim() ? "environment" : "default_local";
  const apiBaseUrl = normalizeApiBaseUrl(rawBaseUrl);
  const targetsLocalhost = isLocalApiBaseUrl(apiBaseUrl);
  const localFallbackEnabled = Boolean(enableLocalFallback);
  const hardWarning =
    !isLocalOrigin && targetsLocalhost
      ? `This deployed editor is still pointing to ${apiBaseUrl}. Set VITE_API_BASE_URL to a public backend URL; localhost is only valid from local browser sessions.`
      : null;

  return {
    apiBaseUrl,
    source,
    isLocalBrowserOrigin: isLocalOrigin,
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

export function analyzeText(payload: AnalyzeRequest): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>("/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function sendFeedback(payload: FeedbackRequest): Promise<void> {
  return request<void>("/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getHealth(): Promise<HealthDeepResponse> {
  return request<HealthDeepResponse>("/health/deep", {
    method: "GET",
  });
}

export function rewriteText(payload: RewriteRequest): Promise<RewriteResponse> {
  return request<RewriteResponse>("/rewrite", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function analyzeTone(payload: ToneAnalysisRequest): Promise<ToneAnalysisResponse> {
  return request<ToneAnalysisResponse>("/tone/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getUserPreferences(userId: string): Promise<UserPreferences> {
  return request<UserPreferences>(`/preferences/${encodeURIComponent(userId)}`, {
    method: "GET",
  });
}

export function saveUserPreferences(userId: string, payload: UserPreferences): Promise<UserPreferences> {
  return request<UserPreferences>(`/preferences/${encodeURIComponent(userId)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getApiBaseUrl(): string {
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
  });
  return apiConfiguration.apiBaseUrl;
}

function resolveApiConfiguration(): ApiConfigurationState {
  return deriveApiConfiguration({
    configuredBaseUrl: readConfiguredBaseUrl(),
    storedBaseUrl: readStoredApiBaseUrl(),
    browserHostname: readBrowserHostname(),
    enableLocalFallback: readLocalFallbackFlag(),
  });
}

function readConfiguredBaseUrl(): string | null {
  const importMetaEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {};
  const configuredBaseUrl = importMetaEnv.VITE_API_BASE_URL ?? importMetaEnv.VITE_API_URL;
  return configuredBaseUrl?.trim() || null;
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
