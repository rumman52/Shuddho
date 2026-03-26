import { getApiBaseUrl } from "./config";

const statusElement = document.getElementById("status");
const apiBaseUrl = getApiBaseUrl();

interface HealthResponse {
  status: string;
  detector_loaded: boolean;
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
    statusElement.textContent = `Backend reachable at ${apiBaseUrl} (${health.detector_loaded ? "detector loaded" : "detector unavailable"})`;
  } catch {
    statusElement.textContent = `Backend not reachable at ${apiBaseUrl}.`;
  }
}

void checkBackend();
