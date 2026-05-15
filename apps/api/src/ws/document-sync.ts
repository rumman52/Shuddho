import type { Server } from 'node:http';
import { createHash } from 'node:crypto';
import { logger } from '@shuddho/observability';
import { parseDocumentDelta } from '@shuddho/shared';
import type { DocumentStore } from '../services/documents.js';

function acceptKey(key: string): string {
  return createHash('sha1').update(key.trim() + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
}
function frame(data: unknown): any {
  const payload = Buffer.from(JSON.stringify(data));
  const header = payload.length < 126 ? Buffer.from([0x81, payload.length]) : Buffer.from([0x81, 126, payload.length >> 8, payload.length & 255]);
  return Buffer.concat([header, payload]);
}
function decode(buffer: any): string | null {
  if (buffer.length < 6) return null;
  const len = buffer[1]! & 0x7f;
  const offset = len === 126 ? 4 : 2;
  const mask = buffer.subarray(offset, offset + 4);
  const data = buffer.subarray(offset + 4, offset + 4 + (len === 126 ? buffer.readUInt16BE(2) : len));
  return Buffer.from(data.map((byte: number, i: number) => byte ^ mask[i % 4]!)).toString('utf8');
}

export function attachDocumentSync(server: Server, store: DocumentStore) {
  const clients = new Map<string, Set<any>>();
  server.on('upgrade', (request, socket) => {
    const url = new URL(request.url ?? '', 'http://localhost');
    if (!url.pathname.startsWith('/ws/docs/')) return;
    const documentId = decodeURIComponent(url.pathname.replace('/ws/docs/', ''));
    const key = request.headers['sec-websocket-key'];
    if (typeof key !== 'string') { socket.destroy(); return; }
    socket.write(['HTTP/1.1 101 Switching Protocols', 'Upgrade: websocket', 'Connection: Upgrade', `Sec-WebSocket-Accept: ${acceptKey(key)}`, '\r\n'].join('\r\n'));
    const set = clients.get(documentId) ?? new Set(); set.add(socket); clients.set(documentId, set);
    socket.write(frame({ type: 'server_hello', documentId, document: store.get(documentId) ?? { id: documentId, text: '', revision: 0, updatedAt: new Date().toISOString() } }));
    socket.on('data', (chunk: any) => {
      try {
        const text = decode(chunk); if (!text) return;
        const msg = JSON.parse(text);
        if (msg.type === 'client_hello') { socket.write(frame({ type: 'server_hello', documentId, document: store.get(documentId) })); return; }
        if (msg.type !== 'edit') return;
        const result = store.applyDelta(parseDocumentDelta({ ...msg, documentId }));
        if (!result.accepted) { socket.write(frame({ type: 'resync_required', documentId, document: result.document })); return; }
        const out = frame({ type: 'ack', documentId, revision: result.document.revision, document: result.document });
        for (const client of clients.get(documentId) ?? []) client.write(out);
      } catch (error) { socket.write(frame({ type: 'error', message: error instanceof Error ? error.message : 'invalid_message' })); }
    });
    socket.on('close', () => set.delete(socket)); socket.on('end', () => set.delete(socket));
    logger.info({ documentId }, 'websocket sync connected');
  });
  return { close: () => clients.clear() };
}
