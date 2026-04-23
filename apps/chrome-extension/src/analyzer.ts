import { modeFromWritingGoal } from "./config";
import type { AnalyzeResponse, ExtensionSettings, FeedbackRequest, RewriteIntent, RewriteResponse, SuggestionRange, ToneAnalysisResponse } from "./types";

export class DebouncedAnalyzer {
  private readonly delayMs: number;
  private timerId: number | null = null;
  private activeController: AbortController | null = null;

  constructor(delayMs = 650) {
    this.delayMs = delayMs;
  }

  schedule(
    text: string,
    settings: ExtensionSettings,
    onSuccess: (response: AnalyzeResponse, tone: ToneAnalysisResponse | null) => void,
    onError: (error: unknown) => void,
  ): void {
    if (this.timerId) {
      window.clearTimeout(this.timerId);
    }

    this.timerId = window.setTimeout(() => {
      void this.execute(text, settings, onSuccess, onError);
    }, this.delayMs);
  }

  async rewrite(
    text: string,
    range: SuggestionRange,
    intent: RewriteIntent,
    settings: ExtensionSettings,
  ): Promise<RewriteResponse> {
    const response = await fetch(`${settings.backendBaseUrl}/rewrite`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        text,
        selection_start: range.start,
        selection_end: range.end,
        intent,
        user_id: settings.currentUserId,
        writing_goal: settings.writingGoal,
        tone_goal: settings.toneGoal,
      }),
    });
    if (!response.ok) {
      throw new Error(`Rewrite failed with ${response.status}`);
    }
    return (await response.json()) as RewriteResponse;
  }

  async sendFeedback(payload: FeedbackRequest, settings: ExtensionSettings): Promise<void> {
    const response = await fetch(`${settings.backendBaseUrl}/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Feedback failed with ${response.status}`);
    }
  }

  private async execute(
    text: string,
    settings: ExtensionSettings,
    onSuccess: (response: AnalyzeResponse, tone: ToneAnalysisResponse | null) => void,
    onError: (error: unknown) => void,
  ): Promise<void> {
    this.activeController?.abort();
    this.activeController = new AbortController();

    try {
      const analyzeResponsePromise = fetch(`${settings.backendBaseUrl}/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text,
          mode: modeFromWritingGoal(settings.writingGoal),
          personal_dictionary: settings.localPersonalDictionaryMirror,
          user_id: settings.currentUserId,
        }),
        signal: this.activeController.signal,
      });

      const toneResponsePromise = settings.autoShowTone && text.trim().length >= 30
        ? fetch(`${settings.backendBaseUrl}/tone/analyze`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              text,
              user_id: settings.currentUserId,
            }),
            signal: this.activeController.signal,
          })
        : Promise.resolve(null);

      const [analyzeResponse, toneResponse] = await Promise.all([analyzeResponsePromise, toneResponsePromise]);
      if (!analyzeResponse.ok) {
        throw new Error(`Analyze failed with ${analyzeResponse.status}`);
      }

      let tone: ToneAnalysisResponse | null = null;
      if (toneResponse && toneResponse.ok) {
        tone = (await toneResponse.json()) as ToneAnalysisResponse;
      }

      onSuccess((await analyzeResponse.json()) as AnalyzeResponse, tone);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      onError(error);
    }
  }
}
