import type { AnalyzeMode, AnalyzeRequest, AnalyzeResponse, Suggestion } from "@shared/schemas/contracts";

const BANGLA_WORD_PATTERN = /[\u0980-\u09FFA-Za-z]+/gu;
export const LOCAL_FALLBACK_LABEL = "Local fallback checks";
export const LOCAL_FALLBACK_DESCRIPTION =
  "Browser-only safe checks are active. Backend contextual analysis is not available right now.";

const SAFE_EXACT_REPLACEMENTS = new Map<string, string>([
  ["কিন্ত", "কিন্তু"],
  ["ব্যাবহার", "ব্যবহার"],
  ["বংলা", "বাংলা"],
  ["ব্যকরন", "ব্যাকরণ"],
  ["ব্যকরণ", "ব্যাকরণ"],
  ["অবশ্যইই", "অবশ্যই"],
]);

const SAFE_VARIANT_REPLACEMENTS = new Map<string, string>([
  ["নিয়ে", "নিয়ে"],
  ["নিয়েই", "নিয়েই"],
  ["হয়", "হয়"],
  ["হয়নি", "হয়নি"],
  ["হয়েছে", "হয়েছে"],
  ["দেয়", "দেয়"],
]);

export function analyzeTextLocally(
  payload: Pick<AnalyzeRequest, "text" | "mode" | "personal_dictionary">,
): AnalyzeResponse {
  const text = payload.text;
  const mode = payload.mode ?? "standard";
  const suggestions = dedupeSuggestions([
    ...buildRepeatedWordSuggestions(text),
    ...buildDuplicatePunctuationSuggestions(text),
    ...buildExtraWhitespaceSuggestions(text),
    ...buildWhitespaceBeforePunctuationSuggestions(text),
    ...buildBanglaFullStopSuggestions(text),
    ...buildSpaceAfterTerminatorSuggestions(text),
    ...buildExactCorrectionSuggestions(text, payload.personal_dictionary ?? []),
    ...buildVariantSuggestions(text, mode, payload.personal_dictionary ?? []),
  ]);

  return {
    text,
    normalized_text: normalizePreviewText(text),
    corrected_text: applySafeCorrections(text, suggestions),
    suggestions,
    analysis_profile: "frontend_local_fallback",
    runtime_source: "frontend_local_fallback",
    runtime_warnings: ["frontend_local_fallback"],
    used_detector: false,
    used_openrouter: false,
    lexicon_source: "frontend_local_dictionary",
    lexicon_version: null,
    backend_version: null,
    sentence_count: countSentences(text),
    request_mode_applied: mode,
  };
}

function buildRepeatedWordSuggestions(text: string): Suggestion[] {
  const suggestions: Suggestion[] = [];
  let previousToken: { value: string; start: number; end: number } | null = null;

  for (const match of text.matchAll(BANGLA_WORD_PATTERN)) {
    const value = match[0];
    const start = match.index ?? 0;
    const end = start + value.length;
    if (!previousToken) {
      previousToken = { value, start, end };
      continue;
    }

    const between = text.slice(previousToken.end, start);
    if (previousToken.value === value && /\s+/u.test(between) && between.trim().length === 0 && value.length >= 2) {
      suggestions.push(
        buildSuggestion({
          prefix: "local-repeat",
          ruleId: "REP_001",
          category: "grammar",
          subtype: "repeated_word",
          start: previousToken.start,
          end,
          originalText: text.slice(previousToken.start, end),
          replacementOptions: [value],
          confidence: 0.84,
          explanationBn: `একই শব্দ '${value}' পরপর দুইবার এসেছে।`,
          explanationEn: `The word '${value}' appears twice in a row.`,
          source: "rule",
          severity: "medium",
        }),
      );
    }

    previousToken = { value, start, end };
  }

  return suggestions;
}

function buildDuplicatePunctuationSuggestions(text: string): Suggestion[] {
  const suggestions: Suggestion[] = [];
  const pattern = /([!?।,.])\1+/gu;
  for (const match of text.matchAll(pattern)) {
    const originalText = match[0];
    const start = match.index ?? 0;
    suggestions.push(
      buildSuggestion({
        prefix: "local-punc-dup",
        ruleId: "PUNC_001",
        category: "punctuation",
        subtype: "duplicate_punctuation",
        start,
        end: start + originalText.length,
        originalText,
        replacementOptions: [originalText[0] ?? ""],
        confidence: 0.99,
        explanationBn: "এখানে বাড়তি যতিচিহ্ন আছে।",
        explanationEn: "There is duplicate punctuation here.",
        source: "rule",
        severity: "low",
      }),
    );
  }
  return suggestions;
}

function buildExtraWhitespaceSuggestions(text: string): Suggestion[] {
  const suggestions: Suggestion[] = [];
  const pattern = /(?<=[\u0980-\u09FFA-Za-z0-9])[^\S\r\n]{2,}(?=[\u0980-\u09FFA-Za-z0-9])/gu;
  for (const match of text.matchAll(pattern)) {
    const originalText = match[0];
    const start = match.index ?? 0;
    suggestions.push(
      buildSuggestion({
        prefix: "local-space-extra",
        ruleId: "SPACE_001",
        category: "grammar",
        subtype: "extra_whitespace",
        start,
        end: start + originalText.length,
        originalText,
        replacementOptions: [" "],
        confidence: 0.98,
        explanationBn: "এখানে অতিরিক্ত ফাঁকা আছে।",
        explanationEn: "There is extra whitespace here.",
        source: "rule",
        severity: "low",
      }),
    );
  }
  return suggestions;
}

function buildWhitespaceBeforePunctuationSuggestions(text: string): Suggestion[] {
  const suggestions: Suggestion[] = [];
  const pattern = /\s+([!?।,.])/gu;
  for (const match of text.matchAll(pattern)) {
    const punctuation = match[1] ?? "";
    const originalText = match[0];
    const start = match.index ?? 0;
    suggestions.push(
      buildSuggestion({
        prefix: "local-space-before-punc",
        ruleId: "PUNC_002",
        category: "punctuation",
        subtype: "space_before_punctuation",
        start,
        end: start + originalText.length,
        originalText,
        replacementOptions: [punctuation],
        confidence: 0.98,
        explanationBn: "যতিচিহ্নের আগে অপ্রয়োজনীয় ফাঁকা আছে।",
        explanationEn: "There is unnecessary whitespace before punctuation.",
        source: "rule",
        severity: "low",
      }),
    );
  }
  return suggestions;
}

function buildBanglaFullStopSuggestions(text: string): Suggestion[] {
  if (!/[\u0980-\u09FF]/u.test(text)) {
    return [];
  }

  const suggestions: Suggestion[] = [];
  for (const match of text.matchAll(/\./gu)) {
    const start = match.index ?? 0;
    const previousCharacter = text[start - 1] ?? "";
    const nextCharacter = text[start + 1] ?? "";
    if (/\d/u.test(previousCharacter) || nextCharacter === ".") {
      continue;
    }
    if (nextCharacter && !/\s/u.test(nextCharacter)) {
      continue;
    }

    suggestions.push(
      buildSuggestion({
        prefix: "local-bangla-full-stop",
        ruleId: "PUNC_003",
        category: "punctuation",
        subtype: "bangla_full_stop",
        start,
        end: start + 1,
        originalText: ".",
        replacementOptions: ["।"],
        confidence: 0.9,
        explanationBn: "বাংলা বাক্যের শেষে '.' এর বদলে '।' ব্যবহার করুন।",
        explanationEn: "Use '।' instead of '.' at the end of a Bangla sentence.",
        source: "rule",
        severity: "low",
      }),
    );
  }
  return suggestions;
}

function buildSpaceAfterTerminatorSuggestions(text: string): Suggestion[] {
  const suggestions: Suggestion[] = [];
  const pattern = /([।!?])([^\s"'”’)\]}])/gu;
  for (const match of text.matchAll(pattern)) {
    const punctuation = match[1] ?? "";
    const nextCharacter = match[2] ?? "";
    const originalText = match[0];
    const start = match.index ?? 0;
    suggestions.push(
      buildSuggestion({
        prefix: "local-space-after-punc",
        ruleId: "PUNC_004",
        category: "punctuation",
        subtype: "space_after_punctuation",
        start,
        end: start + originalText.length,
        originalText,
        replacementOptions: [`${punctuation} ${nextCharacter}`],
        confidence: 0.86,
        explanationBn: "যতিচিহ্নের পরে সাধারণত একটি ফাঁকা থাকে।",
        explanationEn: "Punctuation is usually followed by a space here.",
        source: "rule",
        severity: "low",
      }),
    );
  }
  return suggestions;
}

function buildVariantSuggestions(
  text: string,
  mode: AnalyzeMode,
  personalDictionary: string[],
): Suggestion[] {
  if (mode === "standard") {
    return [];
  }

  const ignoredWords = new Set(personalDictionary.map((entry) => entry.trim()).filter(Boolean));
  const suggestions: Suggestion[] = [];
  for (const match of text.matchAll(BANGLA_WORD_PATTERN)) {
    const originalText = match[0];
    const replacement = SAFE_VARIANT_REPLACEMENTS.get(originalText);
    if (!replacement || ignoredWords.has(originalText) || ignoredWords.has(replacement)) {
      continue;
    }

    const start = match.index ?? 0;
    suggestions.push(
      buildSuggestion({
        prefix: "local-variant",
        ruleId: "SPELL_002",
        category: "style",
        subtype: "orthography_variant",
        start,
        end: start + originalText.length,
        originalText,
        replacementOptions: [replacement],
        confidence: 0.84,
        explanationBn: `এখানে '${replacement}' রূপটি বেশি মানক।`,
        explanationEn: `'${replacement}' is the more standard form here.`,
        source: "spell",
        severity: "low",
        optionalModeVisibility: ["strict", "formal"],
        isVariantOnly: true,
      }),
    );
  }

  return suggestions;
}

function buildExactCorrectionSuggestions(text: string, personalDictionary: string[]): Suggestion[] {
  const ignoredWords = new Set(personalDictionary.map((entry) => entry.trim()).filter(Boolean));
  const suggestions: Suggestion[] = [];
  for (const match of text.matchAll(BANGLA_WORD_PATTERN)) {
    const originalText = match[0];
    const replacement = SAFE_EXACT_REPLACEMENTS.get(originalText);
    if (!replacement || ignoredWords.has(originalText) || ignoredWords.has(replacement)) {
      continue;
    }

    const start = match.index ?? 0;
    suggestions.push(
      buildSuggestion({
        prefix: "local-exact",
        ruleId: "SPELL_001",
        category: "spelling",
        subtype: "spelling_error",
        start,
        end: start + originalText.length,
        originalText,
        replacementOptions: [replacement],
        confidence: 0.98,
        explanationBn: `এখানে '${originalText}' এর বদলে '${replacement}' লেখা উচিত।`,
        explanationEn: `Replace '${originalText}' with '${replacement}' here.`,
        source: "rule",
        severity: "medium",
      }),
    );
  }

  return suggestions;
}

function buildSuggestion(args: {
  prefix: string;
  ruleId: string;
  category: Suggestion["category"];
  subtype: string;
  start: number;
  end: number;
  originalText: string;
  replacementOptions: string[];
  confidence: number;
  explanationBn: string;
  explanationEn: string;
  source: Suggestion["source"];
  severity: Suggestion["severity"];
  optionalModeVisibility?: AnalyzeMode[];
  isVariantOnly?: boolean;
}): Suggestion {
  const replacementKey = args.replacementOptions.join("|");
  const feedbackKey = buildStableId("fbk", `${args.category}:${args.originalText}:${replacementKey}`);
  const suppressionKey = buildStableId("sup", `${args.ruleId}:${args.subtype}:${args.originalText}:${replacementKey}`);
  return {
    id: buildStableId(args.prefix, `${args.start}:${args.end}:${args.originalText}:${replacementKey}`),
    rule_id: args.ruleId,
    category: args.category,
    subtype: args.subtype,
    span_start: args.start,
    span_end: args.end,
    original_text: args.originalText,
    replacement_options: args.replacementOptions,
    confidence: args.confidence,
    explanation_bn: args.explanationBn,
    explanation_en: args.explanationEn,
    source: args.source,
    severity: args.severity,
    feedback_key: feedbackKey,
    suppression_key: suppressionKey,
    optional_mode_visibility: args.optionalModeVisibility,
    is_variant_only: args.isVariantOnly,
    source_trace: ["frontend_local_fallback"],
  };
}

function dedupeSuggestions(suggestions: Suggestion[]): Suggestion[] {
  const uniqueSuggestions = new Map<string, Suggestion>();
  for (const suggestion of suggestions) {
    const key = `${suggestion.rule_id}:${suggestion.span_start}:${suggestion.span_end}:${suggestion.replacement_options.join("|")}`;
    if (!uniqueSuggestions.has(key)) {
      uniqueSuggestions.set(key, suggestion);
    }
  }

  return [...uniqueSuggestions.values()].sort(
    (left, right) => left.span_start - right.span_start || left.span_end - right.span_end || right.confidence - left.confidence,
  );
}

function applySafeCorrections(text: string, suggestions: Suggestion[]): string {
  const safeSuggestions = suggestions
    .filter((suggestion) => isSafeAutoApplySuggestion(text, suggestion))
    .sort((left, right) => left.span_start - right.span_start || right.confidence - left.confidence || left.span_end - right.span_end);

  if (safeSuggestions.length === 0) {
    return text;
  }

  let cursor = 0;
  const parts: string[] = [];
  for (const suggestion of safeSuggestions) {
    if (suggestion.span_start < cursor) {
      continue;
    }

    parts.push(text.slice(cursor, suggestion.span_start));
    parts.push(suggestion.replacement_options[0] ?? "");
    cursor = suggestion.span_end;
  }

  parts.push(text.slice(cursor));
  const correctedText = parts.join("");
  return correctedText || text;
}

function isSafeAutoApplySuggestion(text: string, suggestion: Suggestion): boolean {
  if (suggestion.category === "style") {
    return false;
  }
  if (suggestion.replacement_options.length !== 1) {
    return false;
  }

  const replacement = suggestion.replacement_options[0] ?? "";
  const originalText = text.slice(suggestion.span_start, suggestion.span_end);
  if (!replacement || originalText !== suggestion.original_text || replacement === originalText) {
    return false;
  }

  return SAFE_AUTO_APPLY_SUBTYPES.has(suggestion.subtype);
}

const SAFE_AUTO_APPLY_SUBTYPES = new Set([
  "repeated_word",
  "duplicate_punctuation",
  "extra_whitespace",
  "space_before_punctuation",
  "bangla_full_stop",
  "space_after_punctuation",
]);

function normalizePreviewText(text: string): string {
  return text.replace(/\u00a0/g, " ").replace(/[ \t]{2,}/g, " ");
}

function countSentences(text: string): number {
  const matches = text.match(/[^.!?\u0964\n]+(?:[.!?\u0964]+|$)/gu);
  return matches?.length ?? 0;
}

function buildStableId(prefix: string, payload: string): string {
  let hash = 0;
  for (let index = 0; index < payload.length; index += 1) {
    hash = (hash * 31 + payload.charCodeAt(index)) >>> 0;
  }
  return `${prefix}_${hash.toString(16)}`;
}
