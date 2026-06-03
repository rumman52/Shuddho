export type SuggestionCategory =
  | "spelling"
  | "grammar"
  | "punctuation"
  | "spacing"
  | "register"
  | "clarity"
  | "style"
  | "rewrite_only";

export type SuggestionSource = "rule" | "spell" | "model" | "hybrid";
export type SuggestionSeverity = "low" | "medium" | "high";
export type AnalyzeMode = "standard" | "strict" | "formal";
export type AnalysisProfile =
  | "full_local"
  | "backend_without_detector"
  | "backend_without_corrector"
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
export type SuggestionUiGroup =
  | "correctness"
  | "spacing"
  | "punctuation"
  | "register"
  | "clarity";
export type PreferredLanguageVariant = "bangla";
export type WritingGoal =
  | "general"
  | "formal"
  | "academic"
  | "business"
  | "casual"
  | "social";
export type ToneGoal =
  | "neutral"
  | "friendly"
  | "professional"
  | "concise"
  | "confident";
export type SuggestionDensity = "low" | "balanced" | "high";
export type RewriteIntent =
  | "clarity"
  | "formal"
  | "concise"
  | "friendly"
  | "professional";
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
  suggestion_kind?: SuggestionKind | null;
  suppression_key?: string | null;
  is_variant_only?: boolean;
  source_trace?: string[] | null;
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
  conflict_group_id?: string | null;
  is_primary?: boolean;
  primary_reason?: string | null;
  alternatives?: SuggestionAlternative[];
  short_title?: string | null;
  ui_group?: SuggestionUiGroup | null;
  can_auto_apply?: boolean | null;
  learnable?: boolean | null;
  ranking_score?: number | null;
  suggestion_reason_short_bn?: string | null;
  suggestion_reason_short_en?: string | null;
  action_hints?: string[];
  rewrite_intents?: RewriteIntent[];
  tone_labels?: ToneLabel[];
  provider?: string | null;
  metadata?: Record<string, unknown> | null;
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
  used_corrector: boolean;
  backend_warning?: string | null;
  lexicon_source: string;
  lexicon_version?: string | null;
  backend_version?: string | null;
  sentence_count: number;
  request_mode_applied: AnalyzeMode;
  warnings?: string[];
  llm_requested?: boolean;
  llm_attempted?: boolean;
  llm_used?: boolean;
  llm_status?: string | null;
  llm_provider?: string | null;
  llm_model?: string | null;
  llm_response_mode?: string | null;
  local_suggestion_count?: number;
  ai_suggestion_count?: number;
  rejected_ai_suggestion_count?: number;
  diagnostics?: Record<string, unknown>;
  llm?: Record<string, unknown> | null;
}

export interface UserPreferences {
  user_id: string;
  preferred_language_variant: PreferredLanguageVariant;
  writing_goal: WritingGoal;
  tone_goal: ToneGoal;
  suggestion_density: SuggestionDensity;
  auto_show_tone: boolean;
  enable_rewrites: boolean;
  personal_dictionary: string[];
  suppressed_rule_keys: string[];
  disabled_sites: string[];
}

export interface RewriteRequest {
  text: string;
  selection_start?: number | null;
  selection_end?: number | null;
  intent: RewriteIntent;
  user_id?: string | null;
  writing_goal?: WritingGoal | null;
  tone_goal?: ToneGoal | null;
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

export interface ToneAnalysisRequest {
  text: string;
  user_id?: string | null;
}

export interface ToneAnalysisResponse {
  detected_tones: ToneLabel[];
  primary_tone?: ToneLabel | null;
  confidence: number;
  explanation_bn: string;
  explanation_en: string;
  suggestions: string[];
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

export interface CorrectorHealth {
  enabled: boolean;
  loaded: boolean;
  status: string;
  reason?: string | null;
  checkpoint?: string | null;
  checkpoint_exists: boolean;
  backend_name: string;
  threshold: number;
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
  ok: boolean;
  service: string;
  status: string;
  backend_reachable: boolean;
  detector_loaded: boolean;
  detector_checkpoint?: string | null;
  corrector_loaded: boolean;
  corrector_checkpoint?: string | null;
  allowed_origins: string[];
  detector: DetectorHealth;
  corrector: CorrectorHealth;
  analysis_profile: AnalysisProfile;
  degraded_reasons: string[];
  backend_warning?: string | null;
  mode_capabilities: Record<string, string[]>;
}

export interface HealthDeepResponse extends HealthResponse {
  backend_version?: string | null;
  env_file_path?: string | null;
  env_file_loaded: boolean;
  last_startup_timestamp: string;
  llm?: {
    enabled: boolean;
    configured: boolean;
    provider: string;
    model: string;
    status?: string;
    warnings?: string[];
    circuit_open?: boolean;
    on_check?: "manual" | "always" | "never" | string;
    interactive_timeout_seconds?: number;
    background_timeout_seconds?: number;
    timeout_seconds?: number;
    cache_ttl_seconds?: number;
    max_candidates?: number;
    max_candidate_chars?: number;
    max_ai_text_chars?: number;
  };
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

// Canonical Shuddho gateway contract. Legacy AnalyzeResponse remains above for old consumers.
export type CanonicalSuggestionType =
  | "grammar"
  | "spelling"
  | "punctuation"
  | "spacing"
  | "style"
  | "tone"
  | "rewrite"
  | "clarity"
  | "fluency"
  | "word_choice";
export type CanonicalSuggestionSeverity = "low" | "medium" | "high";
export type CanonicalSuggestionSource =
  | "rule"
  | "spell"
  | "grammar"
  | "tone"
  | "rewrite"
  | "ml"
  | "model"
  | "hybrid";
export interface TextSpan {
  startIndex: number;
  endIndex: number;
  utf16StartIndex?: number;
  utf16EndIndex?: number;
  codePointStartIndex?: number;
  codePointEndIndex?: number;
  graphemeStartIndex?: number;
  graphemeEndIndex?: number;
}
export interface CanonicalSuggestion {
  id: string;
  suppressionKey: string;
  ruleId: string;
  type: CanonicalSuggestionType;
  severity: CanonicalSuggestionSeverity;
  originalText: string;
  suggestedText: string;
  replacementOptions: string[];
  explanationBn: string;
  explanationEn?: string;
  span: TextSpan;
  confidence: number;
  source: CanonicalSuggestionSource;
  provider: string;
  metadata?: Record<string, unknown>;
}
export interface CheckRequest {
  text: string;
  documentId?: string;
  revision?: number;
  language: "bn";
  dialect?: "standard" | "west_bengal" | "bangladesh" | "mixed";
  userId?: string;
  client?: {
    surface: "web" | "extension" | "desktop" | "mobile" | "api";
    version?: string;
  };
  options?: {
    includeGrammar?: boolean;
    includeSpelling?: boolean;
    includeStyle?: boolean;
    includeTone?: boolean;
    includeRewrite?: boolean;
    includeLLM?: boolean;
    asyncLLM?: boolean;
    llmMode?: "review_candidates" | "none" | string;
    mode?: "smart" | "fast" | string;
  };
  consent?: {
    productImprovementConsent?: boolean;
  };
}
export interface CheckResponse {
  requestId: string;
  documentId?: string;
  revision?: number;
  language: "bn";
  normalizedText?: string;
  correctedText?: string;
  documentAssessment?: Record<string, unknown>;
  suggestions: CanonicalSuggestion[];
  timings?: Record<string, unknown>;
  warnings?: string[];
  llm_requested?: boolean;
  llm_attempted?: boolean;
  llm_used?: boolean;
  llm_status?: string | null;
  llm_provider?: string | null;
  llm_model?: string | null;
  llm_response_mode?: string | null;
  llm?: Record<string, unknown> | null;
  local_suggestion_count?: number;
  ai_suggestion_count?: number;
  rejected_ai_suggestion_count?: number;
  diagnostics?: Record<string, unknown>;
}
