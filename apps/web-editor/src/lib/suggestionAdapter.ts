import type {
  Suggestion,
  SuggestionCategory,
  SuggestionSeverity,
  SuggestionSource,
} from "@shared/schemas/contracts";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.trunc(value);
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function normalizeCategory(value: unknown): SuggestionCategory {
  const raw = stringValue(value).toLowerCase();
  if (["spelling", "grammar", "punctuation", "spacing", "register", "clarity", "style", "rewrite_only"].includes(raw)) {
    return raw as SuggestionCategory;
  }
  if (raw === "fluency" || raw === "word_choice") return "clarity";
  return "grammar";
}

export function normalizeGatewaySuggestionSource(source: unknown): SuggestionSource {
  if (source === "rule" || source === "spell" || source === "model" || source === "hybrid") return source;
  if (source === "ml" || source === "ai") return "model";
  return "rule";
}

function normalizeSeverity(value: unknown): SuggestionSeverity {
  return value === "medium" || value === "high" || value === "low" ? value : "low";
}

export function getReplacementOptions(suggestion: unknown): string[] {
  const record = asRecord(suggestion);
  if (!record) return [];
  const camel = stringArray(record.replacementOptions);
  if (camel.length) return camel;
  const snake = stringArray(record.replacement_options);
  if (snake.length) return snake;
  const suggested = stringValue(record.suggestedText, stringValue(record.suggested_text));
  return suggested ? [suggested] : [];
}

export function getPrimaryReplacement(suggestion: unknown): string {
  return getReplacementOptions(suggestion)[0] ?? "";
}

export function normalizeGatewaySuggestion(value: unknown, index: number, _text = ""): Suggestion | null {
  const record = asRecord(value);
  if (!record) return null;
  const span = asRecord(record.span);
  const start = numberValue(span?.codePointStartIndex) ?? numberValue(span?.startIndex) ?? numberValue(record.span_start);
  const end = numberValue(span?.codePointEndIndex) ?? numberValue(span?.endIndex) ?? numberValue(record.span_end);
  if (start === null || end === null || start < 0 || end < start) return null;

  const ruleId = stringValue(record.ruleId, stringValue(record.rule_id, "unknown_rule"));
  const original = stringValue(record.originalText, stringValue(record.original_text));
  const id = stringValue(record.id, `${ruleId}-${start}-${end}-${index}`);
  const category = normalizeCategory(record.type ?? record.category);
  return {
    id,
    rule_id: ruleId,
    category,
    subtype: stringValue(record.subtype, ruleId || "suggestion"),
    span_start: start,
    span_end: end,
    original_text: original,
    replacement_options: getReplacementOptions(record),
    confidence: typeof record.confidence === "number" && Number.isFinite(record.confidence) ? record.confidence : 0,
    explanation_bn: stringValue(record.explanationBn, stringValue(record.explanation_bn)),
    explanation_en: stringValue(record.explanationEn, stringValue(record.explanation_en)),
    source: normalizeGatewaySuggestionSource(record.source),
    severity: normalizeSeverity(record.severity),
    feedback_key: stringValue(record.feedbackKey, stringValue(record.feedback_key)) || null,
    suppression_key: stringValue(record.suppressionKey, stringValue(record.suppression_key)) || null,
    alternatives: stringArray(record.alternatives).length ? [] : Array.isArray(record.alternatives) ? (record.alternatives as Suggestion["alternatives"]) : [],
    source_trace: stringArray(record.source_trace),
    rewrite_intents: stringArray(record.rewrite_intents) as Suggestion["rewrite_intents"],
    action_hints: stringArray(record.action_hints),
    provider: stringValue(record.provider) || null,
    metadata: asRecord(record.metadata),
  };
}

export function normalizeGatewaySuggestions(value: unknown, text = ""): Suggestion[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item, index) => {
    const normalized = normalizeGatewaySuggestion(item, index, text);
    return normalized ? [normalized] : [];
  });
}
