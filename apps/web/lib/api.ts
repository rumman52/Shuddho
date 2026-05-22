import type { CheckResponse, Suggestion } from '@shuddho/shared';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:4000';

export async function checkText(text: string, documentId: string, revision: number, signal?: AbortSignal): Promise<CheckResponse> {
  const response = await fetch(`${API_BASE}/api/check`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ documentId, text, revision, language: 'bn', client: { surface: 'web', version: 'next-mvp' }, options: { includeGrammar: true, includeSpelling: true, includeStyle: true, includeTone: true, includeRewrite: true } }),
    signal,
  });
  if (!response.ok) throw new Error(`check failed: ${response.status}`);
  return response.json();
}

export async function trackSuggestion(type: 'suggestion_accepted' | 'suggestion_rejected', suggestion: Suggestion, documentId: string) {
  const action = type === 'suggestion_accepted' ? 'accepted' : 'dismissed';
  await fetch(`${API_BASE}/api/feedback`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      suggestion_id: suggestion.id,
      action,
      text: '',
      replacement: suggestion.replacementOptions?.[0] ?? null,
      feedback_key: suggestion.feedbackKey ?? null,
      rule_id: suggestion.ruleId ?? null,
      subtype: suggestion.type ?? null,
      source: suggestion.source ?? null,
      original_text: suggestion.originalText ?? null,
      suppression_key: suggestion.suppressionKey ?? null,
      user_id: null,
    }),
  }).catch((error) => {
    if (process.env.NODE_ENV !== 'production') {
      console.warn('Shuddho feedback request failed', error);
    }
  });

  await fetch(`${API_BASE}/api/events`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ events: [{ type, documentId, suggestionId: suggestion.id, language: 'bn', suppressionKey: suggestion.suppressionKey, metadata: { suggestionType: suggestion.type, ruleId: suggestion.ruleId } }] }),
  }).catch(() => undefined);
}
