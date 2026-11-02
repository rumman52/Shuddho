export type CoworkerView = "conversations" | "agent" | "goals" | "automations" | "browser" | "drafts" | "actions" | "sandbox" | "transactions" | "negotiations";
export type CoworkerNavigationItem = { id: string; label: string; icon: string; group: string; view: CoworkerView };
export const coworkerNavigation: readonly CoworkerNavigationItem[];
export function getCoworkerView(id: string): CoworkerView;
export function getInitialConversationId(search: string): string | null;
