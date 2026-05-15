import type { ProductEvent } from '@shuddho/shared';

export interface EventSink {
  record(events: ProductEvent[], context: { requestId: string; userId: string }): Promise<void>;
}

export class InMemoryEventSink implements EventSink {
  readonly events: ProductEvent[] = [];
  async record(events: ProductEvent[], _context?: { requestId: string; userId: string }): Promise<void> {
    this.events.push(...events.map((event) => ({ ...event, occurredAt: event.occurredAt ?? new Date().toISOString() })));
  }
}
