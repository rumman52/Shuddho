import type { DocumentDelta, DocumentRecord } from '@shuddho/shared';

export class DocumentStore {
  private documents = new Map<string, DocumentRecord>();

  get(documentId: string): DocumentRecord | undefined {
    return this.documents.get(documentId);
  }

  save(document: DocumentRecord): DocumentRecord {
    this.documents.set(document.id, document);
    return document;
  }

  applyDelta(delta: DocumentDelta, ownerId: string): { document: DocumentRecord; accepted: boolean; reason?: string } {
    const current = this.documents.get(delta.documentId) ?? {
      id: delta.documentId,
      ownerId,
      title: 'Untitled draft',
      plainText: '',
      revision: 0,
      updatedAt: new Date().toISOString(),
    };
    if (delta.baseRevision !== current.revision) {
      return { document: current, accepted: false, reason: 'revision_mismatch' };
    }
    let nextText = current.plainText;
    if (delta.op.type === 'replace_all') nextText = delta.op.text;
    if (delta.op.type === 'insert') nextText = current.plainText.slice(0, delta.op.index) + delta.op.text + current.plainText.slice(delta.op.index);
    if (delta.op.type === 'delete') nextText = current.plainText.slice(0, delta.op.startIndex) + current.plainText.slice(delta.op.endIndex);
    const next = { ...current, plainText: nextText, revision: current.revision + 1, updatedAt: new Date().toISOString() };
    this.documents.set(delta.documentId, next);
    return { document: next, accepted: true };
  }
}
