import type { AnalyzeRequest, AnalyzeResponse, FeedbackRequest } from "@shared/schemas/contracts";

const API_BASE_URL = resolveApiBaseUrl();

function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_API_BASE_URL;
  return (configuredBaseUrl ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

async function request<TResponse>(path: string, init: RequestInit): Promise<TResponse> {
  const url = `${API_BASE_URL}${path}`;
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

