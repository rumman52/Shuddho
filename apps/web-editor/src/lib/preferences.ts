import type { UserPreferences } from "@shared/schemas/contracts";

export type ShuddhoPreferences = UserPreferences & {
  language: "bn";
  dialect: "standard" | "bangladesh" | "west_bengal" | "mixed";
  enabledSuggestionTypes: string[];
  disabledSuggestionTypes: string[];
  ignoredRuleIds: string[];
  ignoredSuggestionIds: string[];
  ignoredSuppressionKeys: string[];
  productImprovementConsent: boolean;
};

export const DEFAULT_PREFERENCES: ShuddhoPreferences = {
  user_id: "anonymous-web-editor",
  preferred_language_variant: "bangla",
  writing_goal: "general",
  tone_goal: "neutral",
  suggestion_density: "balanced",
  auto_show_tone: true,
  enable_rewrites: true,
  personal_dictionary: [],
  suppressed_rule_keys: [],
  disabled_sites: [],
  language: "bn",
  dialect: "standard",
  enabledSuggestionTypes: [
    "grammar",
    "spelling",
    "punctuation",
    "spacing",
    "style",
    "tone",
    "rewrite",
  ],
  disabledSuggestionTypes: [],
  ignoredRuleIds: [],
  ignoredSuggestionIds: [],
  ignoredSuppressionKeys: [],
  productImprovementConsent: false,
};

export function createDefaultPreferences(userId = DEFAULT_PREFERENCES.user_id): ShuddhoPreferences {
  return normalizePreferences({ user_id: userId });
}

export function normalizePreferences(input: Partial<ShuddhoPreferences> | null | undefined): ShuddhoPreferences {
  const base = {
    ...DEFAULT_PREFERENCES,
    ...(input || {}),
  };

  return {
    ...base,
    language: "bn",
    dialect: isDialect(base.dialect) ? base.dialect : DEFAULT_PREFERENCES.dialect,
    personal_dictionary: safeStringArray(input?.personal_dictionary, DEFAULT_PREFERENCES.personal_dictionary),
    suppressed_rule_keys: safeStringArray(input?.suppressed_rule_keys, DEFAULT_PREFERENCES.suppressed_rule_keys),
    disabled_sites: safeStringArray(input?.disabled_sites, DEFAULT_PREFERENCES.disabled_sites),
    enabledSuggestionTypes: safeStringArray(input?.enabledSuggestionTypes, DEFAULT_PREFERENCES.enabledSuggestionTypes),
    disabledSuggestionTypes: safeStringArray(input?.disabledSuggestionTypes, DEFAULT_PREFERENCES.disabledSuggestionTypes),
    ignoredRuleIds: safeStringArray(input?.ignoredRuleIds, DEFAULT_PREFERENCES.ignoredRuleIds),
    ignoredSuggestionIds: safeStringArray(input?.ignoredSuggestionIds, DEFAULT_PREFERENCES.ignoredSuggestionIds),
    ignoredSuppressionKeys: safeStringArray(input?.ignoredSuppressionKeys, DEFAULT_PREFERENCES.ignoredSuppressionKeys),
    productImprovementConsent: Boolean(input?.productImprovementConsent ?? DEFAULT_PREFERENCES.productImprovementConsent),
  };
}

function safeStringArray(value: unknown, fallback: string[]): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [...fallback];
}

function isDialect(value: unknown): value is ShuddhoPreferences["dialect"] {
  return value === "standard" || value === "bangladesh" || value === "west_bengal" || value === "mixed";
}
