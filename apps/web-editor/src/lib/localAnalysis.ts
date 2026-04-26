import type { AnalyzeMode, AnalyzeRequest, AnalyzeResponse, Suggestion } from "@shared/schemas/contracts";

const BANGLA_WORD_PATTERN = /[\u0980-\u09FFA-Za-z]+/gu;
const ACCEPTED_REDUPLICATION = new Set(["ধীরে ধীরে", "মাঝে মাঝে", "দিন দিন", "বার বার"]);

export const LOCAL_FALLBACK_LABEL = "Limited browser fallback";
export const LOCAL_FALLBACK_DESCRIPTION =
  "Only limited browser fallback checks are active: duplicate spaces, repeated words, duplicate punctuation, and exact typo map.";

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
    ...buildExactCorrectionSuggestions(text, payload.personal_dictionary ?? []),
  ]);

  return {
    text,
    normalized_text: normalizePreviewText(text),
    corrected_text: applySafeCorrections(text, suggestions),
    suggestions,
    analysis_profile: "frontend_local_fallback",
    runtime_source: "frontend_local_fallback",
    runtime_warnings: ["frontend_local_fallback", "limited_browser_fallback"],
    used_detector: false,
    used_corrector: false,
    backend_warning: "Limited browser fallback is active. Only duplicate spaces, repeated words, duplicate punctuation, and exact typo checks are available.",
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
    if (
      previousToken.value === value &&
      /\s+/u.test(between) &&
      between.trim().length === 0 &&
      value.length >= 2 &&
      !ACCEPTED_REDUPLICATION.has(`${value} ${value}`)
    ) {
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
        category: "spelling",
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
    .sort((left, right) => left.span_start - right.span_start || left.span_end - right.span_end || right.confidence - left.confidence);

  if (safeSuggestions.length === 0) {
    return text;
  }

  const candidates = buildEditCandidates(text, safeSuggestions);
  if (candidates.length === 0) {
    return text;
  }

  const selected = selectBestNonOverlappingCandidates(candidates);
  if (selected.length === 0) {
    return text;
  }

  let cursor = 0;
  const parts: string[] = [];
  for (const candidate of selected.sort((left, right) => left.start - right.start || left.end - right.end)) {
    if (candidate.start < cursor) {
      continue;
    }

    parts.push(text.slice(cursor, candidate.start));
    parts.push(candidate.replacement);
    cursor = candidate.end;
  }

  parts.push(text.slice(cursor));
  const correctedText = parts.join("");
  return correctedText || text;
}

function isSafeAutoApplySuggestion(text: string, suggestion: Suggestion): boolean {
  if (suggestion.category === "register" || suggestion.category === "clarity" || suggestion.category === "rewrite_only") {
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

interface EditCandidate {
  start: number;
  end: number;
  replacement: string;
  score: number;
}

function buildEditCandidates(text: string, suggestions: Suggestion[]): EditCandidate[] {
  const candidates = new Map<string, EditCandidate>();

  for (const suggestion of suggestions) {
    const replacement = suggestion.replacement_options[0] ?? "";
    setBestCandidate(candidates, {
      start: suggestion.span_start,
      end: suggestion.span_end,
      replacement,
      score: editWeight(suggestion),
    });
  }

  for (const cluster of buildOverlapClusters(suggestions)) {
    if (cluster.length <= 1 || cluster.length > 5) {
      continue;
    }

    for (const candidate of buildCompositeCandidates(text, cluster)) {
      setBestCandidate(candidates, candidate);
    }
  }

  return [...candidates.values()];
}

function setBestCandidate(store: Map<string, EditCandidate>, candidate: EditCandidate): void {
  const key = `${candidate.start}:${candidate.end}:${candidate.replacement}`;
  const existing = store.get(key);
  if (!existing || candidate.score > existing.score) {
    store.set(key, candidate);
  }
}

function buildOverlapClusters(suggestions: Suggestion[]): Suggestion[][] {
  const clusters: Suggestion[][] = [];
  let current: Suggestion[] = [];
  let currentEnd = -1;

  for (const suggestion of suggestions) {
    if (current.length === 0 || suggestion.span_start >= currentEnd) {
      if (current.length > 0) {
        clusters.push(current);
      }
      current = [suggestion];
      currentEnd = suggestion.span_end;
      continue;
    }

    current.push(suggestion);
    currentEnd = Math.max(currentEnd, suggestion.span_end);
  }

  if (current.length > 0) {
    clusters.push(current);
  }

  return clusters;
}

function buildCompositeCandidates(text: string, cluster: Suggestion[]): EditCandidate[] {
  const clusterStart = Math.min(...cluster.map((suggestion) => suggestion.span_start));
  const clusterEnd = Math.max(...cluster.map((suggestion) => suggestion.span_end));
  const clusterText = text.slice(clusterStart, clusterEnd);
  const generated = new Map<string, EditCandidate>();

  for (let size = 2; size <= cluster.length; size += 1) {
    for (const subset of combinations(cluster, size)) {
      if (!subsetContainsOverlap(subset)) {
        continue;
      }

      for (const replacement of composeSubset(clusterText, clusterStart, subset)) {
        if (replacement === clusterText) {
          continue;
        }

        setBestCandidate(generated, {
          start: clusterStart,
          end: clusterEnd,
          replacement,
          score: subset.reduce((total, suggestion) => total + editWeight(suggestion), 0) + cleanupBonus(clusterText, replacement),
        });
      }
    }
  }

  return [...generated.values()];
}

function composeSubset(clusterText: string, clusterStart: number, subset: Suggestion[]): Set<string> {
  const composed = new Set<string>();
  for (const ordering of permutations(subset)) {
    const candidate = applyOrdering(clusterText, clusterStart, ordering);
    if (candidate) {
      composed.add(candidate);
    }
  }
  return composed;
}

function applyOrdering(clusterText: string, clusterStart: number, ordering: Suggestion[]): string | null {
  let current = clusterText;
  const priorEdits: Array<{ start: number; end: number; delta: number }> = [];

  for (const suggestion of ordering) {
    const needle = suggestion.original_text;
    const replacement = suggestion.replacement_options[0] ?? "";
    if (!needle || !replacement) {
      return null;
    }

    const relativeStart = suggestion.span_start - clusterStart;
    const shift = priorEdits.filter((edit) => edit.end <= relativeStart).reduce((total, edit) => total + edit.delta, 0);
    const expectedIndex = Math.max(0, relativeStart + shift);
    const occurrences = findOccurrences(current, needle);
    if (occurrences.length === 0) {
      return null;
    }

    const selectedIndex = occurrences.reduce((best, occurrence) => {
      if (best === null) {
        return occurrence;
      }
      const bestDistance = Math.abs(best - expectedIndex);
      const occurrenceDistance = Math.abs(occurrence - expectedIndex);
      if (occurrenceDistance < bestDistance || (occurrenceDistance === bestDistance && occurrence < best)) {
        return occurrence;
      }
      return best;
    }, null as number | null);

    if (selectedIndex === null) {
      return null;
    }

    current = `${current.slice(0, selectedIndex)}${replacement}${current.slice(selectedIndex + needle.length)}`;
    priorEdits.push({
      start: relativeStart,
      end: suggestion.span_end - clusterStart,
      delta: replacement.length - needle.length,
    });
  }

  return current;
}

function findOccurrences(text: string, needle: string): number[] {
  const occurrences: number[] = [];
  let cursor = 0;
  while (cursor <= text.length) {
    const index = text.indexOf(needle, cursor);
    if (index < 0) {
      break;
    }
    occurrences.push(index);
    cursor = index + 1;
  }
  return occurrences;
}

function selectBestNonOverlappingCandidates(candidates: EditCandidate[]): EditCandidate[] {
  const ordered = [...candidates].sort((left, right) => left.end - right.end || left.start - right.start || right.score - left.score);
  const predecessors = ordered.map((candidate, index) => findPredecessorIndex(ordered, candidate, index));
  const bestScores = new Array<number>(ordered.length + 1).fill(0);
  const selectedFlags = new Array<boolean>(ordered.length).fill(false);

  for (let index = 1; index <= ordered.length; index += 1) {
    const candidate = ordered[index - 1];
    const includeScore = candidate.score + bestScores[predecessors[index - 1] + 1];
    const excludeScore = bestScores[index - 1];
    if (includeScore > excludeScore) {
      bestScores[index] = includeScore;
      selectedFlags[index - 1] = true;
    } else {
      bestScores[index] = excludeScore;
    }
  }

  const selected: EditCandidate[] = [];
  let index = ordered.length;
  while (index > 0) {
    const candidate = ordered[index - 1];
    const predecessor = predecessors[index - 1];
    const includeScore = candidate.score + bestScores[predecessor + 1];
    if (selectedFlags[index - 1] && includeScore >= bestScores[index - 1]) {
      selected.push(candidate);
      index = predecessor + 1;
    } else {
      index -= 1;
    }
  }

  return selected.reverse();
}

function findPredecessorIndex(candidates: EditCandidate[], candidate: EditCandidate, index: number): number {
  let left = 0;
  let right = index - 1;
  let result = -1;

  while (left <= right) {
    const middle = Math.floor((left + right) / 2);
    if (candidates[middle]?.end <= candidate.start) {
      result = middle;
      left = middle + 1;
    } else {
      right = middle - 1;
    }
  }

  return result;
}

function subsetContainsOverlap(subset: Suggestion[]): boolean {
  return subset.some((left, leftIndex) =>
    subset.slice(leftIndex + 1).some((right) => left.span_start < right.span_end && right.span_start < left.span_end),
  );
}

function editWeight(suggestion: Suggestion): number {
  const kindBonus =
    suggestion.category === "grammar"
      ? 1.18
      : suggestion.category === "punctuation"
        ? 1.1
        : suggestion.category === "spelling"
          ? 1.0
          : 0.6;
  return kindBonus + suggestion.confidence;
}

function cleanupBonus(originalText: string, replacement: string): number {
  return (localErrorCount(originalText) - localErrorCount(replacement)) * 0.12;
}

function localErrorCount(text: string): number {
  return [
    /[^\S\r\n]{2,}/gu,
    /\s+([!?।,.])/gu,
    /([!?।,.])\1+/gu,
    /(?<![\u0980-\u09FFA-Za-z])([\u0980-\u09FF]{2,})\s+\1(?![\u0980-\u09FFA-Za-z])/gu,
  ].reduce((total, pattern) => total + [...text.matchAll(pattern)].length, 0);
}

function* combinations<T>(items: T[], size: number, start = 0, prefix: T[] = []): Generator<T[]> {
  if (prefix.length === size) {
    yield prefix;
    return;
  }

  for (let index = start; index < items.length; index += 1) {
    yield* combinations(items, size, index + 1, [...prefix, items[index] as T]);
  }
}

function* permutations<T>(items: T[]): Generator<T[]> {
  if (items.length <= 1) {
    yield items;
    return;
  }

  for (let index = 0; index < items.length; index += 1) {
    const head = items[index] as T;
    const tail = [...items.slice(0, index), ...items.slice(index + 1)];
    for (const permutation of permutations(tail)) {
      yield [head, ...permutation];
    }
  }
}

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
