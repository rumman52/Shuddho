export const coworkerNavigation = Object.freeze([
  { id: "home", label: "Home", icon: "home", group: "Workspace", view: "conversations" },
  { id: "agent", label: "Agent activity", icon: "activity", group: "Workspace", view: "agent" },
  { id: "goals", label: "Goals & ideas", icon: "target", group: "Workspace", view: "goals" },
  { id: "automations", label: "Automations", icon: "calendar", group: "Workspace", view: "automations" },
  { id: "browser", label: "Browser", icon: "globe", group: "Tools", view: "browser" },
  { id: "files", label: "Files & drafts", icon: "file-text", group: "Tools", view: "drafts" },
  { id: "approvals", label: "Approvals & integrations", icon: "shield", group: "Manage", view: "actions" },
  { id: "sandbox", label: "Sandbox", icon: "terminal", group: "Tools", view: "sandbox" },
  { id: "transactions", label: "Transactions", icon: "wallet", group: "Manage", view: "transactions" },
  { id: "negotiations", label: "Negotiations", icon: "handshake", group: "Manage", view: "negotiations" },
]);

export function getCoworkerView(id) {
  return coworkerNavigation.find(item => item.id === id)?.view ?? "conversations";
}

export function getInitialConversationId(search) {
  const value = new URLSearchParams(search.startsWith("?") ? search : `?${search}`).get("conversation");
  return value && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value) ? value : null;
}
