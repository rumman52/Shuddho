export const suggestionTypes = ['grammar', 'spelling', 'style', 'tone', 'rewrite'] as const;
export const suggestionSeverities = ['info', 'low', 'medium', 'high'] as const;
export type SuggestionType = typeof suggestionTypes[number];
export type SuggestionSeverity = typeof suggestionSeverities[number];

export interface Suggestion {
  id: string;
  type: SuggestionType;
  severity: SuggestionSeverity;
  originalText: string;
  suggestedText: string;
  explanation: string;
  startIndex: number;
  endIndex: number;
  confidence: number;
  sourceProvider: string;
}

export interface CheckRequest {
  documentId?: string;
  text: string;
  locale: string;
  goals: SuggestionType[];
  revision?: number;
  consent?: { productImprovement: boolean };
}
export interface CheckResponse { requestId: string; documentId?: string; revision?: number; suggestions: Suggestion[]; timings: Record<string, number>; }
export interface RewriteRequest { text: string; instruction?: string; tone?: string; }
export interface ToneRequest { text: string; }
export interface DocumentRecord { id: string; ownerId: string; title: string; plainText: string; revision: number; updatedAt: string; }
export type DocumentOperation = { type: 'replace_all'; text: string } | { type: 'insert'; index: number; text: string } | { type: 'delete'; startIndex: number; endIndex: number };
export interface DocumentDelta { documentId: string; baseRevision: number; clientOperationId: string; op: DocumentOperation; }
export interface UserPreference { userId: string; locale: string; formality: 'casual' | 'neutral' | 'formal'; enabledSuggestionTypes: SuggestionType[]; allowProductImprovement: boolean; }
export type EventType = 'user_typed' | 'suggestion_generated' | 'suggestion_accepted' | 'suggestion_rejected' | 'rewrite_requested' | 'latency_metric' | 'error';
export interface ProductEvent { type: EventType; documentId?: string; suggestionId?: string; metadata: Record<string, unknown>; occurredAt?: string; }

function isSuggestionType(value: unknown): value is SuggestionType { return typeof value === 'string' && (suggestionTypes as readonly string[]).includes(value); }
function textLimit(value: unknown, max: number, min = 0): string {
  if (typeof value !== 'string' || value.length < min || value.length > max) throw new Error('invalid_text');
  return value;
}
export function parseCheckRequest(input: unknown): CheckRequest {
  const body = (input && typeof input === 'object') ? input as Record<string, unknown> : {};
  const goalsRaw = Array.isArray(body.goals) ? body.goals : ['grammar', 'spelling', 'style', 'tone'];
  const goals = goalsRaw.filter(isSuggestionType);
  return {
    documentId: typeof body.documentId === 'string' ? body.documentId : undefined,
    text: textLimit(body.text, 20000),
    locale: typeof body.locale === 'string' ? body.locale : 'en-US',
    goals: goals.length ? goals : ['grammar', 'spelling', 'style', 'tone'],
    revision: Number.isInteger(body.revision) && Number(body.revision) >= 0 ? Number(body.revision) : undefined,
    consent: body.consent && typeof body.consent === 'object' ? { productImprovement: Boolean((body.consent as Record<string, unknown>).productImprovement) } : undefined,
  };
}
export function parseRewriteRequest(input: unknown): RewriteRequest {
  const body = (input && typeof input === 'object') ? input as Record<string, unknown> : {};
  return { text: textLimit(body.text, 8000, 1), instruction: typeof body.instruction === 'string' ? body.instruction.slice(0, 400) : undefined, tone: typeof body.tone === 'string' ? body.tone.slice(0, 80) : undefined };
}
export function parseToneRequest(input: unknown): ToneRequest { return { text: textLimit((input as Record<string, unknown>)?.text, 12000, 1) }; }
export function parseEventRequest(input: unknown): { events: ProductEvent[] } {
  const events = (input as { events?: unknown[] })?.events;
  if (!Array.isArray(events) || events.length === 0 || events.length > 100) throw new Error('invalid_events');
  return { events: events.map((event) => ({ ...(event as ProductEvent), metadata: (event as ProductEvent).metadata ?? {} })) };
}
export function parseDocumentDelta(input: unknown): DocumentDelta {
  const delta = input as DocumentDelta;
  if (!delta || typeof delta.documentId !== 'string' || !Number.isInteger(delta.baseRevision) || typeof delta.clientOperationId !== 'string' || !delta.op) throw new Error('invalid_delta');
  return delta;
}
