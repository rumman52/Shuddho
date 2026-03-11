import type { AnalyzeRequest, AnalyzeResponse, FeedbackRequest } from "@shared/schemas/contracts";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<TResponse>(path: string, init: RequestInit): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });

  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
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

