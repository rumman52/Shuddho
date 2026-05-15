import type { SuggestionType } from './index.js';

function stableHash(input: unknown): string {
  const value = JSON.stringify(input);
  let h1 = 0x811c9dc5;
  let h2 = 0x9e3779b9;
  for (let i = 0; i < value.length; i += 1) {
    const c = value.charCodeAt(i);
    h1 ^= c; h1 = Math.imul(h1, 0x01000193) >>> 0;
    h2 ^= c; h2 = Math.imul(h2, 0x85ebca6b) >>> 0;
  }
  return `${h1.toString(16).padStart(8, '0')}${h2.toString(16).padStart(8, '0')}`;
}

export function makeStableSuggestionId(input: { documentId?: string; ruleId: string; type: SuggestionType; startIndex: number; endIndex: number; originalText: string; suggestedText: string; provider: string }): string {
  return `sg_${stableHash({ documentId: input.documentId ?? 'global', ruleId: input.ruleId, type: input.type, startIndex: input.startIndex, endIndex: input.endIndex, originalText: input.originalText, suggestedText: input.suggestedText, provider: input.provider })}`;
}

export function makeSuppressionKey(input: { ruleId: string; originalText: string; suggestedText: string; type: SuggestionType }): string {
  return `sk_${stableHash({ ruleId: input.ruleId, originalText: input.originalText, suggestedText: input.suggestedText, type: input.type })}`;
}
