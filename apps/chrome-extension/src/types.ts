export interface Suggestion {
  id: string;
  rule_id: string;
  category: "spelling" | "grammar" | "punctuation" | "style";
  subtype: string;
  span_start: number;
  span_end: number;
  original_text: string;
  replacement_options: string[];
  confidence: number;
  explanation_bn: string;
  explanation_en: string;
  source: "rule" | "spell" | "model" | "hybrid";
  severity: "low" | "medium" | "high";
  feedback_key?: string | null;
}

export interface FeedbackRequest {
  suggestion_id: string;
  action: "accepted" | "dismissed";
  text: string;
  replacement?: string | null;
  feedback_key?: string | null;
  rule_id?: string | null;
  subtype?: string | null;
  source?: Suggestion["source"] | null;
  original_text?: string | null;
}

export interface AnalyzeResponse {
  text: string;
  normalized_text: string;
  suggestions: Suggestion[];
}

export interface SuggestionRange {
  suggestion: Suggestion;
  start: number;
  end: number;
}

export interface OverlayState {
  text: string;
  ranges: SuggestionRange[];
}
