export type SuggestionCategory =
  | "spelling"
  | "grammar"
  | "punctuation"
  | "style";

export type SuggestionSource = "rule" | "spell" | "model" | "hybrid";
export type SuggestionSeverity = "low" | "medium" | "high";
export type AnalyzeMode = "standard" | "strict" | "formal";

export interface Suggestion {
  id: string;
  rule_id: string;
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
  feedback_key?: string | null;
}

export interface AnalyzeRequest {
  text: string;
  personal_dictionary?: string[];
  mode?: AnalyzeMode;
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
  feedback_key?: string | null;
  rule_id?: string | null;
  subtype?: string | null;
  source?: SuggestionSource | null;
  original_text?: string | null;
}
