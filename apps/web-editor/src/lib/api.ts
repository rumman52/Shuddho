import type { AnalyzeRequest, AnalyzeResponse, FeedbackRequest, HealthResponse } from "@shared/schemas/contracts";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_URL_STORAGE_KEY = "shuddho-api-base-url";
let apiBaseUrl = resolveApiBaseUrl();

function resolveApiBaseUrl(): string {
  const runtimeOverride = readStoredApiBaseUrl();
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL;
  return normalizeApiBaseUrl(runtimeOverride ?? configuredBaseUrl ?? DEFAULT_API_BASE_URL);
}

async function request<TResponse>(path: string, init: RequestInit): Promise<TResponse> {
  const url = `${apiBaseUrl}${path}`;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers
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
    body: JSON.stringify(payload)
  });
}

export function sendFeedback(payload: FeedbackRequest): Promise<void> {
  return request<void>("/feedback", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health", {
    method: "GET",
  });
}

export function getApiBaseUrl(): string {
  return apiBaseUrl;
}

export function setApiBaseUrlOverride(nextBaseUrl: string): string {
  apiBaseUrl = normalizeApiBaseUrl(nextBaseUrl || DEFAULT_API_BASE_URL);
  if (typeof window !== "undefined") {
    const trimmedValue = nextBaseUrl.trim();
    if (trimmedValue) {
      window.localStorage.setItem(API_BASE_URL_STORAGE_KEY, trimmedValue);
    } else {
      window.localStorage.removeItem(API_BASE_URL_STORAGE_KEY);
    }
  }

  return apiBaseUrl;
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

function normalizeApiBaseUrl(rawBaseUrl: string): string {
  const trimmedValue = rawBaseUrl.trim();
  if (!trimmedValue) {
    return DEFAULT_API_BASE_URL;
  }

  if (/^[a-z]+:\/\//i.test(trimmedValue) || trimmedValue.startsWith("/")) {
    return trimmedValue.replace(/\/+$/, "");
  }

  if (/^(localhost|127\.0\.0\.1)(:\d+)?$/i.test(trimmedValue)) {
    return `http://${trimmedValue}`.replace(/\/+$/, "");
  }

  return `https://${trimmedValue}`.replace(/\/+$/, "");
}
