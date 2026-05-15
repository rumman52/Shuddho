import type { CheckResponse, Suggestion } from '@shuddho/shared';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:4000';

export async function checkText(text: string, documentId: string, revision: number): Promise<CheckResponse> {
  const response = await fetch(`${API_BASE}/api/check`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ documentId, text, revision, goals: ['grammar', 'spelling', 'style', 'tone', 'rewrite'] }),
  });
  if (!response.ok) throw new Error(`check failed: ${response.status}`);
  return response.json();
}

export async function trackSuggestion(type: 'suggestion_accepted' | 'suggestion_rejected', suggestion: Suggestion, documentId: string) {
  await fetch(`${API_BASE}/api/events`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ events: [{ type, documentId, suggestionId: suggestion.id, metadata: { suggestionType: suggestion.type } }] }),
  }).catch(() => undefined);
}
