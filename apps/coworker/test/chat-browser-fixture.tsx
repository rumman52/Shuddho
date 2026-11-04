// Synthetic API fixture for browser checks of the real workspace components.
import React from "react";
import { createRoot } from "react-dom/client";
import CoworkerWorkspace from "../../web-editor/src/coworker/CoworkerWorkspace";
import ThemeToggle from "../../web-editor/src/components/ThemeToggle";
import { initializeRukhTheme } from "../../web-editor/src/lib/theme";
import type { CoworkerClient, ConversationMessageRecord, ConversationRecord } from "../../web-editor/src/coworker/client";
import "@rukh/design-system/tokens.css";
import "../../web-editor/src/coworker/workspace.css";
import "../src/styles.css";
const conversations: ConversationRecord[] = [];
const messages: ConversationMessageRecord[] = [];
const client = {
  me: async () => ({ account_id: "browser-fixture", usage: { tasks_today: 0 }, limits: { daily_tasks: 10 } }),
  list: async () => ({ tasks: [] }), documents: async () => ({ documents: [] }), skills: async () => ({ skills: [], upload_formats: ["txt"] }),
  runtimeManifest: async () => ({ capabilities: { conversation_replies: true } }),
  conversations: async () => ({ items: [...conversations] }),
  conversationHistory: async (id: string) => ({ items: messages.filter(item => item.conversation_id === id).map(item => ({ ...item })) }),
  conversationActivityHistory: async () => ({ items: [] }),
  workspaceManifest: async () => ({ documents: [], artifacts: [], memory: [], revision_sha256: "a".repeat(64), truncated: {} }),
  memory: async () => ({ enabled: false, facts: [] }),
  createConversation: async (title: string) => {
    const now = new Date().toISOString();
    const item = { id: crypto.randomUUID(), title, message_sequence: 0, created_at: now, updated_at: now };
    conversations.unshift(item); return { ...item };
  },
  appendConversationMessage: async (id: string, text: string) => {
    const conversation = conversations.find(item => item.id === id)!;
    const item = { id: crypto.randomUUID(), conversation_id: id, sequence: ++conversation.message_sequence, text, resource_links: [], selected_sources: [], created_at: new Date().toISOString() };
    messages.push(item); return { ...item };
  },
  replyToConversationMessage: async (_id: string, messageId: string) => {
    await new Promise(resolve => setTimeout(resolve, 350));
    const reply = { state: "completed" as const, text: "Let’s turn that idea into a clear plan.\n\n1. Define the result you want.\n2. Identify the information you need.\n3. Choose one useful next step.\n\nআপনি চাইলে আমরা বাংলায়ও কাজ করতে পারি।", context_truncated: false };
    messages.find(item => item.id === messageId)!.assistant_reply = reply;
    return reply;
  },
};
initializeRukhTheme();
createRoot(document.getElementById("root")!).render(<div className="rukh-coworker-app">
  <header className="rukh-productbar"><a className="rukh-product-brand" href="#"><span className="rukh-brand-mark">r</span><span><strong>Rukh AI</strong><small>AI Coworker</small></span></a><nav className="rukh-product-switcher" aria-label="Workspace navigation"><a className="rukh-product-switch rukh-product-switch--home" href="/workspaces">All workspaces</a><a className="rukh-product-switch" href="/editor">Web Editor</a><ThemeToggle /></nav></header>
  <CoworkerWorkspace client={client as unknown as CoworkerClient} email="preview@example.test" signOut={async () => undefined} />
</div>);
