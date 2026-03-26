import type { AnalyzeResponse, FeedbackRequest } from "./types";
import { getApiBaseUrl } from "./config";

export class DebouncedAnalyzer {
  private readonly baseUrl: string;
  private readonly delayMs: number;
  private timerId: number | null = null;
  private activeController: AbortController | null = null;

  constructor(baseUrl = getApiBaseUrl(), delayMs = 650) {
    this.baseUrl = baseUrl;
    this.delayMs = delayMs;
  }

  schedule(text: string, onSuccess: (response: AnalyzeResponse) => void, onError: (error: unknown) => void): void {
    if (this.timerId) {
      window.clearTimeout(this.timerId);
    }

    this.timerId = window.setTimeout(() => {
      this.execute(text, onSuccess, onError);
    }, this.delayMs);
  }

  private async execute(
    text: string,
    onSuccess: (response: AnalyzeResponse) => void,
    onError: (error: unknown) => void
  ): Promise<void> {
    this.activeController?.abort();
    this.activeController = new AbortController();

    try {
      const response = await fetch(`${this.baseUrl}/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ text }),
        signal: this.activeController.signal
      });

      if (!response.ok) {
        throw new Error(`Analyze failed with ${response.status}`);
      }

      onSuccess((await response.json()) as AnalyzeResponse);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      onError(error);
    }
  }

  async sendFeedback(payload: FeedbackRequest): Promise<void> {
    const response = await fetch(`${this.baseUrl}/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(`Feedback failed with ${response.status}`);
    }
  }
}
