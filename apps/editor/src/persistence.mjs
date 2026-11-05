export function editorDraftStorageKey(userId) {
  return `rukh-editor-draft:${userId}`;
}

export function readEditorDraft(storage, userId) {
  try {
    const raw = storage.getItem(editorDraftStorageKey(userId));
    if (!raw) return null;
    const value = JSON.parse(raw);
    if (!value || typeof value !== "object" || typeof value.text !== "string") return null;
    return {
      text: value.text,
      openedArtifact: typeof value.openedArtifact === "string" ? value.openedArtifact : "",
      openedArtifactId: typeof value.openedArtifactId === "string" ? value.openedArtifactId : "",
      originConversationId: typeof value.originConversationId === "string" ? value.originConversationId : null,
      originProjectId: typeof value.originProjectId === "string" ? value.originProjectId : null,
      savedDocumentId: typeof value.savedDocumentId === "string" ? value.savedDocumentId : null,
      savedSha256: typeof value.savedSha256 === "string" ? value.savedSha256 : null,
      savedDocumentName: typeof value.savedDocumentName === "string" ? value.savedDocumentName : "",
    };
  } catch {
    return null;
  }
}

export function writeEditorDraft(storage, userId, record) {
  if (!record.text.trim()) {
    storage.removeItem(editorDraftStorageKey(userId));
    return;
  }
  storage.setItem(editorDraftStorageKey(userId), JSON.stringify(record));
}

export function clearEditorDraft(storage, userId) {
  storage.removeItem(editorDraftStorageKey(userId));
}

export async function sha256Hex(text, cryptoProvider = globalThis.crypto) {
  if (!cryptoProvider?.subtle) throw new Error("Secure SHA-256 is unavailable in this browser context.");
  const digest = await cryptoProvider.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}

export async function persistEditorCopy(client, text, filename, attempt, cryptoProvider = globalThis.crypto) {
  if (!text.trim()) throw new Error("Add text to the editor before saving.");
  const digest = await sha256Hex(text, cryptoProvider);
  const before = await client.workspaceManifest();
  const existing = before.documents.find(item => item.name === filename && item.sha256 === digest && item.available);
  if (existing) return { documentId: existing.document_id, sha256: digest, name: existing.name };

  if (!attempt.uploaded) {
    attempt.uploaded = await client.upload(new File([text], filename, { type: "text/plain" }));
  }
  const uploaded = attempt.uploaded;
  if (!uploaded) throw new Error("The upload did not return a workspace document record.");

  const [after, listing] = await Promise.all([client.workspaceManifest(), client.documents()]);
  const manifestRecord = after.documents.find(item => item.document_id === uploaded.id && item.available && item.sha256 === digest);
  const listedRecord = listing.documents.find(item => item.id === uploaded.id && item.state === "available");
  if (!manifestRecord && !listedRecord) {
    throw new Error("The upload was accepted but its workspace persistence could not be verified. Retry verification before uploading another copy.");
  }
  return {
    documentId: uploaded.id,
    sha256: digest,
    name: manifestRecord?.name ?? listedRecord?.filename ?? uploaded.filename,
  };
}
