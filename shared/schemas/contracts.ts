export type SuggestionCategory =
  | "spelling"
  | "grammar"
  | "punctuation"
  | "style";

export type SuggestionSource = "rule" | "spell" | "model" | "hybrid";
export type SuggestionSeverity = "low" | "medium" | "high";
export type AnalyzeMode = "standard" | "strict" | "formal";
export type AnalysisProfile =
  | "full_backend"
  | "backend_without_detector"
  | "backend_without_openrouter"
  | "backend_rules_and_spell_only"
  | "frontend_local_fallback";
export type SuggestionKind =
  | "true_spelling_error"
  | "orthography_variant"
  | "style_suggestion"
  | "grammar_error"
  | "punctuation_error"
  | "spacing_error"
  | "named_entity_or_user_word"
  | "no_suggestion";
export type FeedbackAction =
  | "accepted"
  | "dismissed"
  | "suppressed"
  | "ignore_forever"
  | "add_to_personal_dictionary"
  | "not_wrong";

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
  suggestion_kind?: SuggestionKind | null;
  is_contextual?: boolean | null;
  optional_mode_visibility?: AnalyzeMode[];
  suppression_key?: string | null;
  is_variant_only?: boolean;
  sentence_index?: number | null;
  sentence_start?: number | null;
  sentence_end?: number | null;
  occurrence_index?: number | null;
  anchor_before?: string | null;
  anchor_after?: string | null;
  source_trace?: string[] | null;
}

export interface AnalyzeRequest {
  text: string;
  personal_dictionary?: string[];
  mode?: AnalyzeMode;
  user_id?: string | null;
}

export interface AnalyzeResponse {
  text: string;
  normalized_text: string;
  corrected_text: string;
  suggestions: Suggestion[];
  analysis_profile: AnalysisProfile;
  runtime_source: AnalysisProfile;
  runtime_warnings: string[];
  used_detector: boolean;
  used_openrouter: boolean;
  lexicon_source: string;
  lexicon_version?: string | null;
  backend_version?: string | null;
  sentence_count: number;
  request_mode_applied: AnalyzeMode;
}

export interface DetectorHealth {
  enabled: boolean;
  loaded: boolean;
  status: string;
  reason?: string | null;
  checkpoint?: string | null;
  checkpoint_exists: boolean;
  backend_name: string;
  threshold: number;
}

export interface OpenRouterHealth {
  configured: boolean;
  available: boolean;
  status: string;
  reason?: string | null;
  model?: string | null;
  api_key_present: boolean;
  timeout_seconds: number;
  probed: boolean;
  probe_success?: boolean | null;
  probe_status?: string | null;
  probe_reason?: string | null;
  probe_checked_at?: string | null;
}

export interface LexiconHealth {
  runtime_source_of_truth: string;
  runtime_source: string;
  runtime_path?: string | null;
  runtime_exists: boolean;
  version?: string | null;
  checksum?: string | null;
  accepted_word_count: number;
  candidate_word_count: number;
  correction_map_count: number;
  import_database_path?: string | null;
  import_database_exists: boolean;
  loaded_at?: string | null;
  reload_supported: boolean;
  restart_required: boolean;
}

export interface HealthResponse {
  status: string;
  backend_reachable: boolean;
  detector_loaded: boolean;
  detector_checkpoint?: string | null;
  allowed_origins: string[];
  openrouter_configured: boolean;
  openrouter_available: boolean;
  openrouter_model?: string | null;
  detector: DetectorHealth;
  openrouter: OpenRouterHealth;
  analysis_profile: AnalysisProfile;
  degraded_reasons: string[];
  mode_capabilities: Record<string, string[]>;
}

export interface HealthDeepResponse extends HealthResponse {
  backend_version?: string | null;
  env_file_path?: string | null;
  env_file_loaded: boolean;
  last_startup_timestamp: string;
  lexicon: LexiconHealth;
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
