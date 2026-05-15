import type {
  AnalyzeMode,
  AnalyzeResponse,
  FeedbackRequest,
  RewriteIntent,
  RewriteResponse,
  Suggestion,
  ToneAnalysisResponse,
} from "@shared/schemas/contracts";

export type { AnalyzeMode, AnalyzeResponse, FeedbackRequest, RewriteIntent, RewriteResponse, Suggestion, ToneAnalysisResponse };

export interface SuggestionRange {
  suggestion: Suggestion;
  start: number;
  end: number;
}

export interface OverlayState {
  text: string;
  ranges: SuggestionRange[];
  tone: ToneAnalysisResponse | null;
}

export interface ExtensionSettings {
  backendBaseUrl: string;
  writingGoal: "general" | "formal" | "academic" | "business" | "casual" | "social";
  toneGoal: "neutral" | "friendly" | "professional" | "concise" | "confident";
  suggestionDensity: "low" | "balanced" | "high";
  rewritesEnabled: boolean;
  autoShowTone: boolean;
  disabledSites: string[];
  currentUserId: string;
  localPersonalDictionaryMirror: string[];
  suppressedRuleKeys: string[];
}
