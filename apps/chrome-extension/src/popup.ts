import { getApiBaseUrl } from "./config";

const statusElement = document.getElementById("status");
const apiBaseUrl = getApiBaseUrl();

interface HealthResponse {
  status: string;
  detector_loaded: boolean;
  detector_checkpoint: string | null;
  allowed_origins: string[];
  analysis_profile: string;
  degraded_reasons: string[];
  detector: {
    loaded: boolean;
    reason: string | null;
  };
  openrouter: {
    available: boolean;
    reason: string | null;
    model: string | null;
  };
}

async function checkBackend(): Promise<void> {
  if (!statusElement) {
    return;
  }

  try {
    const response = await fetch(`${apiBaseUrl}/health`);
    if (!response.ok) {
      throw new Error(String(response.status));
    }
    const health = (await response.json()) as HealthResponse;
    statusElement.textContent = describeBackendStatus(health, apiBaseUrl);
    statusElement.title = buildHealthTitle(health);
  } catch {
    statusElement.textContent = `Backend unreachable — smart analysis paused at ${apiBaseUrl}.`;
    statusElement.title = "";
  }
}

void checkBackend();

function describeBackendStatus(health: HealthResponse, baseUrl: string): string {
  if (!health.detector.loaded) {
    return `Backend live but detector disabled at ${baseUrl}.`;
  }
  if (!health.openrouter.available) {
    return `Backend live but OpenRouter unavailable at ${baseUrl}.`;
  }
  return `Backend live at ${baseUrl}.`;
}

function buildHealthTitle(health: HealthResponse): string {
  const details = [`Allowed origins: ${health.allowed_origins.join(", ") || "none"}`];
  if (health.detector_checkpoint) {
    details.push(`Checkpoint: ${health.detector_checkpoint}`);
  }
  if (!health.detector.loaded && health.detector.reason) {
    details.push(`Detector: ${health.detector.reason}`);
  }
  if (!health.openrouter.available && health.openrouter.reason) {
    details.push(`OpenRouter: ${health.openrouter.reason}`);
  } else if (health.openrouter.model) {
    details.push(`OpenRouter model: ${health.openrouter.model}`);
  }
  if (health.degraded_reasons.length) {
    details.push(`Degraded reasons: ${health.degraded_reasons.join(", ")}`);
  }
  return details.join(" | ");
}
