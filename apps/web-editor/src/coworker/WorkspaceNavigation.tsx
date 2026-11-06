import NavigationIcon from "./WorkspaceNavigationIcon";
import type { CoworkerView } from "./client";
import { coworkerNavigation } from "../../../coworker/src/navigation.mjs";

export default function WorkspaceNavigation({ active, onNavigate, writingHref = "/writing" }: {
  active: CoworkerView | "writing";
  onNavigate: (view: CoworkerView) => void;
  writingHref?: string;
}) {
  function item(view: CoworkerView, label: string, icon: string) {
    return <button key={view} type="button" className={"rukh-design-nav-link" + (active === view ? " is-active" : "")} aria-current={active === view ? "page" : undefined} onClick={() => onNavigate(view)}><NavigationIcon name={icon} />{label}</button>;
  }
  return <>
    <nav aria-label="Primary workspace navigation">
      <a href="/coworker" className={"rukh-design-nav-link" + (active === "conversations" ? " is-active" : "")} aria-current={active === "conversations" ? "page" : undefined}><NavigationIcon name="chat" />Coworker</a>
      <a href="/fly" className={"rukh-design-nav-link" + (active === "sandbox" ? " is-active" : "")} aria-current={active === "sandbox" ? "page" : undefined}><NavigationIcon name="terminal" />Fly</a>
      <a href={writingHref} className={"rukh-design-nav-link" + (active === "writing" ? " is-active" : "")} aria-current={active === "writing" ? "page" : undefined}><NavigationIcon name="file-text" />Writing Assistant</a>
      {item("projects", "Projects", "folder")}
      {item("actions", "Plugins", "grid")}
    </nav>
    <nav className="rukh-design-workspace-links" aria-label="Workspace tools">
      <span className="rukh-design-section-label">WORKSPACE</span>
      {item("library", "Files", "file-text")}
      {item("goals", "Goals", "target")}
      {item("automations", "Automations", "clock")}
    </nav>
    <button type="button" className="rukh-design-settings" onClick={() => onNavigate("settings")}>Settings</button>
    <details className="rukh-design-more-tools">
      <summary>More tools</summary>
      <nav aria-label="Additional tools">{coworkerNavigation.filter(value => ["drafts", "agent", "browser", "transactions", "negotiations"].includes(value.view)).map(value => item(value.view as CoworkerView, value.label, value.icon))}</nav>
    </details>
  </>;
}
