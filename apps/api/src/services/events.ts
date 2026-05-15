import { randomUUID } from 'node:crypto';
import type { ShuddhoEvent } from '@shuddho/shared';
import { sanitizeEventMetadata } from '@shuddho/shared';
export interface EventSink { record(events: ShuddhoEvent[], context?: { requestId: string; userId?: string }): Promise<void>; }
export class InMemoryEventSink implements EventSink {
  readonly events: ShuddhoEvent[] = [];
  async record(events: ShuddhoEvent[], context?: { requestId: string; userId?: string }): Promise<void> {
    this.events.push(...events.map((event) => ({ ...event, id: event.id ?? randomUUID(), requestId: event.requestId ?? context?.requestId, userId: event.userId ?? context?.userId, timestamp: event.timestamp ?? new Date().toISOString(), language: 'bn' as const, metadata: sanitizeEventMetadata(event.metadata ?? {}) })));
  }
}
