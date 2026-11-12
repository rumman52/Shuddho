import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import ConversationReply from "./ConversationReply";
import ConversationWorkspace from "./ConversationWorkspace";
import type { CoworkerClient, ConversationMessageRecord, WorkspaceManifest } from "./client";

const stamp = "2026-11-12T00:00:00Z";
const conversation = { id: "conversation-1", title: "Contract", message_sequence: 1, created_at: stamp, updated_at: stamp };
const source = { resource_type: "document_version", resource_id: "version-1", document_id: "document-1", version: 1, sha256: "a".repeat(64) };
const response = {
  state: "completed" as const,
  text: "The renewal date is 17 March 2027. [[src-1]]",
  sources: [{ source_id: "src-1", label: "contract.pdf", resource_type: "document_version" as const }],
};
const message: ConversationMessageRecord = {
  id: "message-1", conversation_id: conversation.id, sequence: 1, text: "When does the contract renew?",
  selected_sources: [source], resource_links: [], created_at: stamp, assistant_reply: null,
};

test("completed grounded answers display verified file references, never internal object paths", async () => {
  let tree!: ReactTestRenderer;
  await act(async () => { tree = create(<ConversationReply reply={response} pending={false} disabled={false} retry={() => undefined} />); });
  try {
    const labels = tree.root.findByProps({ "aria-label": "Answer sources" });
    assert.ok(labels.findAllByType("span").some(node => node.children.includes("contract.pdf")));
    assert.equal(tree.root.findAllByProps({ "aria-label": "Copy AI reply" }).length, 1);
  } finally { await act(async () => tree.unmount()); }
});

test("Ask Rukh on an attached PDF uses the reply endpoint without dispatching an AgentRun", async () => {
  const oldWindow = globalThis.window;
  globalThis.window = { location: { search: "" }, setInterval, clearInterval } as unknown as Window & typeof globalThis;
  let tree: ReactTestRenderer | undefined;
  let replyCalls = 0, dispatchCalls = 0;
  const manifest = {
    schema_version: 1, workspace_id: "workspace-1", workspace_name: "Workspace",
    documents: [{ document_id: "document-1", version_id: "version-1", name: "contract.pdf", version: 1, sha256: "a".repeat(64), available: true, trust: "untrusted_source" as const }],
    artifacts: [], memory: [], revision_sha256: "a".repeat(64),
    truncated: { documents: false, artifacts: false, memory: false },
  } as WorkspaceManifest;
  const client = {
    conversations: async () => ({ items: [conversation] }),
    conversationHistory: async () => ({ items: [message] }),
    conversationActivityHistory: async () => ({ items: [] }),
    workspaceManifest: async () => manifest,
    memory: async () => ({ enabled: false, facts: [] }),
    runtimeManifest: async () => ({ capabilities: { conversation_replies: true, grounded_conversation_replies: true } }),
    replyToConversationMessageStream: async (_conversation: string, _message: string, _sequence: number,
      onUpdate: (value: typeof response) => void) => { replyCalls++; onUpdate(response); return response; },
    dispatchConversationMessage: async () => { dispatchCalls++; },
  } as unknown as CoworkerClient;
  try {
    await act(async () => { tree = create(<ConversationWorkspace client={client} openAgent={() => undefined} />); });
    const ask = tree!.root.findAllByType("button").find(node => node.children.includes("Ask Rukh"));
    assert.ok(ask, "Ask Rukh is available for a selected supported document");
    assert.equal(ask.props.disabled, false);
    await act(async () => ask.props.onClick());
    assert.equal(replyCalls, 1);
    assert.equal(dispatchCalls, 0);
    assert.ok(tree!.root.findAllByProps({ "aria-label": "Answer sources" }).length === 1);
  } finally {
    if (tree) await act(async () => tree!.unmount());
    globalThis.window = oldWindow;
  }
});
