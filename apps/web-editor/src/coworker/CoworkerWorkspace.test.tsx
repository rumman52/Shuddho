import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import CoworkerWorkspace from "./CoworkerWorkspace";
import { WorkspaceError, type CoworkerClient, type WorkspaceManifest } from "./client";

test("Projects view uses the approved sidebar, recent chats, account footer and Activity & context control", async () => {
  const previousWindow = globalThis.window;
  const location = { origin: "https://rukh.test", pathname: "/coworker", search: "?view=projects" };
  globalThis.window = {
    location,
    history: {
      pushState: (_state: unknown, _title: string, url?: string | URL | null) => {
        if (!url) return;
        const next = new URL(String(url), location.origin);
        location.pathname = next.pathname;
        location.search = next.search;
      },
      replaceState() {},
    },
    matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }),
    setTimeout, clearTimeout, setInterval, clearInterval,
    addEventListener() {}, removeEventListener() {},
    requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(() => callback(0), 0) as unknown as number,
    cancelAnimationFrame: (id: number) => clearTimeout(id),
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  } as unknown as Window & typeof globalThis;

  const now = new Date().toISOString();
  const conversation = { id: "44444444-4444-4444-8444-444444444444", title: "Launch plan for Rukh", message_sequence: 2, created_at: now, updated_at: now };
  const client = {
    me: async () => ({ account_id: "account-test", workspace_name: "Anowar", preferences: {}, usage: { tasks_today: 0 }, limits: { daily_tasks: 10, upload_bytes: 1024 } }),
    list: async () => ({ tasks: [] }),
    documents: async () => ({ documents: [] }),
    skills: async () => ({ skills: [], upload_formats: ["txt", "docx", "pdf"] }),
    conversations: async () => ({ items: [conversation] }),
    projects: async () => ({ items: [] }),
  } as unknown as CoworkerClient;

  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => { tree = create(<CoworkerWorkspace client={client} email="anowar@example.test" signOut={async () => undefined} />); });
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
    assert.ok(tree!.root.findAllByType("h1").some(node => node.children.includes("Projects")));
    assert.ok(tree!.root.findByProps({ "aria-label": "Recent chats" }));
    assert.ok(tree!.root.findAllByProps({ className: "rukh-design-history-list" }).length > 0);
    assert.ok(tree!.root.findAllByType("button").some(node => node.children.includes("Launch plan for Rukh")));
    assert.ok(tree!.root.findByProps({ className: "rukh-section-context" }));
    assert.ok(tree!.root.findByProps({ "aria-label": "Settings" }));
    assert.ok(tree!.root.findByProps({ "aria-label": "Sign out" }));
    assert.ok(tree!.root.findAllByType("strong").some(node => node.children.includes("Anowar")));
  } finally {
    if (tree) await act(async () => tree!.unmount());
    globalThis.window = previousWindow;
  }
});

test("Coworker keeps the message composer visible when workspace profile metadata is unavailable", async () => {
  const previousWindow = globalThis.window;
  globalThis.window = {
    location: { search: "" },
    matchMedia: () => ({
      matches: false,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
    }),
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    addEventListener() {},
    removeEventListener() {},
    requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(() => callback(0), 0) as unknown as number,
    cancelAnimationFrame: (id: number) => clearTimeout(id),
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  } as unknown as Window & typeof globalThis;

  const manifest: WorkspaceManifest = {
    schema_version: 1,
    workspace_id: "workspace-test",
    workspace_name: "Workspace",
    documents: [],
    artifacts: [],
    memory: [],
    revision_sha256: "a".repeat(64),
    truncated: { documents: false, artifacts: false, memory: false },
  };
  const client = {
    me: async () => { throw new WorkspaceError("Workspace profile unavailable", 503); },
    list: async () => ({ tasks: [] }),
    documents: async () => ({ documents: [] }),
    skills: async () => ({
      skills: [{
        id: "report_email",
        name: "Report & email",
        description: "Prepare a report and email draft.",
        instruction: "Prepare a report.",
        output: "Report",
      }],
      upload_formats: ["txt", "docx", "pdf"],
    }),
    conversations: async () => ({ items: [] }),
    workspaceManifest: async () => manifest,
    memory: async () => ({ enabled: false, facts: [] }),
  } as unknown as CoworkerClient;

  let tree: ReactTestRenderer | undefined;
  try {
    await act(async () => {
      tree = create(<CoworkerWorkspace client={client} email="test@example.invalid" signOut={async () => undefined} />);
    });
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
    assert.ok(tree!.root.findByProps({ "aria-label": "Message composer" }));
    assert.equal(tree!.root.findByProps({ id: "cw-conversation-message" }).props.disabled, false);
    assert.ok(tree!.root.findAllByProps({ role: "alert" }).some(node => node.children.join("").includes("Workspace profile unavailable")));
  } finally {
    if (tree) await act(async () => tree!.unmount());
    globalThis.window = previousWindow;
  }
});
