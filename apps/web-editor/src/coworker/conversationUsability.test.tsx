import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import ConversationWorkspace from "./ConversationWorkspace";
import { WorkspaceError, type CoworkerClient, type ConversationMessageRecord, type AgentRun, type WorkspaceManifest } from "./client";

const timestamp = "2026-11-04T00:00:00Z";
const record = { id: "conversation-1", title: "Research brief", message_sequence: 0, created_at: timestamp, updated_at: timestamp };
function fixture(initial = [] as typeof record[]) {
  let items = [...initial];
  const calls = { reads: [] as string[], titles: [] as string[], creates: [] as string[], messages: [] as { id: string; text: string; key: string }[], renames: [] as { id: string; title: string; expectedUpdatedAt: string }[], dispatches: 0 };
  const client = {
    conversations: async () => ({ items }),
    workspaceManifest: async (): Promise<WorkspaceManifest> => ({
      schema_version: 1, workspace_id: "workspace-1", workspace_name: "Workspace",
      documents: [], artifacts: [], memory: [], revision_sha256: "a".repeat(64),
      truncated: { documents: false, artifacts: false, memory: false },
    }),
    upload: async (file: File) => ({ id: "document-1", filename: file.name, state: "uploaded", byte_size: file.size }),
    memory: async () => ({ enabled: false, facts: [] }),
    conversationHistory: async () => ({ items: [] as ConversationMessageRecord[] }),
    agentRun: async (id: string) => { calls.reads.push(id); return { id, state: "completed", final_state: "completed", message: "Ready", plan: [], tool_results: [] } as unknown as AgentRun; },
    conversationActivityHistory: async () => ({ items: [] }),
    createConversation: async (title: string, key: string) => { calls.creates.push(key); calls.titles.push(title); const next = { ...record, title }; items = [next]; return next; },
    renameConversation: async (id: string, title: string, expectedUpdatedAt: string) => {
      calls.renames.push({ id, title, expectedUpdatedAt });
      const next = { ...record, id, title, updated_at: "2026-11-04T00:01:00Z" };
      items = items.map(item => item.id === id ? next : item);
      return next;
    },
    appendConversationMessage: async (id: string, text: string, key: string) => { calls.messages.push({ id, text, key }); return {}; },
    dispatchConversationMessage: async () => { calls.dispatches++; },
  };
  return { client, calls };
}
async function mount(run: (tree: ReactTestRenderer, data: ReturnType<typeof fixture>) => Promise<void>, data = fixture(), extraProps: Partial<React.ComponentProps<typeof ConversationWorkspace>> = {}, search = "") {
  const previous = globalThis.window;
  globalThis.window = { location: { search }, setInterval, clearInterval } as unknown as Window & typeof globalThis;
  let tree!: ReactTestRenderer;
  try {
    await act(async () => { tree = create(<ConversationWorkspace client={data.client as unknown as CoworkerClient} openAgent={() => undefined} {...extraProps} />); });
    await run(tree, data);
  } finally { if (tree) await act(async () => tree.unmount()); globalThis.window = previous; }
}
async function send(tree: ReactTestRenderer, text: string) {
  await act(async () => tree.root.findByProps({ id: "cw-conversation-message" }).props.onChange({ target: { value: text } }));
  await act(async () => tree.root.findByProps({ "aria-label": "Message composer" }).props.onSubmit({ preventDefault() {} }));
}

test("empty workspace has a composer and first message creates a conversation without dispatch", async () => {
  await mount(async (tree, { calls }) => {
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.disabled, false);
    await send(tree, "আমার কাজের পরিকল্পনা করুন");
    assert.equal(calls.creates.length, 1);
    assert.equal(calls.messages[0].text, "আমার কাজের পরিকল্পনা করুন");
    assert.equal(calls.dispatches, 0);
  });
});

test("lost first-message response retries in the same conversation with the same key", async () => {
  const data = fixture(); const append = data.client.appendConversationMessage;
  data.client.appendConversationMessage = async (...args) => { await append(...args); if (data.calls.messages.length === 1) throw new Error("response lost"); return {}; };
  await mount(async (tree, { calls }) => {
    await send(tree, "A research brief");
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.value, "A research brief");
    await send(tree, "A research brief");
    assert.equal(calls.creates.length, 1);
    assert.equal(calls.messages[0].key, calls.messages[1].key);
    assert.equal(calls.messages[0].id, calls.messages[1].id);
  }, data);
});

test("conversation search filters history without changing the selected thread", async () => {
  await mount(async tree => {
    await act(async () => tree.root.findByProps({ "aria-label": "Search conversations" }).props.onChange({ target: { value: "missing" } }));
    assert.equal(tree.root.findByProps({ className: "rukh-conversation-items" }).findAllByType("li").length, 0);
    assert.ok(tree.root.findAllByType("h2").some(node => node.children.includes("Research brief")));
  }, fixture([record]));
});

test("prompt starters fill the composer without sending or dispatching", async () => {
  await mount(async (tree, { calls }) => {
    await act(async () => tree.root.findByProps({ "aria-label": "Start with a research brief" }).props.onClick());
    assert.match(tree.root.findByProps({ id: "cw-conversation-message" }).props.value, /Research/);
    assert.equal(calls.creates.length, 0); assert.equal(calls.dispatches, 0);
  });
});

test("new conversation clears the old draft without creating an empty server record", async () => {
  await mount(async (tree, { calls }) => {
    await act(async () => tree.root.findByProps({ id: "cw-conversation-message" }).props.onChange({ target: { value: "Old draft" } }));
    await act(async () => tree.root.findByProps({ "aria-label": "New conversation" }).props.onClick());
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.value, "");
    assert.equal(calls.creates.length, 0);
  }, fixture([record]));
});

test("Enter submits while Shift Enter and IME composition keep editing", async () => {
  await mount(async tree => {
    let submits = 0;
    const invoke = (extra: object) => tree.root.findByProps({ id: "cw-conversation-message" }).props.onKeyDown({ key: "Enter", shiftKey: false, nativeEvent: {}, preventDefault() {}, currentTarget: { form: { requestSubmit() { submits++; } } }, ...extra });
    await act(async () => tree.root.findByProps({ id: "cw-conversation-message" }).props.onChange({ target: { value: "Draft" } }));
    invoke({ shiftKey: true }); invoke({ nativeEvent: { isComposing: true } });
    assert.equal(submits, 0); invoke({}); assert.equal(submits, 1);
  });
});

test("rollout-disabled conversations show an explanation in the visible thread and prevent sending", async () => {
  const data = fixture(); data.client.conversations = async () => { throw new WorkspaceError("Conversations disabled", 403); };
  await mount(async tree => {
    const thread = tree.root.findByProps({ "aria-label": "Conversation" });
    assert.ok(thread.findAllByProps({ role: "alert" }).length);
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.disabled, true);
  }, data);
});

test("a transient initial list failure offers retry and unlocks the composer only after success", async () => {
  const data = fixture(); let reads = 0;
  data.client.conversations = async () => { if (++reads === 1) throw new WorkspaceError("Temporary outage", 503); return { items: [] }; };
  await mount(async tree => {
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.disabled, true);
    await act(async () => tree.root.findByProps({ "aria-label": "Retry conversations" }).props.onClick());
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.disabled, false);
    assert.equal(reads, 2);
  }, data);
});

test("lost conversation-create response retries with the identical title request identity", async () => {
  const data = fixture(); const createConversation = data.client.createConversation;
  data.client.createConversation = async (...args) => { const result = await createConversation(...args); if (data.calls.creates.length === 1) throw new Error("Create response lost"); return result; };
  await mount(async (tree, { calls }) => {
    await send(tree, "My topic"); await send(tree, "My topic");
    assert.equal(calls.creates.length, 2);
    assert.equal(calls.creates[0], calls.creates[1]);
    assert.equal(calls.messages.length, 1);
  }, data);
});

test("manual title creation errors remain visible inside an open Conversations drawer", async () => {
  const data = fixture(); data.client.createConversation = async () => { throw new Error("Could not create this conversation"); };
  await mount(async tree => {
    await act(async () => tree.root.findByProps({ "aria-label": "Open navigation" }).props.onClick({ currentTarget: {} }));
    await act(async () => tree.root.findByProps({ id: "cw-conversation-title" }).props.onChange({ target: { value: "New title" } }));
    const input = tree.root.findByProps({ id: "cw-conversation-title" });
    await act(async () => input.parent!.props.onSubmit({ preventDefault() {} }));
    const dialog = tree.root.findByProps({ role: "dialog" });
    assert.ok(dialog.findAllByProps({ role: "alert" }).some(item => item.children.includes("Could not create this conversation")));
  }, data);
});


test("first-message title keeps a complete emoji at the truncation boundary", async () => {
  await mount(async (tree, { calls }) => {
    await send(tree, "a".repeat(79) + "😀" + "more");
    assert.equal(calls.titles[0], "a".repeat(79) + "😀");
    assert.equal(Array.from(calls.titles[0]).length, 80);
  });
});


test("a mature conversation loads only its newest run eagerly and expands older runs on demand", async () => {
  const data = fixture([{ ...record, message_sequence: 20 }]);
  data.client.conversationHistory = async () => ({ items: Array.from({ length: 20 }, (_, index) => ({
    id: `message-${index}`, conversation_id: record.id, sequence: index + 1, text: `Brief ${index}`,
    selected_sources: [], resource_links: [{ resource_type: "agent_run", resource_id: `run-${index}` }], created_at: timestamp,
  })) });
  await mount(async (tree, { calls }) => {
    assert.deepEqual(calls.reads, ["run-19"]);
    await act(async () => tree.root.findAllByProps({ "aria-label": "Show coworker progress" })[0].props.onClick());
    assert.deepEqual(calls.reads, ["run-19", "run-0"]);
  }, data);
});

test("selected conversation can be renamed with its current revision", async () => {
  const data = fixture([record]);
  await mount(async (tree, { calls }) => {
    await act(async () => tree.root.findByProps({ "aria-label": "Rename conversation" }).props.onClick());
    const input = tree.root.findByProps({ id: "cw-conversation-rename" });
    await act(async () => input.props.onChange({ target: { value: "Updated title" } }));
    const form = tree.root.findByProps({ "aria-label": "Rename conversation form" });
    await act(async () => form.props.onSubmit({ preventDefault() {} }));
    assert.deepEqual(calls.renames, [{ id: record.id, title: "Updated title", expectedUpdatedAt: timestamp }]);
    assert.ok(tree.root.findAllByType("h2").some(node => node.children.includes("Updated title")));
  }, data);
});

test("conversation context uploads a source and attaches it only for explicit Agent tasks", async () => {
  const data = fixture();
  const document = {
    document_id: "document-1", version_id: "version-1", name: "brief.pdf",
    version: 1, sha256: "a".repeat(64), available: true, trust: "untrusted_source" as const,
  };
  data.client.workspaceManifest = async () => ({
    schema_version: 1, workspace_id: "workspace-1", workspace_name: "Workspace",
    revision_sha256: "b".repeat(64), documents: [document], artifacts: [],
    memory: [], truncated: { documents: false, artifacts: false, memory: false },
  });
  data.client.upload = async (file: File) => ({
    id: "document-1", filename: file.name, state: "uploaded", byte_size: file.size,
  });
  await mount(async tree => {
    const input = tree.root.findByProps({ "aria-label": "Upload a source file" });
    await act(async () => input.props.onChange({
      currentTarget: { files: [{ name: "brief.pdf", size: 12 }], value: "" },
    }));
    const checkbox = tree.root.findByProps({ "aria-label": "Attach source file brief.pdf" });
    assert.equal(checkbox.props.checked, true);
    assert.match(JSON.stringify(tree.toJSON()), /Ask Rukh for supported files/i);
  }, data);
});

test("conversation source picker advertises only accepted upload types", async () => {
  await mount(async tree => {
    const input = tree.root.findByProps({ "aria-label": "Upload a source file" });
    assert.equal(input.props.accept, ".txt,.docx,.pdf");
    const upload = tree.root.findByProps({ className: "rukh-context-upload" });
    assert.ok(upload.findAllByType("small").some(node =>
      node.children.join("") === "TXT, DOCX or PDF · maximum 8 MB"));
  });
});

test("conversation context reports upload failures without selecting an invalid source", async () => {
  const data = fixture();
  data.client.upload = async () => { throw new Error("Storage rejected the upload"); };
  await mount(async tree => {
    const input = tree.root.findByProps({ "aria-label": "Upload a source file" });
    await act(async () => input.props.onChange({
      currentTarget: { files: [{ name: "blocked.pdf", size: 12 }], value: "" },
    }));
    const alert = tree.root.findByProps({ role: "alert" });
    assert.match(alert.children.join(""), /Storage rejected the upload/);
    assert.equal(tree.root.findAll(node => node.props["aria-label"]?.startsWith("Attach source file ")).length, 0);
  }, data);
});

test("source selection enforces five items across uploaded documents and generated artifacts", async () => {
  const data = fixture();
  const documents = Array.from({ length: 4 }, (_, index) => ({
    document_id: "document-" + index, version_id: "version-" + index,
    name: "Source " + (index + 1) + ".pdf", version: 1,
    sha256: String(index).repeat(64), available: true, trust: "untrusted_source" as const,
  }));
  const artifacts = Array.from({ length: 2 }, (_, index) => ({
    artifact_id: "artifact-" + index, name: "Artifact " + (index + 1) + ".docx",
    sha256: String(index + 4).repeat(64), available: true, trust: "untrusted_source" as const,
  }));
  data.client.workspaceManifest = async () => ({
    schema_version: 1, workspace_id: "workspace-1", workspace_name: "Workspace",
    revision_sha256: "b".repeat(64), documents, artifacts, memory: [],
    truncated: { documents: false, artifacts: false, memory: false },
  });
  await mount(async tree => {
    for (const document of documents) {
      const checkbox = tree.root.findByProps({ "aria-label": "Attach source file " + document.name });
      await act(async () => checkbox.props.onChange({ target: { checked: true } }));
    }
    const fifth = tree.root.findByProps({ "aria-label": "Attach generated artifact Artifact 1.docx" });
    await act(async () => fifth.props.onChange({ target: { checked: true } }));
    const sixth = tree.root.findByProps({ "aria-label": "Attach generated artifact Artifact 2.docx" });
    assert.equal(sixth.props.disabled, true);
    const selected = tree.root.findAll(node => node.props.type === "checkbox" && node.props.checked === true);
    assert.equal(selected.length, 5);
  }, data);
});

test("saved messages display the names of their attached sources", async () => {
  const data = fixture([record]);
  const document = {
    document_id: "document-1", version_id: "version-1", name: "brief.pdf",
    version: 1, sha256: "a".repeat(64), available: true, trust: "untrusted_source" as const,
  };
  data.client.workspaceManifest = async () => ({
    schema_version: 1, workspace_id: "workspace-1", workspace_name: "Workspace",
    revision_sha256: "b".repeat(64), documents: [document], artifacts: [],
    memory: [], truncated: { documents: false, artifacts: false, memory: false },
  });
  data.client.conversationHistory = async () => ({ items: [{
    id: "message-with-source", conversation_id: record.id, sequence: 1, text: "Review this file",
    selected_sources: [{ resource_type: "document_version", resource_id: "version-1", document_id: "document-1", version: 1, sha256: "a".repeat(64), trust: "untrusted_source" }],
    resource_links: [], created_at: timestamp,
  }] });
  await mount(async tree => {
    const attached = tree.root.findByProps({ className: "rukh-message-sources" });
    assert.deepEqual(attached.findAllByType("li").map(item => item.children.join("")), ["brief.pdf"]);
  }, data);
});

test("chat mode saves once and shows the real assistant reply without starting Agent work", async () => {
  const data = fixture();
  Object.assign(data.client, {
    runtimeManifest: async () => ({ capabilities: { conversation_replies: true } }),
    replyToConversationMessage: async () => ({ state: "completed", text: "বাংলায় উত্তর", context_truncated: false }),
  });
  data.client.appendConversationMessage = async (id, text, key) => {
    data.calls.messages.push({ id, text, key });
    const saved = { id: "saved-message", conversation_id: id, sequence: 1, text, selected_sources: [], resource_links: [], created_at: timestamp };
    data.client.conversationHistory = async () => ({ items: [saved] });
    return saved;
  };
  await mount(async (tree, { calls }) => {
    await send(tree, "Explain recursion");
    assert.equal(calls.messages.length, 1);
    assert.equal(calls.dispatches, 0);
    assert.match(JSON.stringify(tree.toJSON()), /বাংলায় উত্তর/);
  }, data);
});

test("chat mode applies incremental streamed reply updates without dispatching Agent work", async () => {
  const data = fixture([record]);
  const updates: string[] = [];
  const message = {
    id: "saved-message", conversation_id: record.id, sequence: 1, text: "Explain recursion",
    selected_sources: [], resource_links: [], created_at: timestamp,
  };
  data.client.conversationHistory = async () => ({ items: [message] });
  data.client.appendConversationMessage = async (id, text, key) => {
    data.calls.messages.push({ id, text, key });
    return message;
  };
  Object.assign(data.client, {
    runtimeManifest: async () => ({ capabilities: { conversation_replies: true } }),
    replyToConversationMessageStream: async (
      _id: string, _messageId: string, _sequence: number,
      onUpdate: (reply: { state: "generating" | "completed"; text: string }) => void,
    ) => {
      onUpdate({ state: "generating", text: "Partial " });
      updates.push("Partial ");
      onUpdate({ state: "generating", text: "Partial answer" });
      updates.push("Partial answer");
      const completed = { state: "completed" as const, text: "Partial answer", context_truncated: false };
      onUpdate(completed);
      return completed;
    },
  });
  await mount(async (tree, { calls }) => {
    await send(tree, "Explain recursion");
    assert.deepEqual(updates, ["Partial ", "Partial answer"]);
    assert.equal(calls.messages.length, 1);
    assert.equal(calls.dispatches, 0);
    assert.match(JSON.stringify(tree.toJSON()), /Partial answer/);
  }, data);
});

test("composer stays disabled while an admitted streamed reply is still generating", async () => {
  const data = fixture([record]);
  const message = {
    id: "saved-message", conversation_id: record.id, sequence: 1, text: "Explain recursion",
    assistant_reply: null, selected_sources: [], resource_links: [], created_at: timestamp,
  };
  data.client.conversationHistory = async () => ({ items: [message] });
  data.client.appendConversationMessage = async () => message;
  Object.assign(data.client, {
    runtimeManifest: async () => ({ capabilities: { conversation_replies: true } }),
    replyToConversationMessageStream: async (
      _id: string, _messageId: string, _sequence: number,
      onUpdate: (reply: { state: "generating"; text: string }) => void,
    ) => {
      onUpdate({ state: "generating", text: "Partial response" });
      throw new Error("Connection lost");
    },
  });
  await mount(async tree => {
    await send(tree, "Explain recursion");
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.disabled, true);
    assert.ok(tree.root.findAllByProps({ role: "alert" }).some(node => node.children.join("").includes("Connection lost")));
  }, data);
});

test("failed reply transport preserves the saved message and retries the reply only", async () => {
  const data = fixture(); let requests = 0;
  const message = { id: "saved-message", conversation_id: record.id, sequence: 1, text: "Explain recursion", selected_sources: [], resource_links: [], created_at: timestamp };
  data.client.conversationHistory = async () => ({ items: [message] });
  data.client.appendConversationMessage = async (id, text, key) => { data.calls.messages.push({ id, text, key }); return message; };
  Object.assign(data.client, {
    runtimeManifest: async () => ({ capabilities: { conversation_replies: true } }),
    replyToConversationMessage: async () => { if (++requests === 1) throw new Error("Connection lost"); return { state: "completed", text: "Recovered answer" }; },
  });
  await mount(async (tree, { calls }) => {
    await send(tree, message.text);
    await act(async () => tree.root.findByProps({ "aria-label": "Retry AI reply" }).props.onClick());
    assert.equal(requests, 2); assert.equal(calls.messages.length, 1);
    assert.match(JSON.stringify(tree.toJSON()), /Recovered answer/);
  }, data);
});

test("authenticated conversation composer receives and synchronizes the pre-auth draft", async () => {
  const data = fixture();
  let latestDraft = "first prompt";
  await mount(async tree => {
    const textarea = tree.root.findByProps({ id: "cw-conversation-message" });
    assert.equal(textarea.props.value, "first prompt");
    await act(async () => textarea.props.onChange({ target: { value: "edited prompt" } }));
    assert.equal(latestDraft, "edited prompt");
    await act(async () => tree.root.findByProps({ "aria-label": "Message composer" }).props.onSubmit({ preventDefault() {} }));
    assert.equal(data.calls.messages[0].text, "edited prompt");
    assert.equal(latestDraft, "");
  }, data, {
    initialDraft: "first prompt",
    onInitialDraftChange: (value: string) => { latestDraft = value; },
  });
});

test("failed first-message admission keeps the pre-auth draft available for retry", async () => {
  const data = fixture();
  data.client.appendConversationMessage = async () => { throw new Error("Temporary network failure"); };
  let latestDraft = "keep this draft";
  await mount(async tree => {
    await act(async () => tree.root.findByProps({ "aria-label": "Message composer" }).props.onSubmit({ preventDefault() {} }));
    assert.equal(tree.root.findByProps({ id: "cw-conversation-message" }).props.value, "keep this draft");
    assert.equal(latestDraft, "keep this draft");
  }, data, {
    initialDraft: "keep this draft",
    onInitialDraftChange: (value: string) => { latestDraft = value; },
  });
});


test("active Runtime v3 conversation task can be steered at its current revision", async () => {
  const data = fixture([{ ...record, message_sequence: 1 }]);
  const message = {
    id: "message-steer", conversation_id: record.id, sequence: 1, text: "Prepare a report",
    selected_sources: [], resource_links: [{ resource_type: "agent_run", resource_id: "run-steer" }],
    created_at: timestamp,
  };
  data.client.conversationHistory = async () => ({ items: [message] });
  data.client.conversationActivityHistory = async () => ({ items: [{
    message_id: message.id, sequence: 1, run_id: "run-steer", state: "running", phase: "planning",
    cancel_requested: false, event_sequence: 4, steering_revision: 2, runtime_version: 3,
    updated_at: timestamp, detail: "Planning the report",
  }] });
  const steers: unknown[][] = [];
  Object.assign(data.client, {
    steerConversationAgent: async (...args: unknown[]) => {
      steers.push(args);
      return { run_id: "run-steer", steering_revision: 3 };
    },
  });
  await mount(async tree => {
    await act(async () => tree.root.findByProps({ "aria-label": "Steer Agent task" }).props.onClick());
    const input = tree.root.findByProps({ "aria-label": "Instruction for Agent" });
    await act(async () => input.props.onChange({ target: { value: "Prioritize the Bangla summary." } }));
    const form = tree.root.findByProps({ "aria-label": "Steer Agent form" });
    await act(async () => form.props.onSubmit({ preventDefault() {} }));
    assert.deepEqual(steers, [[record.id, message.id, 1, 2, "Prioritize the Bangla summary."]]);
  }, data, {}, "?conversation=conversation-1");
});


test("three queued conversation tasks show independent progress and controls", async () => {
  const data = fixture([{ ...record, message_sequence: 3 }]);
  const messages = [1, 2, 3].map(sequence => ({
    id: "message-" + sequence, conversation_id: record.id, sequence,
    text: "Task " + sequence, selected_sources: [],
    resource_links: [{ resource_type: "agent_run", resource_id: "run-" + sequence }],
    created_at: timestamp,
  }));
  data.client.conversationHistory = async () => ({ items: messages });
  data.client.conversationActivityHistory = async () => ({ items: [1, 2, 3].map(sequence => ({
    message_id: "message-" + sequence, sequence, run_id: "run-" + sequence,
    state: "queued", phase: "planning", cancel_requested: false, event_sequence: 1,
    steering_revision: 0, runtime_version: 3, updated_at: timestamp, detail: "Conversation work accepted.",
  })) });
  data.client.agentRun = async (id: string) => {
    data.calls.reads.push(id);
    return { id, state: "queued", final_state: null, message: "Conversation work accepted.",
      plan: [], tool_results: [] } as unknown as AgentRun;
  };
  await mount(async (tree, { calls }) => {
    assert.deepEqual(calls.reads.sort(), ["run-1", "run-2", "run-3"]);
    const progress = tree.root.findAllByType("section").filter(node => node.props["aria-label"] === "Coworker progress");
    assert.equal(progress.length, 3);
    for (const region of progress) {
      const statuses = region.findAllByProps({ role: "status" });
      assert.equal(statuses.length, 1);
      assert.deepEqual(statuses[0].children, ["Queued"]);
    }
    assert.equal(tree.root.findAllByProps({ "aria-label": "Steer Agent task" }).length, 3);
    assert.equal(tree.root.findAllByType("button").filter(node => node.children.join("") === "Cancel Agent work").length, 3);
  }, data, {}, "?conversation=conversation-1");
});
