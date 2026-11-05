export type EditorDraftRecord = {
  text: string;
  openedArtifact: string;
  openedArtifactId: string;
  originConversationId: string | null;
  originProjectId: string | null;
  savedDocumentId: string | null;
  savedSha256: string | null;
  savedDocumentName: string;
};

export type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export type SaveAttemptLike = { uploaded?: { id: string; filename: string } };
export type EditorCopyClient = {
  workspaceManifest(): Promise<{ documents: Array<{ document_id: string; name: string; sha256: string; available: boolean }> }>;
  upload(file: File): Promise<{ id: string; filename: string }>;
  documents(): Promise<{ documents: Array<{ id: string; filename: string; state: string }> }>;
};
export type SavedEditorCopy = { documentId: string; sha256: string; name: string };

export function editorDraftStorageKey(userId: string): string;
export function readEditorDraft(storage: StorageLike, userId: string): EditorDraftRecord | null;
export function writeEditorDraft(storage: StorageLike, userId: string, record: EditorDraftRecord): void;
export function clearEditorDraft(storage: StorageLike, userId: string): void;
export function sha256Hex(text: string, cryptoProvider?: Pick<Crypto, "subtle">): Promise<string>;
export function persistEditorCopy(client: EditorCopyClient, text: string, filename: string, attempt: SaveAttemptLike, cryptoProvider?: Pick<Crypto, "subtle">): Promise<SavedEditorCopy>;
