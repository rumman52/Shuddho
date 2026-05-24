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
    return (await sendBackgroundApiRequest<RewriteResponse>({
      endpoint: "/api/rewrite",
      body: {
        text,
        selection_start: range.start,
        selection_end: range.end,
        intent,
        user_id: settings.currentUserId,
        writing_goal: settings.writingGoal,
        tone_goal: settings.toneGoal,
      },
    })) as RewriteResponse;
  }

  async sendFeedback(payload: FeedbackRequest): Promise<void> {
    await sendBackgroundApiRequest({ endpoint: "/api/feedback", body: payload });
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
      const analyzeResponsePromise = sendBackgroundApiRequest({
        endpoint: "/api/check",
        body: {
          text,
          language: "bn",
          userId: settings.currentUserId,
          client: { surface: "extension", version: "mvp" },
          options: {
            includeGrammar: true,
            includeSpelling: true,
            includeStyle: true,
            includeTone: settings.autoShowTone,
          },
        },
      });

      const toneResponsePromise = settings.autoShowTone && text.trim().length >= 30
        ? sendBackgroundApiRequest<ToneAnalysisResponse>({
            endpoint: "/api/tone",
            body: {
              text,
              user_id: settings.currentUserId,
            },
          })
        : Promise.resolve(null);

      const [analyzeResponse, toneResponse] = await Promise.all([analyzeResponsePromise, toneResponsePromise]);
      const tone = toneResponse ?? null;
      const gatewayBody = analyzeResponse as any;
      const adaptedAnalyzeResponse = {
        text,
        corrected_text: gatewayBody.normalizedText ?? text,
        analysis_profile: "frontend_local_fallback",
        runtime_source: "gateway",
        runtime_source_path: null,
        runtime_lexicon_version: null,
        runtime_lexicon_checksum: null,
        detector_enabled: false,
        corrector_enabled: false,
        degraded_reasons: gatewayBody.warnings ?? [],
        normalized_text: gatewayBody.normalizedText,
        suggestions: (gatewayBody.suggestions ?? []).map((suggestion: any) => ({
          id: suggestion.id,
          rule_id: suggestion.ruleId,
          category: suggestion.type,
          subtype: suggestion.ruleId,
          span_start: suggestion.span?.codePointStartIndex ?? suggestion.span?.startIndex ?? 0,
          span_end: suggestion.span?.codePointEndIndex ?? suggestion.span?.endIndex ?? 0,
          original_text: suggestion.originalText,
          replacement_options: suggestion.replacementOptions ?? [suggestion.suggestedText],
          confidence: suggestion.confidence,
          explanation_bn: suggestion.explanationBn,
          explanation_en: suggestion.explanationEn ?? "",
          source: suggestion.source,
          severity: suggestion.severity,
          suppression_key: suggestion.suppressionKey,
        })),
        warnings: gatewayBody.warnings ?? [],
      } as unknown as AnalyzeResponse;
      onSuccess(adaptedAnalyzeResponse, tone);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      onError(error);
    }
  }
}

interface ApiRequestMessage {
  type: "api:request";
  endpoint: string;
  method?: string;
  body?: unknown;
}

function sendBackgroundApiRequest<TResponse>(message: Omit<ApiRequestMessage, "type">): Promise<TResponse> {
  return new Promise((resolve, reject) => {
    if (!chrome.runtime?.id) {
      reject(new Error("Extension runtime is unavailable"));
      return;
    }
    chrome.runtime.sendMessage({ type: "api:request", ...message }, (response: TResponse | { error?: string }) => {
      const runtimeError = chrome.runtime.lastError;
      if (runtimeError) {
        reject(new Error(runtimeError.message));
        return;
      }
      if (response && typeof response === "object" && "error" in response && response.error) {
        reject(new Error(response.error));
        return;
      }
      resolve(response as TResponse);
    });
  });
}
