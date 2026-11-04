import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import CoworkerWorkspace from "./CoworkerWorkspace";
import { WorkspaceError, type CoworkerClient, type WorkspaceManifest } from "./client";

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
