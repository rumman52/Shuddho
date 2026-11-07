import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { act, create, type ReactTestRenderer } from "react-test-renderer";
import ProjectWorkspace from "./ProjectWorkspace";
import type {
  CoworkerClient,
  ProjectRecord,
  ProjectDetail,
  ConversationRecord,
  SourceDocument,
} from "./client";

const projectId = "11111111-1111-4111-8111-111111111111";
const conversationId = "22222222-2222-4222-8222-222222222222";
const fileId = "33333333-3333-4333-8333-333333333333";
const timestamp = "2026-11-07T10:00:00Z";
const project: ProjectRecord = {
  id: projectId,
  name: "Research desk",
  description: "Research notes and source material.",
  revision: 1,
  created_at: timestamp,
  updated_at: timestamp,
};
const conversation: ConversationRecord = {
  id: conversationId,
  title: "Market research brief",
  message_sequence: 1,
  created_at: timestamp,
  updated_at: timestamp,
};
const source: SourceDocument = {
  id: fileId,
  filename: "research.pdf",
  state: "uploaded",
  byte_size: 2048,
};

function fixture() {
  let detail: ProjectDetail = { ...project, resources: [] };
  const calls = {
    links: [] as { projectId: string; type: "conversation" | "document"; resourceId: string; revision: number }[],
    unlinks: [] as { type: "conversation" | "document"; resourceId: string }[],
  };
  const client = {
    projects: async () => ({ items: [project] }),
    project: async () => ({ ...detail, resources: [...detail.resources] }),
    conversations: async () => ({ items: [conversation] }),
    documents: async () => ({ documents: [source] }),
    linkProjectResource: async (id: string, type: "conversation" | "document", resourceId: string, revision: number) => {
      calls.links.push({ projectId: id, type, resourceId, revision });
      detail = {
        ...detail,
        revision: detail.revision + 1,
        updated_at: "2026-11-07T11:00:00Z",
        resources: [...detail.resources, {
          resource_type: type,
          resource_id: resourceId,
          title: type === "conversation" ? conversation.title : source.filename,
        }],
      };
      return { ...detail, resources: [...detail.resources] };
    },
    unlinkProjectResource: async (_id: string, type: "conversation" | "document", resourceId: string) => {
      calls.unlinks.push({ type, resourceId });
      detail = {
        ...detail,
        revision: detail.revision + 1,
        resources: detail.resources.filter(item => item.resource_id !== resourceId),
      };
      return { ...detail, resources: [...detail.resources] };
    },
  } as unknown as CoworkerClient;
  return { client, calls };
}

async function mount(run: (tree: ReactTestRenderer, data: ReturnType<typeof fixture>) => Promise<void>) {
  const data = fixture();
  let tree!: ReactTestRenderer;
  try {
    await act(async () => {
      tree = create(<ProjectWorkspace client={data.client} />);
    });
    await run(tree, data);
  } finally {
    if (tree) await act(async () => tree.unmount());
  }
}

test("Projects home searches real project records and opens the project workspace", async () => {
  await mount(async tree => {
    assert.equal(tree.root.findAllByProps({ className: "rukh-project-card" }).length, 1);
    await act(async () => {
      tree.root.findByProps({ "aria-label": "Search projects" }).props.onChange({ target: { value: "missing" } });
    });
    assert.equal(tree.root.findAllByProps({ className: "rukh-project-card" }).length, 0);
    await act(async () => {
      tree.root.findByProps({ "aria-label": "Search projects" }).props.onChange({ target: { value: "research" } });
    });
    const card = tree.root.findByProps({ className: "rukh-project-card" });
    await act(async () => card.props.onClick());
    assert.equal(tree.root.findByProps({ role: "tablist" }).props["aria-label"], "Project sections");
    assert.ok(tree.root.findAllByProps({ role: "tab" }).some(item => item.children.includes("Chats")));
    assert.ok(tree.root.findAllByProps({ role: "tab" }).some(item => item.children.includes("Files")));
    assert.ok(tree.root.findAllByType("a").some(item => String(item.props.href).includes("project=" + projectId)));
  });
});

test("a project can link an existing conversation using the owner-scoped project API", async () => {
  await mount(async (tree, data) => {
    const card = tree.root.findByProps({ className: "rukh-project-card" });
    await act(async () => card.props.onClick());
    await act(async () => {
      tree.root.findByProps({ id: "rukh-project-link-select" }).props.onChange({
        target: { value: "conversation:" + conversationId },
      });
    });
    const add = tree.root.findAllByType("button").find(item => item.children.join("") === "Add to project");
    assert.ok(add);
    await act(async () => add!.props.onClick());
    assert.deepEqual(data.calls.links, [{
      projectId,
      type: "conversation",
      resourceId: conversationId,
      revision: 1,
    }]);
    assert.ok(tree.root.findAllByType("a").some(item => item.children.includes(conversation.title)));
  });
});

test("the Files tab exposes the real project upload control", async () => {
  await mount(async tree => {
    const card = tree.root.findByProps({ className: "rukh-project-card" });
    await act(async () => card.props.onClick());
    const filesTab = tree.root.findAllByProps({ role: "tab" }).find(item => item.children.includes("Files"));
    assert.ok(filesTab);
    await act(async () => filesTab!.props.onClick());
    assert.equal(tree.root.findByProps({ "aria-label": "Upload project file" }).props.accept, ".txt,.docx,.pdf");
  });
});
