export interface Suggestion {
  id: string;
  category: "correctness" | "spelling" | "grammar" | "punctuation" | "clarity" | "style";
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
  status: "open" | "accepted" | "dismissed";
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
  textLength: number;
  ranges: SuggestionRange[];
}

