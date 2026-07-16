export type SuggestionType = 'grammar' | 'spelling' | 'punctuation' | 'spacing' | 'style' | 'tone' | 'rewrite' | 'clarity' | 'fluency' | 'word_choice';
export type SuggestionSeverity = 'low' | 'medium' | 'high';
export type SuggestionSource = 'rule' | 'spell' | 'grammar' | 'tone' | 'rewrite' | 'ml' | 'model' | 'hybrid';
export type BanglaDialect = 'standard' | 'west_bengal' | 'bangladesh' | 'mixed';
export type ClientSurface = 'web' | 'extension' | 'desktop' | 'mobile' | 'api';

export const suggestionTypes: readonly SuggestionType[] = ['grammar', 'spelling', 'punctuation', 'spacing', 'style', 'tone', 'rewrite', 'clarity', 'fluency', 'word_choice'];
export const suggestionSeverities: readonly SuggestionSeverity[] = ['low', 'medium', 'high'];
export const suggestionSources: readonly SuggestionSource[] = ['rule', 'spell', 'grammar', 'tone', 'rewrite', 'ml', 'model', 'hybrid'];

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

export interface Suggestion {
  id: string;
  suppressionKey: string;
  feedbackKey?: string | null;
  ruleId: string;
  type: SuggestionType;
  severity: SuggestionSeverity;
  originalText: string;
  suggestedText: string;
  replacementOptions: string[];
  explanationBn: string;
  explanationEn?: string;
  span: TextSpan;
  confidence: number;
  source: SuggestionSource;
  provider: string;
  metadata?: Record<string, unknown>;
}

export interface CheckRequest {
  text: string;
  documentId?: string;
  revision?: number;
  language: 'bn';
  dialect?: BanglaDialect;
  userId?: string;
  client?: { surface: ClientSurface; version?: string };
  options?: { includeGrammar?: boolean; includeSpelling?: boolean; includeStyle?: boolean; includeTone?: boolean; includeRewrite?: boolean; includeLLM?: boolean; asyncLLM?: boolean; llmMode?: 'review_candidates' | 'none' | string; mode?: 'smart' | 'fast' | string };
  consent?: { productImprovementConsent?: boolean; productImprovement?: boolean };
}

export interface CheckResponse {
  requestId: string;
  documentId?: string;
  revision?: number;
  language: 'bn';
  normalizedText?: string;
  suggestions: Suggestion[];
  timings?: Record<string, number>;
  warnings?: string[];
  correctedText?: string;
  documentAssessment?: Record<string, unknown>;
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

export interface RewriteRequest { text: string; instruction?: string; tone?: string; intent?: string; }
export interface ToneRequest { text: string; }
export interface DocumentRecord { id: string; text: string; revision: number; updatedAt: string; ownerId?: string; title?: string; plainText?: string; }
export type DocumentOperation = { type: 'replace_all'; text: string } | { type: 'insert'; index: number; text: string } | { type: 'delete'; startIndex: number; endIndex: number };
export interface DocumentDelta { documentId: string; baseRevision: number; clientOperationId: string; op: DocumentOperation; }
export interface UserPreference { userId?: string; language: 'bn'; dialect: BanglaDialect; enabledSuggestionTypes: SuggestionType[]; productImprovementConsent: boolean; }
export type EventType = 'suggestion_generated' | 'suggestion_accepted' | 'suggestion_rejected' | 'suggestion_ignored' | 'rewrite_requested' | 'tone_requested' | 'api_latency' | 'provider_error' | 'editor_loaded' | 'error';
export interface ShuddhoEvent { id?: string; type: EventType | string; timestamp?: string; requestId?: string; documentId?: string; userId?: string; suggestionId?: string; suppressionKey?: string; language: 'bn'; metadata?: Record<string, unknown>; }
export type ProductEvent = ShuddhoEvent;

function textLimit(value: unknown, max: number, min = 0): string {
  if (typeof value !== 'string' || value.length < min || value.length > max) throw new Error('invalid_text');
  return value;
}
function isSuggestionType(value: unknown): value is SuggestionType { return typeof value === 'string' && suggestionTypes.includes(value as SuggestionType); }

export function parseCheckRequest(input: unknown, maxChars = 10000): CheckRequest {
  const body = (input && typeof input === 'object') ? input as Record<string, unknown> : {};
  const language = body.language ?? body.locale;
  if (language !== undefined && language !== 'bn' && language !== 'bn-BD' && language !== 'bn-IN') throw new Error('unsupported_language');
  const goals = Array.isArray(body.goals) ? body.goals.filter(isSuggestionType) : [];
  const options = (body.options && typeof body.options === 'object') ? body.options as CheckRequest['options'] : undefined;
  return {
    documentId: typeof body.documentId === 'string' ? body.documentId : undefined,
    text: textLimit(body.text, maxChars),
    language: 'bn',
    dialect: ['standard', 'west_bengal', 'bangladesh', 'mixed'].includes(String(body.dialect)) ? body.dialect as BanglaDialect : 'standard',
    revision: Number.isInteger(body.revision) && Number(body.revision) >= 0 ? Number(body.revision) : undefined,
    userId: typeof body.userId === 'string' ? body.userId : typeof body.user_id === 'string' ? body.user_id : undefined,
    client: body.client && typeof body.client === 'object' ? body.client as CheckRequest['client'] : undefined,
    options: options ?? (goals.length ? {
      includeGrammar: goals.includes('grammar'), includeSpelling: goals.includes('spelling'), includeStyle: goals.includes('style'), includeTone: goals.includes('tone'), includeRewrite: goals.includes('rewrite'),
    } : undefined),
    consent: body.consent && typeof body.consent === 'object' ? body.consent as CheckRequest['consent'] : undefined,
  };
}
export function parseRewriteRequest(input: unknown): RewriteRequest {
  const body = (input && typeof input === 'object') ? input as Record<string, unknown> : {};
  return { text: textLimit(body.text, 8000, 1), instruction: typeof body.instruction === 'string' ? body.instruction.slice(0, 400) : undefined, tone: typeof body.tone === 'string' ? body.tone.slice(0, 80) : undefined, intent: typeof body.intent === 'string' ? body.intent : undefined };
}
export function parseToneRequest(input: unknown): ToneRequest { return { text: textLimit((input as Record<string, unknown>)?.text, 12000, 1) }; }
export function parseEventRequest(input: unknown): { events: ShuddhoEvent[] } {
  const body = input as { events?: unknown[] };
  const rawEvents = Array.isArray(body?.events) ? body.events : (input && typeof input === 'object' ? [input] : []);
  if (rawEvents.length === 0 || rawEvents.length > 100) throw new Error('invalid_events');
  return { events: rawEvents.map((event) => ({ ...(event as ShuddhoEvent), language: 'bn', metadata: sanitizeEventMetadata((event as ShuddhoEvent).metadata ?? {}) })) };
}
export function parseDocumentDelta(input: unknown): DocumentDelta {
  const body = input as any;
  const delta = body?.delta ?? body;
  if (!delta || typeof delta.documentId !== 'string' || !Number.isInteger(delta.baseRevision) || typeof delta.clientOperationId !== 'string' || !delta.op) throw new Error('invalid_delta');
  return delta as DocumentDelta;
}
export function sanitizeEventMetadata(metadata: Record<string, unknown>): Record<string, unknown> {
  const copy = { ...metadata };
  delete copy.text; delete copy.rawText; delete copy.fullText; delete copy.documentText;
  return copy;
}

export * from './bangla/unicode.js';
export * from './suggestionIds.js';
export * from './adapters/legacyAnalyzeToCheckResponse.js';
export * from './adapters/checkResponseToLegacyAnalyze.js';
