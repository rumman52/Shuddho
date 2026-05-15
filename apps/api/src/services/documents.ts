import type { DocumentDelta, DocumentRecord } from '@shuddho/shared';

export class DocumentStore {
  private documents = new Map<string, DocumentRecord>();
  get(documentId: string): DocumentRecord | undefined { return this.documents.get(documentId); }
  put(documentId: string, text: string): DocumentRecord {
    const current = this.documents.get(documentId);
    const next: DocumentRecord = { id: documentId, text, plainText: text, revision: (current?.revision ?? 0) + 1, updatedAt: new Date().toISOString(), ownerId: current?.ownerId, title: current?.title ?? 'Untitled draft' };
    this.documents.set(documentId, next); return next;
  }
  save(document: DocumentRecord): DocumentRecord { const normalized = { ...document, text: document.text ?? document.plainText ?? '', plainText: document.plainText ?? document.text ?? '' }; this.documents.set(document.id, normalized); return normalized; }
  applyDelta(delta: DocumentDelta, ownerId = 'anonymous'): { document: DocumentRecord; accepted: boolean; reason?: string } {
    const current = this.documents.get(delta.documentId) ?? { id: delta.documentId, ownerId, title: 'Untitled draft', text: '', plainText: '', revision: 0, updatedAt: new Date().toISOString() };
    if (delta.baseRevision !== current.revision) return { document: current, accepted: false, reason: 'revision_mismatch' };
    const currentText = current.text ?? current.plainText ?? '';
    let nextText = currentText;
    if (delta.op.type === 'replace_all') nextText = delta.op.text;
    if (delta.op.type === 'insert') nextText = currentText.slice(0, delta.op.index) + delta.op.text + currentText.slice(delta.op.index);
    if (delta.op.type === 'delete') nextText = currentText.slice(0, delta.op.startIndex) + currentText.slice(delta.op.endIndex);
    const next = { ...current, text: nextText, plainText: nextText, revision: current.revision + 1, updatedAt: new Date().toISOString() };
    this.documents.set(delta.documentId, next); return { document: next, accepted: true };
  }
}
