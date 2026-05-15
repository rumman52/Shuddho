import type { Server } from 'node:http';
import { logger } from '@shuddho/observability';
import type { DocumentStore } from '../services/documents.js';

export function attachDocumentSync(server: Server, store: DocumentStore) {
  server.on('upgrade', (request, socket) => {
    const url = new URL(request.url ?? '', 'http://localhost');
    if (!url.pathname.startsWith('/ws/docs/')) return;
    const documentId = decodeURIComponent(url.pathname.replace('/ws/docs/', ''));
    const document = store.get(documentId);
    logger.info({ documentId, hasDocument: Boolean(document) }, 'websocket sync upgrade placeholder');
    socket.write('HTTP/1.1 501 Not Implemented\r\nConnection: close\r\n\r\n');
    socket.destroy();
  });
  return { close: () => undefined };
}
