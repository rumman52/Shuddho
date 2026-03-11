export type SuggestionCategory =
  | "correctness"
  | "spelling"
  | "grammar"
  | "punctuation"
  | "clarity"
  | "style";

export type SuggestionSource = "rule" | "spell" | "model" | "hybrid";
export type SuggestionSeverity = "low" | "medium" | "high";
export type SuggestionStatus = "open" | "accepted" | "dismissed";

export interface Suggestion {
  id: string;
  category: SuggestionCategory;
  subtype: string;
  span_start: number;
  span_end: number;
  original_text: string;
  replacement_options: string[];
  confidence: number;
  explanation_bn: string;
  explanation_en: string;
  source: SuggestionSource;
  severity: SuggestionSeverity;
  status: SuggestionStatus;
}

export interface AnalyzeRequest {
  text: string;
  personal_dictionary?: string[];
}

export interface AnalyzeResponse {
  text: string;
  normalized_text: string;
  suggestions: Suggestion[];
}

export interface FeedbackRequest {
  suggestion_id: string;
  action: "accepted" | "dismissed";
  text: string;
  replacement?: string | null;
}

