import assert from "node:assert/strict";
import test from "node:test";
import { webcrypto } from "node:crypto";
import {
  clearEditorDraft,
  editorDraftStorageKey,
  persistEditorCopy,
  readEditorDraft,
  sha256Hex,
  writeEditorDraft,
} from "../src/persistence.mjs";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
}

test("editor drafts are isolated by authenticated user", () => {
  const storage = memoryStorage();
  writeEditorDraft(storage, "user-a", {
    text: "A private draft",
    openedArtifact: "",
    openedArtifactId: "",
    originConversationId: "conversation-a",
    originProjectId: null,
    savedDocumentId: null,
    savedSha256: null,
    savedDocumentName: "",
  });
  assert.equal(editorDraftStorageKey("user-a"), "rukh-editor-draft:user-a");
  assert.equal(readEditorDraft(storage, "user-a")?.text, "A private draft");
  assert.equal(readEditorDraft(storage, "user-b"), null);
  clearEditorDraft(storage, "user-a");
  assert.equal(readEditorDraft(storage, "user-a"), null);
});

test("editor draft reader rejects malformed or structurally invalid storage", () => {
  const storage = memoryStorage();
  storage.setItem(editorDraftStorageKey("user-a"), "{broken");
  assert.equal(readEditorDraft(storage, "user-a"), null);
  storage.setItem(editorDraftStorageKey("user-a"), JSON.stringify({ text: 42 }));
  assert.equal(readEditorDraft(storage, "user-a"), null);
});

test("editor draft writer removes an empty draft", () => {
  const storage = memoryStorage();
  writeEditorDraft(storage, "user-a", {
    text: " ",
    openedArtifact: "",
    openedArtifactId: "",
    originConversationId: null,
    originProjectId: null,
    savedDocumentId: null,
    savedSha256: null,
    savedDocumentName: "",
  });
  assert.equal(readEditorDraft(storage, "user-a"), null);
});

test("SHA-256 helper produces the standard digest", async () => {
  assert.equal(
    await sha256Hex("abc", webcrypto),
    "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
  );
});

test("workspace copy persistence verifies an existing exact-content document without uploading", async () => {
  const digest = await sha256Hex("existing text", webcrypto);
  let uploads = 0;
  const client = {
    workspaceManifest: async () => ({ documents: [{ document_id: "doc-1", name: "draft.txt", sha256: digest, available: true }] }),
    upload: async () => { uploads += 1; throw new Error("should not upload"); },
    documents: async () => ({ documents: [] }),
  };
  const result = await persistEditorCopy(client, "existing text", "draft.txt", {}, webcrypto);
  assert.deepEqual(result, { documentId: "doc-1", sha256: digest, name: "draft.txt" });
  assert.equal(uploads, 0);
});

test("workspace copy retry verifies the accepted upload without creating a duplicate", async () => {
  const digest = await sha256Hex("new text", webcrypto);
  let uploads = 0;
  let uploaded;
  let verified = false;
  const client = {
    workspaceManifest: async () => ({
      documents: verified ? [{ document_id: "doc-2", name: "draft.txt", sha256: digest, available: true }] : [],
    }),
    upload: async file => {
      uploads += 1;
      uploaded = { id: "doc-2", filename: file.name };
      return uploaded;
    },
    documents: async () => ({ documents: verified ? [{ id: "doc-2", filename: "draft.txt", state: "available" }] : [] }),
  };
  const attempt = {};
  await assert.rejects(persistEditorCopy(client, "new text", "draft.txt", attempt, webcrypto), /could not be verified/);
  assert.equal(uploads, 1);
  verified = true;
  const result = await persistEditorCopy(client, "new text", "draft.txt", attempt, webcrypto);
  assert.deepEqual(result, { documentId: "doc-2", sha256: digest, name: "draft.txt" });
  assert.equal(uploads, 1);
});
