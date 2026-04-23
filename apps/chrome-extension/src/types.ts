export type SuggestionCategory = "spelling" | "grammar" | "punctuation" | "style";
export type SuggestionSource = "rule" | "spell" | "model" | "hybrid";
export type SuggestionSeverity = "low" | "medium" | "high";
export type AnalyzeMode = "standard" | "strict" | "formal";
export type RewriteIntent = "clarity" | "formal" | "concise" | "friendly" | "professional";
export type ToneLabel =
  | "neutral"
  | "friendly"
  | "professional"
  | "casual"
  | "confident"
  | "respectful"
  | "urgent"
  | "unclear";
export type FeedbackAction =
  | "accepted"
  | "dismissed"
  | "suppressed"
  | "ignore_forever"
  | "add_to_personal_dictionary"
  | "not_wrong"
  | "rewrite_accepted"
  | "rewrite_dismissed"
  | "tone_helpful"
  | "tone_not_helpful";

export interface SuggestionAlternative {
  id: string;
  rule_id: string;
  category: SuggestionCategory;
  subtype: string;
  original_text: string;
  replacement_options: string[];
  confidence: number;
  explanation_bn: string;
  explanation_en: string;
  source: SuggestionSource;
  severity: SuggestionSeverity;
  feedback_key?: string | null;
}

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
  suppression_key?: string | null;
  short_title?: string | null;
  suggestion_reason_short_bn?: string | null;
  rewrite_intents?: RewriteIntent[];
}

export interface FeedbackRequest {
  suggestion_id: string;
  action: FeedbackAction;
  text: string;
  replacement?: string | null;
  feedback_key?: string | null;
  rule_id?: string | null;
  subtype?: string | null;
  source?: SuggestionSource | null;
  original_text?: string | null;
  suppression_key?: string | null;
  user_dictionary_entry?: string | null;
  user_id?: string | null;
}

export interface AnalyzeResponse {
  text: string;
  normalized_text: string;
  corrected_text: string;
  suggestions: Suggestion[];
  runtime_warnings: string[];
}

export interface RewriteOption {
  id: string;
  label: string;
  rewritten_text: string;
  confidence: number;
  explanation_bn: string;
  explanation_en: string;
  source: string;
}

export interface RewriteResponse {
  original_text: string;
  target_text: string;
  selection_start?: number | null;
  selection_end?: number | null;
  intent: RewriteIntent;
  options: RewriteOption[];
  warnings: string[];
}

export interface ToneAnalysisResponse {
  detected_tones: ToneLabel[];
  primary_tone?: ToneLabel | null;
  confidence: number;
  explanation_bn: string;
  explanation_en: string;
  suggestions: string[];
}

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
